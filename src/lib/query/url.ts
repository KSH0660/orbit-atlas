import { BLOCS, type BlocId, MISSIONS, type MissionId, REGIMES, type RegimeId, SECTORS, type SectorId } from '../data/taxonomy';
import { isEmptyLens, type Lens, normalizeLens } from './lens';

/**
 * Shareable URL state. Readable on purpose:
 *   /?cs=starlink&only=1&sat=44714
 *   /?bloc=US&vs.bloc=CN
 *   /?alt=500-600&color=owner&cam=37.5,127.0,3.2
 */
export interface ViewState {
  lens: Lens;
  only: boolean;
  compare?: Lens;
  sat?: number;
  follow: boolean;
  color: 'mission' | 'owner';
  warp: number;
  cam?: { lat: number; lon: number; dist: number };
}

const list = (v: string | null) =>
  v ? v.split(',').map((s) => decodeURIComponent(s.trim())).filter(Boolean) : undefined;
const join = (xs: (string | number)[]) => xs.map((x) => encodeURIComponent(String(x))).join(',');

const MISSION_IDS = new Set<string>(MISSIONS.map((m) => m.id));
const BLOC_IDS = new Set<string>(BLOCS.map((b) => b.id));
const REGIME_IDS = new Set<string>(REGIMES.map((r) => r.id));
const SECTOR_IDS = new Set<string>(SECTORS.map((s) => s.id));

function readLens(p: URLSearchParams, prefix = ''): Lens {
  const g = (k: string) => p.get(prefix + k);
  const lens: Lens = {
    constellations: list(g('cs')),
    countries: list(g('cc'))?.map((s) => s.toUpperCase()),
    blocs: list(g('bloc'))?.filter((b): b is BlocId => BLOC_IDS.has(b)),
    operators: list(g('op')),
    missions: list(g('mission'))?.filter((m): m is MissionId => MISSION_IDS.has(m)),
    regimes: list(g('regime'))?.map((r) => r.toUpperCase()).filter((r): r is RegimeId => REGIME_IDS.has(r)),
    sectors: list(g('sector'))?.filter((s): s is SectorId => SECTOR_IDS.has(s)),
    ids: list(g('ids'))?.map(Number).filter(Number.isFinite),
  };
  const alt = g('alt');
  if (alt) {
    const [lo, hi] = alt.split('-').map(Number);
    if (Number.isFinite(lo) && Number.isFinite(hi) && hi > lo) lens.altitude = [lo, hi];
  }
  const days = Number(g('new'));
  if (days > 0) lens.launchedWithinDays = days;
  return normalizeLens(lens);
}

function writeLens(p: URLSearchParams, lens: Lens, prefix = '') {
  const s = (k: string, v: (string | number)[] | undefined) => {
    if (v?.length) p.set(prefix + k, join(v));
  };
  s('cs', lens.constellations);
  s('cc', lens.countries);
  s('bloc', lens.blocs);
  s('op', lens.operators);
  s('mission', lens.missions);
  s('regime', lens.regimes);
  s('sector', lens.sectors);
  s('ids', lens.ids);
  if (lens.altitude) p.set(prefix + 'alt', `${Math.round(lens.altitude[0])}-${Math.round(lens.altitude[1])}`);
  if (lens.launchedWithinDays) p.set(prefix + 'new', String(lens.launchedWithinDays));
}

export function parseViewState(search: string): ViewState {
  const p = new URLSearchParams(search);
  const compare = readLens(p, 'vs.');
  const sat = Number(p.get('sat'));
  const warp = Number(p.get('warp'));
  let cam: ViewState['cam'];
  const c = p.get('cam')?.split(',').map(Number);
  if (c && c.length === 3 && c.every(Number.isFinite) && c[2] > 1) cam = { lat: c[0], lon: c[1], dist: c[2] };
  return {
    lens: readLens(p),
    only: p.get('only') === '1',
    compare: isEmptyLens(compare) ? undefined : compare,
    sat: Number.isFinite(sat) && sat > 0 ? sat : undefined,
    follow: p.get('follow') === '1',
    color: p.get('color') === 'owner' ? 'owner' : 'mission',
    warp: Number.isFinite(warp) && warp >= 1 && warp <= 3600 ? warp : 1,
    cam,
  };
}

export function serializeViewState(v: ViewState): string {
  const p = new URLSearchParams();
  writeLens(p, v.lens);
  if (v.compare) writeLens(p, v.compare, 'vs.');
  if (v.only) p.set('only', '1');
  if (v.sat) p.set('sat', String(v.sat));
  if (v.follow && v.sat) p.set('follow', '1');
  if (v.color !== 'mission') p.set('color', v.color);
  if (v.warp !== 1) p.set('warp', String(v.warp));
  if (v.cam) p.set('cam', `${v.cam.lat.toFixed(1)},${v.cam.lon.toFixed(1)},${v.cam.dist.toFixed(2)}`);
  const s = p.toString().replace(/%2C/g, ',');
  return s ? `?${s}` : '';
}
