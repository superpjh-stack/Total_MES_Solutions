// 네이버 클라우드 CLOVA Voice(Premium) API 로 내레이션 14문장을 문장별 mp3 로 만든다.
//   node docs/promo/clova_tts.mjs --sample nara,nminsang,vdain   # 01번 문장을 목소리별로 만들어 비교 (voice/sample_<목소리>.mp3)
//   node docs/promo/clova_tts.mjs <목소리> [속도]                  # 14문장 전부 → voice/01.mp3 … 14.mp3  (속도 -5 빠름 ~ 5 느림, 기본 0)
// 키는 저장소 .env 에만 둔다(G-C19): MES_CLOVA_CLIENT_ID · MES_CLOVA_CLIENT_SECRET. 이 스크립트는 키 값을 출력하지 않는다.
// 문장 텍스트가 네이버 클라우드로 전송되고, 호출량만큼 요금이 나온다.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, '../..');
const env = Object.fromEntries(
  fs.readFileSync(path.join(repo, '.env'), 'utf8').split('\n')
    .filter((l) => /^MES_CLOVA_\w+=/.test(l))
    .map((l) => [l.slice(0, l.indexOf('=')), l.slice(l.indexOf('=') + 1).trim()])
);
const id = env.MES_CLOVA_CLIENT_ID;
const secret = env.MES_CLOVA_CLIENT_SECRET;
if (!id || !secret) {
  console.error('.env 에 MES_CLOVA_CLIENT_ID · MES_CLOVA_CLIENT_SECRET 이 없다');
  process.exit(2);
}
const { NARRATION } = await import(pathToFileURL(path.join(here, 'promo.scenario.mjs')).href);
const outDir = path.join(here, 'voice');
fs.mkdirSync(outDir, { recursive: true });

async function tts(text, speaker, speed, file) {
  const res = await fetch('https://naveropenapi.apigw.ntruss.com/tts-premium/v1/tts', {
    method: 'POST',
    headers: {
      'X-NCP-APIGW-API-KEY-ID': id,
      'X-NCP-APIGW-API-KEY': secret,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: new URLSearchParams({ speaker, text, speed: String(speed), volume: '0', pitch: '0', format: 'mp3' }),
  });
  if (!res.ok) throw new Error(`${path.basename(file)}: HTTP ${res.status} ${(await res.text()).slice(0, 300)}`);
  fs.writeFileSync(file, Buffer.from(await res.arrayBuffer()));
  console.log('저장', path.relative(repo, file));
}

const args = process.argv.slice(2);
if (args[0] === '--sample') {
  for (const sp of (args[1] || 'nara').split(',')) await tts(NARRATION[0], sp, 0, path.join(outDir, `sample_${sp}.mp3`));
} else {
  const [speaker, speed = '0'] = args;
  if (!speaker) {
    console.error('사용법: node docs/promo/clova_tts.mjs <목소리> [속도]  또는  --sample <목소리,목소리>');
    process.exit(2);
  }
  for (const [i, text] of NARRATION.entries()) await tts(text, speaker, speed, path.join(outDir, `${String(i + 1).padStart(2, '0')}.mp3`));
}
