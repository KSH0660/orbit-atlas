'use client';

import { useFrame, useLoader, useThree } from '@react-three/fiber';
import { useMemo, useRef } from 'react';
import * as THREE from 'three';
import { gmst, sunDirection } from '@/lib/sim/frames';
import { simClock } from '@/lib/sim/clock';
import { Borders } from './Borders';
import { GroundTrack } from './GroundTrack';

/**
 * The Earth is deliberately subdued (slightly desaturated, darker day side) so
 * satellite colors read on top of it. Real sun position drives the
 * day/night terminator and city lights.
 */
const vertex = /* glsl */ `
  varying vec2 vUv;
  varying vec3 vNormalW;
  varying vec3 vPosW;
  void main() {
    vUv = uv;
    vNormalW = normalize(mat3(modelMatrix) * normal);
    vec4 wp = modelMatrix * vec4(position, 1.0);
    vPosW = wp.xyz;
    gl_Position = projectionMatrix * viewMatrix * wp;
  }
`;

const fragment = /* glsl */ `
  uniform sampler2D dayMap;
  uniform sampler2D nightMap;
  uniform sampler2D waterMap;
  uniform vec3 sunDir;
  varying vec2 vUv;
  varying vec3 vNormalW;
  varying vec3 vPosW;
  void main() {
    vec3 n = normalize(vNormalW);
    vec3 viewDir = normalize(cameraPosition - vPosW);
    float ndl = dot(n, sunDir);
    float day = smoothstep(-0.12, 0.22, ndl);

    vec3 dayCol = texture2D(dayMap, vUv).rgb;
    float lum = dot(dayCol, vec3(0.2126, 0.7152, 0.0722));
    dayCol = mix(vec3(lum), dayCol, 0.78) * 0.78;
    vec3 lit = dayCol * (0.18 + 0.82 * clamp(ndl * 1.2 + 0.1, 0.0, 1.0));

    vec3 night = texture2D(nightMap, vUv).rgb;
    night = pow(night, vec3(1.4)) * vec3(1.0, 0.72, 0.42) * 1.6;
    vec3 dark = dayCol * 0.035 + night;

    vec3 col = mix(dark, lit, day);

    float water = texture2D(waterMap, vUv).r;
    vec3 h = normalize(sunDir + viewDir);
    float spec = pow(max(dot(n, h), 0.0), 90.0) * water * 0.1 * day;
    col += spec * vec3(1.0, 0.94, 0.82);

    // Limb tint: thin atmosphere edge on the lit side.
    float fres = pow(1.0 - max(dot(n, viewDir), 0.0), 3.0);
    col += vec3(0.25, 0.5, 1.0) * fres * (0.08 + 0.55 * day);

    gl_FragColor = vec4(col, 1.0);
    #include <colorspace_fragment>
  }
`;

const atmoVertex = /* glsl */ `
  varying vec3 vNormalW;
  varying vec3 vPosW;
  void main() {
    vNormalW = normalize(mat3(modelMatrix) * normal);
    vec4 wp = modelMatrix * vec4(position, 1.0);
    vPosW = wp.xyz;
    gl_Position = projectionMatrix * viewMatrix * wp;
  }
`;
const atmoFragment = /* glsl */ `
  uniform vec3 sunDir;
  uniform float uLimb;
  varying vec3 vNormalW;
  varying vec3 vPosW;
  void main() {
    // Rendered on the back faces of a slightly larger sphere: -dot(n, view)
    // is uLimb at the Earth's limb and 0 at the outer edge of the shell.
    vec3 n = normalize(vNormalW);
    vec3 viewDir = normalize(cameraPosition - vPosW);
    float rim = pow(clamp(-dot(n, viewDir) / uLimb, 0.0, 1.0), 1.7);
    float lit = 0.25 + 0.75 * smoothstep(-0.3, 0.45, dot(n, sunDir));
    vec3 col = vec3(0.3, 0.58, 1.0) * rim * lit * 0.85;
    gl_FragColor = vec4(col, 1.0);
    #include <colorspace_fragment>
  }
`;

const ATMO_SCALE = 1.07;

export function Earth({ hiRes }: { hiRes: boolean }) {
  const { gl } = useThree();
  const res = hiRes && gl.capabilities.maxTextureSize >= 4096 ? '4k' : '2k';
  const [day, night, water] = useLoader(THREE.TextureLoader, [
    `/textures/earth-day-${res}.jpg`,
    `/textures/earth-night-${res}.jpg`,
    '/textures/earth-water-2k.jpg',
  ]);
  useMemo(() => {
    for (const t of [day, night]) {
      t.colorSpace = THREE.SRGBColorSpace;
      t.anisotropy = Math.min(8, gl.capabilities.getMaxAnisotropy());
    }
  }, [day, night, gl]);

  const group = useRef<THREE.Group>(null);
  const sun = useMemo(() => new THREE.Vector3(1, 0, 0), []);
  const tmp = useMemo<[number, number, number]>(() => [0, 0, 0], []);

  const earthMat = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: vertex,
        fragmentShader: fragment,
        uniforms: {
          dayMap: { value: day },
          nightMap: { value: night },
          waterMap: { value: water },
          sunDir: { value: sun },
        },
      }),
    [day, night, water, sun],
  );
  const atmoMat = useMemo(
    () =>
      new THREE.ShaderMaterial({
        vertexShader: atmoVertex,
        fragmentShader: atmoFragment,
        uniforms: { sunDir: { value: sun }, uLimb: { value: Math.sqrt(1 - 1 / (ATMO_SCALE * ATMO_SCALE)) } },
        side: THREE.BackSide,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    [sun],
  );

  useFrame(() => {
    const t = simClock.now();
    sunDirection(t, tmp);
    sun.set(tmp[0], tmp[1], tmp[2]);
    if (group.current) group.current.rotation.y = gmst(t);
  });

  return (
    <>
      <group ref={group}>
        <mesh material={earthMat} renderOrder={0}>
          <sphereGeometry args={[1, 128, 64]} />
        </mesh>
        <Borders />
        <GroundTrack />
      </group>
      <mesh material={atmoMat} scale={ATMO_SCALE} renderOrder={1}>
        <sphereGeometry args={[1, 96, 48]} />
      </mesh>
    </>
  );
}
