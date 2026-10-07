export const fmt = (v: number) => Math.round(v).toLocaleString('en-US');

export function fmtCompact(v: number): string {
  if (v >= 10000) return `${(v / 1000).toFixed(v >= 100000 ? 0 : 1).replace(/\.0$/, '')}k`;
  return fmt(v);
}

export function pct(part: number, whole: number): string {
  if (!whole) return '0%';
  const p = (part / whole) * 100;
  if (p > 0 && p < 1) return '<1%';
  return `${Math.round(p)}%`;
}

export function relTime(fromMs: number, now = Date.now()): string {
  const s = Math.round((now - fromMs) / 1000);
  if (s < 60) return 'just now';
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 48) return `${h} h ago`;
  return `${Math.round(h / 24)} days ago`;
}

export function fmtLat(lat: number): string {
  return `${Math.abs(lat).toFixed(1)}°${lat >= 0 ? 'N' : 'S'}`;
}
export function fmtLon(lon: number): string {
  return `${Math.abs(lon).toFixed(1)}°${lon >= 0 ? 'E' : 'W'}`;
}

export function fmtDuration(min: number): string {
  if (min < 120) return `${Math.round(min)} min`;
  const h = min / 60;
  if (h < 48) return `${h.toFixed(1).replace(/\.0$/, '')} h`;
  return `${(h / 24).toFixed(1)} days`;
}

export function fmtAge(launchMs: number, now = Date.now()): string {
  const days = (now - launchMs) / 86400000;
  if (!Number.isFinite(days)) return '';
  if (days < 1) return 'launched today';
  if (days < 60) return `${Math.round(days)} days in orbit`;
  if (days < 730) return `${Math.round(days / 30.4)} months in orbit`;
  return `${Math.round(days / 365.25)} years in orbit`;
}

export function utcClock(ms: number): string {
  const d = new Date(ms);
  return `${d.toISOString().slice(11, 19)} UTC`;
}
export function utcDate(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}
