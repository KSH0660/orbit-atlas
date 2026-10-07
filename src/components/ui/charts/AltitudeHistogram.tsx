'use client';

import { useMemo, useRef, useState } from 'react';
import { ALT_BIN_COUNT, altToUnit, binToAlt, unitToAlt } from '@/lib/query/stats';
import { fmt } from '../format';

export interface HistLayer {
  counts: Uint32Array;
  color: string;
  label: string;
}

const TICKS = [200, 500, 1000, 2000, 5000, 10000, 20000, 36000];
const tickLabel = (km: number) => (km >= 1000 ? `${km / 1000}k` : String(km));
const ZONES = [
  { label: 'LEO', from: 150, to: 2000 },
  { label: 'MEO', from: 2000, to: 35286 },
  { label: 'GEO', from: 35286, to: 36286 },
];

/**
 * Where satellites concentrate, by altitude, on a log-altitude axis.
 * Bar heights are log-scaled too (stated on the chart) so the GNSS shell and
 * GEO spike stay visible next to Starlink's thousands. Drag to filter by band.
 */
export function AltitudeHistogram({
  base,
  layers = [],
  range,
  marker,
  onRange,
  height = 64,
}: {
  base: Uint32Array;
  layers?: HistLayer[];
  range?: [number, number];
  marker?: number;
  onRange?: (r: [number, number] | undefined) => void;
  height?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<{ a: number; b: number } | null>(null);
  const [hover, setHover] = useState<number | null>(null);

  const max = useMemo(() => {
    let m = 1;
    for (let i = 0; i < base.length; i++) m = Math.max(m, base[i]);
    for (const l of layers) for (let i = 0; i < l.counts.length; i++) m = Math.max(m, l.counts[i]);
    return m;
  }, [base, layers]);
  const h = (c: number) => (c <= 0 ? 0 : Math.max(1.5, (Math.log10(1 + c) / Math.log10(1 + max)) * (height - 4)));

  const unitAt = (clientX: number) => {
    const r = ref.current!.getBoundingClientRect();
    return Math.min(1, Math.max(0, (clientX - r.left) / r.width));
  };
  const binAtUnit = (u: number) => Math.min(ALT_BIN_COUNT - 1, Math.floor(u * ALT_BIN_COUNT));

  const shown = drag ? ([Math.min(drag.a, drag.b), Math.max(drag.a, drag.b)] as [number, number]) : undefined;
  const sel = shown ?? (range ? [altToUnit(range[0]), altToUnit(range[1])] : undefined);
  const barW = 100 / ALT_BIN_COUNT;
  const hb = hover !== null ? hover : null;

  return (
    <div className="select-none">
      <div
        ref={ref}
        className="relative cursor-crosshair touch-none"
        style={{ height }}
        role="img"
        aria-label="Satellites by altitude (log scale). Drag to filter by altitude band."
        onPointerDown={(e) => {
          if (!onRange) return;
          (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
          const u = unitAt(e.clientX);
          setDrag({ a: u, b: u });
        }}
        onPointerMove={(e) => {
          const u = unitAt(e.clientX);
          setHover(binAtUnit(u));
          if (drag) setDrag({ a: drag.a, b: u });
        }}
        onPointerLeave={() => setHover(null)}
        onPointerUp={() => {
          if (!drag || !onRange) return;
          let lo = Math.min(drag.a, drag.b);
          let hi = Math.max(drag.a, drag.b);
          if (hi - lo < 1 / ALT_BIN_COUNT) {
            // a click selects the bin under the pointer
            const b = binAtUnit(lo);
            lo = b / ALT_BIN_COUNT;
            hi = (b + 1) / ALT_BIN_COUNT;
          }
          setDrag(null);
          onRange([Math.floor(unitToAlt(lo)), Math.ceil(unitToAlt(hi))]);
        }}
      >
        <svg className="absolute inset-0 h-full w-full" viewBox={`0 0 100 ${height}`} preserveAspectRatio="none">
          {ZONES.map((z, k) => (
            <rect
              key={z.label}
              x={altToUnit(z.from) * 100}
              width={(altToUnit(z.to) - altToUnit(z.from)) * 100}
              y={0}
              height={height}
              fill={k % 2 === 0 ? 'rgba(140,200,255,0.045)' : 'rgba(140,200,255,0.0)'}
            />
          ))}
          {sel && (
            <rect x={sel[0] * 100} width={Math.max(0.4, (sel[1] - sel[0]) * 100)} y={0} height={height} fill="rgba(233,244,255,0.12)" stroke="rgba(233,244,255,0.5)" strokeWidth={0.3} vectorEffect="non-scaling-stroke" />
          )}
          {Array.from(base, (c, i) => (
            <rect key={`b${i}`} x={i * barW + barW * 0.12} width={barW * 0.76} y={height - h(c)} height={h(c)} rx={0.4} fill={layers.length ? 'rgba(160,172,200,0.28)' : hb === i ? '#b9c6e4' : '#7f8db0'} />
          ))}
          {layers.map((l, li) =>
            Array.from(l.counts, (c, i) =>
              c ? (
                <rect
                  key={`l${li}-${i}`}
                  x={i * barW + barW * (layers.length > 1 ? 0.12 + li * 0.38 : 0.12)}
                  width={barW * (layers.length > 1 ? 0.38 : 0.76)}
                  y={height - h(c)}
                  height={h(c)}
                  rx={0.4}
                  fill={l.color}
                />
              ) : null,
            ),
          )}
          {marker !== undefined && (
            <line x1={altToUnit(marker) * 100} x2={altToUnit(marker) * 100} y1={0} y2={height} stroke="#e9f4ff" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
          )}
        </svg>
        {hb !== null && (
          <div
            className="pointer-events-none absolute -top-9 z-10 -translate-x-1/2 whitespace-nowrap rounded-md border border-white/10 bg-[#0b1020] px-2 py-1 text-[11px] text-white shadow-lg"
            style={{ left: `${((hb + 0.5) / ALT_BIN_COUNT) * 100}%` }}
          >
            <span className="tabular font-semibold">{fmt(base[hb])}</span>
            {layers.map((l) => (
              <span key={l.label} className="tabular ml-2" style={{ color: l.color }}>
                {fmt(l.counts[hb])}
              </span>
            ))}
            <span className="ml-1.5 text-[#8b93a7]">
              at {fmt(binToAlt(hb))}–{fmt(binToAlt(hb + 1))} km
            </span>
          </div>
        )}
      </div>
      <div className="relative mt-1 h-3.5 text-[9.5px] text-[#8b93a7]">
        {TICKS.map((t) => (
          <span key={t} className="tabular absolute -translate-x-1/2" style={{ left: `${altToUnit(t) * 100}%` }}>
            {tickLabel(t)}
          </span>
        ))}
      </div>
      <div className="mt-0.5 flex justify-between text-[9.5px] uppercase tracking-wider text-[#8b93a7]">
        <span>LEO</span>
        <span>altitude, km · log scale</span>
        <span>MEO · GEO</span>
      </div>
    </div>
  );
}
