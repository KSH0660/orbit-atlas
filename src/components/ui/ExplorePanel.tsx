'use client';

import { useMemo } from 'react';
import { lensEquals, lensMask, countMask, PRESETS } from '@/lib/query/lens';
import { useAtlas } from '@/store/atlas';
import { applyLens } from './actions';
import { fmtCompact } from './format';

function usePresetCounts() {
  const catalog = useAtlas((s) => s.catalog);
  return useMemo(() => {
    if (!catalog) return {} as Record<string, number>;
    const out: Record<string, number> = {};
    for (const p of PRESETS) out[p.id] = countMask(lensMask(catalog, p.lens));
    return out;
  }, [catalog]);
}

/**
 * Explore: one click to the questions people actually come with. Hovering a
 * row previews it on the globe without committing; clicking applies it as the
 * lens (and clicking again clears it).
 */
export function ExplorePanel() {
  const lens = useAtlas((s) => s.lens);
  const setPreview = useAtlas((s) => s.setPreview);
  const clearLens = useAtlas((s) => s.clearLens);
  const counts = usePresetCounts();

  return (
    <nav
      className="glass pointer-events-auto absolute left-4 top-[72px] hidden w-[208px] rounded-2xl py-2 lg:block"
      aria-label="Explore"
      onMouseLeave={() => setPreview(undefined)}
    >
      <div className="px-3.5 pb-1 pt-1 text-[10.5px] font-semibold uppercase tracking-[0.13em] text-[#8b93a7]">Explore</div>
      <ul>
        {PRESETS.map((p) => {
          const active = lensEquals(lens, p.lens);
          return (
            <li key={p.id}>
              <button
                type="button"
                title={p.hint}
                aria-pressed={active}
                onMouseEnter={() => !active && setPreview(p.lens)}
                onFocus={() => !active && setPreview(p.lens)}
                onBlur={() => setPreview(undefined)}
                onClick={() => {
                  setPreview(undefined);
                  if (active) clearLens();
                  else applyLens(p.lens, { frame: true });
                }}
                className={`group flex w-full items-center gap-2 px-3.5 py-[7px] text-left text-[13px] transition-colors ${
                  active ? 'bg-[#8cc8ff]/15 text-white' : 'text-[#c6cbd8] hover:bg-white/[0.06] hover:text-white'
                }`}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${active ? 'bg-[#e9f4ff]' : 'bg-white/20 group-hover:bg-white/60'}`} />
                <span className="flex-1 truncate">{p.label}</span>
                <span className="tabular text-[11.5px] text-[#8b93a7]">{counts[p.id] !== undefined ? fmtCompact(counts[p.id]) : ''}</span>
              </button>
            </li>
          );
        })}
      </ul>
      <div className="px-3.5 pb-1 pt-2 text-[10.5px] leading-snug text-[#8b93a7]">
        Hover to preview · click to focus · <kbd className="rounded border border-white/15 px-1">/</kbd> to search anything
      </div>
    </nav>
  );
}

/** Mobile / tablet: the same presets as a horizontally scrolling chip row. */
export function ExploreChips() {
  const lens = useAtlas((s) => s.lens);
  const clearLens = useAtlas((s) => s.clearLens);
  const counts = usePresetCounts();
  return (
    <div className="scrollbar-none pointer-events-auto flex gap-1.5 overflow-x-auto px-3 pb-1 lg:hidden">
      {PRESETS.map((p) => {
        const active = lensEquals(lens, p.lens);
        return (
          <button
            key={p.id}
            type="button"
            aria-pressed={active}
            onClick={() => (active ? clearLens() : applyLens(p.lens, { frame: true }))}
            className={`glass shrink-0 rounded-full px-3 py-1.5 text-[12.5px] ${active ? '!border-[#8cc8ff]/60 !bg-[#8cc8ff]/20 text-white' : 'text-[#c6cbd8]'}`}
          >
            {p.label}
            <span className="tabular ml-1.5 text-[11px] text-[#8b93a7]">{counts[p.id] !== undefined ? fmtCompact(counts[p.id]) : ''}</span>
          </button>
        );
      })}
    </div>
  );
}
