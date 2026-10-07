'use client';

import { useAtlas } from '@/store/atlas';
import { HomeIcon } from './icons';
import { Legend, TimeControl, ViewControls } from './BottomBar';

/** Desktop: legend left, time centered, camera controls by the panel. Mobile: time + controls above the sheet. */
export function BottomBarLayout() {
  const sheet = useAtlas((s) => s.sheet);
  const requestCamera = useAtlas((s) => s.requestCamera);
  return (
    <>
      <div className="absolute bottom-4 left-4 hidden w-[208px] lg:block">
        <Legend />
      </div>
      <div className="absolute bottom-4 left-1/2 hidden -translate-x-1/2 lg:block">
        <TimeControl />
      </div>
      <div className="absolute bottom-[84px] right-[384px] hidden lg:block">
        <ViewControls />
      </div>

      {/* mobile / tablet: pinch zooms, so only time + reset; hidden while the sheet is open */}
      {sheet === 'peek' && (
        <div className="absolute inset-x-0 bottom-[88px] flex items-end justify-between gap-2 px-3 lg:hidden" style={{ marginBottom: 'env(safe-area-inset-bottom)' }}>
          <TimeControl compact />
          <button
            type="button"
            onClick={() => requestCamera({ kind: 'home' })}
            className="glass pointer-events-auto flex h-11 w-11 items-center justify-center rounded-xl text-[#c6cbd8]"
            aria-label="Reset view"
          >
            <HomeIcon />
          </button>
        </div>
      )}
    </>
  );
}
