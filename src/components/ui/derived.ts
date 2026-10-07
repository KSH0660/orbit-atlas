'use client';

import { useMemo } from 'react';
import type { Catalog } from '@/lib/catalog/catalog';
import { aggregate, allIndices, indicesFromMask, type Stats } from '@/lib/query/stats';
import { useAtlas } from '@/store/atlas';

export function intersect(idx: ArrayLike<number>, mask: Uint8Array): Uint32Array {
  const out = new Uint32Array(idx.length);
  let k = 0;
  for (let j = 0; j < idx.length; j++) if (mask[idx[j]]) out[k++] = idx[j];
  return out.slice(0, k);
}

const allStatsCache = new WeakMap<Catalog, { idx: Uint32Array; stats: Stats }>();
export function allScope(cat: Catalog) {
  let v = allStatsCache.get(cat);
  if (!v) {
    const idx = allIndices(cat);
    v = { idx, stats: aggregate(cat, idx) };
    allStatsCache.set(cat, v);
  }
  return v;
}

/** Indices + stats for "in view" or "all", optionally restricted to a mask. */
export function useScopeStats(scope: 'view' | 'all', mask?: Uint8Array) {
  const catalog = useAtlas((s) => s.catalog);
  const inView = useAtlas((s) => s.inView);
  return useMemo(() => {
    if (!catalog) return undefined;
    const base = scope === 'view' && inView ? inView : allScope(catalog).idx;
    const idx = mask ? intersect(base, mask) : base;
    return { idx, stats: aggregate(catalog, idx) };
  }, [catalog, inView, scope, mask]);
}

export function useMaskIndices(mask?: Uint8Array) {
  return useMemo(() => (mask ? indicesFromMask(mask) : undefined), [mask]);
}
