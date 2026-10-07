'use client';

import { PerformanceMonitor } from '@react-three/drei';
import { Canvas } from '@react-three/fiber';
import { Bloom, EffectComposer } from '@react-three/postprocessing';
import { Suspense, useState } from 'react';
import type { Catalog } from '@/lib/catalog/catalog';
import { CameraRig, type InitialView } from './CameraRig';
import { Earth } from './Earth';
import { LensOrbits } from './LensOrbits';
import { RegimeRings } from './RegimeRings';
import { SatellitePoints } from './SatellitePoints';
import { Selection } from './Selection';
import { Stars } from './Stars';

/**
 * Render budget: Earth (1 mesh) + atmosphere + borders + all satellites in a
 * single Points draw call + a handful of lines. Bloom is the only full-screen
 * effect and is dropped automatically when the frame rate sags.
 */
export default function Scene({ catalog, initial }: { catalog: Catalog; initial: InitialView }) {
  const [quality, setQuality] = useState<'high' | 'low'>('high');
  const [dpr, setDpr] = useState(1.75);

  return (
    <Canvas
      dpr={[1, dpr]}
      flat
      gl={{ antialias: true, powerPreference: 'high-performance', alpha: false }}
      camera={{ fov: 42, near: 0.005, far: 2000, position: [0, 4, 10] }}
      onCreated={({ gl }) => gl.setClearColor('#03050b')}
      aria-label="3D globe of active satellites"
    >
      <PerformanceMonitor
        onDecline={() => {
          setQuality('low');
          setDpr(1);
        }}
      />
      <Stars />
      <Suspense fallback={null}>
        <Earth hiRes={quality === 'high'} />
      </Suspense>
      <RegimeRings />
      <LensOrbits catalog={catalog} />
      <SatellitePoints catalog={catalog} />
      <Selection catalog={catalog} />
      <CameraRig catalog={catalog} initial={initial} />
      {quality === 'high' && (
        <EffectComposer multisampling={4}>
          <Bloom mipmapBlur luminanceThreshold={1.0} luminanceSmoothing={0.15} intensity={0.9} radius={0.65} />
        </EffectComposer>
      )}
    </Canvas>
  );
}
