"""환경 설정 — `MES_*` 환경변수 단일 소스 (`.env.example`).

정본에 수치가 없는 값(자동 로그아웃 · 잠금 횟수)은 **코드에 기본값을 지어내지 않는다.** 값이 없으면 `None` 이고 그 기능을 적용하지 않는다.
비밀(세션 비밀 · 시드 비밀번호 · 수집 토큰)은 저장소 밖 `.env`(gitignore)에만 둔다 (G-C19).
`MES_PACK` 이 팩을 고른다(비우면 코어 단독). `MES_PG_DSN` 이 비면 팩에 따라 `mes_core_db` / `mes_<팩>_db`.
`MES_ENV` 는 **비면 `prod`**(안전한 쪽 · DEF-QA1-001 · QA3-001) — 개발 편의(설명 패널 · 개발용 로그인 · 500 사유 노출)는 `MES_ENV=dev` 를 적었을 때만.
"""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PREFIX = "MES_"
ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = ROOT / ".env"
UNDECIDED = "미확정"
DEFAULT_PORT = 8030


def load_dotenv(path: Path = ENV_FILE) -> int:
    """`.env` 를 읽어 **아직 없는** 환경변수만 채운다(셸 값이 우선). 파일이 없으면 0."""
    if not path.exists():
        return 0
    n = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:
            os.environ[k] = v
            n += 1
    return n


load_dotenv()


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(PREFIX + name)
    if v is None or v.strip() == "":
        return default
    return v.strip()


def _env_int(name: str) -> int | None:
    v = _env(name)
    if v is None:
        return None
    try:
        return int(v)
    except ValueError as exc:
        raise ValueError(f"{PREFIX}{name} 는 정수여야 한다: {v!r}") from exc


def db_name_for(pack: str | None) -> str:
    """팩별 DB 이름 — 코어 단독 `mes_core_db`, 팩은 `mes_<팩>_db` (`_template` 등 `_` 팩은 코어 DB)."""
    if not pack or pack.startswith("_"):
        return "mes_core_db"
    return f"mes_{pack}_db"


@dataclass(frozen=True)
class Settings:
    env: str                           # dev | prod
    pack: str | None                   # MES_PACK — 비우면 코어 단독
    pg_dsn: str                        # MES_PG_DSN 또는 팩에 따른 기본값
    port: int                          # 8030 (8000 · 8020 은 다른 사업이 쓴다)
    session_secret: str                # 비면 기동할 때마다 난수
    session_cookie: str
    seed_password: str | None          # 시드 계정 비밀번호 — 환경변수로만 (G-C19)
    collect_token: str | None          # POST /ifc/collect 의 X-Collect-Token
    migrate_dir: str | None            # 이관 배치 폴더 (F-SYS-15)
    login_lock_count: int | None       # 정본에 수치 없음 → None 이면 잠그지 않는다 (D-14)
    board_refresh_seconds: int         # 현황판 폴링 — spec.md §11 5초
    grid_page_size: int

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"

    @property
    def db_name(self) -> str:
        return db_name_for(self.pack)

    @property
    def migrate_dir_label(self) -> str:
        return self.migrate_dir or f"{UNDECIDED} (MES_MIGRATE_DIR 없음)"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    pack = _env("PACK")
    return Settings(
        env=_env("ENV", "prod") or "prod",
        pack=pack,
        pg_dsn=_env("PG_DSN") or f"postgresql:///{db_name_for(pack)}",
        port=_env_int("PORT") or DEFAULT_PORT,
        session_secret=_env("SESSION_SECRET", "") or "",
        session_cookie=_env("SESSION_COOKIE", "mes_session") or "mes_session",
        seed_password=_env("SEED_PASSWORD"),
        collect_token=_env("COLLECT_TOKEN"),
        migrate_dir=_env("MIGRATE_DIR"),
        login_lock_count=_env_int("LOGIN_LOCK_COUNT"),
        board_refresh_seconds=_env_int("BOARD_REFRESH_SECONDS") or 5,
        grid_page_size=_env_int("GRID_PAGE_SIZE") or 10,
    )


def is_loopback(host: str | None) -> bool:
    """요청 상대 주소가 루프백(127.0.0.0/8 · ::1)인가. 이름(`localhost` · `testclient`)이나 빈 값은 루프백이 아니다 — 주소로만 판정."""
    if not host:
        return False
    try:
        return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def dev_login_allowed(request) -> bool:
    """D-605 개발용 무비밀번호 로그인(`POST /login/as`)을 열어도 되는가 — **`MES_ENV=dev` 이고 요청이 루프백에서 왔을 때만.**
    아니면 그 경로는 404 다(`routers/home.login_as` 가 이 판정을 쓰고, `main.py` 미들웨어가 한 번 더 막는다).
    프록시 뒤라면 상대 주소가 프록시(대개 루프백)이므로 운영은 `MES_ENV` 를 dev 로 두지 않는다 — 기본값 prod."""
    if not get_settings().is_dev:
        return False
    client = getattr(request, "client", None)
    return is_loopback(getattr(client, "host", None))


def reset_cache() -> None:
    """테스트용 — 환경변수를 바꾼 뒤 부른다."""
    get_settings.cache_clear()
