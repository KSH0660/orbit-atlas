'use client';

import { useMemo } from 'react';
import * as THREE from 'three';

/** A sparse, static star field: a depth and rotation cue, kept dim on purpose. */
export function Stars({ count = 3500 }: { count?: number }) {
  const geometry = useMemo(() => {
    const pos = new Float32Array(count * 3);
    const bright = new Float32Array(count);
    let seed = 1337;
    const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
    for (let i = 0; i < count; i++) {
      const u = rnd() * 2 - 1;
      const t = rnd() * Math.PI * 2;
      const r = Math.sqrt(1 - u * u);
      pos.set([r * Math.cos(t) * 400, u * 400, r * Math.sin(t) * 400], i * 3);
      bright[i] = Math.pow(rnd(), 3);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('aBright', new THREE.BufferAttribute(bright, 1));
    return g;
  }, [count]);

  const material = useMemo(
    () =>
      new THREE.ShaderMaterial({
        transparent: true,
        depthWrite: false,
        vertexShader: /* glsl */ `
          attribute float aBright;
          varying float vB;
          void main() {
            vB = aBright;
            gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
            gl_PointSize = 0.8 + aBright * 1.8;
          }`,
        fragmentShader: /* glsl */ `
          varying float vB;
          void main() {
            float d = length(gl_PointCoord - 0.5);
            if (d > 0.5) discard;
            gl_FragColor = vec4(vec3(0.75, 0.82, 1.0), (0.12 + vB * 0.5) * smoothstep(0.5, 0.0, d));
          }`,
      }),
    [],
  );

  return <points geometry={geometry} material={material} renderOrder={-1} frustumCulled={false} />;
}
