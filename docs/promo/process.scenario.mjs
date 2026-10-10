// 업무 프로세스 유형별 영상 — 메인 › 업무 프로세스(app/guide.py)의 한 유형을 단계 화면 순서대로 보여 준다. test_video_maker 녹화기로 찍는다.
//   PROC=P01 node ~/.claude/skills/test_video_maker/bin/record.mjs docs/promo/process.scenario.mjs --work <작업폴더>   # → docs/promo/process/P01.mp4
//   (전부: docs/promo/process_all.sh)
//
// 단계 · 화면 · 담당 역할 · 남는 데이터는 guide.py 에서 그때 읽는다(여기에 다시 적지 않는다). 원고는 process_narration.mjs.
// 개발 DB 는 건드리지 않는다: setup() 이 mes_demo_db 를 createdb -T 로 사본(promo_proc)을 떠 녹화 전용 포트에서 띄운다.
// 화면 조회만 한다(쓰기 없음). 샘플 번호가 화면에 없으면 멈춘다 — 지어내지 않는다.
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { PROCESS_NARRATION } from './process_narration.mjs';

const REPO = process.env.REPO ?? process.cwd();
const PROC = process.env.PROC ?? 'P01';
const PG = ['-h', '/tmp'];
const DB = 'promo_proc';
const SRC_DB = 'mes_demo_db';
const PORT = 8091;
const base = `http://127.0.0.1:${PORT}`;

// 데모 DB(mes_demo_db) 의 샘플 — 화면이 비어 보이지 않게 번호를 넘긴다. 화면에 그 번호가 보이는지 확인한다.
const SAMPLE = { shipLot: 'X261009-0001', matLot: 'M261009-0009', prodLot: 'P261010-0009', workOrder: 'W261010-010' };
const QUERY = {
  'POP-02': () => `?id=${SAMPLE.resultId}`,
  'POP-03': () => `?result=${SAMPLE.resultId}`,
  'JOB-03': () => `?no=${SAMPLE.workOrder}`,
  'QUA-02': () => `?no=${SAMPLE.prodLot}`,
  'MAT-05': () => `?frm=${SAMPLE.from}&to=${SAMPLE.to}`,
  'TRC-03': () => `?q=${SAMPLE.shipLot}`,
  'TRC-02': () => `?no=${SAMPLE.shipLot}`,
  'TRC-01': () => `?no=${SAMPLE.matLot}`,
};
const EXPECT = { 'JOB-03': 'workOrder', 'TRC-03': 'shipLot', 'TRC-02': 'shipLot', 'TRC-01': 'matLot' };
const ZOOM = { 'KPI-01': '0.66' };

export const config = {
  voice: 'Yuna',
  out: `docs/promo/process/${PROC}.mp4`,
  checkPrefix: '확인',
  accent: '#2563eb',
};

const psql = (sql) => execFileSync('psql', [...PG, '-d', DB, '-tAc', sql]).toString().trim();

function readEnv(file) {
  return Object.fromEntries(
    fs.readFileSync(file, 'utf8').split('\n')
      .filter((l) => /^MES_\w+=/.test(l))
      .map((l) => [l.slice(0, l.indexOf('=')), l.slice(l.indexOf('=') + 1)])
  );
}

// guide.py 의 유형 하나 + 화면 이름 · 경로 · 역할 이름(DB 권한 표)
function loadProcess(code) {
  const py = `
import json, sys
from mescore.app import guide, nav, rbac
roles = {r.code: r.name for r in rbac.roles()}
p = next(p for p in guide.processes() if p.code == sys.argv[1])
print(json.dumps({"code": p.code, "name": p.name, "kind": p.kind, "when": p.when, "goal": p.goal,
  "checks": list(p.checks), "measures": list(p.measures),
  "steps": [{"screen_id": s.screen_id, "screen": nav.by_id(s.screen_id).name, "path": nav.path_of(s.screen_id),
             "role": roles.get(s.role, s.role), "action": s.action, "output": s.output} for s in p.steps]}, ensure_ascii=False))`;
  const out = execFileSync('uv', ['run', 'python', '-c', py, code], {
    cwd: REPO, env: { ...process.env, MES_PACK: '', MES_ADDONS: '', MES_PG_DSN: `postgresql:///${DB}` },
  }).toString();
  return JSON.parse(out.trim().split('\n').pop());
}

export async function setup({ startServer }) {
  const env = readEnv(path.join(REPO, '.env'));
  if (!env.MES_SEED_PASSWORD) throw new Error('.env 에 MES_SEED_PASSWORD 가 없다');
  execFileSync('dropdb', [...PG, '--if-exists', DB]);
  execFileSync('createdb', [...PG, '-T', SRC_DB, DB]); // 원본에 접속이 있으면 실패한다 — 그때는 원본 쪽 서버를 잠시 내린다
  SAMPLE.resultId = psql(`select r.id from pop_work_result r join job_work_order w on w.id=r.work_order_id where w.work_order_no='${SAMPLE.workOrder}' order by r.id desc limit 1`);
  [SAMPLE.from, SAMPLE.to] = psql(`select min(plan_date)||'|'||max(plan_date) from ord_plan`).split('|');
  if (!SAMPLE.resultId || !SAMPLE.from) throw new Error('데모 DB 에 샘플 실적 · 계획이 없다');
  const proc = loadProcess(PROC);
  await startServer({
    name: 'core',
    cmd: 'uv',
    args: ['run', 'uvicorn', 'mescore.app.main:app', '--app-dir', 'src', '--port', String(PORT)],
    cwd: REPO,
    env: { MES_ENV: 'prod', MES_PACK: '', MES_ADDONS: '', MES_PG_DSN: `postgresql:///${DB}` },
    port: PORT,
    readyUrl: `${base}/health`,
  });
  return {
    url: base, password: env.MES_SEED_PASSWORD, proc,
    teardown: () => execFileSync('dropdb', [...PG, '--if-exists', DB]),
  };
}

// ── 카드 ─────────────────────────────────────────────
const F = `-apple-system,'Apple SD Gothic Neo','Pretendard',sans-serif`;
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const eyebrow = (t) => `<div style="font:700 15px ${F};letter-spacing:.18em;color:#93c5fd">${esc(t)}</div>`;
const pill = (t, bg = 'rgba(255,255,255,.1)', bd = 'rgba(255,255,255,.25)') =>
  `<span style="display:inline-block;padding:7px 16px;border-radius:999px;background:${bg};border:1px solid ${bd};font:600 17px ${F};color:#fff">${esc(t)}</span>`;

const INTRO = (p) => {
  const flow = p.steps.map((s) => s.screen).filter((s, i, a) => s !== a[i - 1]);
  return `${eyebrow(`업무 프로세스 ${p.code} · ${p.kind}`)}
  <h1 style="font-size:56px;letter-spacing:-.02em">${esc(p.name)}</h1>
  <h2 style="font-size:24px;color:#cbd5e1">${esc(p.when)}</h2>
  <div style="max-width:1100px;font:500 20px/1.6 ${F};color:#e0f2fe;margin-top:4px">${esc(p.goal)}</div>
  <div style="display:flex;flex-wrap:wrap;gap:8px 6px;justify-content:center;align-items:center;max-width:1240px;margin-top:14px">
    ${flow.map((s, i) => pill(s) + (i < flow.length - 1 ? `<span style="color:#93c5fd;font:700 18px ${F}">→</span>` : '')).join('')}
  </div>
  <div style="font:500 16px ${F};color:#94a3b8;margin-top:6px">단계 ${p.steps.length} · 화면 ${new Set(p.steps.map((s) => s.screen_id)).size}</div>`;
};

const OUTRO = (p) => `${eyebrow(`${p.code} ${p.name} · 확인 포인트`)}
  <div style="display:flex;flex-direction:column;gap:12px;width:1000px;margin-top:6px">
    ${p.checks.map((c) => `<div style="text-align:left;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.18);border-radius:14px;padding:16px 22px;font:600 22px ${F};color:#fff"><span style="color:#4ade80;margin-right:12px">✔</span>${esc(c)}</div>`).join('')}
  </div>
  <div style="font:700 15px ${F};color:#93c5fd;margin-top:14px">보는 지표 · 화면</div>
  <div style="display:flex;flex-wrap:wrap;gap:8px;justify-content:center">${p.measures.map((m) => pill(m, 'rgba(74,222,128,.14)', '#4ade80')).join('')}</div>
  <div style="font:600 18px ${F};color:#cbd5e1;margin-top:18px">MES 표준플랫폼 · Rodem MES Solution</div>`;

export default async function scenario(r, { password, proc: p }) {
  const { page, say, settle, scene, moveTo, box, pause } = r;
  const n = PROCESS_NARRATION[p.code];
  const assert = (label, cond, detail = '') => {
    if (!cond) throw new Error(`확인 실패: ${label} ${detail}`);
    console.log('  ✔', label);
  };
  assert(`${p.code} 원고 있음`, n);
  assert(`${p.code} 원고 단계 수 = guide.py 단계 수 (${p.steps.length})`, n.steps.length === p.steps.length, `원고 ${n.steps.length}`);

  const res = await r.context.request.post(base + '/login', {
    form: { login_id: 'admin', password },
    headers: { accept: 'application/json' },
  });
  if (!res.ok()) throw new Error(`로그인 실패 ${res.status()}`);
  await page.goto(base + '/main/processes?code=' + p.code);
  await r.card(INTRO(p));
  await r.start();

  scene(`${p.code} ${p.name}`);
  await say(n.intro, `${p.when} — ${p.goal}`);
  await settle(0.6);
  await r.card(null);

  for (const [i, s] of p.steps.entries()) {
    await settle(0.2);
    const url = s.path + (QUERY[s.screen_id]?.() ?? '');
    const resp = await page.goto(base + url);
    assert(`${s.screen_id} ${s.screen} 열림`, resp && resp.ok(), `${url} → ${resp?.status()}`);
    if (ZOOM[s.screen_id]) await page.evaluate((z) => (document.body.style.zoom = z), ZOOM[s.screen_id]);
    const main = page.locator('main').first();
    if (EXPECT[s.screen_id]) {
      const no = SAMPLE[EXPECT[s.screen_id]];
      assert(`${s.screen_id} 화면에 ${no}`, (await main.innerText()).includes(no));
    }
    scene(`${i + 1}/${p.steps.length} · ${s.screen}`);
    const out = s.output && s.output !== '—' ? ` → ${s.output}` : '';
    await say(n.steps[i], `[${s.role}] ${s.action}${out}`);
    const target = (await page.locator('main .panel').count()) ? page.locator('main .panel').first() : main;
    await moveTo(620 + (i % 3) * 160, 300 + (i % 2) * 80);
    await box(target, 2200);
    await pause(300);
  }

  await settle(0.4);
  scene(`${p.code} ${p.name}`);
  await r.card(OUTRO(p));
  await say(n.outro, p.checks.join(' · '));
  await r.stop(1.6);
}
