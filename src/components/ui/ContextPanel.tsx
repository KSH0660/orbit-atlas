'use client';

import { useRef, useState } from 'react';
import { isEmptyLens, lensLabel } from '@/lib/query/lens';
import { useAtlas } from '@/store/atlas';
import { allScope, useScopeStats } from './derived';
import { fmt } from './format';
import { CompareView } from './panel/CompareView';
import { LensView } from './panel/LensView';
import { OverviewView } from './panel/OverviewView';
import { SatelliteCard } from './panel/SatelliteCard';
import { DataSource } from './DataStatus';

/**
 * Contextual information only: overview → lens → satellite, never all at
 * once. On desktop it is a side column; on mobile the same content lives in a
 * bottom sheet with peek / half / full states.
 */
function PanelBody({ onShared }: { onShared: (ok: boolean) => void }) {
  const selected = useAtlas((s) => s.selected);
  const compare = useAtlas((s) => s.compare);
  const lens = useAtlas((s) => s.lens);
  const select = useAtlas((s) => s.select);
  const [scope, setScope] = useState<'view' | 'all'>('view');

  const lensActive = !isEmptyLens(lens);
  let body;
  if (selected >= 0) body = <SatelliteCard onShared={onShared} />;
  else if (compare) body = <CompareView />;
  else if (lensActive) body = <LensView scope={scope} setScope={setScope} />;
  else body = <OverviewView scope={scope} setScope={setScope} />;

  return (
    <div className="flex min-h-full flex-col">
      {selected >= 0 && (lensActive || compare) && (
        <button
          type="button"
          onClick={() => select(-1)}
          className="mx-4 mt-3 self-start truncate rounded-md px-1.5 py-0.5 text-[11.5px] text-[#8b93a7] hover:bg-white/5 hover:text-white"
        >
          ← {compare ? 'Back to comparison' : lensLabel(lens)}
        </button>
      )}
      <div className="flex-1">{body}</div>
      <div className="border-t border-white/[0.07] px-4 py-3">
        <DataSource />
      </div>
    </div>
  );
}

export function DesktopPanel({ onShared }: { onShared: (ok: boolean) => void }) {
  return (
    <aside
      className="glass thin-scroll pointer-events-auto absolute bottom-[76px] right-4 top-[72px] hidden w-[352px] overflow-y-auto rounded-2xl lg:block"
      aria-label="Context"
    >
      <PanelBody onShared={onShared} />
    </aside>
  );
}

/** Mobile bottom sheet. */
export function MobileSheet({ onShared }: { onShared: (ok: boolean) => void }) {
  const sheet = useAtlas((s) => s.sheet);
  const setSheet = useAtlas((s) => s.setSheet);
  const selected = useAtlas((s) => s.selected);
  const catalog = useAtlas((s) => s.catalog);
  const lens = useAtlas((s) => s.lens);
  const lensMask = useAtlas((s) => s.lensMask);
  const view = useScopeStats('view', lensMask);
  const startY = useRef<number | null>(null);

  const heights = { peek: 'h-[76px]', half: 'h-[52dvh]', full: 'h-[88dvh]' } as const;
  const next = sheet === 'peek' ? 'half' : sheet === 'half' ? 'full' : 'half';

  let peekTitle = '';
  let peekSub = '';
  if (catalog) {
    if (selected >= 0) {
      peekTitle = catalog.names[selected];
      peekSub = catalog.operators[catalog.operator[selected]];
    } else if (!isEmptyLens(lens)) {
      peekTitle = lensLabel(lens);
      peekSub = `${fmt(view?.stats.total ?? 0)} in view`;
    } else {
      peekTitle = `${fmt(allScope(catalog).stats.total)} active satellites`;
      peekSub = `${fmt(view?.stats.total ?? 0)} in this view`;
    }
  }

  return (
    <div
      className={`glass pointer-events-auto fixed inset-x-0 bottom-0 z-30 flex flex-col rounded-t-2xl !bg-[#0b1020]/95 transition-[height] duration-300 lg:hidden ${heights[sheet]}`}
      style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      <button
        type="button"
        aria-label={sheet === 'full' ? 'Collapse panel' : 'Expand panel'}
        className="flex shrink-0 flex-col items-center px-4 pb-1 pt-2"
        onClick={() => setSheet(sheet === 'full' ? 'peek' : next)}
        onTouchStart={(e) => (startY.current = e.touches[0].clientY)}
        onTouchEnd={(e) => {
          if (startY.current === null) return;
          const dy = e.changedTouches[0].clientY - startY.current;
          startY.current = null;
          if (dy < -30) setSheet(sheet === 'peek' ? 'half' : 'full');
          else if (dy > 30) setSheet(sheet === 'full' ? 'half' : 'peek');
        }}
      >
        <span className="h-1 w-10 rounded-full bg-white/25" />
        {sheet === 'peek' && (
          <span className="mt-2 flex w-full items-baseline justify-between gap-2 text-left">
            <span className="truncate text-[15px] font-semibold text-white">{peekTitle}</span>
            <span className="tabular shrink-0 text-[12px] text-[#8b93a7]">{peekSub}</span>
          </span>
        )}
      </button>
      {sheet !== 'peek' && (
        <div className="thin-scroll min-h-0 flex-1 overflow-y-auto">
          <PanelBody onShared={onShared} />
        </div>
      )}
    </div>
  );
}
