'use client';

import { useEffect, useRef } from 'react';
import { RINGS } from '@/lib/data/rings';
import { anchors } from '@/lib/sim/labels';
import { useAtlas } from '@/store/atlas';

/** DOM labels positioned from scene anchors in one rAF loop. */
export function SceneLabels() {
  const root = useRef<HTMLDivElement>(null);
  const catalog = useAtlas((s) => s.catalog);
  const selected = useAtlas((s) => s.selected);

  useEffect(() => {
    let raf = 0;
    const loop = () => {
      raf = requestAnimationFrame(loop);
      root.current?.querySelectorAll<HTMLElement>('[data-anchor]').forEach((el) => {
        const a = anchors.get(el.dataset.anchor!);
        if (!a || !a.visible) {
          el.style.opacity = '0';
          return;
        }
        el.style.opacity = '1';
        el.style.transform = `translate(${a.x}px, ${a.y}px)`;
      });
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <div ref={root} className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
      {RINGS.map((r) => (
        <div key={r.id} data-anchor={`ring-${r.id}`} className="absolute left-0 top-0 opacity-0 transition-opacity duration-300">
          <div className="-translate-x-1/2 -translate-y-1/2 whitespace-nowrap text-center leading-tight [text-shadow:0_0_6px_#03050b,0_0_2px_#03050b]">
            <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#b9c6e4]/75">{r.label}</div>
            <div className="text-[10px] text-[#8b93a7]/90">{r.sub}</div>
          </div>
        </div>
      ))}
      <div data-anchor="selected" className="absolute left-0 top-0 opacity-0">
        {catalog && selected >= 0 && (
          <div className="ml-4 -translate-y-1/2 whitespace-nowrap rounded-md border border-white/15 bg-[#0b1020]/80 px-2 py-0.5 text-[11px] font-medium text-white shadow-lg backdrop-blur">
            {catalog.names[selected]}
          </div>
        )}
      </div>
    </div>
  );
}
