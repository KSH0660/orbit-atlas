'use client';

import { Billboard, Line } from '@react-three/drei';
import { useFrame } from '@react-three/fiber';
import { useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import type { Line2 } from 'three-stdlib';
import type { Catalog } from '@/lib/catalog/catalog';
import { simClock } from '@/lib/sim/clock';
import { hideAnchor, projectAnchor } from '@/lib/sim/labels';
import { orbitPath, satrecFor, stateAt } from '@/lib/sim/single';
import { useAtlas } from '@/store/atlas';

const SAMPLES = 240;
const SELECT_COLOR = '#e9f4ff';

/**
 * Selected satellite: bright orbit (future half solid, past half faint),
 * pulsing marker, nadir line and a name tag. Uses a precise per-frame SGP4
 * state rather than the interpolated cloud.
 */
export function Selection({ catalog }: { catalog: Catalog }) {
  const selected = useAtlas((s) => s.selected);
  if (selected < 0) return null;
  return <SelectionInner key={selected} catalog={catalog} index={selected} />;
}

function SelectionInner({ catalog, index }: { catalog: Catalog; index: number }) {
  const satrec = useMemo(() => satrecFor(catalog, index), [catalog, index]);
  const period = catalog.periodMin[index];
  const [path, setPath] = useState<Float32Array | null>(() =>
    satrec ? orbitPath(satrec, simClock.now(), period, SAMPLES) : null,
  );
  const marker = useRef<THREE.Group>(null);
  const ring = useRef<THREE.Mesh>(null);
  const nadir = useRef<Line2>(null);
  const lastPathAt = useRef(0);

  const [past, future] = useMemo(() => {
    if (!path) return [null, null];
    const pts: [number, number, number][] = [];
    for (let k = 0; k <= SAMPLES; k++) pts.push([path[k * 3], path[k * 3 + 1], path[k * 3 + 2]]);
    const mid = SAMPLES / 2;
    return [pts.slice(0, mid + 1), pts.slice(mid)];
  }, [path]);

  const v = useMemo(() => new THREE.Vector3(), []);
  useEffect(() => () => hideAnchor('selected'), []);

  useFrame(({ camera, size }) => {
    if (!satrec) return;
    const now = simClock.now();
    const st = stateAt(satrec, now);
    if (!st) return;
    projectAnchor('selected', camera, size.width, size.height, st.x, st.y, st.z, v);
    if (marker.current) {
      marker.current.position.set(st.x, st.y, st.z);
      // constant screen size
      const d = camera.position.distanceTo(marker.current.position);
      marker.current.scale.setScalar(d * 0.018);
    }
    if (ring.current) {
      const t = (performance.now() / 1400) % 1;
      ring.current.scale.setScalar(1 + t * 1.6);
      (ring.current.material as THREE.MeshBasicMaterial).opacity = 0.85 * (1 - t);
    }
    if (nadir.current) {
      const r = Math.hypot(st.x, st.y, st.z);
      const g = nadir.current.geometry as unknown as { setPositions: (p: number[]) => void };
      g.setPositions([st.x, st.y, st.z, st.x / r, st.y / r, st.z / r]);
    }
    // Re-center the orbit around "now" as time advances (orbits precess slowly).
    if (Math.abs(now - lastPathAt.current) > (period * 60000) / 24) {
      lastPathAt.current = now;
      setPath(orbitPath(satrec, now, period, SAMPLES));
    }
  });

  if (!satrec) return null;
  return (
    <group>
      {past && (
        <Line points={past} color={SELECT_COLOR} lineWidth={1.4} transparent opacity={0.28} depthWrite={false} />
      )}
      {future && (
        <Line points={future} color={SELECT_COLOR} lineWidth={2.4} transparent opacity={0.92} depthWrite={false} />
      )}
      <Line
        ref={nadir}
        points={[
          [0, 0, 0],
          [0, 0, 1],
        ]}
        color={SELECT_COLOR}
        lineWidth={1}
        transparent
        opacity={0.35}
        depthWrite={false}
      />
      <group ref={marker}>
        <Billboard>
          <mesh>
            <ringGeometry args={[0.55, 0.7, 48]} />
            <meshBasicMaterial color={SELECT_COLOR} transparent depthWrite={false} toneMapped={false} />
          </mesh>
          <mesh ref={ring}>
            <ringGeometry args={[0.55, 0.62, 48]} />
            <meshBasicMaterial color={SELECT_COLOR} transparent depthWrite={false} toneMapped={false} />
          </mesh>
        </Billboard>
      </group>
    </group>
  );
}
