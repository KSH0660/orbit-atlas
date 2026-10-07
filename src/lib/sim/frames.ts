import { SCENE_UNIT_KM } from '../data/orbit';

/**
 * Coordinate frames.
 *
 * Scene frame = TEME/ECI with Y up:  scene(x, y, z) = (eci.x, eci.z, -eci.y) / 6371 km.
 * The Earth mesh lives in an Earth-fixed group rotated by GMST about +Y, so
 * orbits stay fixed in inertial space and the planet turns beneath them.
 * Earth-fixed (ECEF) maps the same way: lon 0 → +X, lon 90°E → −Z, north → +Y.
 */

export function julianDate(ms: number): number {
  return ms / 86400000 + 2440587.5;
}

/** Greenwich mean sidereal time in radians (IAU 1982, same as SGP4's gstime). */
export function gmst(ms: number): number {
  const tut1 = (julianDate(ms) - 2451545.0) / 36525.0;
  let temp =
    -6.2e-6 * tut1 * tut1 * tut1 +
    0.093104 * tut1 * tut1 +
    (876600.0 * 3600 + 8640184.812866) * tut1 +
    67310.54841;
  temp = ((temp * (Math.PI / 180)) / 240.0) % (2 * Math.PI);
  if (temp < 0) temp += 2 * Math.PI;
  return temp;
}

/** Unit vector toward the Sun in the scene (inertial) frame. Low-precision almanac, ~0.01°. */
export function sunDirection(ms: number, out: [number, number, number] = [0, 0, 0]): [number, number, number] {
  const n = julianDate(ms) - 2451545.0;
  const L = ((280.46 + 0.9856474 * n) % 360) * (Math.PI / 180);
  const g = ((357.528 + 0.9856003 * n) % 360) * (Math.PI / 180);
  const lambda = L + (1.915 * Math.sin(g) + 0.02 * Math.sin(2 * g)) * (Math.PI / 180);
  const eps = (23.439 - 0.0000004 * n) * (Math.PI / 180);
  const x = Math.cos(lambda);
  const y = Math.cos(eps) * Math.sin(lambda);
  const z = Math.sin(eps) * Math.sin(lambda);
  out[0] = x;
  out[1] = z;
  out[2] = -y;
  return out;
}

export function eciKmToScene(x: number, y: number, z: number, out: [number, number, number] = [0, 0, 0]) {
  out[0] = x / SCENE_UNIT_KM;
  out[1] = z / SCENE_UNIT_KM;
  out[2] = -y / SCENE_UNIT_KM;
  return out;
}

/** Earth-fixed geodetic (spherical approximation) → Earth-fixed scene direction. */
export function latLonToEarthFixed(latDeg: number, lonDeg: number, r = 1): [number, number, number] {
  const lat = (latDeg * Math.PI) / 180;
  const lon = (lonDeg * Math.PI) / 180;
  return [r * Math.cos(lat) * Math.cos(lon), r * Math.sin(lat), -r * Math.cos(lat) * Math.sin(lon)];
}

/** Earth-fixed lat/lon → inertial scene position at time `ms`. */
export function latLonToScene(latDeg: number, lonDeg: number, r: number, ms: number): [number, number, number] {
  const [x, y, z] = latLonToEarthFixed(latDeg, lonDeg, r);
  const g = gmst(ms);
  // rotate about +Y by g (same rotation the Earth group uses)
  const c = Math.cos(g);
  const s = Math.sin(g);
  return [x * c + z * s, y, -x * s + z * c];
}

/** Inertial scene position → Earth-fixed lat/lon (spherical) at time `ms`. */
export function sceneToLatLon(x: number, y: number, z: number, ms: number): { lat: number; lon: number; r: number } {
  const g = -gmst(ms);
  const c = Math.cos(g);
  const s = Math.sin(g);
  const ex = x * c + z * s;
  const ez = -x * s + z * c;
  const r = Math.hypot(ex, y, ez);
  const lat = (Math.asin(y / r) * 180) / Math.PI;
  let lon = (Math.atan2(-ez, ex) * 180) / Math.PI;
  if (lon > 180) lon -= 360;
  return { lat, lon, r };
}
