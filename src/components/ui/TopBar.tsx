'use client';

import Link from 'next/link';

import { isEmptyLens, lensLabel } from '@/lib/query/lens';
import { useAtlas } from '@/store/atlas';
import { copyShareLink } from './actions';
import { DataStatusPill } from './DataStatus';
import { useMaskIndices } from './derived';
import { fmt } from './format';
import { CloseIcon, CompareIcon, FocusIcon, SearchIcon, ShareIcon } from './icons';

export function TopBar({ onShared }: { onShared: (ok: boolean) => void }) {
  const openCommand = useAtlas((s) => s.openCommand);
  return (
    <header className="pointer-events-none absolute inset-x-0 top-0 z-20 flex items-center gap-3 px-3 pt-3 lg:px-4" style={{ paddingTop: 'max(12px, env(safe-area-inset-top))' }}>
      <div className="pointer-events-auto flex min-w-0 items-center gap-2.5">
        <Link href="/" className="flex items-center gap-2" aria-label="Orbit Atlas home">
          <svg width="26" height="26" viewBox="0 0 64 64" aria-hidden>
            <circle cx="32" cy="32" r="11" fill="#1d4f8f" />
            <circle cx="32" cy="32" r="11" fill="none" stroke="#8cc8ff" strokeWidth="1.5" opacity=".7" />
            <ellipse cx="32" cy="32" rx="25" ry="9" fill="none" stroke="#8cc8ff" strokeWidth="2.5" transform="rotate(-24 32 32)" />
            <circle cx="54" cy="22" r="4" fill="#e9f4ff" />
          </svg>
          <span className="hidden text-[15px] font-semibold tracking-tight text-white sm:inline">Orbit Atlas</span>
        </Link>
        <DataStatusPill />
      </div>

      <button
        type="button"
        onClick={() => openCommand(true)}
        className="glass pointer-events-auto mx-auto hidden h-10 w-full max-w-[460px] items-center gap-2.5 rounded-xl px-3.5 text-left text-[13.5px] text-[#8b93a7] hover:text-[#c6cbd8] md:flex"
        aria-label="Search"
      >
        <SearchIcon />
        <span className="flex-1 truncate">Search satellites, companies, countries…</span>
        <kbd className="rounded border border-white/15 px-1.5 py-0.5 text-[10px]">⌘K</kbd>
      </button>

      <div className="pointer-events-auto ml-auto flex items-center gap-2 md:ml-0">
        <button
          type="button"
          onClick={() => openCommand(true)}
          className="glass flex h-10 w-10 items-center justify-center rounded-xl text-white md:hidden"
          aria-label="Search"
        >
          <SearchIcon width={18} height={18} />
        </button>
        <button
          type="button"
          onClick={() => copyShareLink().then(onShared)}
          className="glass flex h-10 items-center gap-2 rounded-xl px-3 text-[13px] text-[#c6cbd8] hover:text-white"
          title="Copy a link to exactly this view"
        >
          <ShareIcon /> <span className="hidden sm:inline">Share view</span>
        </button>
      </div>
    </header>
  );
}

/** The active lens as a removable chip with its quick actions. */
export function LensBar() {
  const lens = useAtlas((s) => s.lens);
  const mask = useAtlas((s) => s.lensMask);
  const compare = useAtlas((s) => s.compare);
  const mode = useAtlas((s) => s.mode);
  const setMode = useAtlas((s) => s.setMode);
  const clearLens = useAtlas((s) => s.clearLens);
  const openCommand = useAtlas((s) => s.openCommand);
  const setCompare = useAtlas((s) => s.setCompare);
  const idx = useMaskIndices(mask);
  if (isEmptyLens(lens)) return null;

  return (
    <div className="pointer-events-none flex justify-center px-3">
      <div className="glass fade-up pointer-events-auto flex max-w-full items-center gap-1 rounded-full py-1 pl-3 pr-1 text-[12.5px]">
        <span className={`h-2 w-2 shrink-0 rounded-full ${compare ? 'bg-[#3987e5]' : 'bg-[#e9f4ff]'}`} />
        <span className="max-w-[40vw] truncate font-medium text-white">{lensLabel(lens)}</span>
        <span className="tabular text-[#8b93a7]">{fmt(idx?.length ?? 0)}</span>
        {compare && (
          <>
            <span className="px-1 text-[#8b93a7]">vs</span>
            <span className="h-2 w-2 shrink-0 rounded-full bg-[#d95926]" />
            <span className="max-w-[28vw] truncate font-medium text-white">{lensLabel(compare)}</span>
            <button type="button" onClick={() => setCompare(undefined)} className="rounded-full p-1 text-[#8b93a7] hover:bg-white/10 hover:text-white" aria-label="End comparison">
              <CloseIcon width={13} height={13} />
            </button>
          </>
        )}
        <span className="mx-1 h-4 w-px bg-white/10" />
        <button
          type="button"
          onClick={() => setMode(mode === 'only' ? 'highlight' : 'only')}
          aria-pressed={mode === 'only'}
          className={`flex items-center gap-1 rounded-full px-2 py-1 ${mode === 'only' ? 'bg-[#8cc8ff]/20 text-white' : 'text-[#c6cbd8] hover:bg-white/10'}`}
          title="Hide everything else"
        >
          <FocusIcon width={14} height={14} /> <span className="hidden sm:inline">Only</span>
        </button>
        {!compare && (
          <button
            type="button"
            onClick={() => openCommand(true, 'compare')}
            className="flex items-center gap-1 rounded-full px-2 py-1 text-[#c6cbd8] hover:bg-white/10"
            title="Compare with another group"
          >
            <CompareIcon width={14} height={14} /> <span className="hidden sm:inline">Compare</span>
          </button>
        )}
        <button type="button" onClick={clearLens} className="rounded-full p-1.5 text-[#8b93a7] hover:bg-white/10 hover:text-white" aria-label="Clear lens">
          <CloseIcon width={14} height={14} />
        </button>
      </div>
    </div>
  );
}
