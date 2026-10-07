'use client';

import { useMemo } from 'react';
import { BLOCS, MISSIONS } from '@/lib/data/taxonomy';
import { scopeInsights } from '@/lib/query/insights';
import type { Lens } from '@/lib/query/lens';
import { useAtlas } from '@/store/atlas';
import { applyLens } from '../actions';
import { AltitudeHistogram } from '../charts/AltitudeHistogram';
import { ShareBar } from '../charts/ShareBar';
import { allScope, useScopeStats } from '../derived';
import { fmt } from '../format';
import { InsightList, ScopeToggle, Section } from './parts';

/** Before any selection: the whole picture, scoped to what is in view. */
export function OverviewView({ scope, setScope }: { scope: 'view' | 'all'; setScope: (s: 'view' | 'all') => void }) {
  const catalog = useAtlas((s) => s.catalog)!;
  const data = useScopeStats(scope);
  const total = allScope(catalog).stats.total;
  const insights = useMemo(
    () => (data ? scopeInsights(catalog, data.stats, scope === 'view' ? 'in view' : 'in total') : []),
    [catalog, data, scope],
  );
  if (!data) return null;
  const s = data.stats;
  const pick = (lens: Lens) => applyLens(lens, { frame: true });

  return (
    <>
      <div className="px-4 pb-3 pt-4">
        <div className="flex items-center justify-between">
          <span className="text-[10.5px] font-semibold uppercase tracking-[0.13em] text-[#8b93a7]">Right now</span>
          <ScopeToggle scope={scope} onChange={setScope} />
        </div>
        <div className="mt-1.5 flex items-baseline gap-2">
          <span className="tabular text-[34px] font-semibold leading-none tracking-tight text-white">{fmt(total)}</span>
          <span className="text-[13px] text-[#c6cbd8]">active satellites in orbit</span>
        </div>
        <div className="mt-1.5 text-[12px] text-[#8b93a7]">
          {scope === 'view' ? (
            <>
              <span className="tabular font-semibold text-[#e9f4ff]">{fmt(s.total)}</span> in this view · the numbers below follow the camera
            </>
          ) : (
            <>Numbers below cover every active satellite</>
          )}
        </div>
      </div>

      {insights.length > 0 && (
        <Section title="Worth knowing">
          <InsightList items={insights.slice(0, 3)} />
        </Section>
      )}

      <Section title="Where they fly">
        <AltitudeHistogram base={s.altHist} onRange={(r) => r && applyLens({ altitude: r })} />
      </Section>

      <Section title="Who operates them">
        <ShareBar
          total={s.total}
          items={BLOCS.map((b, i) => ({ key: b.id, label: b.label, value: s.bloc[i], color: b.color }))}
          onPick={(k) => (k === 'OT' ? undefined : pick({ blocs: [k as (typeof BLOCS)[number]['id']] }))}
          maxRows={6}
        />
      </Section>

      <Section title="What they do">
        <ShareBar
          total={s.total}
          items={MISSIONS.map((m, i) => ({ key: m.id, label: m.short, value: s.mission[i], color: m.color }))}
          onPick={(k) => pick({ missions: [k as (typeof MISSIONS)[number]['id']] })}
          maxRows={6}
        />
      </Section>

      {insights.length > 3 && (
        <Section title={scope === 'view' ? 'Also in this view' : 'More facts'}>
          <InsightList items={insights.slice(3)} />
        </Section>
      )}
    </>
  );
}
