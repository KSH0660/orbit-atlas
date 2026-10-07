'use client';

import { isEmptyLens, type Lens, lensMask } from '@/lib/query/lens';
import { SCENE_UNIT_KM } from '@/lib/data/orbit';
import { useAtlas } from '@/store/atlas';

/** Camera distance that frames ~90% of a lens's satellites. */
export function frameDistanceFor(lens: Lens): number | undefined {
  const { catalog } = useAtlas.getState();
  if (!catalog || isEmptyLens(lens)) return undefined;
  const mask = lensMask(catalog, lens);
  const radii: number[] = [];
  for (let i = 0; i < catalog.count; i++) if (mask[i]) radii.push(1 + catalog.apogeeKm[i] / SCENE_UNIT_KM);
  if (!radii.length) return undefined;
  radii.sort((a, b) => a - b);
  const r90 = radii[Math.floor(radii.length * 0.9)] ?? radii[radii.length - 1];
  return Math.min(30, Math.max(3.8, r90 * 2.05));
}

/** Apply a lens from an explicit user choice (preset, search, stat click). */
export function applyLens(lens: Lens, opts: { frame?: boolean; keepSelection?: boolean } = {}) {
  const st = useAtlas.getState();
  const frame = opts.frame ? frameDistanceFor(lens) : undefined;
  if (!opts.keepSelection && st.selected >= 0) st.select(-1);
  st.setLens(lens, { frame });
}

export function copyShareLink(): Promise<boolean> {
  const url = window.location.href;
  if (navigator.share && /Mobi|Android/i.test(navigator.userAgent)) {
    return navigator
      .share({ title: 'Orbit Atlas', url })
      .then(() => true)
      .catch(() => false);
  }
  return navigator.clipboard
    .writeText(url)
    .then(() => true)
    .catch(() => false);
}
