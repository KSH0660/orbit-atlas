import { deriveOrbit } from '../data/orbit';
import { BLOC_INDEX, countryBloc, REGIME_INDEX } from '../data/taxonomy';
import type { CatalogPayload, CatalogSource } from '../data/types';

/**
 * Client-side catalog: struct-of-arrays so filtering, stats and GPU uploads
 * touch contiguous memory. Index `i` is the row; `ids[i]` is the NORAD number.
 */
export interface Catalog {
  count: number;
  generatedAt: string;
  source: CatalogSource;

  ids: Int32Array;
  names: string[];
  cospar: string[];
  searchNames: string[];

  // mean elements (for SGP4)
  epochMs: Float64Array;
  meanMotion: Float64Array;
  eccentricity: Float64Array;
  inclination: Float64Array;
  raan: Float64Array;
  argPericenter: Float64Array;
  meanAnomaly: Float64Array;
  bstar: Float64Array;
  meanMotionDot: Float64Array;
  meanMotionDdot: Float64Array;
  elementSetNo: Int32Array;
  revAtEpoch: Int32Array;

  // metadata
  operator: Uint16Array;
  operators: string[];
  country: Uint16Array;
  countries: string[];
  bloc: Uint8Array;
  constellation: Int16Array;
  constellations: string[];
  mission: Uint8Array;
  sector: Uint8Array;
  launchDate: string[];
  launchMs: Float64Array; // NaN when unknown
  massKg: Float32Array;

  // derived
  regime: Uint8Array;
  perigeeKm: Float32Array;
  apogeeKm: Float32Array;
  meanAltKm: Float32Array;
  periodMin: Float32Array;

  idToIndex: Map<number, number>;
}

function launchToMs(s: string): number {
  if (!s) return Number.NaN;
  if (/^\d{4}$/.test(s)) return Date.UTC(Number(s), 6, 1); // year only → mid-year
  const t = Date.parse(`${s}T00:00:00Z`);
  return Number.isFinite(t) ? t : Number.NaN;
}

export function decodeCatalog(p: CatalogPayload): Catalog {
  const n = p.count;
  const c = p.cols;
  const f64 = (a: number[]) => Float64Array.from(a);
  const regime = new Uint8Array(n);
  const perigeeKm = new Float32Array(n);
  const apogeeKm = new Float32Array(n);
  const meanAltKm = new Float32Array(n);
  const periodMin = new Float32Array(n);
  const bloc = new Uint8Array(n);
  const launchMs = new Float64Array(n);
  const idToIndex = new Map<number, number>();
  const blocByCountry = p.dict.countries.map((code) => BLOC_INDEX[countryBloc(code)]);

  for (let i = 0; i < n; i++) {
    const d = deriveOrbit(c.mm[i], c.ecc[i]);
    regime[i] = REGIME_INDEX[d.regime];
    perigeeKm[i] = d.perigeeKm;
    apogeeKm[i] = d.apogeeKm;
    meanAltKm[i] = d.meanAltitudeKm;
    periodMin[i] = d.periodMin;
    bloc[i] = blocByCountry[c.cc[i]];
    launchMs[i] = launchToMs(c.ld[i]);
    idToIndex.set(c.id[i], i);
  }

  return {
    count: n,
    generatedAt: p.generatedAt,
    source: p.source,
    ids: Int32Array.from(c.id),
    names: c.name,
    cospar: c.cospar,
    searchNames: c.name.map((s) => s.toUpperCase()),
    epochMs: Float64Array.from(c.epoch, (s) => s * 1000),
    meanMotion: f64(c.mm),
    eccentricity: f64(c.ecc),
    inclination: f64(c.inc),
    raan: f64(c.raan),
    argPericenter: f64(c.argp),
    meanAnomaly: f64(c.ma),
    bstar: f64(c.bstar),
    meanMotionDot: f64(c.ndot),
    meanMotionDdot: f64(c.nddot),
    elementSetNo: Int32Array.from(c.esn),
    revAtEpoch: Int32Array.from(c.rev),
    operator: Uint16Array.from(c.op),
    operators: p.dict.operators,
    country: Uint16Array.from(c.cc),
    countries: p.dict.countries,
    bloc,
    constellation: Int16Array.from(c.cs),
    constellations: p.dict.constellations,
    mission: Uint8Array.from(c.mi),
    sector: Uint8Array.from(c.se),
    launchDate: c.ld,
    launchMs,
    massKg: Float32Array.from(c.ms),
    regime,
    perigeeKm,
    apogeeKm,
    meanAltKm,
    periodMin,
    idToIndex,
  };
}

/** OMM-shaped record for satellite.js `json2satrec`. */
export function ommFor(cat: Catalog, i: number) {
  return {
    OBJECT_NAME: cat.names[i],
    OBJECT_ID: cat.cospar[i],
    EPOCH: new Date(cat.epochMs[i]).toISOString(),
    MEAN_MOTION: cat.meanMotion[i],
    ECCENTRICITY: cat.eccentricity[i],
    INCLINATION: cat.inclination[i],
    RA_OF_ASC_NODE: cat.raan[i],
    ARG_OF_PERICENTER: cat.argPericenter[i],
    MEAN_ANOMALY: cat.meanAnomaly[i],
    EPHEMERIS_TYPE: 0 as const,
    CLASSIFICATION_TYPE: 'U' as const,
    NORAD_CAT_ID: cat.ids[i],
    ELEMENT_SET_NO: cat.elementSetNo[i],
    REV_AT_EPOCH: cat.revAtEpoch[i],
    BSTAR: cat.bstar[i],
    MEAN_MOTION_DOT: cat.meanMotionDot[i],
    MEAN_MOTION_DDOT: cat.meanMotionDdot[i],
  };
}
