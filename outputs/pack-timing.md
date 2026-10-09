# G-P06 착수 시간 — 더미 팩 `_timing` (QA3 실측 · 2026-10-09 09:35)

`spec.md` §8.1 단계 1~2 를 `_template` 복사로 실제로 돌려 잰 시간. 기준 ≤ 4h.
DB 는 QA3 전용 `mes_qa3_db`(`MES_PG_DSN`) — `_` 팩은 원래 `mes_core_db` 를 쓰지만 공유 DB 를 지우지 않으려고 접속 문자열만 바꿨다. 서버 포트 8054.
끝난 뒤 `packs/_timing` 은 지웠다(`git status` 에 남지 않음).

| 단계 | 한 일 | 명령 | 실측 |
|---|---|---|---|
| 1-a | `_template` 복사 · `pack:` 채움 | `make pack-new NAME=_timing` | 1초 미만 |
| 1-b | `pack.yaml` 편집 — `name: 착수 시간 더미` · `company: (예시) 더미 회사` · `terms: {작업지시: 작업표, 생산 LOT: 제조번호, 품목: 제품코드}` | 스크립트로 3줄 치환 (사람이 손으로 하면 수 분) | 1초 미만 |
| 1-c | 병합 규칙 확인 | `MES_PACK=_timing make pack-check` → `OK _timing 모듈 12 화면 51 역할 4 용어 3 WARN []` | 1초 미만 |
| 2-a | 스키마 · 시드 | `psql -f schema.sql · views.sql` + `MES_PACK=_timing MES_PG_DSN=postgresql:///mes_qa3_db uv run python -m mescore.db.seed_core` → `시드 완료 — 팩 _timing · 역할 4 · 권한 칸 48 · 계정 4 …` | 1초 |
| 2-b | 기동 | `MES_PACK=_timing … uvicorn … --port 8054` → `/health` `{"system":"착수 시간 더미","pack":"_timing","placeholders":0,"router_include_errors":[]}` | 0.6초 |
| 2-c | 브라우저 로그인 → 메인 · 작업지시 · LOT 라벨 화면에서 용어 확인 | `check_security.py --_browser timing` (헤드리스 Chrome) | 로그인 0.28초 · 3화면 1.6초 |

용어 치환 실측(화면 본문 글자): 메인 `/` — 「작업표」 있음 · 「제품코드」 있음 · 「작업지시」 **0** / `/job/work-orders` — 「작업표」 · 「제품코드」 있음 · 「작업지시」 0 / `/pop/labels` — 「작업표」 · 「제조번호」 있음 · 「작업지시」 0.

시작 09:35:42 → 메뉴 용어 확인까지 약 20초(기계 시간). 사람이 `pack.yaml` 을 읽고 고치는 시간을 넉넉히 더해도 4시간 기준 안이다.
남은 조건: §8.1 단계 2 의 「`make gate` 코어 게이트 전부 PASS」 는 이 실측과 따로 — 회전 4 gate 의 코어 FAIL 은 `qa3-채널보안.md` · progress 참조.

```
G-P06  착수 시간 — _timing 팩 단계 1~2  PASS  pack-new → pack.yaml 3줄 → pack-check OK → 스키마 · 시드 1초 → 기동 0.6초 → 로그인 · 메뉴 용어 치환 확인 1.6초 · 합계 약 20초 ≤ 4h (2026-10-09 QA3 실측 · mes_qa3_db · 8054)
```
