import type { CatalogPayload } from '../data/types';

/**
 * Catalog loading with three layers of fallback, so a CelesTrak outage or a
 * function failure never leaves the user with an empty globe:
 *   1. /api/catalog                (live CelesTrak, ISR-cached on the edge)
 *   2. IndexedDB copy of the last good payload in this browser
 *   3. /data/catalog-snapshot.json (static snapshot shipped with the build)
 */
export type LoadOrigin = 'api' | 'browser-cache' | 'static-snapshot';

const DB = 'orbit-atlas';
const STORE = 'catalog';
const KEY = 'latest';

function idb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function idbGet(): Promise<CatalogPayload | undefined> {
  try {
    const db = await idb();
    return await new Promise((resolve) => {
      const req = db.transaction(STORE).objectStore(STORE).get(KEY);
      req.onsuccess = () => resolve(req.result as CatalogPayload | undefined);
      req.onerror = () => resolve(undefined);
    });
  } catch {
    return undefined;
  }
}

async function idbPut(p: CatalogPayload) {
  try {
    const db = await idb();
    db.transaction(STORE, 'readwrite').objectStore(STORE).put(p, KEY);
  } catch {
    /* storage unavailable (private mode) — fine */
  }
}

function valid(p: unknown): p is CatalogPayload {
  const c = p as CatalogPayload;
  return Boolean(c && c.version === 1 && c.count > 0 && Array.isArray(c.cols?.id) && c.cols.id.length === c.count);
}

async function fetchJson(url: string, timeoutMs: number): Promise<unknown> {
  const res = await fetch(url, { signal: AbortSignal.timeout(timeoutMs) });
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  return res.json();
}

export async function loadCatalogPayload(): Promise<{ payload: CatalogPayload; origin: LoadOrigin; error?: string }> {
  let apiError: string | undefined;
  try {
    const p = await fetchJson('/api/catalog', 25_000);
    if (!valid(p)) throw new Error('invalid catalog payload');
    if (p.source.mode !== 'snapshot') void idbPut(p);
    return { payload: p, origin: 'api' };
  } catch (err) {
    apiError = (err as Error).message;
  }

  const [cached, snapshot] = await Promise.all([
    idbGet(),
    fetchJson('/data/catalog-snapshot.json', 25_000).catch(() => undefined),
  ]);
  const snap = valid(snapshot) ? snapshot : undefined;
  const cache = valid(cached) ? cached : undefined;
  if (cache && (!snap || cache.source.newestEpoch > snap.source.newestEpoch)) {
    return { payload: cache, origin: 'browser-cache', error: apiError };
  }
  if (snap) return { payload: snap, origin: 'static-snapshot', error: apiError };
  throw new Error(`Satellite catalog unavailable (${apiError ?? 'unknown error'})`);
}
