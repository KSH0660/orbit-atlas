import { gstime } from './sgp4-lib';
import { describe, expect, it } from 'vitest';
import { gmst, latLonToScene, sceneToLatLon, sunDirection } from './frames';

describe('frames', () => {
  it('GMST matches satellite.js', () => {
    const t = Date.UTC(2026, 9, 7, 12, 0, 0);
    expect(gmst(t)).toBeCloseTo(gstime(new Date(t)), 6);
  });

  it('lat/lon ↔ scene round-trips through Earth rotation', () => {
    const t = Date.UTC(2026, 9, 7, 3, 21, 0);
    for (const [lat, lon] of [
      [37.5, 127],
      [-33.9, 18.4],
      [0, -179],
      [64, -21],
    ]) {
      const [x, y, z] = latLonToScene(lat, lon, 2, t);
      const back = sceneToLatLon(x, y, z, t);
      expect(back.lat).toBeCloseTo(lat, 6);
      expect(back.lon).toBeCloseTo(lon, 6);
      expect(back.r).toBeCloseTo(2, 6);
    }
  });

  it('puts the Sun over the northern tropics in June and southern in December', () => {
    const june = sunDirection(Date.UTC(2026, 5, 21, 12));
    const dec = sunDirection(Date.UTC(2026, 11, 21, 12));
    // scene Y is north; sin(23.4°) ≈ 0.40
    expect(june[1]).toBeCloseTo(0.4, 1);
    expect(dec[1]).toBeCloseTo(-0.4, 1);
    // Local noon at Greenwich: the Sun is near longitude 0
    const noon = sunDirection(Date.UTC(2026, 2, 20, 12, 7));
    const ll = sceneToLatLon(noon[0], noon[1], noon[2], Date.UTC(2026, 2, 20, 12, 7));
    expect(Math.abs(ll.lon)).toBeLessThan(3);
  });
});
