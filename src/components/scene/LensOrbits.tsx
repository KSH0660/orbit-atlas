'use client';

import { useEffect, useMemo, useState } from 'react';
import * as THREE from 'three';
import type { Catalog } from '@/lib/catalog/catalog';
import { BLOCS, MISSIONS } from '@/lib/data/taxonomy';
import { simClock } from '@/lib/sim/clock';
import { orbitPath, satrecFor } from '@/lib/sim/single';
import { useAtlas } from '@/store/atlas';

const MAX_ORBITS = 320;

/**
 * For small lenses (GPS, Galileo, stations, a country's fleet…) draw every
 * member's orbit. This is what makes orbital *planes* visible: GPS's six
 * rings, the GEO belt, polar sun-synchronous paths.
 */
export function LensOrbits({ catalog }: { catalog: Catalog }) {
  const lensMask = useAtlas((s) => s.lensMask);
  const compareMask = useAtlas((s) => s.compareMask);
  const colorBy = useAtlas((s) => s.colorBy);
  const [tick, setTick] = useState(0);

  // Recompute occasionally so long-running sessions keep up with precession.
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 60_000);
    return () => clearInterval(id);
  }, []);

  const geometry = useMemo(() => {
    void tick;
    const groups: { mask: Uint8Array; color?: string }[] = [];
    if (lensMask) groups.push({ mask: lensMask, color: compareMask ? '#3987e5' : undefined });
    if (compareMask) groups.push({ mask: compareMask, color: '#d95926' });
    const rows: { i: number; color: THREE.Color }[] = [];
    for (const g of groups) {
      const idx: number[] = [];
      for (let i = 0; i < catalog.count && idx.length <= MAX_ORBITS; i++) if (g.mask[i]) idx.push(i);
      if (idx.length > MAX_ORBITS) continue;
      for (const i of idx) {
        const hex = g.color ?? (colorBy === 'owner' ? BLOCS[catalog.bloc[i]].color : MISSIONS[catalog.mission[i]].color);
        rows.push({ i, color: new THREE.Color(hex) });
        if (rows.length > MAX_ORBITS) break;
      }
    }
    if (!rows.length) return null;
    const SAMPLES = rows.length > 90 ? 96 : 160;
    const now = simClock.now();
    const pos = new Float32Array(rows.length * SAMPLES * 6);
    const col = new Float32Array(rows.length * SAMPLES * 6);
    let o = 0;
    for (const { i, color } of rows) {
      const s = satrecFor(catalog, i);
      if (!s) continue;
      const p = orbitPath(s, now, catalog.periodMin[i], SAMPLES);
      for (let k = 0; k < SAMPLES; k++) {
        pos.set([p[k * 3], p[k * 3 + 1], p[k * 3 + 2], p[k * 3 + 3], p[k * 3 + 4], p[k * 3 + 5]], o);
        col.set([color.r, color.g, color.b, color.r, color.g, color.b], o);
        o += 6;
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos.subarray(0, o), 3));
    g.setAttribute('color', new THREE.BufferAttribute(col.subarray(0, o), 3));
    // Satellites sharing a plane share a path; fade with count so stacked
    // rings stay readable instead of saturating.
    return { g, opacity: Math.min(0.35, 2.2 / Math.sqrt(rows.length)) };
  }, [catalog, lensMask, compareMask, colorBy, tick]);

  useEffect(() => () => geometry?.g.dispose(), [geometry]);
  if (!geometry) return null;
  return (
    <lineSegments geometry={geometry.g} renderOrder={2}>
      <lineBasicMaterial vertexColors transparent opacity={geometry.opacity} depthWrite={false} />
    </lineSegments>
  );
}
