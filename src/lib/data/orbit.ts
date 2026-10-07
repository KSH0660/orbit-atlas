import type { RegimeId } from './taxonomy';

/** WGS-72 constants (what SGP4 uses). */
export const MU_KM3_S2 = 398600.8;
export const EARTH_RADIUS_KM = 6378.135;
/** Mean Earth radius used as the scene unit (1 scene unit = this many km). */
export const SCENE_UNIT_KM = 6371;

export const GEO_ALTITUDE_KM = 35786;
export const LEO_CEILING_KM = 2000;

export interface DerivedOrbit {
  semiMajorAxisKm: number;
  perigeeKm: number;
  apogeeKm: number;
  meanAltitudeKm: number;
  periodMin: number;
  regime: RegimeId;
}

/** Derive classical orbit quantities from mean motion (rev/day) and eccentricity. */
export function deriveOrbit(meanMotionRevPerDay: number, eccentricity: number): DerivedOrbit {
  const n = (meanMotionRevPerDay * 2 * Math.PI) / 86400; // rad/s
  const a = Math.cbrt(MU_KM3_S2 / (n * n));
  const perigeeKm = a * (1 - eccentricity) - EARTH_RADIUS_KM;
  const apogeeKm = a * (1 + eccentricity) - EARTH_RADIUS_KM;
  const meanAltitudeKm = a - EARTH_RADIUS_KM;
  const periodMin = 1440 / meanMotionRevPerDay;
  return {
    semiMajorAxisKm: a,
    perigeeKm,
    apogeeKm,
    meanAltitudeKm,
    periodMin,
    regime: classifyRegime(meanMotionRevPerDay, eccentricity, meanAltitudeKm),
  };
}

export function classifyRegime(
  meanMotionRevPerDay: number,
  eccentricity: number,
  meanAltitudeKm: number,
): RegimeId {
  if (eccentricity > 0.25) return 'HEO';
  if (meanAltitudeKm < LEO_CEILING_KM) return 'LEO';
  // Geosynchronous: ~1 rev per sidereal day, near-circular.
  if (meanMotionRevPerDay > 0.95 && meanMotionRevPerDay < 1.05 && eccentricity < 0.1) return 'GEO';
  if (meanAltitudeKm > GEO_ALTITUDE_KM + 1500) return 'HEO';
  return 'MEO';
}

/** Circular-orbit speed approximation via vis-viva at radius r (km/s). */
export function orbitalSpeedKmS(radiusKm: number, semiMajorAxisKm: number): number {
  return Math.sqrt(MU_KM3_S2 * (2 / radiusKm - 1 / semiMajorAxisKm));
}
