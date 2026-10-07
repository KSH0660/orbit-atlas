'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { lensLabel, PRESETS } from '@/lib/query/lens';
import type { SearchKind, SearchResult } from '@/lib/query/search';
import { useAtlas } from '@/store/atlas';
import { applyLens } from './actions';
import { fmt } from './format';
import { SearchIcon } from './icons';

const KIND_LABEL: Record<SearchKind, string> = {
  preset: 'Explore',
  constellation: 'Constellation',
  operator: 'Operator',
  country: 'Country',
  bloc: 'Region',
  mission: 'Mission',
  regime: 'Orbit',
  satellite: 'Satellite',
};

const SUGGEST = ['starlink', 'gnss', 'stations', 'korea', 'military', 'geo'];
const SUGGEST_SATS = [25544, 48274, 20580]; // ISS, Tiangong (CSS Tianhe), Hubble

/**
 * One box for everything: satellites, companies, countries, constellations,
 * missions and orbits. Arrow keys preview a result on the globe before you
 * commit to it.
 */
export function CommandBar() {
  const open = useAtlas((s) => s.commandOpen);
  // Mounting fresh on every open resets the query and selection.
  return open ? <CommandBarInner /> : null;
}

function CommandBarInner() {
  const purpose = useAtlas((s) => s.commandPurpose);
  const search = useAtlas((s) => s.search);
  const catalog = useAtlas((s) => s.catalog);
  const lens = useAtlas((s) => s.lens);
  const openCommand = useAtlas((s) => s.openCommand);
  const setPreview = useAtlas((s) => s.setPreview);
  const [q, setQ] = useState('');
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    requestAnimationFrame(() => input.current?.focus());
    return () => setPreview(undefined);
  }, [setPreview]);

  const results: SearchResult[] = useMemo(() => {
    if (!search || !catalog) return [];
    if (q.trim()) return search.search(q, 12);
    const presets = SUGGEST.map((id) => PRESETS.find((p) => p.id === id)!).map<SearchResult>((p) => ({
      kind: 'preset',
      key: p.id,
      title: p.label,
      subtitle: p.hint,
      lens: p.lens,
      score: 1,
    }));
    const sats = SUGGEST_SATS.map((id) => catalog.idToIndex.get(id))
      .filter((i): i is number => i !== undefined)
      .map<SearchResult>((i) => ({
        kind: 'satellite',
        key: String(catalog.ids[i]),
        title: catalog.names[i],
        subtitle: `#${catalog.ids[i]} · ${catalog.operators[catalog.operator[i]]}`,
        satIndex: i,
        score: 1,
      }));
    return purpose === 'compare' ? presets : [...presets, ...sats];
  }, [search, catalog, q, purpose]);

  // Preview the highlighted result on the globe.
  useEffect(() => {
    const r = results[active];
    const t = setTimeout(() => setPreview(r?.lens && purpose === 'explore' ? r.lens : undefined), 120);
    return () => clearTimeout(t);
  }, [results, active, purpose, setPreview]);

  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>(`[data-idx="${active}"]`)?.scrollIntoView({ block: 'nearest' });
  }, [active]);

  const choose = (r: SearchResult) => {
    const st = useAtlas.getState();
    setPreview(undefined);
    if (purpose === 'compare') {
      st.setCompare(r.lens ?? (r.satIndex !== undefined ? { ids: [catalog!.ids[r.satIndex]] } : undefined));
      st.select(-1);
      return;
    }
    openCommand(false);
    if (r.kind === 'satellite' && r.satIndex !== undefined) {
      st.select(r.satIndex, { fly: true });
    } else if (r.lens) {
      applyLens(r.lens, { frame: true });
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 px-3 pt-[9vh] backdrop-blur-[2px]"
      onMouseDown={(e) => e.target === e.currentTarget && openCommand(false)}
      role="dialog"
      aria-modal="true"
      aria-label={purpose === 'compare' ? 'Choose a group to compare' : 'Search'}
    >
      <div className="glass fade-up w-full max-w-[600px] overflow-hidden rounded-2xl">
        {purpose === 'compare' && (
          <div className="flex items-center gap-2 border-b border-white/[0.07] px-4 py-2 text-[12px] text-[#c6cbd8]">
            <span className="h-2.5 w-2.5 rounded-full bg-[#3987e5]" /> {lensLabel(lens)}
            <span className="text-[#8b93a7]">compared with…</span>
            <span className="h-2.5 w-2.5 rounded-full bg-[#d95926]" />
          </div>
        )}
        <div className="flex items-center gap-3 px-4">
          <SearchIcon className="shrink-0 text-[#8b93a7]" width={18} height={18} />
          <input
            ref={input}
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setActive(0);
            }}
            onKeyDown={(e) => {
              if (e.key === 'ArrowDown') {
                e.preventDefault();
                setActive((a) => Math.min(results.length - 1, a + 1));
              } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                setActive((a) => Math.max(0, a - 1));
              } else if (e.key === 'Enter' && results[active]) {
                e.preventDefault();
                choose(results[active]);
              } else if (e.key === 'Escape') {
                openCommand(false);
              }
            }}
            placeholder={purpose === 'compare' ? 'Compare with… (e.g. Kuiper, China, BeiDou)' : 'Search satellites, companies, countries, constellations…'}
            className="h-14 w-full bg-transparent text-[15px] text-white placeholder:text-[#8b93a7] focus:outline-none focus-visible:outline-none"
            aria-label="Search"
            aria-controls="command-results"
            aria-activedescendant={results[active] ? `cmd-${active}` : undefined}
            autoComplete="off"
            spellCheck={false}
          />
          <kbd className="hidden rounded border border-white/15 px-1.5 py-0.5 text-[10px] text-[#8b93a7] sm:block">esc</kbd>
        </div>
        <ul ref={listRef} id="command-results" role="listbox" className="thin-scroll max-h-[min(60vh,440px)] overflow-y-auto border-t border-white/[0.07] py-1.5">
          {!q.trim() && (
            <li className="px-4 pb-1 pt-1.5 text-[10.5px] font-semibold uppercase tracking-[0.13em] text-[#8b93a7]">
              {purpose === 'compare' ? 'Suggestions' : 'Try'}
            </li>
          )}
          {results.map((r, i) => (
            <li key={`${r.kind}:${r.key}`} id={`cmd-${i}`} role="option" aria-selected={i === active} data-idx={i}>
              <button
                type="button"
                onMouseMove={() => setActive(i)}
                onClick={() => choose(r)}
                className={`flex w-full items-center gap-3 px-4 py-2 text-left ${i === active ? 'bg-white/[0.08]' : ''}`}
              >
                <span className="w-[88px] shrink-0 text-[10.5px] uppercase tracking-wider text-[#8b93a7]">{KIND_LABEL[r.kind]}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[14px] text-white">{r.title}</span>
                  <span className="block truncate text-[11.5px] text-[#8b93a7]">{r.subtitle}</span>
                </span>
                {r.count !== undefined && <span className="tabular shrink-0 text-[12px] text-[#c6cbd8]">{fmt(r.count)}</span>}
              </button>
            </li>
          ))}
          {q.trim() && results.length === 0 && (
            <li className="px-4 py-6 text-center text-[13px] text-[#8b93a7]">No matches. Try a name, a NORAD number (e.g. 25544) or a country.</li>
          )}
        </ul>
        <div className="hidden items-center gap-4 border-t border-white/[0.07] px-4 py-2 text-[10.5px] text-[#8b93a7] sm:flex">
          <span>↑↓ preview on globe</span>
          <span>↵ open</span>
          <span className="ml-auto">한국어 검색 지원 · e.g. 스타링크, 한국, 군사</span>
        </div>
      </div>
    </div>
  );
}
