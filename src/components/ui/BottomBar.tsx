'use client';

import { useEffect, useRef, useState } from 'react';
import { BLOCS, MISSIONS } from '@/lib/data/taxonomy';
import type { Lens } from '@/lib/query/lens';
import { simClock } from '@/lib/sim/clock';
import { useAtlas } from '@/store/atlas';
import { applyLens } from './actions';
import { utcClock, utcDate } from './format';
import { HomeIcon, MinusIcon, PauseIcon, PlayIcon, PlusIcon } from './icons';

const WARPS = [1, 10, 60, 360];

function offsetLabel(ms: number): string {
  const s = Math.round(ms / 1000);
  const sign = s >= 0 ? '+' : '−';
  const a = Math.abs(s);
  const h = Math.floor(a / 3600);
  const m = Math.floor((a % 3600) / 60);
  if (h >= 48) return `${sign}${Math.round(h / 24)} d`;
  if (h) return `${sign}${h} h ${m} m`;
  if (m) return `${sign}${m} m`;
  return `${sign}${a} s`;
}

export function TimeControl({ compact = false }: { compact?: boolean }) {
  const warp = useAtlas((s) => s.warp);
  const paused = useAtlas((s) => s.paused);
  const setWarp = useAtlas((s) => s.setWarp);
  const setPaused = useAtlas((s) => s.setPaused);
  const goLive = useAtlas((s) => s.goLive);
  const clock = useRef<HTMLSpanElement>(null);
  const date = useRef<HTMLSpanElement>(null);
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    let raf = 0;
    let last = 0;
    const loop = (t: number) => {
      raf = requestAnimationFrame(loop);
      if (t - last < 200) return;
      last = t;
      const now = simClock.now();
      if (clock.current) clock.current.textContent = utcClock(now);
      if (date.current) date.current.textContent = utcDate(now);
      setOffset(now - Date.now());
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  const live = !paused && warp === 1 && Math.abs(offset) < 5000;

  return (
    <div className="glass pointer-events-auto flex h-11 items-center gap-1 rounded-xl px-1.5">
      <button
        type="button"
        onClick={goLive}
        className={`flex items-center gap-1.5 rounded-lg px-2 py-1 text-[11px] font-semibold uppercase tracking-wider ${
          live ? 'text-[#0ca30c]' : 'text-[#fab219] hover:bg-white/10'
        }`}
        title={live ? 'Showing real time' : 'Return to real time'}
      >
        <span className={`h-1.5 w-1.5 rounded-full ${live ? 'live-dot bg-[#0ca30c]' : 'bg-[#fab219]'}`} />
        {live ? 'Live' : 'Go live'}
      </button>
      <div className="flex flex-col px-1.5 leading-tight">
        <span ref={clock} className="tabular text-[13px] font-medium text-white">
          --:--:-- UTC
        </span>
        <span className="tabular text-[10px] text-[#8b93a7]">
          <span ref={date} /> {!live && <span className="text-[#fab219]">{offsetLabel(offset)}</span>}
        </span>
      </div>
      <span className="mx-1 h-5 w-px bg-white/10" />
      <button
        type="button"
        onClick={() => setPaused(!paused)}
        className="rounded-lg p-1.5 text-[#c6cbd8] hover:bg-white/10 hover:text-white"
        aria-label={paused ? 'Play' : 'Pause'}
      >
        {paused ? <PlayIcon /> : <PauseIcon />}
      </button>
      {compact ? (
        <button
          type="button"
          onClick={() => setWarp(WARPS[(WARPS.indexOf(warp) + 1) % WARPS.length] ?? 1)}
          className="tabular min-w-[44px] rounded-lg bg-white/10 px-2 py-1 text-[12px] font-semibold text-white"
          aria-label={`Time speed ${warp}×, tap to change`}
        >
          {warp}×
        </button>
      ) : (
      <div className="flex" role="group" aria-label="Time speed">
        {WARPS.map((w) => (
          <button
            key={w}
            type="button"
            onClick={() => setWarp(w)}
            aria-pressed={warp === w && !paused}
            className={`tabular rounded-lg px-2 py-1 text-[12px] ${
              warp === w && !paused ? 'bg-white/15 font-semibold text-white' : 'text-[#8b93a7] hover:bg-white/10 hover:text-white'
            }`}
            title={w === 1 ? 'Real time' : `${w}× speed (${w >= 60 ? `${w / 60} min` : `${w} s`} per second)`}
          >
            {w}×
          </button>
        ))}
      </div>
      )}
    </div>
  );
}

export function Legend() {
  const colorBy = useAtlas((s) => s.colorBy);
  const setColorBy = useAtlas((s) => s.setColorBy);
  const setPreview = useAtlas((s) => s.setPreview);
  const [open, setOpen] = useState(true);
  const items: { key: string; label: string; color: string; lens?: Lens }[] =
    colorBy === 'mission'
      ? MISSIONS.map((m) => ({ key: m.id, label: m.short, color: m.color, lens: { missions: [m.id] } }))
      : BLOCS.map((b) => ({ key: b.id, label: b.label, color: b.color, lens: b.id === 'OT' ? undefined : { blocs: [b.id] } }));

  return (
    <div className="glass pointer-events-auto rounded-xl px-3 py-2" onMouseLeave={() => setPreview(undefined)}>
      <div className="flex items-center gap-2">
        <span className="text-[10.5px] font-semibold uppercase tracking-[0.13em] text-[#8b93a7]">Color</span>
        <div className="flex rounded-md bg-white/[0.06] p-0.5 text-[11px]">
          {(['mission', 'owner'] as const).map((c) => (
            <button
              key={c}
              type="button"
              aria-pressed={colorBy === c}
              onClick={() => setColorBy(c)}
              className={`rounded px-2 py-0.5 ${colorBy === c ? 'bg-white/15 text-white' : 'text-[#8b93a7] hover:text-white'}`}
            >
              {c === 'mission' ? 'Mission' : 'Owner'}
            </button>
          ))}
        </div>
        <button type="button" onClick={() => setOpen(!open)} className="ml-auto text-[11px] text-[#8b93a7] hover:text-white lg:hidden">
          {open ? 'Hide' : 'Show'}
        </button>
      </div>
      {open && (
        <ul className="mt-1.5 grid grid-cols-2 gap-x-3 gap-y-0.5">
          {items.map((it) => (
            <li key={it.key}>
              <button
                type="button"
                disabled={!it.lens}
                onMouseEnter={() => it.lens && setPreview(it.lens)}
                onClick={() => it.lens && applyLens(it.lens, { frame: true })}
                className="flex w-full items-center gap-1.5 rounded px-1 py-0.5 text-left text-[11.5px] text-[#c6cbd8] enabled:hover:bg-white/5 enabled:hover:text-white"
              >
                <span className="h-2 w-2 rounded-full" style={{ background: it.color }} />
                {it.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function ViewControls() {
  const requestCamera = useAtlas((s) => s.requestCamera);
  const btn = 'flex h-9 w-9 items-center justify-center text-[#c6cbd8] hover:bg-white/10 hover:text-white';
  return (
    <div className="glass pointer-events-auto flex flex-col overflow-hidden rounded-xl">
      <button type="button" className={btn} onClick={() => requestCamera({ kind: 'zoom', factor: 0.7 })} aria-label="Zoom in">
        <PlusIcon />
      </button>
      <button type="button" className={btn} onClick={() => requestCamera({ kind: 'zoom', factor: 1.4 })} aria-label="Zoom out">
        <MinusIcon />
      </button>
      <button type="button" className={btn} onClick={() => requestCamera({ kind: 'home' })} aria-label="Reset view" title="Reset view (H)">
        <HomeIcon />
      </button>
    </div>
  );
}
