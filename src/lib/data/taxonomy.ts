/**
 * Orbit Atlas taxonomy: the small, fixed vocabularies every layer agrees on.
 *
 * Colors follow the validated categorical order (dark surface #0b1020, adjacent
 * CVD ΔE ≥ 8.4, normal-vision ΔE ≥ 19.3, all ≥ 3:1). Order is fixed and never
 * cycled: a filter that hides a category never repaints the others.
 */

export const MISSIONS = [
  { id: 'comms', label: 'Communications', short: 'Comms', color: '#3987e5' },
  { id: 'military', label: 'Military & intelligence', short: 'Military', color: '#d95926' },
  { id: 'eo', label: 'Earth observation & weather', short: 'Earth obs.', color: '#199e70' },
  { id: 'nav', label: 'Navigation (GNSS)', short: 'Navigation', color: '#c98500' },
  { id: 'human', label: 'Human spaceflight', short: 'Crewed', color: '#d55181' },
  { id: 'science', label: 'Science', short: 'Science', color: '#008300' },
  { id: 'tech', label: 'Technology & other', short: 'Tech/other', color: '#8b93a7' },
] as const;

export type MissionId = (typeof MISSIONS)[number]['id'];
export const MISSION_INDEX: Record<MissionId, number> = Object.fromEntries(
  MISSIONS.map((m, i) => [m.id, i]),
) as Record<MissionId, number>;

/** Owner blocs: how the first screen answers "who operates them". */
export const BLOCS = [
  { id: 'US', label: 'United States', short: 'US', color: '#3987e5' },
  { id: 'CN', label: 'China', short: 'China', color: '#d95926' },
  { id: 'EU', label: 'Europe', short: 'Europe', color: '#199e70' },
  { id: 'RU', label: 'Russia', short: 'Russia', color: '#c98500' },
  { id: 'JP', label: 'Japan', short: 'Japan', color: '#d55181' },
  { id: 'IN', label: 'India', short: 'India', color: '#008300' },
  { id: 'KR', label: 'South Korea', short: 'S. Korea', color: '#9085e9' },
  { id: 'OT', label: 'Rest of world', short: 'Other', color: '#8b93a7' },
] as const;

export type BlocId = (typeof BLOCS)[number]['id'];
export const BLOC_INDEX: Record<BlocId, number> = Object.fromEntries(
  BLOCS.map((b, i) => [b.id, i]),
) as Record<BlocId, number>;

export const REGIMES = [
  { id: 'LEO', label: 'Low Earth orbit', range: '< 2,000 km' },
  { id: 'MEO', label: 'Medium Earth orbit', range: '2,000 – 35,000 km' },
  { id: 'GEO', label: 'Geostationary', range: '≈ 35,786 km' },
  { id: 'HEO', label: 'Highly elliptical', range: 'eccentric / beyond GEO' },
] as const;
export type RegimeId = (typeof REGIMES)[number]['id'];
export const REGIME_INDEX: Record<RegimeId, number> = { LEO: 0, MEO: 1, GEO: 2, HEO: 3 };

export const SECTORS = [
  { id: 'commercial', label: 'Commercial' },
  { id: 'civil', label: 'Civil government' },
  { id: 'military', label: 'Military' },
  { id: 'academic', label: 'Academic & amateur' },
  { id: 'unknown', label: 'Unknown' },
] as const;
export type SectorId = (typeof SECTORS)[number]['id'];
export const SECTOR_INDEX: Record<SectorId, number> = {
  commercial: 0,
  civil: 1,
  military: 2,
  academic: 3,
  unknown: 4,
};

/** Countries / organisations. Keys are ISO 3166-1 alpha-2 plus a few org codes. */
export const COUNTRIES: Record<string, { name: string; bloc: BlocId }> = {
  US: { name: 'United States', bloc: 'US' },
  CN: { name: 'China', bloc: 'CN' },
  HK: { name: 'Hong Kong (China)', bloc: 'CN' },
  RU: { name: 'Russia', bloc: 'RU' },
  JP: { name: 'Japan', bloc: 'JP' },
  IN: { name: 'India', bloc: 'IN' },
  KR: { name: 'South Korea', bloc: 'KR' },
  EU: { name: 'European agencies (ESA/EU/EUMETSAT)', bloc: 'EU' },
  GB: { name: 'United Kingdom', bloc: 'EU' },
  FR: { name: 'France', bloc: 'EU' },
  DE: { name: 'Germany', bloc: 'EU' },
  IT: { name: 'Italy', bloc: 'EU' },
  ES: { name: 'Spain', bloc: 'EU' },
  LU: { name: 'Luxembourg', bloc: 'EU' },
  FI: { name: 'Finland', bloc: 'EU' },
  NL: { name: 'Netherlands', bloc: 'EU' },
  BE: { name: 'Belgium', bloc: 'EU' },
  NO: { name: 'Norway', bloc: 'EU' },
  SE: { name: 'Sweden', bloc: 'EU' },
  DK: { name: 'Denmark', bloc: 'EU' },
  PT: { name: 'Portugal', bloc: 'EU' },
  PL: { name: 'Poland', bloc: 'EU' },
  GR: { name: 'Greece', bloc: 'EU' },
  CH: { name: 'Switzerland', bloc: 'EU' },
  AT: { name: 'Austria', bloc: 'EU' },
  CZ: { name: 'Czechia', bloc: 'EU' },
  HU: { name: 'Hungary', bloc: 'EU' },
  SK: { name: 'Slovakia', bloc: 'EU' },
  SI: { name: 'Slovenia', bloc: 'EU' },
  LT: { name: 'Lithuania', bloc: 'EU' },
  LV: { name: 'Latvia', bloc: 'EU' },
  EE: { name: 'Estonia', bloc: 'EU' },
  RO: { name: 'Romania', bloc: 'EU' },
  BG: { name: 'Bulgaria', bloc: 'EU' },
  HR: { name: 'Croatia', bloc: 'EU' },
  IE: { name: 'Ireland', bloc: 'EU' },
  MC: { name: 'Monaco', bloc: 'EU' },
  UA: { name: 'Ukraine', bloc: 'EU' },
  BY: { name: 'Belarus', bloc: 'OT' },
  ME: { name: 'Montenegro', bloc: 'EU' },
  CA: { name: 'Canada', bloc: 'OT' },
  AU: { name: 'Australia', bloc: 'OT' },
  NZ: { name: 'New Zealand', bloc: 'OT' },
  TW: { name: 'Taiwan', bloc: 'OT' },
  TR: { name: 'Türkiye', bloc: 'OT' },
  AE: { name: 'United Arab Emirates', bloc: 'OT' },
  SA: { name: 'Saudi Arabia', bloc: 'OT' },
  IL: { name: 'Israel', bloc: 'OT' },
  IR: { name: 'Iran', bloc: 'OT' },
  BR: { name: 'Brazil', bloc: 'OT' },
  AR: { name: 'Argentina', bloc: 'OT' },
  MX: { name: 'Mexico', bloc: 'OT' },
  UY: { name: 'Uruguay', bloc: 'OT' },
  CL: { name: 'Chile', bloc: 'OT' },
  PE: { name: 'Peru', bloc: 'OT' },
  EC: { name: 'Ecuador', bloc: 'OT' },
  BO: { name: 'Bolivia', bloc: 'OT' },
  VE: { name: 'Venezuela', bloc: 'OT' },
  SG: { name: 'Singapore', bloc: 'OT' },
  ID: { name: 'Indonesia', bloc: 'OT' },
  TH: { name: 'Thailand', bloc: 'OT' },
  MY: { name: 'Malaysia', bloc: 'OT' },
  PH: { name: 'Philippines', bloc: 'OT' },
  VN: { name: 'Vietnam', bloc: 'OT' },
  LA: { name: 'Laos', bloc: 'OT' },
  BD: { name: 'Bangladesh', bloc: 'OT' },
  PK: { name: 'Pakistan', bloc: 'OT' },
  KZ: { name: 'Kazakhstan', bloc: 'OT' },
  AZ: { name: 'Azerbaijan', bloc: 'OT' },
  MN: { name: 'Mongolia', bloc: 'OT' },
  KP: { name: 'North Korea', bloc: 'OT' },
  EG: { name: 'Egypt', bloc: 'OT' },
  DZ: { name: 'Algeria', bloc: 'OT' },
  MA: { name: 'Morocco', bloc: 'OT' },
  TN: { name: 'Tunisia', bloc: 'OT' },
  NG: { name: 'Nigeria', bloc: 'OT' },
  ZA: { name: 'South Africa', bloc: 'OT' },
  RW: { name: 'Rwanda', bloc: 'OT' },
  AO: { name: 'Angola', bloc: 'OT' },
  BW: { name: 'Botswana', bloc: 'OT' },
  DJ: { name: 'Djibouti', bloc: 'OT' },
  MU: { name: 'Mauritius', bloc: 'OT' },
  QA: { name: 'Qatar', bloc: 'OT' },
  KW: { name: 'Kuwait', bloc: 'OT' },
  BH: { name: 'Bahrain', bloc: 'OT' },
  JO: { name: 'Jordan', bloc: 'OT' },
  PG: { name: 'Papua New Guinea', bloc: 'OT' },
  SB: { name: 'Solomon Islands', bloc: 'OT' },
  INT: { name: 'International organisation', bloc: 'OT' },
  XX: { name: 'Unknown', bloc: 'OT' },
};

export function countryName(code: string): string {
  return COUNTRIES[code]?.name ?? code;
}

export function countryBloc(code: string): BlocId {
  return COUNTRIES[code]?.bloc ?? 'OT';
}

/** Regional-indicator flag emoji for ISO alpha-2 codes; a neutral glyph otherwise. */
export function countryFlag(code: string): string {
  if (code === 'EU') return '🇪🇺';
  if (!/^[A-Z]{2}$/.test(code) || code === 'XX') return '🌐';
  return String.fromCodePoint(...[...code].map((c) => 0x1f1a5 + c.charCodeAt(0)));
}

/** Well-known constellations: id → display metadata. Order is display order. */
export const CONSTELLATIONS: Record<
  string,
  { label: string; operator: string; blurb: string }
> = {
  starlink: { label: 'Starlink', operator: 'SpaceX', blurb: 'Broadband mega-constellation' },
  oneweb: { label: 'OneWeb', operator: 'Eutelsat OneWeb', blurb: 'Broadband constellation, 1,200 km' },
  kuiper: { label: 'Amazon Leo (Kuiper)', operator: 'Amazon', blurb: 'Broadband constellation' },
  qianfan: { label: 'Qianfan (Thousand Sails)', operator: 'Spacesail', blurb: 'Chinese broadband constellation' },
  guowang: { label: 'Guowang (SatNet)', operator: 'China SatNet', blurb: 'Chinese state broadband constellation' },
  iridium: { label: 'Iridium', operator: 'Iridium', blurb: 'Global voice & data, polar orbits' },
  globalstar: { label: 'Globalstar', operator: 'Globalstar', blurb: 'Mobile satellite services' },
  orbcomm: { label: 'ORBCOMM', operator: 'ORBCOMM', blurb: 'IoT / M2M messaging' },
  o3b: { label: 'O3b mPOWER', operator: 'SES', blurb: 'MEO broadband' },
  ast: { label: 'AST SpaceMobile', operator: 'AST SpaceMobile', blurb: 'Direct-to-phone broadband' },
  gps: { label: 'GPS', operator: 'US Space Force', blurb: 'US navigation system, 6 planes' },
  glonass: { label: 'GLONASS', operator: 'Roscosmos / VKS', blurb: 'Russian navigation system' },
  galileo: { label: 'Galileo', operator: 'EUSPA / ESA', blurb: 'European navigation system' },
  beidou: { label: 'BeiDou', operator: 'CNSA', blurb: 'Chinese navigation system' },
  qzss: { label: 'QZSS (Michibiki)', operator: 'Japan Cabinet Office', blurb: 'Japanese regional navigation' },
  navic: { label: 'NavIC (IRNSS)', operator: 'ISRO', blurb: 'Indian regional navigation' },
  planet: { label: 'Planet Dove/SkySat', operator: 'Planet', blurb: 'Daily Earth imaging' },
  spire: { label: 'Spire Lemur', operator: 'Spire', blurb: 'Weather & ship/aircraft tracking' },
  jilin: { label: 'Jilin-1', operator: 'Chang Guang Satellite', blurb: 'Chinese commercial imaging' },
  yaogan: { label: 'Yaogan', operator: 'PLA', blurb: 'Chinese military reconnaissance' },
  iceye: { label: 'ICEYE', operator: 'ICEYE', blurb: 'SAR radar imaging' },
  sda: { label: 'SDA Tranche', operator: 'Space Development Agency', blurb: 'US military proliferated LEO' },
  stations: { label: 'Space station modules', operator: 'NASA · CMSA · partners', blurb: 'ISS and Tiangong modules' },
};
