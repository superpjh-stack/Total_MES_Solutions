"""비정형 데이터 — 문서 · 이미지 · PDF 같은 파일을 보관하고 찾고 꺼낸다.

- 파일 본체는 `MES_HUB_DIR` 에 무작위 이름으로, 목록 · 메타데이터 · 추출 텍스트는 `hub.file` 에 둔다. 원래 파일 이름은 경로에 쓰지 않는다.
- 확장자 허용 목록 · 크기 상한(`MES_HUB_MAX_MB`, 기본 20)을 넘으면 422. 내용은 sha256 으로 남긴다.
- 텍스트를 뽑을 수 있는 파일(텍스트 · PDF · Word · Excel · PowerPoint)은 앞부분을 검색 · AI Agent RAG 에 쓴다.
- 업무 대상(품목 · LOT · 작업지시 · 설비 · 거래처)에 이을 수 있다 — 번호가 실제로 있어야 한다.
- 지우기는 표시만 한다(되돌릴 수 있게) — 목록 · 검색 · 저장 현황에서 빠진다.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import uuid
import zipfile
from datetime import datetime

from mescore.db import conn

from . import store

TEXT_EXT = {"txt", "md", "csv", "json", "log", "xml"}
OFFICE_EXT = {"docx", "xlsx", "pptx"}
IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
OTHER_EXT = {"pdf", "hwp", "hwpx", "xls", "doc", "ppt", "zip"}
ALLOWED = TEXT_EXT | OFFICE_EXT | IMAGE_EXT | OTHER_EXT
MIME = {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp",
        "txt": "text/plain; charset=utf-8", "md": "text/markdown; charset=utf-8", "csv": "text/csv; charset=utf-8", "json": "application/json",
        "log": "text/plain; charset=utf-8", "xml": "application/xml", "zip": "application/zip",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation"}
CATEGORIES = ("작업표준서", "검사 기록", "성적서", "도면 · 사양", "현장 사진", "교육 자료", "회의 · 보고", "기타")
LINKS = {  # 연결 종류 → (이름, 확인 SQL)
    "item": ("품목", "select 1 from bas_item where item_code = %s"),
    "lot": ("LOT", "select 1 from lot where lot_no = %s"),
    "work_order": ("작업지시", "select 1 from job_work_order where work_order_no = %s"),
    "equipment": ("설비", "select 1 from bas_equipment where equip_code = %s"),
    "partner": ("거래처", "select 1 from bas_partner where partner_code = %s"),
}
EXCERPT_MAX = 20_000


class FileRejected(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field


def max_bytes() -> int:
    try:
        return int(float(os.environ.get("MES_HUB_MAX_MB") or 20) * 1024 * 1024)
    except ValueError:
        return 20 * 1024 * 1024


def ext_of(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _decode(b: bytes) -> str:
    for enc in ("utf-8-sig", "cp949"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", errors="replace")


def _xml_text(z: zipfile.ZipFile, names: list[str]) -> str:
    out = []
    for n in names:
        x = z.read(n).decode("utf-8", errors="replace")
        x = re.sub(r"</w:p>|</a:p>|</si>|</row>", "\n", x)
        out.append(re.sub(r"<[^>]+>", " ", x))
    return "\n".join(out)


def extract_text(ext: str, data: bytes) -> str:
    """검색 · RAG 용 텍스트. 뽑을 수 없으면 빈 문자열(이미지 · 한글 문서 · 압축 등)."""
    try:
        if ext in TEXT_EXT:
            t = _decode(data)
        elif ext == "pdf":
            from pypdf import PdfReader
            r = PdfReader(io.BytesIO(data))
            t = "\n".join((p.extract_text() or "") for p in r.pages[:50])
        elif ext in OFFICE_EXT:
            z = zipfile.ZipFile(io.BytesIO(data))
            names = z.namelist()
            pick = {"docx": [n for n in names if n == "word/document.xml"],
                    "xlsx": [n for n in names if n == "xl/sharedStrings.xml"],
                    "pptx": sorted(n for n in names if re.match(r"ppt/slides/slide\d+\.xml$", n))}[ext]
            t = _xml_text(z, pick)
        else:
            return ""
    except Exception:  # noqa: BLE001 — 깨진 파일도 보관은 한다. 텍스트만 없다(화면에 '추출 안 됨' 으로 보인다)
        return ""
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t).strip()
    return t[:EXCERPT_MAX]


def save(*, user_login: str, filename: str, data: bytes, title: str, category: str, link_kind: str, link_ref: str,
         tags: str, note: str) -> dict:
    store.ensure()
    name = os.path.basename((filename or "").replace("\\", "/")).strip()
    ext = ext_of(name)
    if not name or not data:
        raise FileRejected("file", "파일이 비었습니다")
    if ext not in ALLOWED:
        raise FileRejected("file", f"허용하지 않는 형식입니다 (.{ext or '없음'}) — 허용: {', '.join(sorted(ALLOWED))}")
    if len(data) > max_bytes():
        raise FileRejected("file", f"파일이 너무 큽니다 — 최대 {max_bytes() // (1024 * 1024)}MB")
    if category not in CATEGORIES:
        raise FileRejected("category", "분류를 고르세요")
    link_kind = (link_kind or "").strip()
    link_ref = (link_ref or "").strip()
    if link_kind:
        if link_kind not in LINKS:
            raise FileRejected("link_kind", "연결 종류가 올바르지 않습니다")
        if not link_ref:
            raise FileRejected("link_ref", f"{LINKS[link_kind][0]} 번호를 입력하세요")
        if not conn.q1(LINKS[link_kind][1], (link_ref,)):
            raise FileRejected("link_ref", f"없는 {LINKS[link_kind][0]} 번호입니다: {link_ref}")
    else:
        link_ref = ""
    title = (title or "").strip() or name.rsplit(".", 1)[0]
    text = extract_text(ext, data)
    stored = f"{uuid.uuid4().hex}.{ext}"
    (store.files_dir() / stored).write_bytes(data)
    tag_list = [t.strip() for t in re.split(r"[,#\s]+", tags or "") if t.strip()][:20]
    with conn.tx() as cur:
        cur.execute("""insert into hub.file (title, category, original_name, ext, mime, size_bytes, sha256, stored_name, link_kind, link_ref,
                                             tags, note, text_excerpt, text_chars, created_by)
                       values (%s, %s, %s, %s, %s, %s, %s, %s, nullif(%s, ''), nullif(%s, ''), %s, nullif(%s, ''), nullif(%s, ''), %s, %s)
                       returning id""",
                    (title[:200], category, name[:255], ext, MIME.get(ext, "application/octet-stream"), len(data),
                     hashlib.sha256(data).hexdigest(), stored, link_kind, link_ref, tag_list, (note or "").strip()[:1000], text, len(text), user_login))
        fid = cur.fetchone()["id"]
        file_no = f"F{datetime.now():%y%m%d}-{fid:05d}"
        cur.execute("update hub.file set file_no = %s where id = %s", (file_no, fid))
    _refresh_rag()
    return {"id": fid, "file_no": file_no, "title": title, "text_chars": len(text)}


def search(q: str = "", category: str = "", link_kind: str = "", limit: int = 200) -> list[dict]:
    store.ensure()
    where, args = ["deleted_at is null"], []
    if q.strip():
        like = f"%{q.strip()}%"
        where.append("(title ilike %s or original_name ilike %s or coalesce(note, '') ilike %s or coalesce(link_ref, '') ilike %s"
                     " or array_to_string(tags, ' ') ilike %s or coalesce(text_excerpt, '') ilike %s or coalesce(file_no, '') ilike %s)")
        args += [like] * 7
    if category:
        where.append("category = %s")
        args.append(category)
    if link_kind:
        where.append("link_kind = %s")
        args.append(link_kind)
    rows = conn.q(f"""select id, file_no, title, category, original_name, ext, mime, size_bytes, link_kind, link_ref, tags, note, text_chars,
                             left(coalesce(text_excerpt, ''), 300) as snippet, created_at, created_by
                        from hub.file where {' and '.join(where)} order by created_at desc limit {int(limit)}""", args)
    return rows


def get(fid: int) -> dict | None:
    store.ensure()
    return conn.q1("select * from hub.file where id = %s and deleted_at is null", (fid,))


def path_of(row: dict):
    return store.files_dir() / row["stored_name"]


def delete(fid: int, user_login: str) -> bool:
    store.ensure()
    n = conn.x("update hub.file set deleted_at = now(), deleted_by = %s where id = %s and deleted_at is null", (user_login, fid))
    _refresh_rag()
    return n == 1


def stats() -> dict:
    store.ensure()
    tot = conn.q1("""select count(*)::int as n, coalesce(sum(size_bytes), 0)::bigint as bytes, count(*) filter (where text_chars > 0)::int as with_text,
                            count(*) filter (where link_kind is not null)::int as linked, max(created_at) as last_at,
                            count(*) filter (where created_at >= now() - interval '7 days')::int as new_7d
                       from hub.file where deleted_at is null""")
    cats = conn.q("""select category, count(*)::int as n, coalesce(sum(size_bytes), 0)::bigint as bytes from hub.file
                      where deleted_at is null group by category order by 2 desc""")
    types = conn.q("""select ext, count(*)::int as n from hub.file where deleted_at is null group by ext order by 2 desc""")
    return {**tot, "categories": cats, "types": types}


def rag_chunks(size: int = 900) -> list[tuple[str, str, str]]:
    """AI Agent RAG 용 (출처, 제목, 본문) — 텍스트가 있는 파일만."""
    try:
        store.ensure()
        rows = conn.q("""select file_no, title, category, link_kind, link_ref, text_excerpt from hub.file
                          where deleted_at is null and text_chars > 0 order by id""")
    except Exception:  # noqa: BLE001 — 허브 스키마를 못 만들면(읽기 전용 DB 등) RAG 에서만 빠진다
        return []
    out = []
    for r in rows:
        head = f"데이터 허브 {r['file_no']} {r['title']} ({r['category']}{' · ' + r['link_ref'] if r['link_ref'] else ''})"
        body = r["text_excerpt"]
        for i in range(0, len(body), size):
            out.append((f"hub:{r['file_no']}", head, body[i:i + size]))
    return out


def _refresh_rag() -> None:
    try:
        from mesagent import rag
    except ImportError:
        return
    rag.index.cache_clear()


def daily(days: int = 14) -> list[dict]:
    store.ensure()
    return conn.q("""select d::date as day, coalesce(x.n, 0)::bigint as n
                       from generate_series(current_date - (%s - 1), current_date, interval '1 day') d
                       left join (select created_at::date as day, count(*) as n from hub.file
                                   where deleted_at is null and created_at >= current_date - (%s - 1) group by 1) x
                         on x.day = d::date order by 1""", (days, days))
