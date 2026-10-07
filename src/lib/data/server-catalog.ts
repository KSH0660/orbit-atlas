import 'server-only';
import snapshotJson from '@data/catalog-snapshot.json';
import {
  buildPayload,
  metaIndexFromPayload,
  newestEpochIso,
  resolveMeta,
} from './catalog-builder';
import { fetchActiveElements, fetchActiveSatcat, gpActiveUrl, UpstreamError } from './celestrak';
import type { CatalogPayload } from './types';

const snapshot = snapshotJson as unknown as CatalogPayload;
let snapshotMeta: ReturnType<typeof metaIndexFromPayload> | undefined;

/** Last good live payload held by this (warm) server instance. */
let warm: { payload: CatalogPayload; at: number } | undefined;

const cacheSeconds = () => {
  const raw = process.env.CATALOG_CACHE_SECONDS;
  const v = raw === undefined || raw === '' ? Number.NaN : Number(raw);
  return Number.isFinite(v) && v >= 0 ? v : 7200;
};
const isBuildPhase = () => process.env.NEXT_PHASE === 'phase-production-build';
const isOffline = () => process.env.ORBIT_ATLAS_OFFLINE === '1';

export function getSnapshot(note?: string): CatalogPayload {
  return note ? { ...snapshot, source: { ...snapshot.source, note } } : snapshot;
}

async function loadLive(): Promise<CatalogPayload> {
  const [elements, satcat] = await Promise.all([
    fetchActiveElements(),
    // SATCAT only fills gaps for brand-new satellites, so it is optional.
    fetchActiveSatcat().catch(() => undefined),
  ]);
  snapshotMeta ??= metaIndexFromPayload(snapshot);
  const meta = snapshotMeta;
  return buildPayload(elements, (e) => resolveMeta(e, meta, satcat), {
    mode: 'live',
    elementsFetchedAt: new Date().toISOString(),
    newestEpoch: newestEpochIso(elements),
    elementsProvider: 'CelesTrak GP (active)',
    metadataProvider: snapshot.source.metadataProvider,
    metadataUpdatedAt: snapshot.source.metadataUpdatedAt,
  });
}

/**
 * Live → warm instance cache → bundled snapshot.
 *
 * During a background ISR revalidation on the server we *throw* instead of
 * downgrading to the snapshot: Next.js then keeps serving the last successful
 * (usually live) response and retries on the next request.
 */
export async function getCatalog(): Promise<CatalogPayload> {
  if (isOffline()) return getSnapshot('Offline mode: serving bundled snapshot.');

  if (warm && Date.now() - warm.at < cacheSeconds() * 1000) return warm.payload;

  try {
    const payload = await loadLive();
    warm = { payload, at: Date.now() };
    return payload;
  } catch (err) {
    const reason = err instanceof UpstreamError ? `${err.kind}: ${err.message}` : String(err);
    console.warn(`[orbit-atlas] live catalog unavailable (${gpActiveUrl()}): ${reason}`);
    if (warm) {
      return {
        ...warm.payload,
        source: { ...warm.payload.source, mode: 'warm-cache', note: 'Upstream unavailable; serving last good copy.' },
      };
    }
    if (isBuildPhase() || process.env.NODE_ENV !== 'production') {
      return getSnapshot('Live source unavailable at build time; serving bundled snapshot.');
    }
    throw err;
  }
}
