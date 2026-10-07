import type { Catalog } from '../catalog/catalog';
import { BLOCS, MISSIONS, REGIMES, SECTORS } from '../data/taxonomy';

/* Log-scaled altitude bins: 150 km … 45,000 km. Log spacing is what makes the
 * 550 km Starlink shells, the 20,200 km GNSS shell and the GEO spike visible
 * in one small chart. */
export const ALT_MIN_KM = 150;
export const ALT_MAX_KM = 45_000;
export const ALT_BIN_COUNT = 72;
const LOG_MIN = Math.log10(ALT_MIN_KM);
const LOG_SPAN = Math.log10(ALT_MAX_KM) - LOG_MIN;

export function altToBin(km: number): number {
  const t = (Math.log10(Math.max(km, ALT_MIN_KM)) - LOG_MIN) / LOG_SPAN;
  return Math.min(ALT_BIN_COUNT - 1, Math.max(0, Math.floor(t * ALT_BIN_COUNT)));
}
export function binToAlt(bin: number): number {
  return 10 ** (LOG_MIN + (bin / ALT_BIN_COUNT) * LOG_SPAN);
}
/** 0..1 position of an altitude on the histogram axis. */
export function altToUnit(km: number): number {
  return (Math.log10(Math.min(Math.max(km, ALT_MIN_KM), ALT_MAX_KM)) - LOG_MIN) / LOG_SPAN;
}
export function unitToAlt(u: number): number {
  return 10 ** (LOG_MIN + Math.min(1, Math.max(0, u)) * LOG_SPAN);
}

export interface Stats {
  total: number;
  mission: Uint32Array;
  bloc: Uint32Array;
  regime: Uint32Array;
  sector: Uint32Array;
  constellation: Map<number, number>;
  operator: Map<number, number>;
  country: Map<number, number>;
  altHist: Uint32Array;
  /** Per-bin dominant mission index (for tooltips). */
  launchedLast12Months: number;
  medianAltKm: number;
}

export function indicesFromMask(mask: Uint8Array): Uint32Array {
  let n = 0;
  for (let i = 0; i < mask.length; i++) n += mask[i] ? 1 : 0;
  const out = new Uint32Array(n);
  let k = 0;
  for (let i = 0; i < mask.length; i++) if (mask[i]) out[k++] = i;
  return out;
}

export function allIndices(cat: Catalog): Uint32Array {
  const out = new Uint32Array(cat.count);
  for (let i = 0; i < cat.count; i++) out[i] = i;
  return out;
}

const bump = (m: Map<number, number>, k: number) => m.set(k, (m.get(k) ?? 0) + 1);

export function aggregate(cat: Catalog, idx: ArrayLike<number>, now = Date.now()): Stats {
  const mission = new Uint32Array(MISSIONS.length);
  const bloc = new Uint32Array(BLOCS.length);
  const regime = new Uint32Array(REGIMES.length);
  const sector = new Uint32Array(SECTORS.length);
  const altHist = new Uint32Array(ALT_BIN_COUNT);
  const constellation = new Map<number, number>();
  const operator = new Map<number, number>();
  const country = new Map<number, number>();
  const yearAgo = now - 365 * 86400_000;
  let launched = 0;
  const alts = new Float32Array(idx.length);

  for (let k = 0; k < idx.length; k++) {
    const i = idx[k];
    mission[cat.mission[i]]++;
    bloc[cat.bloc[i]]++;
    regime[cat.regime[i]]++;
    sector[cat.sector[i]]++;
    altHist[altToBin(cat.meanAltKm[i])]++;
    if (cat.constellation[i] >= 0) bump(constellation, cat.constellation[i]);
    bump(operator, cat.operator[i]);
    bump(country, cat.country[i]);
    if (cat.launchMs[i] >= yearAgo) launched++;
    alts[k] = cat.meanAltKm[i];
  }
  alts.sort();
  return {
    total: idx.length,
    mission,
    bloc,
    regime,
    sector,
    constellation,
    operator,
    country,
    altHist,
    launchedLast12Months: launched,
    medianAltKm: alts.length ? alts[alts.length >> 1] : 0,
  };
}

export function topEntries(m: Map<number, number>, n: number): [number, number][] {
  return [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, n);
}

/** Satellites whose mean altitude is within ±band km of `altKm` (whole catalog). */
export function shellNeighbours(cat: Catalog, altKm: number, band = 25): number {
  let n = 0;
  for (let i = 0; i < cat.count; i++) if (Math.abs(cat.meanAltKm[i] - altKm) <= band) n++;
  return n;
}

/**
 * Congestion percentile of a satellite's shell: share of all satellites that
 * sit in a *less* crowded ±25 km shell than this one.
 */
export function shellPercentile(cat: Catalog, altKm: number, band = 25): { neighbours: number; percentile: number } {
  // Sorted altitudes + two-pointer sweep gives each satellite's shell count.
  const sorted = Float32Array.from(cat.meanAltKm).sort();
  const counts = new Uint32Array(sorted.length);
  let lo = 0;
  let hi = 0;
  for (let i = 0; i < sorted.length; i++) {
    while (sorted[lo] < sorted[i] - band) lo++;
    while (hi < sorted.length && sorted[hi] <= sorted[i] + band) hi++;
    counts[i] = hi - lo;
  }
  const neighbours = shellNeighbours(cat, altKm, band);
  let below = 0;
  for (let i = 0; i < counts.length; i++) if (counts[i] < neighbours) below++;
  return { neighbours, percentile: sorted.length ? below / sorted.length : 0 };
}

/**
 * Dominant inclinations — reveals constellation shells (Starlink 53° / 43° /
 * 97.6°, GNSS ~55°). Peaks are found on a 1° histogram and absorb their ±1°
 * neighbours so one shell is not reported three times.
 */
export function inclinationModes(cat: Catalog, idx: ArrayLike<number>, n = 3): { inc: number; count: number }[] {
  const hist = new Uint32Array(181);
  for (let k = 0; k < idx.length; k++) hist[Math.min(180, Math.max(0, Math.round(cat.inclination[idx[k]])))]++;
  const out: { inc: number; count: number }[] = [];
  const used = new Uint8Array(181);
  while (out.length < n) {
    let best = -1;
    for (let d = 0; d <= 180; d++) if (!used[d] && hist[d] > 0 && (best < 0 || hist[d] > hist[best])) best = d;
    if (best < 0) break;
    let count = 0;
    for (let d = Math.max(0, best - 1); d <= Math.min(180, best + 1); d++) {
      if (!used[d]) count += hist[d];
      used[d] = 1;
    }
    out.push({ inc: best, count });
  }
  return out;
}

/** The densest altitude band among the given satellites (in histogram bins, merged by 2). */
export function densestBand(stats: Stats): { lo: number; hi: number; count: number } | undefined {
  let best = -1;
  let bestCount = 0;
  for (let b = 0; b < ALT_BIN_COUNT - 1; b++) {
    const c = stats.altHist[b] + stats.altHist[b + 1];
    if (c > bestCount) {
      bestCount = c;
      best = b;
    }
  }
  if (best < 0) return undefined;
  return { lo: binToAlt(best), hi: binToAlt(best + 2), count: bestCount };
}
