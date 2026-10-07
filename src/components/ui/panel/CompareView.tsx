'use client';

import type { ReactNode } from 'react';
import { REGIMES } from '@/lib/data/taxonomy';
import { inclinationModes, topEntries } from '@/lib/query/stats';
import { lensLabel } from '@/lib/query/lens';
import { useAtlas } from '@/store/atlas';
import { AltitudeHistogram } from '../charts/AltitudeHistogram';
import { allScope, useMaskIndices, useScopeStats } from '../derived';
import { fmt, pct } from '../format';
import { CloseIcon, SwapIcon } from '../icons';
import { ActionButton, Section } from './parts';

export const COMPARE_A = '#3987e5';
export const COMPARE_B = '#d95926';

/** Side-by-side numbers for two lenses. Same encoding on the globe: A blue, B orange. */
export function CompareView() {
  const catalog = useAtlas((s) => s.catalog)!;
  const lens = useAtlas((s) => s.lens);
  const compare = useAtlas((s) => s.compare)!;
  const aMask = useAtlas((s) => s.lensMask);
  const bMask = useAtlas((s) => s.compareMask);
  const swap = useAtlas((s) => s.swapCompare);
  const setCompare = useAtlas((s) => s.setCompare);
  const mode = useAtlas((s) => s.mode);
  const setMode = useAtlas((s) => s.setMode);

  const a = useScopeStats('all', aMask);
  const b = useScopeStats('all', bMask);
  const av = useScopeStats('view', aMask);
  const bv = useScopeStats('view', bMask);
  const aIdx = useMaskIndices(aMask);
  const bIdx = useMaskIndices(bMask);
  const total = allScope(catalog).stats.total;
  if (!a || !b || !av || !bv || !aIdx || !bIdx) return null;
  const A = a.stats;
  const B = b.stats;
  const topOp = (m: Map<number, number>) => {
    const [t] = topEntries(m, 1);
    return t ? catalog.operators[t[0]] : '—';
  };
  const incl = (idx: Uint32Array) => {
    const [m] = inclinationModes(catalog, idx, 1);
    return m ? `${m.inc}°` : '—';
  };

  const rows: { label: string; a: ReactNode; b: ReactNode; winner?: 'a' | 'b' }[] = [
    { label: 'Satellites', a: fmt(A.total), b: fmt(B.total), winner: A.total === B.total ? undefined : A.total > B.total ? 'a' : 'b' },
    { label: 'Share of all active', a: pct(A.total, total), b: pct(B.total, total) },
    { label: 'In view now', a: fmt(av.stats.total), b: fmt(bv.stats.total) },
    { label: 'Median altitude', a: `${fmt(A.medianAltKm)} km`, b: `${fmt(B.medianAltKm)} km` },
    ...REGIMES.map((r, i) => ({ label: `in ${r.id}`, a: fmt(A.regime[i]), b: fmt(B.regime[i]) })).filter(
      (_, i) => A.regime[i] + B.regime[i] > 0,
    ),
    {
      label: 'Launched last 12 mo.',
      a: fmt(A.launchedLast12Months),
      b: fmt(B.launchedLast12Months),
      winner: A.launchedLast12Months === B.launchedLast12Months ? undefined : A.launchedLast12Months > B.launchedLast12Months ? 'a' : 'b',
    },
    { label: 'Main inclination', a: incl(aIdx), b: incl(bIdx) },
    { label: 'Top operator', a: topOp(A.operator), b: topOp(B.operator) },
  ];

  return (
    <>
      <div className="px-4 pb-3 pt-4">
        <div className="flex items-center justify-between">
          <span className="text-[10.5px] font-semibold uppercase tracking-[0.13em] text-[#8b93a7]">Compare</span>
          <button type="button" onClick={() => setCompare(undefined)} className="rounded-md p-1 text-[#8b93a7] hover:bg-white/10 hover:text-white" aria-label="End comparison">
            <CloseIcon />
          </button>
        </div>
        <div className="mt-2 grid grid-cols-[1fr_auto_1fr] items-center gap-2">
          <LensChip color={COMPARE_A} label={lensLabel(lens)} />
          <button type="button" onClick={swap} className="rounded-md p-1 text-[#8b93a7] hover:bg-white/10 hover:text-white" aria-label="Swap">
            <SwapIcon />
          </button>
          <LensChip color={COMPARE_B} label={lensLabel(compare)} />
        </div>
        <div className="mt-3">
          <ActionButton active={mode === 'only'} onClick={() => setMode(mode === 'only' ? 'highlight' : 'only')}>
            {mode === 'only' ? 'Showing only these two' : 'Hide everything else'}
          </ActionButton>
        </div>
      </div>

      <Section title="Side by side">
        <table className="w-full text-[12.5px]">
          <tbody>
            {rows.map((r) => (
              <tr key={r.label} className="border-t border-white/[0.05] first:border-t-0">
                <td className={`tabular py-1.5 pr-2 text-right ${r.winner === 'a' ? 'font-semibold text-white' : 'text-[#c6cbd8]'}`}>{r.a}</td>
                <td className="w-[38%] px-1 py-1.5 text-center text-[10.5px] uppercase tracking-wider text-[#8b93a7]">{r.label}</td>
                <td className={`tabular py-1.5 pl-2 text-left ${r.winner === 'b' ? 'font-semibold text-white' : 'text-[#c6cbd8]'}`}>{r.b}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section title="Where they fly">
        <AltitudeHistogram
          base={allScope(catalog).stats.altHist}
          layers={[
            { counts: A.altHist, color: COMPARE_A, label: 'A' },
            { counts: B.altHist, color: COMPARE_B, label: 'B' },
          ]}
        />
      </Section>
    </>
  );
}

function LensChip({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex min-w-0 items-center gap-2 rounded-lg border border-white/10 bg-white/[0.04] px-2.5 py-1.5">
      <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: color }} />
      <span className="truncate text-[12.5px] font-medium text-white">{label}</span>
    </div>
  );
}
