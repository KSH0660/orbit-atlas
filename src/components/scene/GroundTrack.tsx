'use client';

import { Line } from '@react-three/drei';
import { useFrame } from '@react-three/fiber';
import { useMemo, useRef, useState } from 'react';
import { simClock } from '@/lib/sim/clock';
import { groundTrack, satrecFor } from '@/lib/sim/single';
import { useAtlas } from '@/store/atlas';

/**
 * Where the selected satellite will fly over during its next ~1.5 orbits.
 * Lives inside the Earth-fixed group, so it rotates with the planet.
 */
export function GroundTrack() {
  const catalog = useAtlas((s) => s.catalog);
  const selected = useAtlas((s) => s.selected);
  const satrec = useMemo(() => (catalog && selected >= 0 ? satrecFor(catalog, selected) : null), [catalog, selected]);
  const period = catalog && selected >= 0 ? catalog.periodMin[selected] : 0;
  const [track, setTrack] = useState<[number, number, number][] | null>(null);
  const last = useRef(0);
  const lastSat = useRef<typeof satrec>(null);

  useFrame(() => {
    if (!satrec) {
      if (track) setTrack(null);
      return;
    }
    const now = simClock.now();
    // GEO satellites barely move over the ground; skip the track for them.
    if (period > 1000) {
      if (track) setTrack(null);
      return;
    }
    if (lastSat.current !== satrec || Math.abs(now - last.current) > (period * 60000) / 30) {
      lastSat.current = satrec;
      last.current = now;
      const arr = groundTrack(satrec, now, period * 1.5, 360);
      const pts: [number, number, number][] = [];
      for (let k = 0; k < arr.length / 3; k++) pts.push([arr[k * 3], arr[k * 3 + 1], arr[k * 3 + 2]]);
      setTrack(pts);
    }
  });

  if (!track || track.length < 2) return null;
  return <Line points={track} color="#ffd9a0" lineWidth={1.3} transparent opacity={0.55} depthWrite={false} />;
}
