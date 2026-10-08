"""이관 배치 4종 — B-MIG-01~04 (`contracts/function-list.md` · `migration-files.md` · `api-contract.md` §5 · G-C15). 담당 개발3.

    basics    B-MIG-01  기준정보          01~09
    orders    B-MIG-02  수주 · 작업지시    11 · 12
    lots      B-MIG-03  LOT · 계보        21 · 22 (계보는 lineage.link 로만)
    history   B-MIG-04  실적 · 검사 이력  31~34

    migrate.run(command, dir, *, dry_run=False, run_by=None) -> MigrateReport     # 개발1 F-SYS-15 가 부른다
    uv run python -m mescore.migrate <command> --dir <폴더> [--dry-run]

- 명령 하나 = 커넥션 하나. 파일마다 커밋(앞 파일의 코드를 뒤 파일이 참조한다). `--dry-run` 은 끝에 전부 되돌린다 — 쓰지 않는다.
- 파일 × 실행마다 `sys_migration_log` 한 줄(읽음 · 적재 · 갱신 · 건너뜀 · 오류 · 오류 상세 · dry_run). dry-run 도 로그는 남긴다.
- 폴더에 없는 파일은 "없음" 으로 건너뛴다(오류 아님 — 출력에 보인다). 오류가 1건이라도 있으면 종료 코드 1.
- 예상하지 못한 예외(DB 연결 실패 · lineage 없음)는 삼키지 않고 그대로 올린다.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from ..db import conn
from . import importer
from .importer import COMMAND_FILES, LOADERS, SPECS, Ctx, FileResult, RowError, RowProblem

#: 명령 → 파일 (check_trace 가 `function-list.md` 의 `cli <명령>` 과 대조한다)
COMMANDS: dict[str, tuple[str, ...]] = dict(COMMAND_FILES)
MAX_LOG_ERRORS = 200


@dataclass
class FileReport:
    file: str
    present: bool = True
    read: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[RowError] = field(default_factory=list)
    started_at: datetime | None = None
    ended_at: datetime | None = None

    @property
    def error_count(self) -> int:
        return len(self.errors)

    def line(self) -> str:
        if not self.present:
            return f"{self.file:<22} 없음"
        return f"{self.file:<22} 읽음 {self.read:>5}  적재 {self.inserted:>5}  갱신 {self.updated:>5}  건너뜀 {self.skipped:>5}  오류 {self.error_count:>5}"


@dataclass
class MigrateReport:
    command: str
    dir: str
    dry_run: bool
    files: list[FileReport] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(f.error_count for f in self.files)

    @property
    def exit_code(self) -> int:
        return 1 if self.error_count else 0

    @property
    def ok(self) -> bool:
        return self.error_count == 0

    def totals(self) -> dict[str, int]:
        return {"read": sum(f.read for f in self.files), "inserted": sum(f.inserted for f in self.files), "updated": sum(f.updated for f in self.files),
                "skipped": sum(f.skipped for f in self.files), "errors": self.error_count}

    def text(self) -> str:
        head = f"migrate {self.command} --dir {self.dir}" + (" --dry-run (DB 에 쓰지 않음)" if self.dry_run else "")
        lines = [head, "-" * 92, f"{'파일':<22} 읽음  적재  갱신  건너뜀  오류"]
        lines += [f.line() for f in self.files]
        for f in self.files:
            for e in f.errors[:MAX_LOG_ERRORS]:
                lines.append(f"  ! {f.file} {e.text()}")
            if f.error_count > MAX_LOG_ERRORS:
                lines.append(f"  ! {f.file} … 외 {f.error_count - MAX_LOG_ERRORS}건")
        t = self.totals()
        lines.append("-" * 92)
        lines.append(f"합계 읽음 {t['read']} · 적재 {t['inserted']} · 갱신 {t['updated']} · 건너뜀 {t['skipped']} · 오류 {t['errors']} → 종료 코드 {self.exit_code}")
        return "\n".join(lines)

    def as_dict(self) -> dict:
        return {"command": self.command, "dir": self.dir, "dry_run": self.dry_run, "exit_code": self.exit_code, "totals": self.totals(),
                "files": [{"file": f.file, "present": f.present, "read": f.read, "inserted": f.inserted, "updated": f.updated, "skipped": f.skipped,
                           "errors": [e.as_dict() for e in f.errors]} for f in self.files]}


def _write_log(command: str, dir: str, rep: FileReport, *, dry_run: bool, run_by: str) -> None:
    detail = [e.as_dict() for e in rep.errors[:MAX_LOG_ERRORS]]
    if rep.error_count > MAX_LOG_ERRORS:
        detail.append({"line": 0, "key": "", "reason": f"외 {rep.error_count - MAX_LOG_ERRORS}건"})
    conn.x("""insert into sys_migration_log (command, dir, file, read_count, inserted, updated, skipped, errors, error_detail, dry_run, started_at, ended_at, run_by, created_by)
              values (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)""",
           (command, dir, rep.file, rep.read, rep.inserted, rep.updated, rep.skipped, rep.error_count, json.dumps(detail, ensure_ascii=False),
            dry_run, rep.started_at, rep.ended_at, run_by, importer.LOADED_BY))


def _load_file(cur, folder: Path, res: FileResult, rep: FileReport) -> None:
    loader = LOADERS[res.spec.file]
    ctx = Ctx(cur, folder, res.spec.file)
    rep.read = res.read
    rep.errors.extend(res.errors)
    for row in res.rows:
        cur.execute("savepoint row_sp")
        try:
            status = loader(ctx, row)
        except RowProblem as exc:
            cur.execute("rollback to savepoint row_sp")
            rep.errors.append(RowError(row.line, row.key_text(res.spec), str(exc)))
            continue
        except (psycopg.errors.IntegrityError, psycopg.DataError) as exc:        # 라우터가 못 잡은 제약 위반 → 그 줄 오류
            cur.execute("rollback to savepoint row_sp")
            diag = getattr(exc, "diag", None)
            rep.errors.append(RowError(row.line, row.key_text(res.spec), (getattr(diag, "message_primary", None) or str(exc)).strip()))
            continue
        cur.execute("release savepoint row_sp")
        if status == importer.INSERTED:
            rep.inserted += 1
        elif status == importer.UPDATED:
            rep.updated += 1
        else:
            rep.skipped += 1
    rep.errors.sort(key=lambda e: e.line)


def run(command: str, dir: str | Path, *, dry_run: bool = False, run_by: str | None = None) -> MigrateReport:
    """명령 하나를 돌린다. 폴더가 없으면 FileNotFoundError, 모르는 명령은 ValueError. 결과는 `MigrateReport`(exit_code · text())."""
    if command not in COMMANDS:
        raise ValueError(f"명령은 {' · '.join(COMMANDS)} 중 하나다: {command!r}")
    folder = Path(dir)
    if not folder.is_dir():
        raise FileNotFoundError(f"이관 폴더가 없다: {folder}")
    by = run_by or getpass.getuser()
    report = MigrateReport(command, str(folder), dry_run)
    try:
        pg = psycopg.connect(conn.dsn(), row_factory=dict_row)
    except psycopg.Error as exc:
        raise conn.unavailable(exc) from None
    try:
        with pg.cursor() as cur:
            for file in COMMANDS[command]:
                rep = FileReport(file, started_at=datetime.now())
                path = folder / file
                if not path.exists():
                    rep.present = False
                    rep.ended_at = datetime.now()
                    report.files.append(rep)
                    continue
                res = importer.read_file(path, SPECS[file])
                _load_file(cur, folder, res, rep)
                rep.ended_at = datetime.now()
                report.files.append(rep)
                if not dry_run:
                    pg.commit()
        if dry_run:
            pg.rollback()
        else:
            pg.commit()
    except BaseException:
        pg.rollback()
        raise
    finally:
        pg.close()
    for rep in report.files:
        if rep.present:
            _write_log(command, str(folder), rep, dry_run=dry_run, run_by=by)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m mescore.migrate", description="표준 Import 파일 4종 이관 (B-MIG-01~04)")
    ap.add_argument("command", choices=list(COMMANDS), help="basics · orders · lots · history")
    ap.add_argument("--dir", required=True, help="Import 파일 폴더")
    ap.add_argument("--dry-run", action="store_true", help="DB 에 쓰지 않고 검사만 (로그는 남긴다)")
    args = ap.parse_args(argv)
    report = run(args.command, args.dir, dry_run=args.dry_run)
    print(report.text())
    return report.exit_code


__all__ = ["COMMANDS", "MigrateReport", "FileReport", "run", "main"]
