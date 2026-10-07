'use client';

import dynamic from 'next/dynamic';
import { useCallback, useEffect, useRef, useState } from 'react';
import { decodeCatalog } from '@/lib/catalog/catalog';
import { loadCatalogPayload } from '@/lib/catalog/load';
import { isEmptyLens } from '@/lib/query/lens';
import { parseViewState, serializeViewState, type ViewState } from '@/lib/query/url';
import { simClock } from '@/lib/sim/clock';
import { PropagationManager } from '@/lib/sim/propagation';
import { runtime } from '@/lib/sim/runtime';
import { useAtlas } from '@/store/atlas';
import { defaultView, type InitialView } from './scene/CameraRig';
import { BottomBarLayout } from './ui/BottomBarLayout';
import { CommandBar } from './ui/CommandBar';
import { DesktopPanel, MobileSheet } from './ui/ContextPanel';
import { ExploreChips, ExplorePanel } from './ui/ExplorePanel';
import { HoverTooltip } from './ui/HoverTooltip';
import { FirstVisitHint } from './ui/FirstVisitHint';
import { SceneLabels } from './ui/SceneLabels';
import { LensBar, TopBar } from './ui/TopBar';

const Scene = dynamic(() => import('./scene/Scene'), { ssr: false });

/** Applies URL state once the catalog is ready, then mirrors state back into the URL. */
function useUrlState(initial: ViewState | null) {
  const status = useAtlas((s) => s.status);
  const applied = useRef(false);

  useEffect(() => {
    if (status !== 'ready' || applied.current || !initial) return;
    applied.current = true;
    const st = useAtlas.getState();
    const cat = st.catalog!;
    if (!isEmptyLens(initial.lens)) st.setLens(initial.lens);
    if (initial.compare) st.setCompare(initial.compare);
    if (initial.only) st.setMode('only');
    st.setColorBy(initial.color);
    if (initial.warp !== 1) st.setWarp(initial.warp);
    if (initial.sat !== undefined) {
      const idx = cat.idToIndex.get(initial.sat);
      if (idx !== undefined) {
        st.select(idx, { fly: !initial.cam });
        if (initial.follow) st.setFollow(true);
      }
    }
    if (!initial.sat || window.innerWidth >= 1024) st.setSheet('peek');
  }, [status, initial]);

  useEffect(() => {
    let t: ReturnType<typeof setTimeout> | undefined;
    const write = () => {
      const s = useAtlas.getState();
      if (s.status !== 'ready' || !applied.current) return;
      const v: ViewState = {
        lens: s.lens,
        only: s.mode === 'only',
        compare: s.compare,
        sat: s.selected >= 0 && s.catalog ? s.catalog.ids[s.selected] : undefined,
        follow: s.follow,
        color: s.colorBy,
        warp: s.warp,
        cam: s.cameraView,
      };
      const next = `${window.location.pathname}${serializeViewState(v)}`;
      if (next !== `${window.location.pathname}${window.location.search}`) window.history.replaceState(null, '', next);
    };
    const unsub = useAtlas.subscribe((s, p) => {
      if (
        s.lens !== p.lens ||
        s.mode !== p.mode ||
        s.compare !== p.compare ||
        s.selected !== p.selected ||
        s.follow !== p.follow ||
        s.colorBy !== p.colorBy ||
        s.warp !== p.warp ||
        s.cameraView !== p.cameraView
      ) {
        clearTimeout(t);
        t = setTimeout(write, 350);
      }
    });
    return () => {
      unsub();
      clearTimeout(t);
    };
  }, []);
}

function useKeyboard() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const s = useAtlas.getState();
      const typing = e.target instanceof HTMLElement && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA');
      if ((e.key === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !typing)) {
        e.preventDefault();
        s.openCommand(!s.commandOpen);
        return;
      }
      if (typing || s.commandOpen) return;
      if (e.key === 'Escape') {
        // Back out one level at a time: follow → selection → compare → lens.
        if (s.follow) s.setFollow(false);
        else if (s.selected >= 0) s.select(-1);
        else if (s.compare) s.setCompare(undefined);
        else if (!isEmptyLens(s.lens)) s.clearLens();
      } else if (e.key === 'f' && s.selected >= 0) s.setFollow(!s.follow);
      else if (e.key === 'h') s.requestCamera({ kind: 'home' });
      else if (e.key === ' ') {
        e.preventDefault();
        s.setPaused(!s.paused);
      } else if (e.key === 'l') s.goLive();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
}

export default function AtlasApp() {
  const status = useAtlas((s) => s.status);
  const error = useAtlas((s) => s.error);
  const catalog = useAtlas((s) => s.catalog);
  // URL state is read once on the client; the server render never depends on it.
  const [initialUrl] = useState<ViewState | null>(() =>
    typeof window === 'undefined' ? null : parseViewState(window.location.search),
  );
  const [initialView] = useState<InitialView | null>(() =>
    typeof window === 'undefined' ? null : (initialUrl?.cam ?? defaultView()),
  );
  const [toast, setToast] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let alive = true;
    loadCatalogPayload()
      .then(({ payload, origin, error: warn }) => {
        if (!alive) return;
        const cat = decodeCatalog(payload);
        runtime.propagation?.dispose();
        runtime.propagation = new PropagationManager(cat);
        simClock.goLive();
        useAtlas.getState().setCatalog(cat, origin, warn);
      })
      .catch((err: Error) => alive && useAtlas.getState().setError(err.message));
    return () => {
      alive = false;
    };
  }, [attempt]);

  useEffect(() => () => runtime.propagation?.dispose(), []);

  useUrlState(initialUrl);
  useKeyboard();

  const onShared = useCallback((ok: boolean) => {
    setToast(ok ? 'Link to this exact view copied' : 'Copy the URL from the address bar to share');
    setTimeout(() => setToast(null), 2200);
  }, []);

  return (
    <main className="fixed inset-0 overflow-hidden bg-[#03050b]">
      <div className="absolute inset-0">{catalog && initialView && <Scene catalog={catalog} initial={initialView} />}</div>
      {catalog && <SceneLabels />}

      <div className="pointer-events-none absolute inset-0">
        <TopBar onShared={onShared} />
        <div className="absolute inset-x-0 top-[60px] z-10 flex flex-col gap-2 lg:top-[64px]">
          <ExploreChips />
          <LensBar />
        </div>
        {status === 'ready' && (
          <>
            <ExplorePanel />
            <DesktopPanel onShared={onShared} />
            <BottomBarLayout />
            <MobileSheet onShared={onShared} />
            <FirstVisitHint />
          </>
        )}
      </div>

      <HoverTooltip />
      <CommandBar />

      {status === 'loading' && (
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-3 text-center">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-white/10 border-t-[#8cc8ff]" />
          <div className="text-[14px] font-medium text-white">Loading every active satellite…</div>
          <div className="text-[12px] text-[#8b93a7]">Fetching the latest public orbital elements from CelesTrak</div>
        </div>
      )}
      {status === 'error' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-6 text-center">
          <div className="text-[15px] font-semibold text-white">Satellite data is unavailable right now</div>
          <div className="max-w-md text-[12.5px] text-[#8b93a7]">{error}</div>
          <button
            type="button"
            onClick={() => {
              useAtlas.setState({ status: 'loading', error: undefined });
              setAttempt((a) => a + 1);
            }}
            className="rounded-lg border border-white/15 px-3 py-1.5 text-[13px] text-white hover:bg-white/10"
          >
            Try again
          </button>
        </div>
      )}
      {toast && (
        <div className="glass fade-up fixed left-1/2 top-16 z-50 -translate-x-1/2 rounded-full px-4 py-2 text-[12.5px] text-white" role="status">
          {toast}
        </div>
      )}
    </main>
  );
}
