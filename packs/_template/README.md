# 팩 템플릿 (`packs/_template`) — spec.md §8.2 · contracts/pack-contract.md

`make pack-new NAME=<팩>` 이 이 폴더를 복사한다. 팩은 **이 폴더 안에서만** 산다 — 코어(`src/mescore`)를 고치면 G-P01 FAIL.
팩이 할 수 있는 일은 확장 지점 7개(spec.md §3)뿐이다. 밖이 필요하면 `decisions.md` 에 `코어 변경 요청`(goal.md §4.3).

## 폴더

| 파일 | 확장 지점 | 하는 일 |
|---|---|---|
| `pack.yaml` | E1 · E2 · E3 · E6 | 용어 · 메뉴 · 화면 · 역할 · 권한 · 채번 · 채널 · 속성 · 계보 종류 · write_scope. 모든 키에 주석 |
| `schema_ext.sql` | E2 · E4 | `x_<팩>_*` 테이블만. 코어 테이블 ALTER · DROP · 트리거 금지(R2). 공통 컬럼 6 + `attrs`(R3) |
| `routers/*.py` | E4 | `router = APIRouter()`. `_` 로 시작하는 파일은 include 안 됨(`_example.py` 는 예) |
| `templates/` | E4 · E7 | 코어 `templates/` 보다 먼저 검색 — 같은 이름은 코어를 덮어쓴다(R10 · 아래 목록에 적는다) |
| `hooks.py` | E5 | 모든 훅의 빈 서명. 필요한 것만 채운다 |
| `adapters/` | E7 | `PrintAdapter` · `ErpAdapter` · `CollectDriver` 인터페이스. 기본은 코어(브라우저 인쇄 · 501 · HTTP 수집) |
| `seed/*.csv` | E1 · E3 | `permissions` · `process_params` · `inspection_items` · `codes` · `items_example` 헤더. 멱등 upsert |
| `tests/` | — | `@pytest.mark.fn("F-X-…")`. `gates.yaml: scenarios[].test` 가 가리킨다 |
| `gates.yaml` | — | 팩 게이트 기대값 (화면 · 테이블 · 기능 수 · 시나리오 · terms_sample) |
| `function-list.md` | — | 팩 기능 계약 — 코어 `function-list.md` 와 같은 13열. E4 화면이 있으면 필수 |

## 작성 순서 (spec.md §8.1)

1. `pack.yaml` 의 `pack name company terms roles numbering` → `MES_PACK=<팩> make pack-check`
2. `MES_PACK=<팩> make db-schema db-seed run` → 로그인 → 코어 화면이 업종 말로 뜨는지 (여기까지 4시간 · G-P06)
3. 설계 산출물이 있으면 `tools/import_design.py` → 매핑표 (G-P03)
4. 빠진 것을 E1~E7 로 **분류**(spec.md §3.8). 어디에도 안 들어가면 D-번호
5. E1 · E3 · E6 는 `pack.yaml` · `seed/*.csv` 로 끝낸다 → `make db-seed` ×2 행 수 diff 0
6. E2 · E4 는 `schema_ext.sql` · `routers/` · `templates/` → `make check-schema check-routes check-pack`
7. E5 · E7 은 `hooks.py` · `adapters/`
8. `gates.yaml` 기대값 → `make gate`
9. 브라우저 한 바퀴 캡처 `outputs/e2e/<팩>/`

## 이 팩이 덮어쓴 코어 템플릿 (R10)

(없음)
