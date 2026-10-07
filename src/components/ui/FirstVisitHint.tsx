'use client';

import { useEffect, useState } from 'react';
import { useAtlas } from '@/store/atlas';

const KEY = 'orbit-atlas:hinted';

function seenBefore(): boolean {
  try {
    return Boolean(localStorage.getItem(KEY));
  } catch {
    return false;
  }
}

/** Three verbs, shown once, gone after the first real interaction. */
export function FirstVisitHint() {
  const [show, setShow] = useState(() => !seenBefore());
  const sheet = useAtlas((s) => s.sheet);

  useEffect(() => {
    if (!show) return;
    const first = useAtlas.getState().cameraView;
    return useAtlas.subscribe((s) => {
      const v = s.cameraView;
      const moved = first && v && Math.abs(v.dist - first.dist) + Math.abs(v.lon - first.lon) + Math.abs(v.lat - first.lat) > 3;
      if (s.selected >= 0 || moved || s.commandOpen) {
        setShow(false);
        try {
          localStorage.setItem(KEY, '1');
        } catch {
          /* private mode */
        }
      }
    });
  }, [show]);

  if (!show || sheet !== 'peek') return null;
  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-[150px] flex justify-center lg:bottom-[78px]">
      <div className="fade-up rounded-full border border-white/10 bg-[#0b1020]/70 px-4 py-1.5 text-[12px] text-[#c6cbd8] backdrop-blur">
        Drag to rotate · scroll or pinch to zoom · click any dot
      </div>
    </div>
  );
}
