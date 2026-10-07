import type { Catalog } from '../catalog/catalog';
import { BLOCS, BLOC_INDEX, CONSTELLATIONS, countryName, REGIME_INDEX } from '../data/taxonomy';
import type { Lens } from './lens';
import { densestBand, inclinationModes, type Stats, topEntries } from './stats';

/**
 * The intelligence layer: a few facts, each a number plus a short label,
 * computed from what is in scope right now. No prose generation — if a fact is
 * not interesting (tiny share, empty scope) it is simply not emitted.
 */
export interface Insight {
  id: string;
  value: string;
  label: string;
  /** Clicking the insight applies this lens. */
  lens?: Lens;
}

const pct = (part: number, whole: number) => (whole ? Math.round((part / whole) * 100) : 0);
export const fmtInt = (v: number) => Math.round(v).toLocaleString('en-US');
export const fmtKm = (v: number) => `${fmtInt(v)} km`;

function roundAlt(km: number): number {
  if (km < 1000) return Math.round(km / 10) * 10;
  if (km < 10000) return Math.round(km / 100) * 100;
  return Math.round(km / 500) * 500;
}

export function scopeInsights(cat: Catalog, s: Stats, scopeLabel: 'in view' | 'in total'): Insight[] {
  const out: Insight[] = [];
  if (s.total < 3) return out;

  const leo = s.regime[REGIME_INDEX.LEO];
  if (leo) {
    out.push({
      id: 'leo-share',
      value: `${pct(leo, s.total)}%`,
      label: `of satellites ${scopeLabel} fly in low Earth orbit (< 2,000 km)`,
      lens: { regimes: ['LEO'] },
    });
  }

  const [topC] = topEntries(s.constellation, 1);
  if (topC && pct(topC[1], s.total) >= 5) {
    const id = cat.constellations[topC[0]];
    out.push({
      id: 'top-constellation',
      value: `${pct(topC[1], s.total)}%`,
      label: `belong to ${CONSTELLATIONS[id]?.label ?? id} (${fmtInt(topC[1])})`,
      lens: { constellations: [id] },
    });
  }

  const band = densestBand(s);
  if (band && band.count >= 10) {
    const lo = roundAlt(band.lo);
    const hi = roundAlt(band.hi);
    out.push({
      id: 'densest-band',
      value: `${fmtInt(lo)}–${fmtKm(hi)}`,
      label: `most congested altitude band: ${fmtInt(band.count)} satellites`,
      lens: { altitude: [Math.floor(band.lo), Math.ceil(band.hi)] },
    });
  }

  if (s.launchedLast12Months >= 10) {
    out.push({
      id: 'new',
      value: `${pct(s.launchedLast12Months, s.total)}%`,
      label: `launched in the last 12 months (${fmtInt(s.launchedLast12Months)})`,
      lens: { launchedWithinDays: 365 },
    });
  }

  const kr = s.bloc[BLOC_INDEX.KR];
  if (kr > 0) {
    out.push({
      id: 'korea',
      value: fmtInt(kr),
      label: `South Korean satellites ${scopeLabel}`,
      lens: { countries: ['KR'] },
    });
  }

  const geo = s.regime[REGIME_INDEX.GEO];
  if (geo >= 5) {
    out.push({
      id: 'geo',
      value: fmtInt(geo),
      label: `geostationary satellites ${scopeLabel === 'in view' ? 'visible on the GEO belt' : 'parked on the GEO belt'}`,
      lens: { regimes: ['GEO'] },
    });
  }
  return out;
}

export function lensInsights(cat: Catalog, lensStats: Stats, all: Stats, idx: ArrayLike<number>, lens: Lens): Insight[] {
  const out: Insight[] = [];
  const n = lensStats.total;
  if (!n) return out;

  out.push({
    id: 'share',
    value: `${pct(n, all.total) || '<1'}%`,
    label: `of all ${fmtInt(all.total)} active satellites`,
  });

  if (n >= 3) {
    out.push({
      id: 'median-alt',
      value: fmtKm(roundAlt(lensStats.medianAltKm)),
      label: 'median altitude',
    });
  }

  if (n >= 20) {
    const modes = inclinationModes(cat, idx, 3).filter((m) => m.count / n >= 0.04);
    if (modes.length) {
      out.push({
        id: 'shells',
        value: modes.map((m) => `${m.inc}°`).join(' · '),
        label: `main orbital inclinations (${modes.map((m) => fmtInt(m.count)).join(' · ')})`,
      });
    }
  }

  if (lensStats.launchedLast12Months > 0 && !lens.launchedWithinDays) {
    out.push({
      id: 'growth',
      value: `+${fmtInt(lensStats.launchedLast12Months)}`,
      label: `launched in the last 12 months (${pct(lensStats.launchedLast12Months, n)}%)`,
      lens: { ...lens, launchedWithinDays: 365 },
    });
  }

  if (!lens.operators?.length && !lens.constellations?.length) {
    const [top] = topEntries(lensStats.operator, 1);
    if (top && n >= 5) {
      out.push({
        id: 'top-operator',
        value: `${pct(top[1], n)}%`,
        label: `operated by ${cat.operators[top[0]]}`,
        lens: { ...lens, operators: [cat.operators[top[0]]] },
      });
    }
  }

  if (!lens.countries?.length && !lens.blocs?.length && n >= 5) {
    const [top] = topEntries(lensStats.country, 1);
    if (top && pct(top[1], n) < 100) {
      out.push({
        id: 'top-country',
        value: `${pct(top[1], n)}%`,
        label: `registered to ${countryName(cat.countries[top[0]])}`,
        lens: { ...lens, countries: [cat.countries[top[0]]] },
      });
    }
  }
  return out;
}

export function blocLabel(i: number): string {
  return BLOCS[i].label;
}
