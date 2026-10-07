import type { ElementSet } from './types';

/**
 * CelesTrak access. We use the GP endpoint in CSV form (OMM fields, ~2.5 MB for
 * the whole active catalog) rather than TLE, because NORAD numbers above 99,999
 * cannot be expressed in the TLE format.
 */

export const DEFAULT_CELESTRAK_BASE = 'https://celestrak.org';

export function celestrakBase(): string {
  return (process.env.CELESTRAK_BASE_URL || DEFAULT_CELESTRAK_BASE).replace(/\/$/, '');
}

export const gpActiveUrl = (base = celestrakBase()) =>
  `${base}/NORAD/elements/gp.php?GROUP=active&FORMAT=csv`;
export const satcatActiveUrl = (base = celestrakBase()) =>
  `${base}/satcat/records.php?GROUP=active&FORMAT=csv`;

export class UpstreamError extends Error {
  constructor(
    message: string,
    readonly kind: 'network' | 'http' | 'rate-limited' | 'invalid',
  ) {
    super(message);
    this.name = 'UpstreamError';
  }
}

function userAgent(): string {
  const contact = process.env.ORBIT_ATLAS_CONTACT || 'https://github.com/ksh0660/orbit-atlas';
  return `OrbitAtlas/0.1 (+${contact})`;
}

export async function fetchText(url: string, timeoutMs = 25_000): Promise<string> {
  let res: Response;
  try {
    res = await fetch(url, {
      headers: { 'User-Agent': userAgent(), Accept: 'text/csv,text/plain,*/*' },
      signal: AbortSignal.timeout(timeoutMs),
      cache: 'no-store',
    });
  } catch (err) {
    throw new UpstreamError(`network error for ${url}: ${(err as Error).message}`, 'network');
  }
  if (res.status === 403 || res.status === 429) {
    throw new UpstreamError(`rate limited by upstream (${res.status})`, 'rate-limited');
  }
  if (!res.ok) throw new UpstreamError(`HTTP ${res.status} for ${url}`, 'http');
  return res.text();
}

/** Minimal RFC-4180 CSV parser (handles quoted fields and embedded commas). */
export function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = '';
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i++;
        } else quoted = false;
      } else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ',') {
      row.push(field);
      field = '';
    } else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++;
      row.push(field);
      field = '';
      if (row.length > 1 || row[0] !== '') rows.push(row);
      row = [];
    } else field += c;
  }
  if (field !== '' || row.length) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

function csvObjects(text: string, requiredHeader: string): Record<string, string>[] {
  const trimmed = text.trimStart();
  if (!trimmed.startsWith(requiredHeader)) {
    // CelesTrak answers repeated downloads with a plain-text notice instead of data.
    const snippet = trimmed.slice(0, 120).replace(/\s+/g, ' ');
    const limited = /not updated|too many|exceeded|blocked/i.test(snippet);
    throw new UpstreamError(`unexpected response: "${snippet}"`, limited ? 'rate-limited' : 'invalid');
  }
  const [header, ...rows] = parseCsv(trimmed);
  return rows.map((r) => Object.fromEntries(header.map((h, i) => [h.trim(), (r[i] ?? '').trim()])));
}

/** Parse a CelesTrak UTC epoch like 2026-10-07T07:16:14.356416 (no zone suffix). */
export function parseEpoch(epoch: string): number {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(\.\d+)?/.exec(epoch);
  if (!m) return Number.NaN;
  const [, y, mo, d, h, mi, s, frac] = m;
  return Date.UTC(+y, +mo - 1, +d, +h, +mi, +s) + (frac ? Math.round(parseFloat(frac) * 1000) : 0);
}

export function parseGpCsv(text: string): ElementSet[] {
  const out: ElementSet[] = [];
  for (const r of csvObjects(text, 'OBJECT_NAME')) {
    const id = Number(r.NORAD_CAT_ID);
    const epochMs = parseEpoch(r.EPOCH);
    const meanMotion = Number(r.MEAN_MOTION);
    if (!Number.isFinite(id) || !Number.isFinite(epochMs) || !(meanMotion > 0)) continue;
    out.push({
      id,
      name: r.OBJECT_NAME,
      cospar: r.OBJECT_ID,
      epochMs,
      meanMotion,
      eccentricity: Number(r.ECCENTRICITY),
      inclination: Number(r.INCLINATION),
      raan: Number(r.RA_OF_ASC_NODE),
      argPericenter: Number(r.ARG_OF_PERICENTER),
      meanAnomaly: Number(r.MEAN_ANOMALY),
      bstar: Number(r.BSTAR),
      meanMotionDot: Number(r.MEAN_MOTION_DOT),
      meanMotionDdot: Number(r.MEAN_MOTION_DDOT),
      elementSetNo: Number(r.ELEMENT_SET_NO) || 999,
      revAtEpoch: Number(r.REV_AT_EPOCH) || 0,
    });
  }
  return out;
}

export interface SatcatRow {
  id: number;
  owner: string;
  launchDate: string;
  objectType: string;
}

export function parseSatcatCsv(text: string): Map<number, SatcatRow> {
  const out = new Map<number, SatcatRow>();
  for (const r of csvObjects(text, 'OBJECT_NAME')) {
    const id = Number(r.NORAD_CAT_ID);
    if (!Number.isFinite(id)) continue;
    out.set(id, { id, owner: r.OWNER, launchDate: r.LAUNCH_DATE, objectType: r.OBJECT_TYPE });
  }
  return out;
}

export async function fetchActiveElements(): Promise<ElementSet[]> {
  const elements = parseGpCsv(await fetchText(gpActiveUrl()));
  if (elements.length < 1000) {
    throw new UpstreamError(`suspiciously small catalog (${elements.length} rows)`, 'invalid');
  }
  return elements;
}

export async function fetchActiveSatcat(): Promise<Map<number, SatcatRow>> {
  return parseSatcatCsv(await fetchText(satcatActiveUrl()));
}
