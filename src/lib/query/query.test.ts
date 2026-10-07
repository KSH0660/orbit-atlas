import { beforeAll, describe, expect, it } from 'vitest';
import snapshot from '@data/catalog-snapshot.json';
import { type Catalog, decodeCatalog } from '../catalog/catalog';
import type { CatalogPayload } from '../data/types';
import { scopeInsights } from './insights';
import { countMask, isEmptyLens, lensEquals, lensLabel, lensMask, normalizeLens, PRESETS } from './lens';
import { SearchIndex } from './search';
import { aggregate, ALT_BIN_COUNT, allIndices, altToBin, binToAlt, densestBand, indicesFromMask, inclinationModes } from './stats';
import { parseViewState, serializeViewState } from './url';

let cat: Catalog;
beforeAll(() => {
  cat = decodeCatalog(snapshot as unknown as CatalogPayload);
});

describe('lens', () => {
  it('normalises and compares lenses', () => {
    expect(isEmptyLens({ missions: [] })).toBe(true);
    expect(lensEquals({ blocs: ['US', 'CN'] }, { blocs: ['CN', 'US'] })).toBe(true);
    expect(normalizeLens({ constellations: [], countries: ['KR'] })).toEqual({ countries: ['KR'] });
  });

  it('filters the real catalog sensibly', () => {
    const starlink = countMask(lensMask(cat, { constellations: ['starlink'] }));
    const all = cat.count;
    expect(starlink).toBeGreaterThan(5000);
    expect(starlink).toBeLessThan(all);
    // AND across fields, OR within a field
    const usLeo = countMask(lensMask(cat, { blocs: ['US'], regimes: ['LEO'] }));
    const us = countMask(lensMask(cat, { blocs: ['US'] }));
    expect(usLeo).toBeLessThanOrEqual(us);
    const usOrCn = countMask(lensMask(cat, { blocs: ['US', 'CN'] }));
    expect(usOrCn).toBeGreaterThan(us);
  });

  it('every preset matches at least one satellite', () => {
    for (const p of PRESETS) expect(countMask(lensMask(cat, p.lens)), p.id).toBeGreaterThan(0);
  });

  it('labels lenses for humans', () => {
    expect(lensLabel({ constellations: ['starlink'] })).toBe('Starlink');
    expect(lensLabel({ blocs: ['CN'], missions: ['military'] })).toBe('China · Military');
    expect(lensLabel({ altitude: [500, 600] })).toBe('500 km – 600 km');
  });
});

describe('url state', () => {
  it('round-trips lens, compare, selection and camera', () => {
    const v = {
      lens: { constellations: ['starlink'], operators: ['Spire, Inc.'] },
      only: true,
      compare: { blocs: ['CN' as const] },
      sat: 25544,
      follow: true,
      color: 'owner' as const,
      warp: 60,
      cam: { lat: 37.5, lon: 127, dist: 3.2 },
    };
    const s = serializeViewState(v);
    expect(s).toContain('cs=starlink');
    expect(s).toContain('vs.bloc=CN');
    const back = parseViewState(s);
    expect(back.lens).toEqual(normalizeLens(v.lens));
    expect(back.compare).toEqual({ blocs: ['CN'] });
    expect(back).toMatchObject({ only: true, sat: 25544, follow: true, color: 'owner', warp: 60 });
    expect(back.cam?.lat).toBeCloseTo(37.5);
  });

  it('ignores junk', () => {
    const v = parseViewState('?mission=bogus&warp=-3&cam=a,b,c&alt=9-1');
    expect(isEmptyLens(v.lens)).toBe(true);
    expect(v.warp).toBe(1);
    expect(v.cam).toBeUndefined();
  });
});

describe('search', () => {
  it('finds the ISS by nickname first', () => {
    const r = new SearchIndex(cat).search('ISS');
    expect(r[0].kind).toBe('satellite');
    expect(r[0].key).toBe('25544');
  });

  it('finds by NORAD number', () => {
    expect(new SearchIndex(cat).search('25544')[0].key).toBe('25544');
  });

  it('understands Korean aliases', () => {
    const r = new SearchIndex(cat).search('한국');
    expect(r[0]).toMatchObject({ kind: 'country', key: 'KR' });
    expect(new SearchIndex(cat).search('스타링크')[0].key).toBe('starlink');
  });
});

describe('stats & insights', () => {
  it('altitude bins are monotonic and invertible', () => {
    expect(altToBin(550)).toBeLessThan(altToBin(20200));
    expect(altToBin(1e9)).toBe(ALT_BIN_COUNT - 1);
    expect(altToBin(binToAlt(10) + 1)).toBe(10);
  });

  it('aggregates the whole catalog consistently', () => {
    const s = aggregate(cat, allIndices(cat));
    expect(s.total).toBe(cat.count);
    expect(s.mission.reduce((a, b) => a + b, 0)).toBe(cat.count);
    expect(s.bloc.reduce((a, b) => a + b, 0)).toBe(cat.count);
    expect(s.altHist.reduce((a, b) => a + b, 0)).toBe(cat.count);
    const band = densestBand(s)!;
    expect(band.lo).toBeGreaterThan(300);
    expect(band.hi).toBeLessThan(1000);
  });

  it('finds Starlink shells as distinct inclination modes', () => {
    const idx = indicesFromMask(lensMask(cat, { constellations: ['starlink'] }));
    const modes = inclinationModes(cat, idx, 3).map((m) => m.inc);
    expect(modes).toContain(53);
    // neighbours are merged: no two modes within 1°
    for (const a of modes) for (const b of modes) if (a !== b) expect(Math.abs(a - b)).toBeGreaterThan(1);
  });

  it('produces number-first insights with lens actions', () => {
    const s = aggregate(cat, allIndices(cat));
    const ins = scopeInsights(cat, s, 'in total');
    expect(ins.find((i) => i.id === 'leo-share')?.value).toMatch(/^\d+%$/);
    expect(ins.find((i) => i.id === 'top-constellation')?.lens).toEqual({ constellations: ['starlink'] });
    expect(ins.every((i) => i.label.length < 90)).toBe(true);
  });
});
