// 클로바더빙에서 내려받은 문장별 음성(01.mp3 … 14.mp3)을 녹화기 음성 캐시에 넣는다.
//   node docs/promo/import_voice.mjs <음성 폴더> <녹화 작업 폴더>
// 녹화기(test_video_maker)는 문장마다 `<작업 폴더>/audio/<md5(voice|rate|문장) 앞 12자>.aiff` 가 있으면 say 로 만들지 않고 그 파일을 쓴다.
// 화면 속도는 그 음성 길이에 맞춰지므로, 이 스크립트를 돌린 뒤 같은 작업 폴더로 다시 녹화하면 된다.
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const [voiceDir, workDir] = process.argv.slice(2);
if (!voiceDir || !workDir) {
  console.error('사용법: node docs/promo/import_voice.mjs <음성 폴더> <녹화 작업 폴더>');
  process.exit(2);
}
const here = path.dirname(fileURLToPath(import.meta.url));
const { NARRATION, config } = await import(pathToFileURL(path.join(here, 'promo.scenario.mjs')).href);
const audioDir = path.join(workDir, 'audio');
fs.mkdirSync(audioDir, { recursive: true });

const files = fs.readdirSync(voiceDir);
const missing = [];
let total = 0;
NARRATION.forEach((text, i) => {
  const no = String(i + 1).padStart(2, '0');
  const src = files.find((f) => new RegExp(`^${no}([_ .].*)?\\.(mp3|wav|m4a|aiff?)$`, "i").test(f));
  if (!src) return missing.push(no);
  const key = crypto.createHash('md5').update(`${config.voice}|${config.rate ?? ''}|${text}`).digest('hex').slice(0, 12);
  const dst = path.join(audioDir, key + '.aiff');
  execFileSync('afconvert', ['-f', 'AIFF', '-d', 'BEI16@44100', '-c', '1', path.join(voiceDir, src), dst]);
  const dur = Number(/estimated duration: ([\d.]+)/.exec(execFileSync('afinfo', [dst]).toString())[1]);
  total += dur;
  console.log(`${no}  ${dur.toFixed(1)}초  ${text.slice(0, 30)}…`);
});
console.log(`음성 합계 ${total.toFixed(1)}초 (화면 동작 · 쉼 포함 영상은 이보다 약 15~25초 길다)`);
if (missing.length) {
  console.error(`없는 파일: ${missing.join(', ')} — 이 문장들은 녹화 때 macOS 기본 음성으로 만들어진다`);
  process.exit(1);
}
