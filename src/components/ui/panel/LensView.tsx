'use client';

import { useMemo } from 'react';
import { BLOCS, CONSTELLATIONS, MISSIONS, REGIMES } from '@/lib/data/taxonomy';
import { lensInsights } from '@/lib/query/insights';
import { lensLabel, presetForLens, refineLens } from '@/lib/query/lens';
import { topEntries } from '@/lib/query/stats';
import { useAtlas } from '@/store/atlas';
import { applyLens } from '../actions';
import { AltitudeHistogram } from '../charts/AltitudeHistogram';
import { ShareBar } from '../charts/ShareBar';
import { allScope, useMaskIndices, useScopeStats } from '../derived';
import { fmt, pct } from '../format';
import { CloseIcon, CompareIcon, FocusIcon } from '../icons';
import { ActionButton, InsightList, ScopeToggle, Section } from './parts';

/** A lens is active: only what's needed to understand that group. */
export function LensView({ scope, setScope }: { scope: 'view' | 'all'; setScope: (s: 'view' | 'all') => void }) {
  const catalog = useAtlas((s) => s.catalog)!;
  const lens = useAtlas((s) => s.lens);
  const mode = useAtlas((s) => s.mode);
  const mask = useAtlas((s) => s.lensMask);
  const setMode = useAtlas((s) => s.setMode);
  const openCommand = useAtlas((s) => s.openCommand);
  const clearLens = useAtlas((s) => s.clearLens);

  const lensIdx = useMaskIndices(mask);
  const all = allScope(catalog).stats;
  const lensAll = useScopeStats('all', mask);
  const lensScope = useScopeStats(scope, mask);
  const scopeAll = useScopeStats(scope);

  const insights = useMemo(
    () => (lensAll && lensIdx ? lensInsights(catalog, lensAll.stats, all, lensIdx, lens) : []),
    [catalog, lensAll, all, lensIdx, lens],
  );
  if (!lensAll || !lensScope || !scopeAll) return null;
  const ls = lensScope.stats;
  const preset = presetForLens(lens);
  const singleConstellation = lens.constellations?.length === 1 ? CONSTELLATIONS[lens.constellations[0]] : undefined;

  const topOps = topEntries(ls.operator, 5);

  return (
    <>
      <div className="px-4 pb-3 pt-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="text-[10.5px] font-semibold uppercase tracking-[0.13em] text-[#8b93a7]">Lens</div>
            <h2 className="mt-0.5 truncate text-[18px] font-semibold text-white">{lensLabel(lens)}</h2>
            <div className="truncate text-[12px] text-[#8b93a7]">
              {singleConstellation ? `${singleConstellation.operator} · ${singleConstellation.blurb}` : preset?.hint ?? 'Custom lens'}
            </div>
          </div>
          <button
            type="button"
            onClick={clearLens}
            className="rounded-md p-1 text-[#8b93a7] hover:bg-white/10 hover:text-white"
            aria-label="Clear lens"
          >
            <CloseIcon />
          </button>
        </div>
        <div className="mt-3 flex items-end justify-between">
          <div>
            <div className="tabular text-[30px] font-semibold leading-none text-white">{fmt(lensAll.stats.total)}</div>
            <div className="mt-1 text-[12px] text-[#8b93a7]">
              satellites · <span className="tabular text-[#c6cbd8]">{fmt(ls.total)}</span>{' '}
              {scope === 'view' ? 'in view' : 'total'}
              {scope === 'view' && scopeAll.stats.total > 0 && (
                <> ({pct(ls.total, scopeAll.stats.total)} of what you see)</>
              )}
            </div>
          </div>
          <ScopeToggle scope={scope} onChange={setScope} />
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5">
          <ActionButton active={mode === 'only'} onClick={() => setMode(mode === 'only' ? 'highlight' : 'only')} title="Hide everything else">
            <FocusIcon /> {mode === 'only' ? 'Showing only this' : 'Only show this'}
          </ActionButton>
          <ActionButton onClick={() => openCommand(true, 'compare')} title="Compare with another group">
            <CompareIcon /> Compare…
          </ActionButton>
        </div>
      </div>

      <InsightsBlock items={insights} />

      <Section title="Where they fly" aside={<span className="text-[10.5px] text-[#8b93a7]">lens vs. everything {scope === 'view' ? 'in view' : ''}</span>}>
        <AltitudeHistogram
          base={scopeAll.stats.altHist}
          layers={[{ counts: ls.altHist, color: '#e9f4ff', label: 'lens' }]}
          range={lens.altitude}
          onRange={(r) => applyLens(refineLens(lens, { altitude: r }), { keepSelection: true })}
        />
        <div className="mt-2 flex gap-3 text-[11.5px] text-[#c6cbd8]">
          {REGIMES.map((r, i) =>
            ls.regime[i] ? (
              <button
                key={r.id}
                type="button"
                onClick={() => applyLens(refineLens(lens, { regimes: [r.id] }))}
                className="hover:text-white"
              >
                <span className="font-semibold text-white">{r.id}</span> <span className="tabular">{fmt(ls.regime[i])}</span>
              </button>
            ) : null,
          )}
        </div>
      </Section>

      {!lens.blocs?.length && !lens.countries?.length && !singleConstellation && (
        <Section title="Who operates them">
          <ShareBar
            total={ls.total}
            items={BLOCS.map((b, i) => ({ key: b.id, label: b.label, value: ls.bloc[i], color: b.color }))}
            onPick={(k) => k !== 'OT' && applyLens(refineLens(lens, { blocs: [k as (typeof BLOCS)[number]['id']] }))}
          />
        </Section>
      )}

      {!lens.missions?.length && !lens.constellations?.length && (
        <Section title="What they do">
          <ShareBar
            total={ls.total}
            items={MISSIONS.map((m, i) => ({ key: m.id, label: m.short, value: ls.mission[i], color: m.color }))}
            onPick={(k) => applyLens(refineLens(lens, { missions: [k as (typeof MISSIONS)[number]['id']] }))}
          />
        </Section>
      )}

      {!lens.operators?.length && topOps.length > 1 && (
        <Section title="Top operators">
          <ul>
            {topOps.map(([op, n]) => (
              <li key={op}>
                <button
                  type="button"
                  onClick={() => applyLens(refineLens(lens, { operators: [catalog.operators[op]] }))}
                  className="flex w-full items-center gap-2 rounded px-1 py-1 text-left text-[12px] hover:bg-white/5"
                >
                  <span className="min-w-0 flex-1 truncate text-[#c6cbd8]">{catalog.operators[op]}</span>
                  <span className="h-1.5 w-16 overflow-hidden rounded-full bg-white/[0.06]">
                    <span className="block h-full rounded-full bg-[#8cc8ff]/70" style={{ width: pct(n, topOps[0][1]) }} />
                  </span>
                  <span className="tabular w-12 text-right text-white">{fmt(n)}</span>
                </button>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </>
  );
}

function InsightsBlock({ items }: { items: ReturnType<typeof lensInsights> }) {
  if (!items.length) return null;
  return (
    <Section title="Key numbers">
      <InsightList items={items} max={5} />
    </Section>
  );
}
