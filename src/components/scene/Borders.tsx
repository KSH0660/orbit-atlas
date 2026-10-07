'use client';

import { useEffect, useMemo, useState } from 'react';
import * as THREE from 'three';
import { mesh } from 'topojson-client';
import type { GeometryCollection, Topology } from 'topojson-specification';
import { latLonToEarthFixed } from '@/lib/sim/frames';

/** Country borders and coastlines (Natural Earth 1:110m via world-atlas). Helps orientation. */
export function Borders() {
  const [positions, setPositions] = useState<Float32Array | null>(null);

  useEffect(() => {
    let alive = true;
    fetch('/geo/countries-110m.json')
      .then((r) => r.json())
      .then((topo: Topology<{ countries: GeometryCollection }>) => {
        const m = mesh(topo, topo.objects.countries);
        const segs: number[] = [];
        for (const line of m.coordinates) {
          for (let k = 0; k < line.length - 1; k++) {
            const a = latLonToEarthFixed(line[k][1], line[k][0], 1.0012);
            const b = latLonToEarthFixed(line[k + 1][1], line[k + 1][0], 1.0012);
            segs.push(...a, ...b);
          }
        }
        if (alive) setPositions(new Float32Array(segs));
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  const geom = useMemo(() => {
    if (!positions) return null;
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    return g;
  }, [positions]);

  if (!geom) return null;
  return (
    <lineSegments geometry={geom} renderOrder={1}>
      <lineBasicMaterial color="#9fb6da" transparent opacity={0.22} depthWrite={false} />
    </lineSegments>
  );
}
