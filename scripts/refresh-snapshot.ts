/**
 * Rebuilds data/catalog-snapshot.json: the bundled fallback catalog and the
 * metadata index used to enrich live CelesTrak data at runtime.
 *
 *   npm run data:refresh                 # download everything
 *   npm run data:refresh -- --from DIR   # use previously downloaded files in DIR
 *
 * Sources
 *   CelesTrak GP (active, CSV/OMM)     orbital elements
 *   CelesTrak SATCAT (active)          owner code, launch date
 *   GCAT (J. McDowell, CC-BY 4.0)      operator org, mission category, class, mass
 */
import fs from 'node:fs';
import path from 'node:path';
import {
  fetchText,
  gpActiveUrl,
  parseGpCsv,
  parseSatcatCsv,
  satcatActiveUrl,
} from '../src/lib/data/celestrak';
import { buildPayload, newestEpochIso } from '../src/lib/data/catalog-builder';
import {
  CELESTRAK_OWNER_TO_COUNTRY,
  GCAT_OPERATOR_NAMES,
  gcatCategoryToMission,
  gcatClassToSector,
  gcatStateToCountry,
  matchNameRule,
} from '../src/lib/data/classify';
import type { SatelliteMeta } from '../src/lib/data/types';

const GCAT = 'https://planet4589.org/space/gcat/tsv';
const OUT = path.resolve(__dirname, '../data/catalog-snapshot.json');

const args = process.argv.slice(2);
const fromDir = args.includes('--from') ? args[args.indexOf('--from') + 1] : undefined;

async function load(url: string, localName: string): Promise<string> {
  if (fromDir) {
    const p = path.join(fromDir, localName);
    console.log(`  reading ${p}`);
    return fs.readFileSync(p, 'utf8');
  }
  console.log(`  fetching ${url}`);
  return fetchText(url, 120_000);
}

type Row = Record<string, string>;
function parseTsv(text: string): { rows: Row[]; updated: string } {
  const lines = text.split('\n');
  const header = lines[0].replace(/^#/, '').split('\t').map((h) => h.trim());
  let updated = '';
  const rows: Row[] = [];
  for (const line of lines.slice(1)) {
    if (line.startsWith('#')) {
      const m = /Updated\s+(.+)$/.exec(line);
      if (m) updated = m[1].trim();
      continue;
    }
    if (!line.trim()) continue;
    const cells = line.split('\t');
    rows.push(Object.fromEntries(header.map((h, i) => [h, (cells[i] ?? '').trim()])));
  }
  return { rows, updated };
}

const MONTHS: Record<string, string> = {
  Jan: '01', Feb: '02', Mar: '03', Apr: '04', May: '05', Jun: '06',
  Jul: '07', Aug: '08', Sep: '09', Oct: '10', Nov: '11', Dec: '12',
};
function gcatDate(s: string | undefined): string {
  const m = /^(\d{4})\s+([A-Z][a-z]{2})\s+(\d{1,2})/.exec(s ?? '');
  return m ? `${m[1]}-${MONTHS[m[2]]}-${m[3].padStart(2, '0')}` : '';
}

function gcatUpdatedIso(s: string): string {
  const d = gcatDate(s);
  return d ? `${d}T00:00:00Z` : new Date().toISOString();
}

async function main() {
  console.log('Orbit Atlas — refreshing snapshot');
  const [gpText, satcatText, gcatText, psatText, orgsText] = await Promise.all([
    load(gpActiveUrl(), 'gp_active.csv'),
    load(satcatActiveUrl(), 'satcat_active.csv'),
    load(`${GCAT}/cat/satcat.tsv`, 'gcat_satcat.tsv'),
    load(`${GCAT}/cat/psatcat.tsv`, 'psatcat.tsv'),
    load(`${GCAT}/tables/orgs.tsv`, 'orgs.tsv'),
  ]);

  const elements = parseGpCsv(gpText);
  const satcat = parseSatcatCsv(satcatText);
  const gcat = parseTsv(gcatText);
  const psat = parseTsv(psatText);
  const orgs = parseTsv(orgsText);

  const gcatByNorad = new Map<number, Row>();
  for (const r of gcat.rows) {
    const n = Number(r.Satcat);
    if (Number.isFinite(n) && n > 0) gcatByNorad.set(n, r);
  }
  const psatByJcat = new Map(psat.rows.map((r) => [r.JCAT, r]));
  const orgByCode = new Map(orgs.rows.map((r) => [r.Code, r]));

  const orgName = (code: string | undefined): string | undefined => {
    if (!code || code === '-') return undefined;
    if (GCAT_OPERATOR_NAMES[code]) return GCAT_OPERATOR_NAMES[code];
    const first = code.replace(/\?$/, '').split('/')[0];
    if (GCAT_OPERATOR_NAMES[first]) return GCAT_OPERATOR_NAMES[first];
    const o = orgByCode.get(first);
    if (!o) return undefined;
    const pick = [o.ShortEName, o.EName, o.ShortName, o.Name].find((v) => v && v !== '-');
    return pick;
  };

  let gcatHits = 0;
  const metaFor = (e: (typeof elements)[number]): SatelliteMeta => {
    const rule = matchNameRule(e.name);
    const g = gcatByNorad.get(e.id);
    const p = g ? psatByJcat.get(g.JCAT) : undefined;
    const sc = satcat.get(e.id);
    if (g) gcatHits++;
    const ruleWinsMission = Boolean(rule?.mission && (rule.constellation || rule.mission === 'human'));
    const unnamed = /^\d{4}-\d{3}[A-Z]+$/.test(e.name);
    return {
      operator:
        (rule?.constellation && rule.operator) ||
        orgName(g?.Owner) ||
        rule?.operator ||
        (unnamed ? 'Unidentified' : 'Unknown operator'),
      country:
        gcatStateToCountry(g?.State) ||
        (sc && CELESTRAK_OWNER_TO_COUNTRY[sc.owner]) ||
        rule?.country ||
        'XX',
      mission:
        (ruleWinsMission && rule?.mission) ||
        gcatCategoryToMission(p?.Category, p?.Class) ||
        rule?.mission ||
        'tech',
      sector: gcatClassToSector(p?.Class) || rule?.sector || 'unknown',
      constellation: rule?.constellation ?? '',
      launchDate: sc?.launchDate || gcatDate(g?.LDate) || '',
      massKg: Number(g?.Mass) || 0,
    };
  };

  const now = new Date().toISOString();
  const payload = buildPayload(elements, metaFor, {
    mode: 'snapshot',
    elementsFetchedAt: now,
    newestEpoch: newestEpochIso(elements),
    elementsProvider: 'CelesTrak GP (active)',
    metadataProvider: 'CelesTrak SATCAT · GCAT (J. McDowell, CC-BY 4.0)',
    metadataUpdatedAt: gcatUpdatedIso(gcat.updated),
  });

  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  const json = JSON.stringify(payload);
  fs.writeFileSync(OUT, json);

  const unknownCountry = payload.cols.cc.filter((i) => payload.dict.countries[i] === 'XX').length;
  console.log(`  ${payload.count} satellites, ${gcatHits} matched in GCAT, ${unknownCountry} unknown country`);
  console.log(`  ${payload.dict.operators.length} operators, ${payload.dict.constellations.length} constellations`);
  console.log(`  wrote ${OUT} (${(json.length / 1e6).toFixed(2)} MB)`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
