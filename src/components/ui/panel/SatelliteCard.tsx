'use client';

import { useEffect, useMemo, useState } from 'react';
import { BLOCS, CONSTELLATIONS, countryFlag, countryName, MISSIONS, REGIMES, SECTORS } from '@/lib/data/taxonomy';
import { shellPercentile } from '@/lib/query/stats';
import { simClock } from '@/lib/sim/clock';
import { type SatState, satrecFor, stateAt } from '@/lib/sim/single';
import { useAtlas } from '@/store/atlas';
import { applyLens, copyShareLink } from '../actions';
import { AltitudeHistogram } from '../charts/AltitudeHistogram';
import { allScope } from '../derived';
import { fmt, fmtAge, fmtDuration, fmtLat, fmtLon, pct } from '../format';
import { CloseIcon, FocusIcon, FollowIcon, ShareIcon } from '../icons';
import { ActionButton, Section, Stat } from './parts';

const shellCache = new Map<string, ReturnType<typeof shellPercentile>>();

export function SatelliteCard({ onShared }: { onShared: (ok: boolean) => void }) {
  const catalog = useAtlas((s) => s.catalog)!;
  const i = useAtlas((s) => s.selected);
  const follow = useAtlas((s) => s.follow);
  const setFollow = useAtlas((s) => s.setFollow);
  const select = useAtlas((s) => s.select);
  const requestCamera = useAtlas((s) => s.requestCamera);
  const [live, setLive] = useState<SatState | null>(null);

  const satrec = useMemo(() => satrecFor(catalog, i), [catalog, i]);
  useEffect(() => {
    if (!satrec) return;
    const tick = () => setLive(stateAt(satrec, simClock.now()));
    tick();
    const id = setInterval(tick, 250);
    return () => clearInterval(id);
  }, [satrec]);

  const alt = catalog.meanAltKm[i];
  const shell = useMemo(() => {
    const key = `${catalog.generatedAt}:${Math.round(alt)}`;
    let v = shellCache.get(key);
    if (!v) {
      v = shellPercentile(catalog, alt, 25);
      shellCache.set(key, v);
    }
    return v;
  }, [catalog, alt]);

  const mission = MISSIONS[catalog.mission[i]];
  const regime = REGIMES[catalog.regime[i]];
  const cc = catalog.countries[catalog.country[i]];
  const bloc = BLOCS[catalog.bloc[i]];
  const op = catalog.operators[catalog.operator[i]];
  const csId = catalog.constellation[i] >= 0 ? catalog.constellations[catalog.constellation[i]] : undefined;
  const cs = csId ? CONSTELLATIONS[csId] : undefined;
  const csCount = useMemo(() => {
    if (catalog.constellation[i] < 0) return 0;
    let n = 0;
    for (let k = 0; k < catalog.count; k++) if (catalog.constellation[k] === catalog.constellation[i]) n++;
    return n;
  }, [catalog, i]);
  const launch = catalog.launchDate[i];
  const mass = catalog.massKg[i];
  const all = allScope(catalog).stats;
  const orbitsPerDay = catalog.meanMotion[i];
  const busy = shell.percentile >= 0.6;

  return (
    <>
      <div className="px-4 pb-3 pt-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-[0.13em] text-[#8b93a7]">
              <span className="h-2 w-2 rounded-full" style={{ background: mission.color }} />
              {mission.label} · {regime.id}
            </div>
            <h2 className="mt-1 break-words text-[19px] font-semibold leading-tight text-white">{catalog.names[i]}</h2>
            <div className="tabular mt-0.5 text-[11.5px] text-[#8b93a7]">
              NORAD {catalog.ids[i]} · {catalog.cospar[i]}
            </div>
          </div>
          <button type="button" onClick={() => select(-1)} className="rounded-md p-1 text-[#8b93a7] hover:bg-white/10 hover:text-white" aria-label="Close">
            <CloseIcon />
          </button>
        </div>

        <div className="mt-3 grid grid-cols-3 gap-3">
          <Stat label="Altitude" value={live ? `${fmt(live.altitudeKm)} km` : '—'} sub={regime.label} />
          <Stat label="Speed" value={live ? `${live.speedKmS.toFixed(2)} km/s` : '—'} sub={live ? `${fmt(live.speedKmS * 3600)} km/h` : ''} />
          <Stat label="Now over" value={live ? fmtLat(live.lat) : '—'} sub={live ? fmtLon(live.lon) : ''} />
        </div>

        <div className="mt-3 flex flex-wrap gap-1.5">
          <ActionButton active={follow} onClick={() => setFollow(!follow)} title="Keep the camera on this satellite (F)">
            <FollowIcon /> {follow ? 'Following' : 'Follow'}
          </ActionButton>
          <ActionButton onClick={() => requestCamera({ kind: 'satellite', index: i })} title="Fly to satellite">
            <FocusIcon /> Fly to
          </ActionButton>
          <ActionButton onClick={() => copyShareLink().then(onShared)} title="Copy a link to this view">
            <ShareIcon /> Share
          </ActionButton>
        </div>
      </div>

      <Section title="Who and why">
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-[12.5px]">
          <dt className="text-[#8b93a7]">Operator</dt>
          <dd>
            <button type="button" className="text-left text-white hover:underline" onClick={() => applyLens({ operators: [op] }, { keepSelection: true })}>
              {op}
            </button>
          </dd>
          <dt className="text-[#8b93a7]">Country</dt>
          <dd>
            <button type="button" className="text-left text-white hover:underline" onClick={() => applyLens({ countries: [cc] }, { keepSelection: true })}>
              {countryFlag(cc)} {countryName(cc)}
            </button>
            {bloc.id !== 'OT' && bloc.label !== countryName(cc) && <span className="text-[#8b93a7]"> · {bloc.label}</span>}
          </dd>
          <dt className="text-[#8b93a7]">Mission</dt>
          <dd>
            <button type="button" className="text-left text-white hover:underline" onClick={() => applyLens({ missions: [mission.id] }, { keepSelection: true })}>
              {mission.label}
            </button>
            <span className="text-[#8b93a7]"> · {SECTORS[catalog.sector[i]].label}</span>
          </dd>
          {cs && (
            <>
              <dt className="text-[#8b93a7]">Part of</dt>
              <dd>
                <button type="button" className="text-left text-white hover:underline" onClick={() => applyLens({ constellations: [csId!] }, { keepSelection: true, frame: false })}>
                  {cs.label}
                </button>
                <span className="tabular text-[#8b93a7]"> · 1 of {fmt(csCount)}</span>
              </dd>
            </>
          )}
          <dt className="text-[#8b93a7]">Launched</dt>
          <dd className="text-white">
            {launch || 'Unknown'}
            {launch && <span className="text-[#8b93a7]"> · {fmtAge(catalog.launchMs[i])}</span>}
          </dd>
          {mass > 0 && (
            <>
              <dt className="text-[#8b93a7]">Mass</dt>
              <dd className="tabular text-white">{fmt(mass)} kg</dd>
            </>
          )}
        </dl>
      </Section>

      <Section title="Its orbit">
        <div className="grid grid-cols-3 gap-3">
          <Stat label="Period" value={fmtDuration(catalog.periodMin[i])} sub={`${orbitsPerDay.toFixed(orbitsPerDay < 2 ? 2 : 1)} orbits/day`} />
          <Stat label="Inclination" value={`${catalog.inclination[i].toFixed(1)}°`} sub={catalog.inclination[i] > 90 ? 'retrograde' : catalog.inclination[i] < 1 ? 'equatorial' : 'prograde'} />
          <Stat label="Perigee/apogee" value={`${fmt(catalog.perigeeKm[i])}`} sub={`${fmt(catalog.apogeeKm[i])} km`} />
        </div>
        <div className="mt-3">
          <AltitudeHistogram base={all.altHist} marker={alt} height={44} />
        </div>
        <div className="mt-2 rounded-lg bg-white/[0.04] px-3 py-2 text-[12px] leading-snug text-[#c6cbd8]">
          <span className="tabular font-semibold text-white">{fmt(shell.neighbours)}</span> satellites share its ±25 km altitude shell
          {shell.busiest ? (
            <> — one of the most crowded altitudes in orbit.</>
          ) : busy ? (
            <>
              {' '}
              — busier than <span className="font-semibold text-white">{pct(shell.percentile, 1)}</span> of occupied 50 km altitude bands.
            </>
          ) : (
            <> — a relatively quiet altitude.</>
          )}
        </div>
      </Section>
    </>
  );
}
