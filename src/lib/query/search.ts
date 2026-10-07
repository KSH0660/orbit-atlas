import type { Catalog } from '../catalog/catalog';
import {
  BLOCS,
  CONSTELLATIONS,
  countryFlag,
  countryName,
  MISSIONS,
  REGIMES,
} from '../data/taxonomy';
import { type Lens, PRESETS } from './lens';

/**
 * Command-bar search over every kind of thing you can explore: constellations,
 * operators, countries, missions, orbit regimes, presets and individual
 * satellites (name, NORAD number or COSPAR designator).
 */
export type SearchKind = 'preset' | 'constellation' | 'operator' | 'country' | 'bloc' | 'mission' | 'regime' | 'satellite';

export interface SearchResult {
  kind: SearchKind;
  key: string;
  title: string;
  subtitle: string;
  count?: number;
  lens?: Lens;
  satIndex?: number;
  score: number;
}

interface Entry {
  kind: SearchKind;
  key: string;
  title: string;
  subtitle: string;
  terms: string[];
  count: number;
  lens: Lens;
}

/** Common aliases, including Korean so 한국어 queries work too. */
const ALIASES: Record<string, string[]> = {
  'constellation:starlink': ['spacex', '스타링크'],
  'constellation:kuiper': ['amazon leo', 'project kuiper', '카이퍼', '아마존'],
  'constellation:oneweb': ['eutelsat', '원웹'],
  'constellation:gps': ['navstar', 'gps', '지피에스'],
  'constellation:galileo': ['갈릴레오'],
  'constellation:beidou': ['compass', '베이더우', '북두'],
  'constellation:glonass': ['글로나스'],
  'constellation:qianfan': ['thousand sails', 'g60', 'spacesail', '첸판'],
  'constellation:guowang': ['satnet', 'hulianwang', '궈왕'],
  'constellation:stations': ['iss', 'tiangong', 'css', 'space station', '우주정거장', '국제우주정거장', '톈궁'],
  'country:KR': ['korea', 'south korea', 'rok', '한국', '대한민국', '남한'],
  'country:KP': ['north korea', 'dprk', '북한'],
  'country:JP': ['japan', '일본'],
  'country:IN': ['india', '인도'],
  'country:GB': ['uk', 'britain', 'england', '영국'],
  'country:FR': ['프랑스'],
  'country:DE': ['독일'],
  'bloc:US': ['usa', 'america', 'united states', '미국'],
  'bloc:CN': ['china', 'prc', '중국'],
  'bloc:RU': ['russia', '러시아'],
  'bloc:EU': ['europe', 'esa', 'eu', '유럽'],
  'mission:military': ['defense', 'defence', 'spy', 'reconnaissance', '군사', '정찰'],
  'mission:comms': ['communication', 'internet', 'broadband', 'telecom', '통신'],
  'mission:eo': ['earth observation', 'imaging', 'weather', 'radar', 'sar', '관측', '지구관측', '기상'],
  'mission:nav': ['navigation', 'gnss', 'positioning', '항법', '위성항법'],
  'mission:science': ['telescope', 'astronomy', '과학'],
  'mission:human': ['crew', 'astronaut', 'manned', '유인'],
  'regime:GEO': ['geostationary', 'geosynchronous', '정지궤도'],
  'regime:LEO': ['low earth orbit', '저궤도'],
  'regime:MEO': ['medium earth orbit', '중궤도'],
};

/** Famous objects people search by nickname → NORAD number. */
const SAT_ALIASES: Record<string, number> = {
  iss: 25544,
  'international space station': 25544,
  '국제우주정거장': 25544,
  zarya: 25544,
  tiangong: 48274,
  css: 48274,
  'chinese space station': 48274,
  '톈궁': 48274,
  '톈궁 우주정거장': 48274,
  hubble: 20580,
  hst: 20580,
  '허블': 20580,
};

const norm = (s: string) => s.toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '').trim();

export class SearchIndex {
  private entries: Entry[] = [];

  constructor(private cat: Catalog) {
    const csCount = new Map<number, number>();
    const opCount = new Map<number, number>();
    const ccCount = new Map<number, number>();
    const blocCount = new Uint32Array(BLOCS.length);
    const missionCount = new Uint32Array(MISSIONS.length);
    const regimeCount = new Uint32Array(REGIMES.length);
    for (let i = 0; i < cat.count; i++) {
      if (cat.constellation[i] >= 0) csCount.set(cat.constellation[i], (csCount.get(cat.constellation[i]) ?? 0) + 1);
      opCount.set(cat.operator[i], (opCount.get(cat.operator[i]) ?? 0) + 1);
      ccCount.set(cat.country[i], (ccCount.get(cat.country[i]) ?? 0) + 1);
      blocCount[cat.bloc[i]]++;
      missionCount[cat.mission[i]]++;
      regimeCount[cat.regime[i]]++;
    }

    const add = (e: Omit<Entry, 'terms'> & { terms?: string[] }) => {
      const aliasKey = `${e.kind}:${e.key}`;
      this.entries.push({ ...e, terms: [e.title, ...(e.terms ?? []), ...(ALIASES[aliasKey] ?? [])].map(norm) });
    };

    for (const p of PRESETS) {
      add({ kind: 'preset', key: p.id, title: p.label, subtitle: p.hint, count: 0, lens: p.lens });
    }
    cat.constellations.forEach((id, j) => {
      const meta = CONSTELLATIONS[id];
      add({
        kind: 'constellation',
        key: id,
        title: meta?.label ?? id,
        subtitle: meta ? `${meta.operator} · ${meta.blurb}` : 'Constellation',
        terms: [id, meta?.operator ?? ''],
        count: csCount.get(j) ?? 0,
        lens: { constellations: [id] },
      });
    });
    cat.operators.forEach((name, j) => {
      const count = opCount.get(j) ?? 0;
      if (!count || name === 'Unknown operator' || name === 'Unidentified') return;
      add({ kind: 'operator', key: name, title: name, subtitle: 'Operator', count, lens: { operators: [name] } });
    });
    cat.countries.forEach((code, j) => {
      if (code === 'XX') return;
      add({
        kind: 'country',
        key: code,
        title: `${countryFlag(code)} ${countryName(code)}`,
        subtitle: 'Country of registry',
        terms: [countryName(code), code],
        count: ccCount.get(j) ?? 0,
        lens: { countries: [code] },
      });
    });
    BLOCS.forEach((b, j) => {
      if (b.id === 'OT') return;
      add({ kind: 'bloc', key: b.id, title: b.label, subtitle: 'Owner region', count: blocCount[j], lens: { blocs: [b.id] } });
    });
    MISSIONS.forEach((m, j) => {
      add({ kind: 'mission', key: m.id, title: m.label, subtitle: 'Mission', terms: [m.short], count: missionCount[j], lens: { missions: [m.id] } });
    });
    REGIMES.forEach((r, j) => {
      add({ kind: 'regime', key: r.id, title: `${r.id} · ${r.label}`, subtitle: r.range, terms: [r.id, r.label], count: regimeCount[j], lens: { regimes: [r.id] } });
    });
  }

  search(raw: string, limit = 12): SearchResult[] {
    const q = norm(raw);
    if (!q) return [];
    const results: SearchResult[] = [];

    for (const e of this.entries) {
      let best = 0;
      for (const t of e.terms) best = Math.max(best, termScore(t, q));
      if (best > 0) {
        const kindBoost = e.kind === 'preset' ? 1.15 : e.kind === 'constellation' ? 1.2 : e.kind === 'satellite' ? 1 : 1.05;
        results.push({
          kind: e.kind,
          key: e.key,
          title: e.title,
          subtitle: e.subtitle,
          count: e.count || undefined,
          lens: e.lens,
          score: best * kindBoost + Math.log10(1 + e.count) * 0.08,
        });
      }
    }

    // Individual satellites: nickname, NORAD id, COSPAR, or name.
    const aliasId = SAT_ALIASES[q];
    const upper = raw.trim().toUpperCase();
    const asId = /^\d{1,6}$/.test(upper) ? Number(upper) : undefined;
    const sats: SearchResult[] = [];
    const { cat } = this;
    for (let i = 0; i < cat.count; i++) {
      let s = 0;
      if (aliasId !== undefined && cat.ids[i] === aliasId) s = 3.2;
      else if (asId !== undefined && cat.ids[i] === asId) s = 3;
      else if (cat.cospar[i] === upper) s = 2.5;
      else {
        const name = cat.searchNames[i];
        if (name === upper) s = 2.2;
        else if (name.startsWith(upper)) s = 1.6 - Math.min(0.5, name.length / 200);
        else if (upper.length >= 3 && name.includes(upper)) s = 1.0;
      }
      if (s > 0) {
        sats.push({
          kind: 'satellite',
          key: String(cat.ids[i]),
          title: cat.names[i],
          subtitle: `#${cat.ids[i]} · ${cat.operators[cat.operator[i]]}`,
          satIndex: i,
          score: s,
        });
      }
    }
    sats.sort((a, b) => b.score - a.score || a.title.length - b.title.length);
    const groupsFirst = results.sort((a, b) => b.score - a.score).slice(0, limit);
    // Interleave: a strong satellite hit (exact id/name) goes first.
    const merged = [...groupsFirst, ...sats.slice(0, 8)].sort((a, b) => b.score - a.score);
    return merged.slice(0, limit);
  }
}

function termScore(term: string, q: string): number {
  if (term === q) return 2;
  if (term.startsWith(q)) return 1.6;
  if (term.split(/[\s·()/,-]+/).some((w) => w.startsWith(q))) return 1.3;
  if (q.length >= 3 && term.includes(q)) return 0.9;
  return 0;
}
