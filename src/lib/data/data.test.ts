import { describe, expect, it } from 'vitest';
import { buildPayload, inferMeta, metaIndexFromPayload, elementsFromPayload } from './catalog-builder';
import { parseCsv, parseEpoch, parseGpCsv, parseSatcatCsv, UpstreamError } from './celestrak';
import { gcatCategoryToMission, gcatStateToCountry, matchNameRule } from './classify';
import { deriveOrbit } from './orbit';
import { countryBloc, countryFlag } from './taxonomy';

const GP_SAMPLE = `OBJECT_NAME,OBJECT_ID,EPOCH,MEAN_MOTION,ECCENTRICITY,INCLINATION,RA_OF_ASC_NODE,ARG_OF_PERICENTER,MEAN_ANOMALY,EPHEMERIS_TYPE,CLASSIFICATION_TYPE,NORAD_CAT_ID,ELEMENT_SET_NO,REV_AT_EPOCH,BSTAR,MEAN_MOTION_DOT,MEAN_MOTION_DDOT
ISS (ZARYA),1998-067A,2026-10-07T07:16:14.356416,15.48757,.0006824,51.631,106.8391,231.9092,128.1281,0,U,25544,999,58908,.85983E-4,.00004251,0
"ODD, NAME",2026-001A,2026-10-07T00:00:00,15.0,.001,53,0,0,0,0,U,100951,999,1,0,0,0
`;

describe('CelesTrak parsing', () => {
  it('parses quoted CSV fields with embedded commas', () => {
    const rows = parseCsv('a,b\n"x, y",2\r\n');
    expect(rows).toEqual([
      ['a', 'b'],
      ['x, y', '2'],
    ]);
  });

  it('parses CelesTrak epochs (UTC, microseconds, no zone suffix)', () => {
    expect(parseEpoch('2026-10-07T07:16:14.356416')).toBe(Date.UTC(2026, 9, 7, 7, 16, 14, 356));
    expect(Number.isNaN(parseEpoch('garbage'))).toBe(true);
  });

  it('parses GP CSV into element sets, including 6-digit NORAD ids', () => {
    const els = parseGpCsv(GP_SAMPLE);
    expect(els).toHaveLength(2);
    expect(els[0]).toMatchObject({ id: 25544, name: 'ISS (ZARYA)', cospar: '1998-067A', meanMotion: 15.48757 });
    expect(els[1].id).toBe(100951);
    expect(els[1].name).toBe('ODD, NAME');
  });

  it('classifies CelesTrak throttling notices as rate limiting', () => {
    expect(() => parseGpCsv('GP data has not updated since your last successful download')).toThrowError(UpstreamError);
    try {
      parseGpCsv('GP data has not updated since your last successful download');
    } catch (e) {
      expect((e as UpstreamError).kind).toBe('rate-limited');
    }
  });

  it('parses SATCAT owner and launch date', () => {
    const m = parseSatcatCsv(
      'OBJECT_NAME,OBJECT_ID,NORAD_CAT_ID,OBJECT_TYPE,OPS_STATUS_CODE,OWNER,LAUNCH_DATE\nKOMPSAT-3A,2015-014A,40536,PAY,+,SKOR,2015-03-25\n',
    );
    expect(m.get(40536)).toMatchObject({ owner: 'SKOR', launchDate: '2015-03-25' });
  });
});

describe('classification', () => {
  it('assigns constellations and normalises operators', () => {
    expect(matchNameRule('STARLINK-1008')).toMatchObject({ constellation: 'starlink', operator: 'SpaceX' });
    expect(matchNameRule('ONEWEB-0115')?.constellation).toBe('oneweb');
    expect(matchNameRule('KUIPER-00008')?.constellation).toBe('kuiper');
  });

  it('prefers GLONASS over the generic COSMOS rule', () => {
    expect(matchNameRule('COSMOS 2433 [GLONASS-M]')?.constellation).toBe('glonass');
    expect(matchNameRule('COSMOS 2503')?.mission).toBe('military');
  });

  it('does not confuse Galileo with Indian GSAT comms satellites', () => {
    expect(matchNameRule('GSAT0201 (GALILEO 5)')?.constellation).toBe('galileo');
    expect(matchNameRule('GSAT-30')?.constellation).toBeUndefined();
  });

  it('maps GCAT categories with defense class to military, except navigation', () => {
    expect(gcatCategoryToMission('IMG', 'D')).toBe('military');
    expect(gcatCategoryToMission('NAV', 'D')).toBe('nav');
    expect(gcatCategoryToMission('COM', 'B')).toBe('comms');
    expect(gcatCategoryToMission('IMG-R', 'C')).toBe('eo');
    expect(gcatCategoryToMission('SS', 'C')).toBe('human');
    expect(gcatCategoryToMission('-', 'B')).toBeUndefined();
  });

  it('maps GCAT state codes to ISO / EU', () => {
    expect(gcatStateToCountry('UK')).toBe('GB');
    expect(gcatStateToCountry('J')).toBe('JP');
    expect(gcatStateToCountry('I-ESA')).toBe('EU');
    expect(gcatStateToCountry('I-ARAB')).toBe('INT');
    expect(gcatStateToCountry('KR')).toBe('KR');
  });

  it('places countries in the right owner bloc', () => {
    expect(countryBloc('GB')).toBe('EU');
    expect(countryBloc('KR')).toBe('KR');
    expect(countryBloc('HK')).toBe('CN');
    expect(countryBloc('ZZ')).toBe('OT');
    expect(countryFlag('KR')).toBe('🇰🇷');
  });

  it('infers metadata for satellites missing from the snapshot', () => {
    const [iss] = parseGpCsv(GP_SAMPLE);
    const m = inferMeta({ ...iss, name: 'STARLINK-99999', cospar: '2026-200A' }, undefined);
    expect(m).toMatchObject({ constellation: 'starlink', country: 'US', mission: 'comms', launchDate: '2026' });
  });
});

describe('orbit regimes', () => {
  it('derives altitude and regime from mean motion', () => {
    const iss = deriveOrbit(15.4876, 0.0006824);
    expect(iss.regime).toBe('LEO');
    expect(iss.meanAltitudeKm).toBeGreaterThan(380);
    expect(iss.meanAltitudeKm).toBeLessThan(450);
    expect(deriveOrbit(2.0056, 0.01).regime).toBe('MEO'); // GPS
    expect(deriveOrbit(1.0027, 0.0002).regime).toBe('GEO');
    expect(deriveOrbit(2.006, 0.72).regime).toBe('HEO'); // Molniya
    expect(deriveOrbit(1.0027, 0.0002).meanAltitudeKm).toBeCloseTo(35786, -2);
  });
});

describe('payload round trip', () => {
  it('encodes and decodes element sets and metadata', () => {
    const els = parseGpCsv(GP_SAMPLE);
    const p = buildPayload(els, (e) => inferMeta(e), {
      mode: 'live',
      elementsFetchedAt: '2026-10-07T00:00:00Z',
      newestEpoch: '2026-10-07T00:00:00Z',
      elementsProvider: 'test',
      metadataProvider: 'test',
      metadataUpdatedAt: '2026-10-01T00:00:00Z',
    });
    expect(p.count).toBe(2);
    const back = elementsFromPayload(p);
    expect(back[0].meanMotion).toBe(els[0].meanMotion);
    expect(Math.abs(back[0].epochMs - els[0].epochMs)).toBeLessThan(2);
    const meta = metaIndexFromPayload(p);
    expect(meta.get(25544)?.mission).toBe('human');
  });
});
