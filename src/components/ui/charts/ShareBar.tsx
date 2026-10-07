'use client';

import { useState } from 'react';
import { fmt, pct } from '../format';

export interface ShareItem {
  key: string;
  label: string;
  value: number;
  color: string;
}

/**
 * Part-to-whole bar (2px surface gaps between segments) with a direct-labelled
 * legend that doubles as the click target. Identity is never color-alone:
 * every segment is named in the list beneath it.
 */
export function ShareBar({
  items,
  total,
  onPick,
  maxRows = 4,
  active,
}: {
  items: ShareItem[];
  total: number;
  onPick?: (key: string) => void;
  maxRows?: number;
  active?: string[];
}) {
  const [hover, setHover] = useState<string | null>(null);
  const nonzero = items.filter((i) => i.value > 0);
  const rows = [...nonzero].sort((a, b) => b.value - a.value).slice(0, maxRows);
  const restCount = nonzero.length - rows.length;

  return (
    <div>
      <div className="flex h-2.5 w-full gap-[2px] overflow-hidden rounded-[4px]">
        {nonzero.map((it) => (
          <button
            key={it.key}
            type="button"
            title={`${it.label}: ${fmt(it.value)} (${pct(it.value, total)})`}
            onMouseEnter={() => setHover(it.key)}
            onMouseLeave={() => setHover(null)}
            onClick={() => onPick?.(it.key)}
            className="h-full min-w-[2px] transition-opacity first:rounded-l-[4px] last:rounded-r-[4px]"
            style={{
              flexGrow: it.value,
              background: it.color,
              opacity: hover && hover !== it.key ? 0.35 : active?.length && !active.includes(it.key) ? 0.35 : 1,
            }}
            aria-label={`${it.label}: ${fmt(it.value)}`}
          />
        ))}
      </div>
      <ul className="mt-2 grid grid-cols-2 gap-x-3 gap-y-0.5">
        {rows.map((it) => (
          <li key={it.key}>
            <button
              type="button"
              onMouseEnter={() => setHover(it.key)}
              onMouseLeave={() => setHover(null)}
              onClick={() => onPick?.(it.key)}
              className={`group flex w-full items-center gap-1.5 rounded px-1 py-0.5 text-left text-[12px] hover:bg-white/5 ${
                hover === it.key ? 'bg-white/5' : ''
              }`}
            >
              <span className="h-2 w-2 shrink-0 rounded-[2px]" style={{ background: it.color }} />
              <span className="min-w-0 flex-1 truncate text-[#c6cbd8] group-hover:text-white">{it.label}</span>
              <span className="tabular text-white">{fmt(it.value)}</span>
            </button>
          </li>
        ))}
      </ul>
      {restCount > 0 && <div className="mt-0.5 px-1 text-[10.5px] text-[#8b93a7]">+{restCount} more in the bar above</div>}
    </div>
  );
}
