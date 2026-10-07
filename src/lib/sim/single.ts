import { eciToGeodetic, gstime, json2satrec, type SatRec, sgp4 } from './sgp4-lib';
import { type Catalog, ommFor } from '../catalog/catalog';
import { SCENE_UNIT_KM } from '../data/orbit';
import { latLonToEarthFixed } from './frames';

/** Precise, per-frame state for one satellite (selection, follow, detail card). */
export interface SatState {
  /** Scene-frame position (Earth radii). */
  x: number;
  y: number;
  z: number;
  speedKmS: number;
  altitudeKm: number;
  lat: number;
  lon: number;
}

const satrecCache = new WeakMap<Catalog, Map<number, SatRec | null>>();

export function satrecFor(cat: Catalog, i: number): SatRec | null {
  let m = satrecCache.get(cat);
  if (!m) {
    m = new Map();
    satrecCache.set(cat, m);
  }
  if (!m.has(i)) {
    try {
      const s = json2satrec(ommFor(cat, i));
      m.set(i, s.error ? null : s);
    } catch {
      m.set(i, null);
    }
  }
  return m.get(i) ?? null;
}

function eciAt(s: SatRec, ms: number) {
  const tsince = (ms - (s.jdsatepoch - 2440587.5) * 86400000) / 60000;
  const pv = sgp4(s, tsince);
  if (!pv || !pv.position || typeof pv.position === 'boolean') return null;
  return pv as { position: { x: number; y: number; z: number }; velocity: { x: number; y: number; z: number } };
}

export function stateAt(s: SatRec, ms: number): SatState | null {
  const pv = eciAt(s, ms);
  if (!pv) return null;
  const { position: p, velocity: v } = pv;
  const geo = eciToGeodetic(p, gstime(new Date(ms)));
  return {
    x: p.x / SCENE_UNIT_KM,
    y: p.z / SCENE_UNIT_KM,
    z: -p.y / SCENE_UNIT_KM,
    speedKmS: Math.hypot(v.x, v.y, v.z),
    altitudeKm: geo.height,
    lat: (geo.latitude * 180) / Math.PI,
    lon: (geo.longitude * 180) / Math.PI,
  };
}

/** One full orbit in the inertial scene frame, starting half a period behind `ms`. */
export function orbitPath(s: SatRec, ms: number, periodMin: number, samples = 360): Float32Array {
  const out = new Float32Array((samples + 1) * 3);
  const span = periodMin * 60000;
  let last: [number, number, number] | null = null;
  for (let k = 0; k <= samples; k++) {
    const t = ms - span / 2 + (span * k) / samples;
    const pv = eciAt(s, t);
    const o = k * 3;
    if (pv) {
      last = [pv.position.x / SCENE_UNIT_KM, pv.position.z / SCENE_UNIT_KM, -pv.position.y / SCENE_UNIT_KM];
    }
    if (last) {
      out[o] = last[0];
      out[o + 1] = last[1];
      out[o + 2] = last[2];
    }
  }
  return out;
}

/**
 * Ground track (sub-satellite points) from `ms` forward, as Earth-fixed scene
 * coordinates slightly above the surface. Returns separate polyline segments
 * split where the track wraps around the antimeridian (none in 3D, but kept
 * for consumers that draw 2D maps).
 */
export function groundTrack(s: SatRec, ms: number, durationMin: number, samples = 240, radius = 1.003): Float32Array {
  const out = new Float32Array((samples + 1) * 3);
  for (let k = 0; k <= samples; k++) {
    const t = ms + (durationMin * 60000 * k) / samples;
    const pv = eciAt(s, t);
    if (!pv) continue;
    const geo = eciToGeodetic(pv.position, gstime(new Date(t)));
    const [x, y, z] = latLonToEarthFixed((geo.latitude * 180) / Math.PI, (geo.longitude * 180) / Math.PI, radius);
    out[k * 3] = x;
    out[k * 3 + 1] = y;
    out[k * 3 + 2] = z;
  }
  return out;
}
