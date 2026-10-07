'use client';

import type { ReactNode } from 'react';
import type { Insight } from '@/lib/query/insights';
import { applyLens } from '../actions';

export function Section({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="border-t border-white/[0.07] px-4 py-3 first:border-t-0">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-[10.5px] font-semibold uppercase tracking-[0.13em] text-[#8b93a7]">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

export function InsightList({ items, max = 4 }: { items: Insight[]; max?: number }) {
  if (!items.length) return null;
  return (
    <ul className="space-y-1">
      {items.slice(0, max).map((it) => {
        const body = (
          <>
            <span className="tabular min-w-[4.5rem] shrink-0 text-[15px] font-semibold text-white">{it.value}</span>
            <span className="text-[12px] leading-snug text-[#c6cbd8]">{it.label}</span>
          </>
        );
        return (
          <li key={it.id} className="fade-up">
            {it.lens ? (
              <button
                type="button"
                onClick={() => applyLens(it.lens!, { frame: true })}
                className="group flex w-full items-baseline gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-white/[0.06]"
                title="Show these on the globe"
              >
                {body}
                <span className="ml-auto self-center text-[#8b93a7] opacity-0 transition-opacity group-hover:opacity-100">→</span>
              </button>
            ) : (
              <div className="flex items-baseline gap-2 px-2 py-1.5">{body}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="text-[10.5px] uppercase tracking-wider text-[#8b93a7]">{label}</div>
      <div className="tabular truncate text-[14px] font-medium text-white">{value}</div>
      {sub && <div className="truncate text-[11px] text-[#8b93a7]">{sub}</div>}
    </div>
  );
}

export function ScopeToggle({ scope, onChange }: { scope: 'view' | 'all'; onChange: (s: 'view' | 'all') => void }) {
  return (
    <div className="flex shrink-0 whitespace-nowrap rounded-md bg-white/[0.06] p-0.5 text-[11px]" role="tablist" aria-label="Statistics scope">
      {(['view', 'all'] as const).map((s) => (
        <button
          key={s}
          type="button"
          role="tab"
          aria-selected={scope === s}
          onClick={() => onChange(s)}
          className={`rounded px-2 py-0.5 ${scope === s ? 'bg-white/15 text-white' : 'text-[#8b93a7] hover:text-white'}`}
        >
          {s === 'view' ? 'In view' : 'All'}
        </button>
      ))}
    </div>
  );
}

export function ActionButton({
  onClick,
  children,
  active,
  title,
}: {
  onClick: () => void;
  children: ReactNode;
  active?: boolean;
  title?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-pressed={active}
      className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[12px] font-medium transition-colors ${
        active
          ? 'border-[#8cc8ff]/60 bg-[#8cc8ff]/15 text-white'
          : 'border-white/10 bg-white/[0.04] text-[#c6cbd8] hover:border-white/25 hover:text-white'
      }`}
    >
      {children}
    </button>
  );
}
