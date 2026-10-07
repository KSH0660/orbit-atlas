import type { SatcatRow } from './celestrak';
import {
  CELESTRAK_OWNER_TO_COUNTRY,
  matchNameRule,
} from './classify';
import { MISSIONS, MISSION_INDEX, SECTORS, SECTOR_INDEX } from './taxonomy';
import type { CatalogPayload, CatalogSource, ElementSet, SatelliteMeta } from './types';

const round = (v: number, digits: number) => {
  const f = 10 ** digits;
  return Math.round(v * f) / f;
};

/** Build the columnar wire payload. */
export function buildPayload(
  elements: ElementSet[],
  metaFor: (e: ElementSet) => SatelliteMeta,
  source: CatalogSource,
): CatalogPayload {
  const operators: string[] = [];
  const countries: string[] = [];
  const constellations: string[] = [];
  const opIdx = new Map<string, number>();
  const ccIdx = new Map<string, number>();
  const csIdx = new Map<string, number>();
  const intern = (map: Map<string, number>, list: string[], v: string) => {
    let i = map.get(v);
    if (i === undefined) {
      i = list.length;
      list.push(v);
      map.set(v, i);
    }
    return i;
  };

  const sorted = [...elements].sort((a, b) => a.id - b.id);
  const cols: CatalogPayload['cols'] = {
    id: [], name: [], cospar: [], epoch: [], mm: [], ecc: [], inc: [], raan: [], argp: [], ma: [],
    bstar: [], ndot: [], nddot: [], esn: [], rev: [], op: [], cc: [], cs: [], mi: [], se: [], ld: [], ms: [],
  };
  for (const e of sorted) {
    const m = metaFor(e);
    cols.id.push(e.id);
    cols.name.push(e.name);
    cols.cospar.push(e.cospar);
    cols.epoch.push(round(e.epochMs / 1000, 3));
    cols.mm.push(e.meanMotion);
    cols.ecc.push(e.eccentricity);
    cols.inc.push(e.inclination);
    cols.raan.push(e.raan);
    cols.argp.push(e.argPericenter);
    cols.ma.push(e.meanAnomaly);
    cols.bstar.push(e.bstar);
    cols.ndot.push(e.meanMotionDot);
    cols.nddot.push(e.meanMotionDdot);
    cols.esn.push(e.elementSetNo);
    cols.rev.push(e.revAtEpoch);
    cols.op.push(intern(opIdx, operators, m.operator));
    cols.cc.push(intern(ccIdx, countries, m.country));
    cols.cs.push(m.constellation ? intern(csIdx, constellations, m.constellation) : -1);
    cols.mi.push(MISSION_INDEX[m.mission] ?? MISSION_INDEX.tech);
    cols.se.push(SECTOR_INDEX[m.sector] ?? SECTOR_INDEX.unknown);
    cols.ld.push(m.launchDate);
    cols.ms.push(Math.round(m.massKg));
  }

  return {
    version: 1,
    generatedAt: new Date().toISOString(),
    source,
    count: sorted.length,
    dict: { operators, countries, constellations },
    cols,
  };
}

/** Recover NORAD → metadata from an existing payload (used to enrich live data). */
export function metaIndexFromPayload(p: CatalogPayload): Map<number, SatelliteMeta> {
  const out = new Map<number, SatelliteMeta>();
  const c = p.cols;
  for (let i = 0; i < p.count; i++) {
    out.set(c.id[i], {
      operator: p.dict.operators[c.op[i]],
      country: p.dict.countries[c.cc[i]],
      constellation: c.cs[i] >= 0 ? p.dict.constellations[c.cs[i]] : '',
      mission: MISSIONS[c.mi[i]]?.id ?? 'tech',
      sector: SECTORS[c.se[i]]?.id ?? 'unknown',
      launchDate: c.ld[i],
      massKg: c.ms[i],
    });
  }
  return out;
}

/** Recover element sets from a payload (used for the snapshot fallback). */
export function elementsFromPayload(p: CatalogPayload): ElementSet[] {
  const c = p.cols;
  const out: ElementSet[] = new Array(p.count);
  for (let i = 0; i < p.count; i++) {
    out[i] = {
      id: c.id[i], name: c.name[i], cospar: c.cospar[i], epochMs: c.epoch[i] * 1000,
      meanMotion: c.mm[i], eccentricity: c.ecc[i], inclination: c.inc[i], raan: c.raan[i],
      argPericenter: c.argp[i], meanAnomaly: c.ma[i], bstar: c.bstar[i], meanMotionDot: c.ndot[i],
      meanMotionDdot: c.nddot[i], elementSetNo: c.esn[i], revAtEpoch: c.rev[i],
    };
  }
  return out;
}

/** Launch date from the COSPAR designator when nothing better exists (year only). */
export function launchYearFromCospar(cospar: string): string {
  const m = /^(\d{4})-/.exec(cospar);
  return m ? `${m[1]}` : '';
}

/**
 * Metadata for satellites the snapshot has never seen (launched after the last
 * refresh). Uses the live SATCAT row when available plus name rules.
 */
export function inferMeta(e: ElementSet, satcat?: SatcatRow): SatelliteMeta {
  const rule = matchNameRule(e.name);
  const country =
    (satcat && CELESTRAK_OWNER_TO_COUNTRY[satcat.owner]) || rule?.country || 'XX';
  const unnamed = /^\d{4}-\d{3}[A-Z]+$/.test(e.name);
  return {
    operator: rule?.operator ?? (unnamed ? 'Unidentified' : 'Unknown operator'),
    country,
    mission: rule?.mission ?? 'tech',
    sector: rule?.sector ?? 'unknown',
    constellation: rule?.constellation ?? '',
    launchDate: satcat?.launchDate || launchYearFromCospar(e.cospar),
    massKg: 0,
  };
}

/** Prefer snapshot metadata, but let name rules keep constellation tags fresh. */
export function resolveMeta(
  e: ElementSet,
  snapshotMeta: Map<number, SatelliteMeta>,
  satcat?: Map<number, SatcatRow>,
): SatelliteMeta {
  const known = snapshotMeta.get(e.id);
  if (known) return known;
  return inferMeta(e, satcat?.get(e.id));
}

/** Newest element-set epoch, ignoring the handful of sets dated in the future. */
export function newestEpochIso(elements: ElementSet[], now = Date.now()): string {
  let max = 0;
  const limit = now + 6 * 3600_000;
  for (const e of elements) if (e.epochMs > max && e.epochMs <= limit) max = e.epochMs;
  return new Date(max || now).toISOString();
}
