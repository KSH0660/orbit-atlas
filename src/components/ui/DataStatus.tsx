'use client';

import { useEffect, useState } from 'react';
import { useAtlas } from '@/store/atlas';
import { relTime } from './format';

function useNow(intervalMs = 30_000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}

function useFreshness() {
  const catalog = useAtlas((s) => s.catalog);
  const origin = useAtlas((s) => s.loadOrigin);
  if (!catalog) return undefined;
  const src = catalog.source;
  const live = origin === 'api' && src.mode === 'live';
  const label = live ? 'Live' : src.mode === 'warm-cache' || origin === 'browser-cache' ? 'Cached' : 'Snapshot';
  return { live, label, fetchedAt: Date.parse(src.elementsFetchedAt), src, origin };
}

/** Compact pill for the top bar: status icon + label + age (never color alone). */
export function DataStatusPill() {
  const f = useFreshness();
  const now = useNow();
  if (!f) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 px-2.5 py-1 text-[11px] text-[#8b93a7]">
        Loading orbits…
      </span>
    );
  }
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[11px] text-[#c6cbd8]"
      title={`${f.src.elementsProvider} · fetched ${new Date(f.fetchedAt).toUTCString()}${f.src.note ? ` · ${f.src.note}` : ''}`}
    >
      {f.live ? (
        <span className="live-dot h-1.5 w-1.5 rounded-full bg-[#0ca30c]" aria-hidden />
      ) : (
        <span className="text-[#fab219]" aria-hidden>
          ◆
        </span>
      )}
      <span className="font-semibold text-white">{f.label}</span>
      <span className="hidden sm:inline">· updated {relTime(f.fetchedAt, now)}</span>
    </span>
  );
}

/** Provenance footer for the context panel. */
export function DataSource() {
  const f = useFreshness();
  const warning = useAtlas((s) => s.loadWarning);
  if (!f) return null;
  const fetched = new Date(f.fetchedAt);
  return (
    <div className="space-y-1 text-[10.5px] leading-relaxed text-[#8b93a7]">
      <div>
        <span className="text-[#c6cbd8]">Orbits:</span> {f.src.elementsProvider}, fetched{' '}
        <time dateTime={fetched.toISOString()}>{fetched.toISOString().replace('T', ' ').slice(0, 16)} UTC</time> · newest epoch{' '}
        {f.src.newestEpoch.replace('T', ' ').slice(0, 16)} UTC · SGP4 propagation
      </div>
      <div>
        <span className="text-[#c6cbd8]">Metadata:</span> {f.src.metadataProvider} ({f.src.metadataUpdatedAt.slice(0, 10)})
      </div>
      {(f.src.note || warning) && <div className="text-[#fab219]">◆ {f.src.note ?? 'Live source unavailable; showing a cached copy.'}</div>}
    </div>
  );
}
