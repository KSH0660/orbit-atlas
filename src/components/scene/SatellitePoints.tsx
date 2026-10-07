'use client';

import { useFrame, useThree } from '@react-three/fiber';
import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import type { Catalog } from '@/lib/catalog/catalog';
import { BLOCS, MISSIONS } from '@/lib/data/taxonomy';
import { simClock } from '@/lib/sim/clock';
import { runtime } from '@/lib/sim/runtime';
import { computeStyles, useAtlas } from '@/store/atlas';

/**
 * Every satellite in ONE draw call. Positions arrive from the SGP4 worker as
 * two snapshots (A at tA, B at tB); the vertex shader blends them with uMix,
 * so the CPU never touches per-satellite positions per frame.
 *
 * aStyle: 0 hidden · 1 ghost (context) · 2 base · 3 focus · 4 compare A · 5 compare B
 */
const vertex = /* glsl */ `
  attribute vec3 positionB;
  attribute float aMission;
  attribute float aBloc;
  attribute float aStyle;
  uniform float uMix;
  uniform float uPixelRatio;
  uniform float uSelected;
  uniform float uHovered;
  uniform float uColorBy;
  uniform float uTime;
  uniform float uScale;
  uniform float uFocusScale;
  uniform vec3 uMissionColors[${MISSIONS.length}];
  uniform vec3 uBlocColors[${BLOCS.length}];
  uniform vec3 uCompareA;
  uniform vec3 uCompareB;
  varying vec3 vColor;
  varying float vAlpha;
  varying float vCore;

  void main() {
    if (aStyle < 0.5 || dot(position, position) < 0.25) {
      gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
      gl_PointSize = 0.0;
      return;
    }
    vec3 p = mix(position, positionB, uMix);
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;

    vec3 base = uColorBy < 0.5 ? uMissionColors[int(aMission)] : uBlocColors[int(aBloc)];
    vec3 col = base;
    float size = 2.0;
    float alpha = 0.85;
    vCore = 0.0;
    if (aStyle < 1.5) {            // ghost: keeps context, never competes
      size = 1.25; alpha = 0.2;
      col = mix(base, vec3(0.62, 0.68, 0.8), 0.55) * 0.55;
    } else if (aStyle < 2.5) {     // base
      size = 2.3; alpha = 0.9;
    } else if (aStyle < 3.5) {     // focus: brighter than 1.0 so bloom picks it up
      size = 3.6 * uFocusScale; alpha = 1.0; col = base * 1.65 + 0.06; vCore = 1.0;
    } else if (aStyle < 4.5) {
      size = 3.6 * uFocusScale; alpha = 1.0; col = uCompareA * 1.65 + 0.06; vCore = 1.0;
    } else {
      size = 3.6 * uFocusScale; alpha = 1.0; col = uCompareB * 1.65 + 0.06; vCore = 1.0;
    }

    // Mild perspective: nearer satellites grow a little (depth cue), far ones shrink.
    float dist = -mv.z;
    size *= clamp(pow(7.0 / dist, 0.45), 0.7, 2.4) * uScale;

    float idx = float(gl_VertexID);
    if (abs(idx - uHovered) < 0.5) { size = max(size * 2.2, 7.0); col = col * 1.2 + 0.35; alpha = 1.0; vCore = 1.0; }
    if (abs(idx - uSelected) < 0.5) { size = max(size * 2.0, 8.0); col = vec3(2.0, 2.05, 2.2); alpha = 1.0; vCore = 1.0; }

    gl_PointSize = max(size, 1.0) * uPixelRatio;
    vColor = col;
    vAlpha = alpha;
  }
`;

const fragment = /* glsl */ `
  varying vec3 vColor;
  varying float vAlpha;
  varying float vCore;
  void main() {
    vec2 c = gl_PointCoord - 0.5;
    float d = length(c);
    if (d > 0.5) discard;
    float soft = smoothstep(0.5, 0.18, d);
    float core = smoothstep(0.22, 0.0, d) * vCore * 0.6;
    gl_FragColor = vec4(vColor + core, soft * vAlpha);
    #include <colorspace_fragment>
  }
`;

export function SatellitePoints({ catalog }: { catalog: Catalog }) {
  const { gl } = useThree();
  const n = catalog.count;

  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(n * 3), 3).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute('positionB', new THREE.BufferAttribute(new Float32Array(n * 3), 3).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute('aMission', new THREE.BufferAttribute(Float32Array.from(catalog.mission), 1));
    g.setAttribute('aBloc', new THREE.BufferAttribute(Float32Array.from(catalog.bloc), 1));
    g.setAttribute('aStyle', new THREE.BufferAttribute(new Float32Array(n).fill(2), 1).setUsage(THREE.DynamicDrawUsage));
    g.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 60);
    return g;
  }, [catalog, n]);

  const material = useMemo(() => {
    const col = (hex: string) => new THREE.Color(hex);
    return new THREE.ShaderMaterial({
      vertexShader: vertex,
      fragmentShader: fragment,
      transparent: true,
      depthWrite: false,
      depthTest: true,
      uniforms: {
        uMix: { value: 0 },
        uPixelRatio: { value: 1 },
        uSelected: { value: -1 },
        uHovered: { value: -1 },
        uColorBy: { value: 0 },
        uTime: { value: 0 },
        uScale: { value: 1 },
        uFocusScale: { value: 1 },
        uMissionColors: { value: MISSIONS.map((m) => col(m.color)) },
        uBlocColors: { value: BLOCS.map((b) => col(b.color)) },
        uCompareA: { value: col('#3987e5') },
        uCompareB: { value: col('#d95926') },
      },
    });
  }, []);

  useEffect(() => () => geometry.dispose(), [geometry]);
  useEffect(() => () => material.dispose(), [material]);

  // Style attribute follows the query state (lens / preview / compare / mode).
  const styleBuf = useRef(new Uint8Array(n));
  useEffect(() => {
    const apply = (s: ReturnType<typeof useAtlas.getState>) => {
      computeStyles(n, s, styleBuf.current);
      runtime.styles = styleBuf.current;
      // Small groups (GPS's 31, a country's fleet) get bigger dots so they stay findable.
      let focused = 0;
      for (let i = 0; i < n; i++) if (styleBuf.current[i] >= 3) focused++;
      material.uniforms.uFocusScale.value = focused === 0 ? 1 : focused < 120 ? 1.8 : focused < 1500 ? 1.3 : 1;
      const attr = geometry.getAttribute('aStyle') as THREE.BufferAttribute;
      (attr.array as Float32Array).set(styleBuf.current);
      attr.needsUpdate = true;
      material.uniforms.uColorBy.value = s.colorBy === 'owner' ? 1 : 0;
    };
    apply(useAtlas.getState());
    return useAtlas.subscribe((s, prev) => {
      if (
        s.lensMask !== prev.lensMask ||
        s.previewMask !== prev.previewMask ||
        s.compareMask !== prev.compareMask ||
        s.mode !== prev.mode ||
        s.previewLens !== prev.previewLens ||
        s.colorBy !== prev.colorBy
      )
        apply(s);
    });
  }, [geometry, material, n]);

  const lastVersion = useRef(-1);
  useFrame(({ camera }) => {
    const prop = runtime.propagation;
    if (!prop) return;
    const now = simClock.now();
    prop.tick(now);
    if (prop.version !== lastVersion.current && prop.version > 0) {
      lastVersion.current = prop.version;
      const a = geometry.getAttribute('position') as THREE.BufferAttribute;
      const b = geometry.getAttribute('positionB') as THREE.BufferAttribute;
      (a.array as Float32Array).set(prop.a);
      (b.array as Float32Array).set(prop.b);
      a.needsUpdate = true;
      b.needsUpdate = true;
    }
    const s = useAtlas.getState();
    const u = material.uniforms;
    u.uMix.value = prop.mix(now);
    u.uPixelRatio.value = gl.getPixelRatio();
    u.uSelected.value = s.selected;
    u.uHovered.value = s.hovered;
    // Points shrink slightly when zoomed far out so the LEO shell does not saturate.
    const d = camera.position.length();
    u.uScale.value = d > 14 ? 0.85 : 1;
  });

  return <points geometry={geometry} material={material} frustumCulled={false} renderOrder={3} />;
}
