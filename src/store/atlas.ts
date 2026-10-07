'use client';

import { create } from 'zustand';
import type { Catalog } from '@/lib/catalog/catalog';
import type { LoadOrigin } from '@/lib/catalog/load';
import { EMPTY_LENS, isEmptyLens, type Lens, lensMask, normalizeLens } from '@/lib/query/lens';
import { SearchIndex } from '@/lib/query/search';
import { simClock } from '@/lib/sim/clock';

export type ColorBy = 'mission' | 'owner';
export type LensMode = 'highlight' | 'only';

export type CameraCommand =
  | { id: number; kind: 'home' }
  | { id: number; kind: 'distance'; distance: number }
  | { id: number; kind: 'satellite'; index: number; distance?: number }
  | { id: number; kind: 'latlon'; lat: number; lon: number; distance: number }
  | { id: number; kind: 'zoom'; factor: number };

export type CameraCommandInput =
  | { kind: 'home' }
  | { kind: 'distance'; distance: number }
  | { kind: 'satellite'; index: number; distance?: number }
  | { kind: 'latlon'; lat: number; lon: number; distance: number }
  | { kind: 'zoom'; factor: number };

export interface CameraView {
  lat: number;
  lon: number;
  dist: number;
}

/** Per-satellite render style, packed into a GPU attribute. */
export const STYLE = { HIDDEN: 0, GHOST: 1, BASE: 2, FOCUS: 3, A: 4, B: 5 } as const;

interface AtlasState {
  status: 'loading' | 'ready' | 'error';
  error?: string;
  loadOrigin?: LoadOrigin;
  loadWarning?: string;
  catalog?: Catalog;
  search?: SearchIndex;

  lens: Lens;
  previewLens?: Lens;
  mode: LensMode;
  compare?: Lens;
  selected: number;
  hovered: number;
  follow: boolean;
  colorBy: ColorBy;
  warp: number;
  paused: boolean;
  commandOpen: boolean;
  commandPurpose: 'explore' | 'compare';
  sheet: 'peek' | 'half' | 'full';

  lensMask?: Uint8Array;
  previewMask?: Uint8Array;
  compareMask?: Uint8Array;

  inView?: Uint32Array;
  inViewVersion: number;
  cameraView?: CameraView;
  camera: CameraCommand | null;

  setCatalog: (cat: Catalog, origin: LoadOrigin, warning?: string) => void;
  setError: (msg: string) => void;
  setLens: (lens: Lens, opts?: { frame?: number; keepCompare?: boolean }) => void;
  clearLens: () => void;
  setPreview: (lens: Lens | undefined) => void;
  setMode: (mode: LensMode) => void;
  setCompare: (lens: Lens | undefined) => void;
  swapCompare: () => void;
  select: (index: number, opts?: { fly?: boolean }) => void;
  hover: (index: number) => void;
  setFollow: (follow: boolean) => void;
  setColorBy: (c: ColorBy) => void;
  setWarp: (warp: number) => void;
  setPaused: (paused: boolean) => void;
  goLive: () => void;
  openCommand: (open: boolean, purpose?: 'explore' | 'compare') => void;
  setSheet: (s: 'peek' | 'half' | 'full') => void;
  requestCamera: (cmd: CameraCommandInput) => void;
  setInView: (idx: Uint32Array) => void;
  setCameraView: (v: CameraView) => void;
}

let cameraSeq = 1;

const maskFor = (cat: Catalog | undefined, lens: Lens | undefined) =>
  cat && lens && !isEmptyLens(lens) ? lensMask(cat, lens) : undefined;

export const useAtlas = create<AtlasState>((set, get) => ({
  status: 'loading',
  lens: EMPTY_LENS,
  mode: 'highlight',
  selected: -1,
  hovered: -1,
  follow: false,
  colorBy: 'mission',
  warp: 1,
  paused: false,
  commandOpen: false,
  commandPurpose: 'explore',
  sheet: 'peek',
  inViewVersion: 0,
  camera: null,

  setCatalog: (catalog, loadOrigin, loadWarning) => {
    const { lens, compare } = get();
    set({
      catalog,
      search: new SearchIndex(catalog),
      status: 'ready',
      loadOrigin,
      loadWarning,
      lensMask: maskFor(catalog, lens),
      compareMask: maskFor(catalog, compare),
    });
  },
  setError: (error) => set({ status: 'error', error }),

  setLens: (lens, opts) => {
    const n = normalizeLens(lens);
    const { catalog, compare } = get();
    const keepCompare = opts?.keepCompare && compare;
    set({
      lens: n,
      lensMask: maskFor(catalog, n),
      previewLens: undefined,
      previewMask: undefined,
      compare: keepCompare ? compare : undefined,
      compareMask: keepCompare ? get().compareMask : undefined,
      mode: isEmptyLens(n) ? 'highlight' : get().mode,
      sheet: get().sheet === 'peek' && !isEmptyLens(n) ? 'half' : get().sheet,
    });
    if (opts?.frame) get().requestCamera({ kind: 'distance', distance: opts.frame });
  },
  clearLens: () =>
    set({ lens: EMPTY_LENS, lensMask: undefined, compare: undefined, compareMask: undefined, mode: 'highlight' }),
  setPreview: (previewLens) => {
    const { catalog } = get();
    set({ previewLens, previewMask: maskFor(catalog, previewLens) });
  },
  setMode: (mode) => set({ mode }),
  setCompare: (lens) => {
    const { catalog } = get();
    const n = lens ? normalizeLens(lens) : undefined;
    set({ compare: n, compareMask: maskFor(catalog, n), commandOpen: false });
  },
  swapCompare: () => {
    const { lens, compare, lensMask: lm, compareMask: cm } = get();
    if (!compare) return;
    set({ lens: compare, compare: lens, lensMask: cm, compareMask: lm });
  },
  select: (index, opts) => {
    set({ selected: index, follow: index < 0 ? false : get().follow, sheet: index >= 0 ? 'half' : get().sheet });
    if (index >= 0 && opts?.fly) get().requestCamera({ kind: 'satellite', index });
  },
  hover: (hovered) => {
    if (get().hovered !== hovered) set({ hovered });
  },
  setFollow: (follow) => set({ follow }),
  setColorBy: (colorBy) => set({ colorBy }),
  setWarp: (warp) => {
    simClock.setWarp(warp);
    if (simClock.paused) simClock.setPaused(false);
    set({ warp, paused: false });
  },
  setPaused: (paused) => {
    simClock.setPaused(paused);
    set({ paused });
  },
  goLive: () => {
    simClock.goLive();
    set({ warp: 1, paused: false });
  },
  openCommand: (commandOpen, purpose = 'explore') => set({ commandOpen, commandPurpose: purpose }),
  setSheet: (sheet) => set({ sheet }),
  requestCamera: (cmd) => set({ camera: { ...cmd, id: cameraSeq++ } as CameraCommand }),
  setInView: (inView) => set({ inView, inViewVersion: get().inViewVersion + 1 }),
  setCameraView: (cameraView) => set({ cameraView }),
}));

/** Compute the style attribute for every satellite from the current query state. */
export function computeStyles(
  count: number,
  s: Pick<AtlasState, 'lensMask' | 'previewMask' | 'compareMask' | 'mode' | 'previewLens'>,
  out = new Uint8Array(count),
): Uint8Array {
  const focus = s.previewLens ? s.previewMask : s.lensMask;
  const cmp = s.previewLens ? undefined : s.compareMask;
  const only = s.mode === 'only' && !s.previewLens;
  if (!focus && !cmp) {
    out.fill(STYLE.BASE);
    return out;
  }
  if (focus && !cmp) {
    for (let i = 0; i < count; i++) out[i] = focus[i] ? STYLE.FOCUS : only ? STYLE.HIDDEN : STYLE.GHOST;
    return out;
  }
  for (let i = 0; i < count; i++) {
    const a = focus ? focus[i] : 0;
    const b = cmp ? cmp[i] : 0;
    out[i] = a ? STYLE.A : b ? STYLE.B : only ? STYLE.HIDDEN : STYLE.GHOST;
  }
  return out;
}
