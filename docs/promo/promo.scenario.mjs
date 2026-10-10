// MES 표준플랫폼 홍보 영상 (약 3분) — test_video_maker 녹화기로 찍는다.
//   node ~/.claude/skills/test_video_maker/bin/record.mjs docs/promo/promo.scenario.mjs --dry --work <작업폴더>   # 점검
//   node ~/.claude/skills/test_video_maker/bin/record.mjs docs/promo/promo.scenario.mjs --work <작업폴더>         # 본 녹화
//
// 개발 DB 는 건드리지 않는다: setup() 이 createdb -T 로 사본(promo_*)을 뜨고, 사본을 쓰는 서버 4대를 녹화 전용 포트에 띄운다.
// 영상에 나오는 수치는 화면에서 읽어 확인한다(assert). 틀리면 녹화를 멈춘다 — 홍보 문구라도 지어내지 않는다.
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const REPO = process.env.REPO ?? process.cwd();
const PG = ['-h', '/tmp'];
// 팩 → 원본 DB · 녹화 포트
const SITES = {
  core: { pack: '', src: 'mes_demo_db', port: 8091 },
  kimchi: { pack: 'kimchi', src: 'mes_kimchi_db', port: 8092 },
  printfilm: { pack: 'printfilm', src: 'mes_printfilm_db', port: 8093 },
  foodservice: { pack: 'foodservice', src: 'mes_foodservice_db', port: 8094 },
};
const base = (k) => `http://127.0.0.1:${SITES[k].port}`;

// 내레이션 원고 (귀로 듣는 말) — 번호 = 클로바더빙에서 내려받을 파일 이름(01.mp3 …). 자막은 아래 say() 두 번째 인자.
// 영문 약어는 한글로 적는다(MES → 엠이에스, LOT → 로트). 문장을 고치면 그 번호의 음성 파일을 다시 만든다.
export const NARRATION = [
  /* 01 오프닝 */ '공장이 바뀔 때마다, 엠이에스를 처음부터 다시 만들고 계신가요? 이제는 그럴 필요가 없습니다. 코어 하나에 업종 팩 하나만 붙이면, 새 공장의 엠이에스가 완성됩니다.',
  /* 02 문제 */ '김치 공장, 급식 공장, 인쇄필름 공장, 타월 공장. 저희가 만든 엠이에스 네 벌은, 뼈대가 거의 같았습니다. 그런데도 매번 지난 프로젝트 코드를 복사해서 고쳤죠. 다른 업종 용어가 섞여 들어오고, 검사 도구도 매번 새로 짰습니다.',
  /* 03 구조 */ '그래서 둘로 나눴습니다. 수주부터 출하, 로트 추적까지, 어느 공장에나 있는 열두 가지 업무는 코어가 맡습니다. 공장마다 다른 용어와 메뉴, 전용 화면은 업종 팩이 맡고요.',
  /* 04 구조 */ '팩은 미리 정해 둔 일곱 군데에만 끼워집니다. 그래서 팩을 아무리 붙여도, 코어는 그대로입니다.',
  /* 05 코어 */ '먼저 코어만 띄워 보겠습니다. 이것만으로도 엠이에스 한 벌이 돌아갑니다. 화면 쉰한 개, 기능 백서른두 개가, 일하는 순서대로 한눈에 보이죠.',
  /* 06 코어 */ '사무실 관리자 화면, 현장 단말, 모바일, 그리고 현황판까지. 네 가지 화면이 한 틀로 움직이고, 현황판은 오 초마다 새로 고쳐집니다.',
  /* 07 김치 */ '이번엔 같은 코어에 김치 팩을 붙였습니다. 절임통 운영, 숙성 냉장 같은 메뉴가 생겼고요. 생산 로트는 배치로, 작업지시는 작업지시서로. 김치 공장에서 쓰는 말로 바뀌었습니다.',
  /* 08 김치 */ '이 플랫폼의 핵심은 로트 추적입니다. 출하 번호 하나만 넣어 볼게요.',
  /* 09 김치 */ '출하된 김치가 어떤 배치에서 나왔는지, 거기에 어느 절임통이 들어갔는지, 배추와 고춧가루, 마늘은 어떤 걸 썼는지. 다섯 단계가 한 번에 쭉 펼쳐집니다.',
  /* 10 인쇄 */ '인쇄필름 공장에서는 똑같은 화면이 이렇게 보입니다. 로트는 롤이 되고, 롤을 이어 붙이는 스플라이스, 잘라 나누는 슬리팅까지. 이 업종에만 있는 작업도 그대로 추적됩니다.',
  /* 11 급식 */ '급식 공장에서는 솥 단위 배치, 출고, 조리 지시라는 말을 씁니다. 화면은 같은데, 말은 그 공장의 말이죠.',
  /* 12 측정 */ '공정마다 재는 값이 다르죠. 온도, 무게, 절임 염도처럼요. 이런 항목은 테이블을 새로 만들지 않고, 여기에 적어 두기만 하면 됩니다. 입력 화면과 기록, 기준 이탈 확인은 알아서 따라옵니다.',
  /* 13 검증 */ '말로만 하는 게 아닙니다. 자동 검사 마흔두 개를 모두 통과했고, 세 업종 팩 어디에서도 코어는 한 줄도 고치지 않았습니다. 새 업종 팩은 복사 한 번으로 시작해서, 이십 초 남짓이면 화면에 뜹니다.',
  /* 14 마무리 */ '코어 하나, 업종 팩 하나. 다음 공장의 엠이에스는 복사가 아니라, 선언으로 시작하세요. 로뎀 엠이에스 솔루션이었습니다.',
];
const N = NARRATION;

export const config = {
  voice: 'Yuna',
  out: 'docs/promo/MES표준플랫폼_홍보영상.mp4',
  checkPrefix: '확인',
  accent: '#2563eb',
};

function readEnv(file) {
  return Object.fromEntries(
    fs.readFileSync(file, 'utf8').split('\n')
      .filter((l) => /^MES_\w+=/.test(l))
      .map((l) => [l.slice(0, l.indexOf('=')), l.slice(l.indexOf('=') + 1)])
  );
}

export async function setup({ startServer }) {
  const env = readEnv(path.join(REPO, '.env'));
  if (!env.MES_SEED_PASSWORD) throw new Error('.env 에 MES_SEED_PASSWORD 가 없다');
  for (const [k, s] of Object.entries(SITES)) {
    const db = `promo_${k}`;
    execFileSync('dropdb', [...PG, '--if-exists', db]);
    execFileSync('createdb', [...PG, '-T', s.src, db]); // 원본에 접속이 있으면 실패한다 — 그때는 원본 쪽 서버를 잠시 내린다
    await startServer({
      name: k,
      cmd: 'uv',
      args: ['run', 'uvicorn', 'mescore.app.main:app', '--app-dir', 'src', '--port', String(s.port)],
      cwd: REPO,
      env: { MES_ENV: 'prod', MES_PACK: s.pack, MES_ADDONS: '', MES_PG_DSN: `postgresql:///${db}` },
      port: s.port,
      readyUrl: `${base(k)}/health`,
    });
  }
  return { url: base('core'), password: env.MES_SEED_PASSWORD };
}

// ── 카드 디자인 (녹화기 #demo-card 안에 그린다) ─────────────────────────────
const F = `-apple-system,'Apple SD Gothic Neo','Pretendard',sans-serif`;
const eyebrow = (t) => `<div style="font:700 15px ${F};letter-spacing:.18em;color:#93c5fd;text-transform:uppercase">${t}</div>`;
const pill = (t, bg = 'rgba(255,255,255,.1)', bd = 'rgba(255,255,255,.25)') =>
  `<span style="display:inline-block;padding:8px 18px;border-radius:999px;background:${bg};border:1px solid ${bd};font:600 18px ${F};color:#fff">${t}</span>`;

const TITLE = `
  ${eyebrow('Rodem MES Solution')}
  <h1 style="font-size:58px;letter-spacing:-.02em">MES 표준플랫폼</h1>
  <h2 style="font-size:28px">코어 한 벌 + 업종 팩 하나 = 새 공장의 MES</h2>`;

const PROBLEM = (() => {
  const box = (n, h, p) => `<div style="flex:1;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.18);border-radius:16px;padding:26px 24px;text-align:left">
      <div style="font:800 34px ${F};color:#f87171">${n}</div>
      <div style="font:700 22px ${F};color:#fff;margin:8px 0 10px">${h}</div>
      <div style="font:400 16px/1.55 ${F};color:#cbd5e1">${p}</div></div>`;
  return `${eyebrow('지금까지')}
  <h1 style="font-size:38px">MES 네 벌, 뼈대는 같았다</h1>
  <h2>김치 · 급식 · 인쇄필름 · 타월 — 메뉴 이름과 테이블 접두어만 달랐다</h2>
  <div style="display:flex;gap:22px;width:1040px;margin-top:18px">
    ${box('01', '골격 이식', '직전 사업 폴더의 코드를 복사해 시작하고<br>회사 이름 · DB · 포트를 손으로 바꿨다')}
    ${box('02', '용어 오염', '급식의 솥 · 검식이 인쇄 회사 코드에,<br>김치의 염도가 급식 코드에 남았다')}
    ${box('03', '검증 재작성', '같은 검사 도구와 게이트를<br>사업마다 다시 맞췄다')}
  </div>`;
})();

const ARCH = (() => {
  const mods = ['기준정보', '수주 · 계획', '작업지시', '자재', '생산실적', '품질', '설비', '출하', 'LOT 추적', '현황 · KPI', '시스템', '인터페이스'];
  return `${eyebrow('해법')}
  <h1 style="font-size:38px">고치지 않는 코어, 갈아 끼우는 팩</h1>
  <div style="width:1000px;margin-top:10px;display:flex;flex-direction:column;align-items:center;gap:12px">
    <div style="width:100%;border:2px dashed #fbbf24;border-radius:16px;padding:16px 20px;background:rgba(251,191,36,.08)">
      <div style="font:700 16px ${F};color:#fbbf24;margin-bottom:10px">업종 팩 — 용어 사전 · 메뉴 추가/숨김 · 확장 테이블 · 전용 화면 · 훅</div>
      <div style="display:flex;gap:12px;justify-content:center">
        ${pill('김치 kimchi', 'rgba(251,191,36,.18)', '#fbbf24')}${pill('급식 foodservice', 'rgba(251,191,36,.18)', '#fbbf24')}${pill('인쇄필름 printfilm', 'rgba(251,191,36,.18)', '#fbbf24')}${pill('+ 새 업종', 'transparent', 'rgba(255,255,255,.4)')}
      </div>
    </div>
    <div style="font:700 15px ${F};color:#fbbf24">▼ 확장 지점 7개로만 연결 ▼</div>
    <div style="width:100%;border:2px solid #60a5fa;border-radius:16px;padding:18px 20px;background:rgba(96,165,250,.12)">
      <div style="font:700 16px ${F};color:#93c5fd;margin-bottom:12px">표준 코어 — 업종 무관 · 고치지 않는다</div>
      <div style="display:grid;grid-template-columns:repeat(6,1fr);gap:8px">
        ${mods.map((m) => `<div style="background:rgba(255,255,255,.1);border-radius:8px;padding:9px 4px;font:600 16px ${F};color:#fff">${m}</div>`).join('')}
      </div>
      <div style="margin-top:12px;font:600 16px ${F};color:#e0f2fe">본체: <b style="color:#fff">LOT 재귀 계보</b> (lot + lot_genealogy) · <b style="color:#fff">측정값 선언</b> (bas_process_param → pop_measure)</div>
    </div>
  </div>`;
})();

const PROOF = (gate) => {
  const stat = (big, label, sub) => `<div style="flex:1;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.18);border-radius:16px;padding:24px 10px">
      <div style="font:800 52px ${F};color:#4ade80;letter-spacing:-.02em">${big}</div>
      <div style="font:700 19px ${F};color:#fff;margin-top:6px">${label}</div>
      <div style="font:400 14px ${F};color:#94a3b8;margin-top:6px">${sub}</div></div>`;
  return `${eyebrow('말이 아니라 숫자로')}
  <h1 style="font-size:38px">수용 게이트로 검증한다</h1>
  <div style="display:flex;gap:18px;width:1080px;margin-top:16px">
    ${stat(`${gate.pass}/${gate.total}`, '게이트 전부 통과', '코어 G-C 24 + 팩 G-P 6 × 3 · make gate')}
    ${stat('0', '코어 수정', '참조 팩 3개 모두 · 코어 해시 변동 0')}
    ${stat('3', '참조 팩', '김치 · 급식 · 인쇄필름 핵심 시나리오 재현')}
    ${stat('≈20초', '새 팩 착수', 'pack-new → 기동 → 용어 확인 (기계 시간)')}
  </div>`;
};

const CLOSING = `
  ${eyebrow('Rodem MES Solution')}
  <h1 style="font-size:52px;letter-spacing:-.02em">다음 공장의 MES는<br>복사가 아니라 선언으로</h1>
  <div style="display:flex;gap:12px;margin-top:10px">${pill('코어 한 벌')}${pill('업종 팩 하나')}${pill('LOT 계보 · 측정값')}${pill('4채널')}</div>
  <h2 style="margin-top:14px">MES 표준플랫폼</h2>`;

export default async function scenario(r, { password }) {
  const { page, say, settle, scene, moveTo, click, type, box, scrollTop, pause } = r;
  const assert = (label, cond, detail = '') => {
    if (!cond) throw new Error(`화면 값 확인 실패: ${label} ${detail}`);
    console.log('  ✔', label);
  };
  // 서버를 옮길 때마다 그 서버에 로그인한다(쿠키는 포트를 가리지 않아 서로 덮는다)
  const enter = async (site, p) => {
    const res = await r.context.request.post(base(site) + '/login', {
      form: { login_id: 'admin', password },
      headers: { accept: 'application/json' },
    });
    if (!res.ok()) throw new Error(`${site} 로그인 실패 ${res.status()}`);
    await page.goto(base(site) + p);
  };
  const sidebar = () => page.locator('.menu-group').first().locator('xpath=..');
  const traceBy = async (no) => {
    const input = page.locator('form.scan-box input[data-scan]');
    await click(input);
    await type(input, no);
    await click(page.locator('form.scan-box button[type=submit]'));
    await page.locator('ul.tree').waitFor();
  };

  // 게이트 수치는 지금 저장소에서 다시 돌린 make gate 출력에서 읽는다
  const gateFile = process.env.GATE_FILE;
  const gateText = gateFile && fs.existsSync(gateFile) ? fs.readFileSync(gateFile, 'utf8') : '';
  const gm = /PASS (\d+) · FAIL (\d+) · WARN (\d+) · BLOCKED (\d+) · 미검증 (\d+) \/ 전체 (\d+)/.exec(gateText);
  assert('make gate 결과 있음', gm, gateFile);
  const gate = { pass: Number(gm[1]), total: Number(gm[6]) };
  assert(`게이트 ${gate.pass}/${gate.total} 전부 PASS`, gate.pass === gate.total && gm[2] === '0');
  assert('원고 13번의 「마흔두 개」 = 게이트 전체 수', gate.total === 42, `전체 ${gate.total} — 원고 13번과 그 음성 파일을 고친다`);

  await enter('core', '/');
  await page.locator('.ia-top').waitFor();
  await r.card(TITLE);
  await r.start();

  // ── 0. 오프닝 ──
  scene('MES 표준플랫폼');
  await say(N[0],
    '공장이 바뀔 때마다 MES를 처음부터 다시 만드시나요? 코어 한 벌 + 업종 팩 하나로 새 공장의 MES를 완성합니다.'
  );
  await settle(0.8);

  // ── 1. 문제 ──
  scene('지금까지');
  await r.card(PROBLEM);
  await say(N[1],
    'MES 네 벌은 뼈대가 같았지만 — 매번 코드를 복사했고, 다른 업종 용어가 섞였고, 검증 도구를 다시 짰습니다.'
  );
  await settle(0.6);

  // ── 2. 구조 ──
  scene('코어 + 팩');
  await r.card(ARCH);
  await say(N[2],
    '12개 업무 모듈은 업종 무관한 코어가, 업종마다 다른 용어 · 메뉴 · 확장 테이블 · 전용 화면은 업종 팩이 맡습니다.'
  );
  await say(N[3],
    '팩은 정해진 확장 지점 7개로만 붙습니다 — 코어는 한 줄도 고치지 않습니다.'
  );
  await settle(0.5);
  await r.card(null);

  // ── 3. 코어 단독 ──
  scene('코어 단독');
  const top = page.locator('.ia-top');
  const topText = await top.innerText();
  assert('메인: 모듈 12 · 화면 51 · 기능 132', /모듈 12/.test(topText) && /화면 51/.test(topText) && /기능 132/.test(topText), topText.slice(0, 160));
  await say(N[4],
    '코어만으로 MES 한 벌 — 모듈 12 · 화면 51 · 기능 132가 일하는 순서대로 한 장의 지도에 놓입니다.'
  );
  await moveTo(640, 180);
  await box(top, 2600);
  await moveTo(760, 420);
  await box(page.locator('#ia-menus'), 3000);
  await settle(0.3);

  await page.goto(base('core') + '/kpi/board');
  await page.evaluate(() => (document.body.style.zoom = '0.66'));
  await say(N[5],
    '관리자 Web · 현장 POP · 모바일 · 현황판 — 4채널이 한 틀로. 현황판은 생산 · 품질 · 설비 · 납기를 5초마다 갱신합니다.'
  );
  await moveTo(420, 260);
  await pause(2500);
  await moveTo(900, 300);
  await settle(0.3);

  // ── 4. 김치 팩 + LOT 역추적 ──
  scene('김치 팩');
  await enter('kimchi', '/trc/backward');
  await page.locator('form.scan-box').waitFor();
  await say(N[6],
    '같은 코어 + 김치 팩: 절임통 운영 · 숙성 냉장 메뉴가 더해지고, 생산 LOT → 배치, 작업지시 → 작업지시서로 보입니다.'
  );
  await moveTo(120, 300);
  await box(sidebar(), 3200);
  await settle(0.2);
  await say(N[7],
    '플랫폼의 심장은 LOT 계보 — 출하 로트 번호 하나로 원재료까지 한 번에 거슬러 올라갑니다.'
  );
  await traceBy('X261009-0001');
  const kInfo = await page.locator('h2 .right').first().innerText();
  const kMats = await page.locator('ul.plain-list').first().innerText();
  assert('김치 역추적 깊이 5 · 원부자재 로트 3', /깊이 5/.test(kInfo) && /원부자재 로트 3/.test(kInfo), kInfo);
  assert('원부자재에 배추 · 고춧가루 · 마늘', ['배추', '고춧가루', '마늘'].every((w) => kMats.includes(w)), kMats);
  await say(N[8],
    '출하 로트 → 배치 → 절임통 배치 → 배추 · 고춧가루 · 마늘 원부자재까지, 5단계를 재귀 조회 1회로.'
  );
  await moveTo(700, 270);
  await box(page.locator('ul.tree'), 3800);
  await r.reveal(page.locator('ul.plain-list').first());
  await box(page.locator('ul.plain-list').first(), 2400);
  await settle(0.3);

  // ── 5. 인쇄필름 팩 ──
  scene('인쇄필름 팩');
  await enter('printfilm', '/trc/backward?no=X261009-0038');
  await page.locator('ul.tree').waitFor();
  const pTree = await page.locator('ul.tree').innerText();
  assert('인쇄필름 계보에 ROLL · 슬리팅 · splice', /ROLL/.test(pTree) && /슬리팅/.test(pTree) && /splice/.test(pTree));
  await say(N[9],
    '인쇄필름 팩: 같은 화면이 Roll · Job의 언어로. 슬리팅 · splice 같은 업종 고유 관계도 같은 계보 위에서 추적됩니다.'
  );
  await moveTo(560, 300);
  await box(page.locator('ul.tree'), 3600);
  await moveTo(120, 260);
  await box(sidebar(), 2200);
  await settle(0.3);

  // ── 6. 급식 팩 ──
  scene('급식 팩');
  await enter('foodservice', '/trc/backward?no=X-EX-0001');
  await page.locator('ul.tree').waitFor();
  const fTitle = await page.title();
  assert('급식: 배치 추적 화면', /배치 추적/.test(fTitle), fTitle);
  await say(N[10],
    '급식 팩: 생산 LOT → 배치(솥), 출하 → 출고, 작업지시 → 조리 지시. 화면은 같고, 말은 그 공장의 말입니다.'
  );
  await moveTo(600, 260);
  await box(page.locator('ul.tree'), 3000);
  await settle(0.3);

  // ── 7. 측정값 선언 ──
  scene('측정값 선언');
  await enter('kimchi', '/bas/process-params');
  await page.locator('table').first().waitFor();
  await say(N[11],
    '공정별 측정값은 테이블을 새로 만들지 않습니다 — 선언만 하면 현장 입력 폼 · 기록 · 범위 이탈 판정 · 집계가 따라옵니다.'
  );
  await moveTo(560, 330);
  await box(page.locator('table').first(), 4200);
  await settle(0.4);

  // ── 8. 검증 ──
  scene('검증');
  await r.card(PROOF(gate));
  await say(N[12],
    `수용 게이트 ${gate.pass}/${gate.total} 전부 통과 · 참조 팩 3개 코어 수정 0 · 새 업종 팩 착수부터 화면까지 약 20초.`
  );
  await settle(0.8);

  // ── 9. 마무리 ──
  scene('MES 표준플랫폼');
  await r.card(CLOSING);
  await say(N[13],
    '코어 한 벌, 업종 팩 하나 — 다음 공장의 MES는 복사가 아니라 선언으로. Rodem MES Solution.'
  );
  await r.stop(2.0);
}
