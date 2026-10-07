import type { Catalog } from '../catalog/catalog';
import {
  BLOCS,
  BLOC_INDEX,
  type BlocId,
  CONSTELLATIONS,
  countryName,
  MISSIONS,
  MISSION_INDEX,
  type MissionId,
  REGIMES,
  REGIME_INDEX,
  type RegimeId,
  SECTOR_INDEX,
  type SectorId,
} from '../data/taxonomy';

/**
 * A Lens is the single query every entry point produces: explore presets, the
 * command bar, clicks on stat bars, satellite attributes and the altitude
 * histogram brush. Values within a field are OR-ed; fields are AND-ed.
 */
export interface Lens {
  constellations?: string[];
  countries?: string[];
  blocs?: BlocId[];
  operators?: string[];
  missions?: MissionId[];
  regimes?: RegimeId[];
  sectors?: SectorId[];
  /** Mean altitude band in km, inclusive. */
  altitude?: [number, number];
  /** Launched within this many days of "now". */
  launchedWithinDays?: number;
  ids?: number[];
}

export const EMPTY_LENS: Lens = {};

const LENS_KEYS = [
  'constellations',
  'countries',
  'blocs',
  'operators',
  'missions',
  'regimes',
  'sectors',
  'altitude',
  'launchedWithinDays',
  'ids',
] as const;

export function isEmptyLens(l: Lens | undefined): boolean {
  if (!l) return true;
  return LENS_KEYS.every((k) => {
    const v = l[k];
    return v === undefined || (Array.isArray(v) && v.length === 0);
  });
}

export function lensEquals(a: Lens | undefined, b: Lens | undefined): boolean {
  return JSON.stringify(normalizeLens(a)) === JSON.stringify(normalizeLens(b));
}

export function normalizeLens(l: Lens | undefined): Lens {
  const out: Lens = {};
  if (!l) return out;
  for (const k of LENS_KEYS) {
    const v = l[k];
    if (v === undefined) continue;
    if (Array.isArray(v)) {
      if (!v.length) continue;
      if (k === 'altitude') (out as Record<string, unknown>)[k] = v;
      else (out as Record<string, unknown>)[k] = [...new Set(v as unknown[])].sort();
    } else (out as Record<string, unknown>)[k] = v;
  }
  return out;
}

/** Compile a lens into a fast predicate over catalog rows. */
export function compileLens(cat: Catalog, lens: Lens, now = Date.now()): (i: number) => boolean {
  const tests: ((i: number) => boolean)[] = [];
  const idxSet = (values: string[] | undefined, dict: string[]) => {
    if (!values?.length) return undefined;
    const want = new Set(values);
    const ok = new Uint8Array(dict.length);
    dict.forEach((v, j) => (ok[j] = want.has(v) ? 1 : 0));
    return ok;
  };
  const cs = idxSet(lens.constellations, cat.constellations);
  if (cs) tests.push((i) => cat.constellation[i] >= 0 && cs[cat.constellation[i]] === 1);
  const cc = idxSet(lens.countries, cat.countries);
  if (cc) tests.push((i) => cc[cat.country[i]] === 1);
  const op = idxSet(lens.operators, cat.operators);
  if (op) tests.push((i) => op[cat.operator[i]] === 1);
  if (lens.blocs?.length) {
    const ok = new Set(lens.blocs.map((b) => BLOC_INDEX[b]));
    tests.push((i) => ok.has(cat.bloc[i]));
  }
  if (lens.missions?.length) {
    const ok = new Set(lens.missions.map((m) => MISSION_INDEX[m]));
    tests.push((i) => ok.has(cat.mission[i]));
  }
  if (lens.regimes?.length) {
    const ok = new Set(lens.regimes.map((r) => REGIME_INDEX[r]));
    tests.push((i) => ok.has(cat.regime[i]));
  }
  if (lens.sectors?.length) {
    const ok = new Set(lens.sectors.map((s) => SECTOR_INDEX[s]));
    tests.push((i) => ok.has(cat.sector[i]));
  }
  if (lens.altitude) {
    const [lo, hi] = lens.altitude;
    tests.push((i) => cat.meanAltKm[i] >= lo && cat.meanAltKm[i] <= hi);
  }
  if (lens.launchedWithinDays) {
    const since = now - lens.launchedWithinDays * 86400_000;
    tests.push((i) => cat.launchMs[i] >= since);
  }
  if (lens.ids?.length) {
    const ok = new Set(lens.ids);
    tests.push((i) => ok.has(cat.ids[i]));
  }
  if (!tests.length) return () => true;
  if (tests.length === 1) return tests[0];
  return (i) => {
    for (const t of tests) if (!t(i)) return false;
    return true;
  };
}

/** Membership mask: 1 where the row matches. */
export function lensMask(cat: Catalog, lens: Lens, now = Date.now()): Uint8Array {
  const mask = new Uint8Array(cat.count);
  const test = compileLens(cat, lens, now);
  for (let i = 0; i < cat.count; i++) mask[i] = test(i) ? 1 : 0;
  return mask;
}

export function countMask(mask: Uint8Array): number {
  let n = 0;
  for (let i = 0; i < mask.length; i++) n += mask[i];
  return n;
}

const fmtKm = (v: number) => `${Math.round(v).toLocaleString('en-US')} km`;

/** Human label: "Starlink", "China · Military", "500–600 km". */
export function lensLabel(lens: Lens | undefined): string {
  if (!lens || isEmptyLens(lens)) return 'All active satellites';
  const parts: string[] = [];
  const join = (xs: string[]) => (xs.length > 2 ? `${xs.slice(0, 2).join(', ')} +${xs.length - 2}` : xs.join(' + '));
  if (lens.ids?.length) parts.push(lens.ids.length === 1 ? `#${lens.ids[0]}` : `${lens.ids.length} satellites`);
  if (lens.constellations?.length)
    parts.push(join(lens.constellations.map((c) => CONSTELLATIONS[c]?.label ?? c)));
  if (lens.operators?.length) parts.push(join(lens.operators));
  if (lens.countries?.length) parts.push(join(lens.countries.map(countryName)));
  if (lens.blocs?.length) parts.push(join(lens.blocs.map((b) => BLOCS[BLOC_INDEX[b]].label)));
  if (lens.missions?.length) parts.push(join(lens.missions.map((m) => MISSIONS[MISSION_INDEX[m]].short)));
  if (lens.regimes?.length) parts.push(join(lens.regimes.map((r) => REGIMES[REGIME_INDEX[r]].id)));
  if (lens.sectors?.length) parts.push(join(lens.sectors.map((s) => s[0].toUpperCase() + s.slice(1))));
  if (lens.altitude) parts.push(`${fmtKm(lens.altitude[0])} – ${fmtKm(lens.altitude[1])}`);
  if (lens.launchedWithinDays)
    parts.push(lens.launchedWithinDays >= 365 ? 'Launched in last 12 months' : `Launched in last ${lens.launchedWithinDays} days`);
  return parts.join(' · ');
}

/** Merge b into a, replacing fields b sets (used when refining a lens). */
export function refineLens(a: Lens, b: Lens): Lens {
  return normalizeLens({ ...a, ...b });
}

/* ------------------------------------------------------------------------- */
/* Explore presets: phrased as the questions people actually ask.            */
/* ------------------------------------------------------------------------- */

export interface Preset {
  id: string;
  label: string;
  hint: string;
  lens: Lens;
  /** Suggested camera framing in Earth radii from Earth center. */
  distance?: number;
}

export const PRESETS: Preset[] = [
  { id: 'starlink', label: 'Starlink', hint: 'SpaceX broadband mega-constellation', lens: { constellations: ['starlink'] }, distance: 4.2 },
  { id: 'gnss', label: 'GPS & GNSS', hint: 'GPS, Galileo, BeiDou, GLONASS, QZSS, NavIC', lens: { missions: ['nav'] }, distance: 12 },
  { id: 'stations', label: 'Space stations', hint: 'ISS, Tiangong and crew vehicles', lens: { missions: ['human'] }, distance: 3.2 },
  { id: 'eo', label: 'Earth observation', hint: 'Imaging, radar and weather satellites', lens: { missions: ['eo'] }, distance: 4.2 },
  { id: 'military', label: 'Military', hint: 'Reconnaissance, early warning, military comms', lens: { missions: ['military'] }, distance: 9 },
  { id: 'korea', label: 'South Korea', hint: 'Satellites registered to the Republic of Korea', lens: { countries: ['KR'] }, distance: 9 },
  { id: 'china', label: 'China', hint: 'All Chinese-operated satellites', lens: { blocs: ['CN'] }, distance: 9 },
  { id: 'europe', label: 'Europe', hint: 'ESA, EU and European operators incl. UK', lens: { blocs: ['EU'] }, distance: 9 },
  { id: 'geo', label: 'GEO belt', hint: 'The geostationary ring at 35,786 km', lens: { regimes: ['GEO'] }, distance: 14 },
  { id: 'kuiper', label: 'Amazon Leo', hint: "Amazon's Project Kuiper broadband constellation", lens: { constellations: ['kuiper'] }, distance: 4.2 },
  { id: 'chinese-megaconstellations', label: 'Qianfan & Guowang', hint: "China's two broadband mega-constellations", lens: { constellations: ['qianfan', 'guowang'] }, distance: 4.4 },
  { id: 'new', label: 'Launched last 12 mo', hint: 'Satellites launched in the last 12 months', lens: { launchedWithinDays: 365 }, distance: 6 },
];

export function presetById(id: string): Preset | undefined {
  return PRESETS.find((p) => p.id === id);
}

export function presetForLens(lens: Lens): Preset | undefined {
  return PRESETS.find((p) => lensEquals(p.lens, lens));
}
