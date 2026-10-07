'use client';

import { useEffect, useRef } from 'react';
import { MISSIONS, REGIMES, countryFlag } from '@/lib/data/taxonomy';
import { runtime } from '@/lib/sim/runtime';
import { useAtlas } from '@/store/atlas';
import { fmt } from './format';

/** Name, operator and altitude next to the cursor — enough to decide whether to click. */
export function HoverTooltip() {
  const hovered = useAtlas((s) => s.hovered);
  const selected = useAtlas((s) => s.selected);
  const catalog = useAtlas((s) => s.catalog);
  const el = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let raf = 0;
    const loop = () => {
      raf = requestAnimationFrame(loop);
      const p = runtime.hoverScreen;
      if (el.current && p) el.current.style.transform = `translate(${p.x + 14}px, ${p.y - 12}px)`;
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  if (!catalog || hovered < 0 || hovered === selected) return null;
  const m = MISSIONS[catalog.mission[hovered]];
  const cc = catalog.countries[catalog.country[hovered]];
  return (
    <div ref={el} className="pointer-events-none fixed left-0 top-0 z-40 hidden max-w-[260px] rounded-lg border border-white/10 bg-[#0b1020]/90 px-2.5 py-1.5 shadow-xl backdrop-blur md:block">
      <div className="truncate text-[12.5px] font-semibold text-white">{catalog.names[hovered]}</div>
      <div className="truncate text-[11px] text-[#c6cbd8]">
        {countryFlag(cc)} {catalog.operators[catalog.operator[hovered]]}
      </div>
      <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-[#8b93a7]">
        <span className="h-1.5 w-1.5 rounded-full" style={{ background: m.color }} />
        {m.short} · {REGIMES[catalog.regime[hovered]].id} · <span className="tabular">{fmt(catalog.meanAltKm[hovered])} km</span>
      </div>
    </div>
  );
}
