#!/bin/sh
# 앱 컨테이너 시작 — ① 비밀값 준비 ② DB 대기 ③ 빈 DB 면 스키마 · 시드(· 샘플) ④ uvicorn.
# 비밀값을 환경변수로 주지 않으면 첫 기동 때 난수로 만들어 /data/secrets.env(볼륨)에 둔다. 시드 비밀번호는 그때 한 번만 로그에 찍는다.
set -eu

SECRETS=/data/secrets.env
if [ -f "$SECRETS" ]; then . "$SECRETS"; fi
if [ -z "${MES_SESSION_SECRET:-}" ] || [ -z "${MES_SEED_PASSWORD:-}" ]; then
  if [ ! -f "$SECRETS" ]; then
    gen() { python -c "import secrets; print(secrets.token_urlsafe($1))"; }
    umask 077
    printf 'MES_SESSION_SECRET=%s\nMES_SEED_PASSWORD=%s\n' "${MES_SESSION_SECRET:-$(gen 48)}" "${MES_SEED_PASSWORD:-$(gen 12)}" > "$SECRETS"
    . "$SECRETS"
    echo "================================================================"
    echo " 첫 기동 — 시드 계정(admin · prod · qa · field) 비밀번호: $MES_SEED_PASSWORD"
    echo " 이 줄은 다시 찍히지 않는다. 비밀번호는 볼륨 /data/secrets.env 에 있다."
    echo "================================================================"
  fi
fi
export MES_SESSION_SECRET MES_SEED_PASSWORD

echo "DB 대기 …"
i=0
until pg_isready -q -d "$MES_PG_DSN"; do
  i=$((i + 1)); [ "$i" -gt 60 ] && { echo "DB 에 연결하지 못했다 (MES_PG_DSN 확인)"; exit 1; }
  sleep 2
done

if [ "$(psql -d "$MES_PG_DSN" -Atc "select to_regclass('public.sys_user') is not null")" != "t" ]; then
  echo "빈 DB — 스키마 · 시드를 만든다"
  psql -q -d "$MES_PG_DSN" -v ON_ERROR_STOP=1 -f src/mescore/db/schema.sql
  psql -q -d "$MES_PG_DSN" -v ON_ERROR_STOP=1 -f src/mescore/db/views.sql
  if [ -n "${MES_PACK:-}" ] && [ -f "packs/$MES_PACK/schema_ext.sql" ]; then
    psql -q -d "$MES_PG_DSN" -v ON_ERROR_STOP=1 -f "packs/$MES_PACK/schema_ext.sql"
  fi
  python -m mescore.db.seed_core
  if [ "${MES_SAMPLE:-0}" = "1" ]; then
    echo "샘플 데이터 (예시) 를 넣는다"
    MES_ADDONS= python scripts/sample.py || echo "샘플 데이터 넣기 실패 — 위 [실패] 줄 확인 (앱은 그대로 띄운다)"
  fi
fi
if [ "${MES_SAMPLE:-0}" = "1" ]; then
  MES_ADDONS= python scripts/sample_today.py || true      # 오늘 데이터 — 하루 한 번만 들어간다(이미 있으면 그냥 넘어간다)
fi

exec uvicorn mescore.app.main:app --app-dir src --host 0.0.0.0 --port "${MES_PORT:-8030}" \
  --proxy-headers --forwarded-allow-ips="${MES_PROXY_IP:-172.30.0.10}"
