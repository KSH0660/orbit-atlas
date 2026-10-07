'use client';

import { useFrame } from '@react-three/fiber';
import { useMemo } from 'react';
import * as THREE from 'three';
import { SCENE_UNIT_KM } from '@/lib/data/orbit';
import { RINGS } from '@/lib/data/rings';
import { hideAnchor, projectAnchor } from '@/lib/sim/labels';

function ringGeometry(r: number) {
  const pts: number[] = [];
  const N = 256;
  for (let k = 0; k < N; k++) {
    const a = (k / N) * Math.PI * 2;
    pts.push(Math.cos(a) * r, 0, Math.sin(a) * r);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
  return g;
}

/**
 * Altitude references in the equatorial plane. Without them, 550 km and
 * 1,200 km look the same; with them the three regimes read at a glance.
 */
export function RegimeRings() {
  const rings = useMemo(
    () => RINGS.map((r) => ({ ...r, radius: 1 + r.km / SCENE_UNIT_KM, geom: ringGeometry(1 + r.km / SCENE_UNIT_KM) })),
    [],
  );
  const tmp = useMemo(() => ({ right: new THREE.Vector3(), fwd: new THREE.Vector3(), v: new THREE.Vector3() }), []);

  useFrame(({ camera, size }) => {
    // Park each label near the front of its ring (the part closest to the
    // camera), which keeps labels in the open middle of the screen.
    tmp.right.setFromMatrixColumn(camera.matrixWorld, 0).setY(0);
    tmp.fwd.copy(camera.position).setY(0);
    if (tmp.right.lengthSq() < 1e-6 || tmp.fwd.lengthSq() < 1e-6) return;
    tmp.right.normalize();
    tmp.fwd.normalize();
    const camDist = camera.position.length();
    rings.forEach((r, k) => {
      const id = `ring-${r.id}`;
      if (camDist > r.radius * 7 || camDist < r.radius * 1.05) {
        hideAnchor(id);
        return;
      }
      const a = [0.95, 1.2, 1.38][k];
      const x = (tmp.right.x * Math.cos(a) + tmp.fwd.x * Math.sin(a)) * r.radius;
      const z = (tmp.right.z * Math.cos(a) + tmp.fwd.z * Math.sin(a)) * r.radius;
      projectAnchor(id, camera, size.width, size.height, x, 0, z, tmp.v);
    });
  });

  return (
    <group>
      {rings.map((r) => (
        <lineLoop key={r.id} geometry={r.geom}>
          <lineBasicMaterial color="#8fa6d6" transparent opacity={r.id === 'geo' ? 0.2 : 0.13} depthWrite={false} />
        </lineLoop>
      ))}
    </group>
  );
}
