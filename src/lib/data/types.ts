import type { MissionId, SectorId } from './taxonomy';

/** One General Perturbations element set (OMM mean elements, SGP4-ready). */
export interface ElementSet {
  id: number; // NORAD catalog number (can exceed 99,999 — TLE cannot represent these)
  name: string;
  cospar: string; // international designator, e.g. 1998-067A
  epochMs: number;
  meanMotion: number; // rev/day
  eccentricity: number;
  inclination: number; // deg
  raan: number; // deg
  argPericenter: number; // deg
  meanAnomaly: number; // deg
  bstar: number;
  meanMotionDot: number;
  meanMotionDdot: number;
  elementSetNo: number;
  revAtEpoch: number;
}

/** Descriptive metadata merged from SATCAT, GCAT and name rules. */
export interface SatelliteMeta {
  operator: string;
  country: string; // ISO alpha-2, or EU / INT / XX
  mission: MissionId;
  sector: SectorId;
  constellation: string; // '' when not part of a known constellation
  launchDate: string; // YYYY-MM-DD or ''
  massKg: number; // 0 when unknown
}

export type CatalogMode = 'live' | 'warm-cache' | 'snapshot';

export interface CatalogSource {
  mode: CatalogMode;
  /** When the element sets were downloaded from the upstream provider. */
  elementsFetchedAt: string;
  /** Newest element-set epoch in the catalog. */
  newestEpoch: string;
  elementsProvider: string;
  metadataProvider: string;
  metadataUpdatedAt: string;
  note?: string;
}

/**
 * Wire format: columnar JSON with dictionaries. About 40% smaller than an array
 * of OMM objects and fast to decode into typed arrays.
 */
export interface CatalogPayload {
  version: 1;
  generatedAt: string;
  source: CatalogSource;
  count: number;
  dict: {
    operators: string[];
    countries: string[];
    constellations: string[];
  };
  cols: {
    id: number[];
    name: string[];
    cospar: string[];
    epoch: number[]; // unix seconds
    mm: number[];
    ecc: number[];
    inc: number[];
    raan: number[];
    argp: number[];
    ma: number[];
    bstar: number[];
    ndot: number[];
    nddot: number[];
    esn: number[];
    rev: number[];
    op: number[]; // → dict.operators
    cc: number[]; // → dict.countries
    cs: number[]; // → dict.constellations, -1 none
    mi: number[]; // MISSIONS index
    se: number[]; // SECTORS index
    ld: string[];
    ms: number[];
  };
}
