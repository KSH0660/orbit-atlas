// Copies the bundled snapshot to /public so the browser has a static fallback
// even if the /api/catalog function is unreachable.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const src = path.join(root, 'data/catalog-snapshot.json');
const dest = path.join(root, 'public/data/catalog-snapshot.json');

if (!fs.existsSync(src)) {
  console.warn('[copy-snapshot] data/catalog-snapshot.json missing — run `npm run data:refresh`.');
  process.exit(0);
}
fs.mkdirSync(path.dirname(dest), { recursive: true });
fs.copyFileSync(src, dest);
console.log('[copy-snapshot] public/data/catalog-snapshot.json ready');
