/* Garante que o número da versão esteja consistente em todo o repositório. */
const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');

const version = JSON.parse(read('package.json')).version;
const checks = [
  ['sw.js (nome do cache)', read('sw.js').includes(`trademap-v${version}`)],
  ['README.md (versão atual)', read('README.md').includes(`**v${version}**`)],
  ['CHANGELOG.md (release)', read('CHANGELOG.md').includes(`[v${version}]`)]
];

let failed = false;
for (const [name, ok] of checks) {
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${name}: v${version}`);
  if (!ok) failed = true;
}
process.exit(failed ? 1 : 0);
