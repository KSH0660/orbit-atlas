import { afterEach, describe, expect, it, vi } from 'vitest';

/** The fallback chain: live → warm instance cache → bundled snapshot. */
describe('getCatalog fallback', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it('serves the snapshot when CelesTrak rate-limits us (dev/build)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('Forbidden', { status: 403 })));
    const { getCatalog } = await import('./server-catalog');
    const p = await getCatalog();
    expect(p.source.mode).toBe('snapshot');
    expect(p.count).toBeGreaterThan(1000);
    expect(p.source.note).toMatch(/snapshot/i);
  });

  it('serves the snapshot on network failure', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('fetch failed'))));
    const { getCatalog } = await import('./server-catalog');
    expect((await getCatalog()).source.mode).toBe('snapshot');
  });

  it('throws during runtime revalidation so the last good ISR copy stays cached', async () => {
    vi.stubEnv('NODE_ENV', 'production');
    vi.stubGlobal('fetch', vi.fn(async () => new Response('Forbidden', { status: 403 })));
    const { getCatalog } = await import('./server-catalog');
    await expect(getCatalog()).rejects.toThrow(/rate limited/);
  });

  it('honours offline mode without touching the network', async () => {
    vi.stubEnv('ORBIT_ATLAS_OFFLINE', '1');
    const f = vi.fn();
    vi.stubGlobal('fetch', f);
    const { getCatalog } = await import('./server-catalog');
    expect((await getCatalog()).source.mode).toBe('snapshot');
    expect(f).not.toHaveBeenCalled();
  });

  it('uses live data and the warm cache when the upstream works, then survives an outage', async () => {
    const { getSnapshot } = await import('./server-catalog');
    const snap = getSnapshot();
    // Re-serialise a few snapshot rows as CelesTrak CSV.
    const c = snap.cols;
    const header =
      'OBJECT_NAME,OBJECT_ID,EPOCH,MEAN_MOTION,ECCENTRICITY,INCLINATION,RA_OF_ASC_NODE,ARG_OF_PERICENTER,MEAN_ANOMALY,EPHEMERIS_TYPE,CLASSIFICATION_TYPE,NORAD_CAT_ID,ELEMENT_SET_NO,REV_AT_EPOCH,BSTAR,MEAN_MOTION_DOT,MEAN_MOTION_DDOT';
    const rows: string[] = [];
    for (let i = 0; i < 1200; i++) {
      const epoch = new Date(c.epoch[i] * 1000).toISOString().replace('Z', '');
      rows.push(
        [`"${c.name[i]}"`, c.cospar[i], epoch, c.mm[i], c.ecc[i], c.inc[i], c.raan[i], c.argp[i], c.ma[i], 0, 'U', c.id[i], c.esn[i], c.rev[i], c.bstar[i], c.ndot[i], c.nddot[i]].join(','),
      );
    }
    const csv = `${header}\n${rows.join('\n')}\n`;
    vi.resetModules();
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => (String(url).includes('gp.php') ? new Response(csv) : new Response('nope', { status: 500 }))),
    );
    const mod = await import('./server-catalog');
    const live = await mod.getCatalog();
    expect(live.source.mode).toBe('live');
    expect(live.count).toBe(1200);
    // metadata comes from the snapshot index
    const i = live.cols.id.indexOf(c.id[0]);
    expect(live.dict.operators[live.cols.op[i]]).toBe(snap.dict.operators[c.op[0]]);

    // Upstream goes down: the warm copy is served.
    vi.stubEnv('CATALOG_CACHE_SECONDS', '0');
    vi.stubGlobal('fetch', vi.fn(async () => new Response('Forbidden', { status: 403 })));
    const again = await mod.getCatalog();
    expect(again.source.mode).toBe('warm-cache');
    expect(again.count).toBe(1200);
  });
});
