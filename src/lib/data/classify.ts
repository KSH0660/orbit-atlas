import type { MissionId, SectorId } from './taxonomy';

/**
 * Name-based rules. They do two jobs:
 *  1. Assign a constellation id and normalise operator names across the
 *     several registry codes a constellation may be filed under.
 *  2. Classify brand-new satellites that are not yet in the metadata snapshot.
 * Order matters: the first match wins.
 */
export interface NameRule {
  re: RegExp;
  constellation?: string;
  operator?: string;
  mission?: MissionId;
  country?: string;
  sector?: SectorId;
}

export const NAME_RULES: NameRule[] = [
  // Crewed
  { re: /^(ISS \(|ISS$|ZARYA|ZVEZDA|NAUKA|POISK|UNITY|DESTINY)/, constellation: 'stations', operator: 'ISS partners (NASA · Roscosmos · ESA · JAXA · CSA)', mission: 'human', country: 'US', sector: 'civil' },
  { re: /^(CSS \(|TIANHE|WENTIAN|MENGTIAN|TIANGONG)/, constellation: 'stations', operator: 'China Manned Space Agency', mission: 'human', country: 'CN', sector: 'civil' },
  { re: /^(SHENZHOU|TIANZHOU)/, operator: 'China Manned Space Agency', mission: 'human', country: 'CN', sector: 'civil' },
  { re: /^(SOYUZ|PROGRESS)/, operator: 'Roscosmos', mission: 'human', country: 'RU', sector: 'civil' },
  { re: /^(CREW DRAGON|DRAGON|CRS-|CYGNUS|STARLINER|HTV|DREAM CHASER|AXIOM)/, operator: 'NASA (commercial crew & cargo)', mission: 'human', country: 'US', sector: 'civil' },

  // Broadband & mobile constellations
  { re: /^STARLINK/, constellation: 'starlink', operator: 'SpaceX', mission: 'comms', country: 'US', sector: 'commercial' },
  { re: /^ONEWEB/, constellation: 'oneweb', operator: 'Eutelsat OneWeb', mission: 'comms', country: 'GB', sector: 'commercial' },
  { re: /^(KUIPER|AMAZON LEO)/, constellation: 'kuiper', operator: 'Amazon', mission: 'comms', country: 'US', sector: 'commercial' },
  { re: /^QIANFAN/, constellation: 'qianfan', operator: 'Spacesail (Shanghai)', mission: 'comms', country: 'CN', sector: 'commercial' },
  { re: /^(HULIANWANG|GUOWANG|SATNET)/, constellation: 'guowang', operator: 'China SatNet', mission: 'comms', country: 'CN' },
  { re: /^IRIDIUM/, constellation: 'iridium', operator: 'Iridium', mission: 'comms', country: 'US', sector: 'commercial' },
  { re: /^GLOBALSTAR/, constellation: 'globalstar', operator: 'Globalstar', mission: 'comms', country: 'US', sector: 'commercial' },
  { re: /^ORBCOMM/, constellation: 'orbcomm', operator: 'ORBCOMM', mission: 'comms', country: 'US', sector: 'commercial' },
  { re: /^O3B/, constellation: 'o3b', operator: 'SES', mission: 'comms', country: 'LU', sector: 'commercial' },
  { re: /^(BLUEBIRD|BLUEWALKER|SPACEMOBILE)/, constellation: 'ast', operator: 'AST SpaceMobile', mission: 'comms', country: 'US', sector: 'commercial' },

  // Navigation
  { re: /^(NAVSTAR|GPS )/, constellation: 'gps', operator: 'US Space Force', mission: 'nav', country: 'US', sector: 'military' },
  { re: /GLONASS/, constellation: 'glonass', operator: 'Russian Aerospace Forces (GLONASS)', mission: 'nav', country: 'RU', sector: 'military' },
  { re: /^GSAT0\d{3}|\(GALILEO/, constellation: 'galileo', operator: 'EUSPA / ESA (Galileo)', mission: 'nav', country: 'EU', sector: 'civil' },
  { re: /^BEIDOU/, constellation: 'beidou', operator: 'China Satellite Navigation Office', mission: 'nav', country: 'CN', sector: 'military' },
  { re: /^QZS-/, constellation: 'qzss', operator: 'Japan Cabinet Office (QZSS)', mission: 'nav', country: 'JP', sector: 'civil' },
  { re: /^(IRNSS|NVS-)/, constellation: 'navic', operator: 'ISRO', mission: 'nav', country: 'IN', sector: 'civil' },

  // Earth observation
  { re: /^(FLOCK|DOVE|SUPERDOVE|SKYSAT|PELICAN|TANAGER)/, constellation: 'planet', operator: 'Planet', mission: 'eo', country: 'US', sector: 'commercial' },
  { re: /^LEMUR/, constellation: 'spire', operator: 'Spire Global', mission: 'eo', country: 'US', sector: 'commercial' },
  { re: /^JILIN/, constellation: 'jilin', operator: 'Chang Guang Satellite', mission: 'eo', country: 'CN', sector: 'commercial' },
  { re: /^ICEYE/, constellation: 'iceye', operator: 'ICEYE', mission: 'eo', country: 'FI', sector: 'commercial' },
  { re: /^(CAPELLA)/, operator: 'Capella Space', mission: 'eo', country: 'US', sector: 'commercial' },
  { re: /^(UMBRA)/, operator: 'Umbra', mission: 'eo', country: 'US', sector: 'commercial' },
  { re: /^(SENTINEL)/, operator: 'ESA / Copernicus', mission: 'eo', country: 'EU', sector: 'civil' },
  { re: /^(NOAA|GOES|JPSS|SUOMI)/, operator: 'NOAA', mission: 'eo', country: 'US', sector: 'civil' },
  { re: /^(METEOSAT|METOP)/, operator: 'EUMETSAT', mission: 'eo', country: 'EU', sector: 'civil' },
  { re: /^(FENGYUN)/, operator: 'China Meteorological Administration', mission: 'eo', country: 'CN', sector: 'civil' },
  { re: /^(GAOFEN|ZIYUAN|HAIYANG|HUANJING)/, operator: 'China (CNSA / SASTIND)', mission: 'eo', country: 'CN', sector: 'civil' },
  { re: /^(WORLDVIEW|LEGION|GEOEYE)/, operator: 'Maxar Intelligence', mission: 'eo', country: 'US', sector: 'commercial' },

  // Military
  { re: /^YAOGAN/, constellation: 'yaogan', operator: "People's Liberation Army", mission: 'military', country: 'CN', sector: 'military' },
  { re: /SDA[_ ]|^TRANCHE|^(PRAETORIAN|CHECKMATE)/, constellation: 'sda', operator: 'Space Development Agency', mission: 'military', country: 'US', sector: 'military' },
  { re: /^(USA \d+|NROL|SBIRS|AEHF|WGS|MUOS|MILSTAR|DSCS|GSSAP)/, operator: 'US Department of Defense', mission: 'military', country: 'US', sector: 'military' },
  { re: /^(COSMOS|KOSMOS)/, operator: 'Russian Aerospace Forces', mission: 'military', country: 'RU', sector: 'military' },
  { re: /^(ANASIS|KORSAT|425 PROJECT)/, operator: 'ROK Ministry of National Defense', mission: 'military', country: 'KR', sector: 'military' },
  { re: /^(SHIYAN|TJS|TONGXIN JISHU SHIYAN)/, operator: 'China (experimental / PLA)', mission: 'military', country: 'CN', sector: 'military' },

  // South Korea (civil & commercial)
  { re: /^(ARIRANG|KOMPSAT|CAS500|GEO-KOMPSAT)/, operator: 'KARI (Korea Aerospace Research Institute)', mission: 'eo', country: 'KR', sector: 'civil' },
  { re: /^KOREASAT/, operator: 'KT SAT', mission: 'comms', country: 'KR', sector: 'commercial' },
  { re: /^(NEONSAT|NEXTSAT|STSAT)/, operator: 'KAIST SaTReC', country: 'KR', sector: 'civil' },
];

export function matchNameRule(name: string): NameRule | undefined {
  const upper = name.toUpperCase();
  return NAME_RULES.find((r) => r.re.test(upper));
}

/**
 * CelesTrak SATCAT owner codes → ISO country (or EU / INT).
 * https://celestrak.org/satcat/sources.php
 */
export const CELESTRAK_OWNER_TO_COUNTRY: Record<string, string> = {
  US: 'US', PRC: 'CN', CIS: 'RU', UK: 'GB', JPN: 'JP', IT: 'IT', IND: 'IN', FR: 'FR', ESA: 'EU',
  GER: 'DE', SKOR: 'KR', CA: 'CA', SPN: 'ES', TURK: 'TR', SES: 'LU', ITSO: 'INT', O3B: 'LU',
  AUS: 'AU', EUTE: 'FR', ARGN: 'AR', GLOB: 'US', ROC: 'TW', FIN: 'FI', UAE: 'AE', NOR: 'NO',
  GREC: 'GR', ISRA: 'IL', SAUD: 'SA', BRAZ: 'BR', IM: 'GB', ORB: 'US', POL: 'PL', IRAN: 'IR',
  SING: 'SG', LUXE: 'LU', POR: 'PT', BEL: 'BE', AB: 'INT', INDO: 'ID', EGYP: 'EG', EUME: 'EU',
  SWTZ: 'CH', THAI: 'TH', MALA: 'MY', PAKI: 'PK', RWA: 'RW', AC: 'HK', ALG: 'DZ', BUL: 'BG',
  TBD: 'XX', NETH: 'NL', DEN: 'DK', SWED: 'SE', MEX: 'MX', KAZ: 'KZ', AZER: 'AZ', VTNM: 'VN',
  NIG: 'NG', CHLE: 'CL', PER: 'PE', ECU: 'EC', BOL: 'BO', VENZ: 'VE', QAT: 'QA', KUWT: 'KW',
  BHR: 'BH', JOR: 'JO', NZ: 'NZ', SAFR: 'ZA', HUN: 'HU', CZCH: 'CZ', SVK: 'SK', SVN: 'SI',
  LTU: 'LT', LAOS: 'LA', BGD: 'BD', MNG: 'MN', NKOR: 'KP', TUN: 'TN', MA: 'MA', ANG: 'AO',
  BOTS: 'BW', DJI: 'DJ', MAUR: 'MU', AUT: 'AT', IRL: 'IE', UKR: 'UA', BELA: 'BY', CRO: 'HR',
  ROM: 'RO', MCO: 'MC', EST: 'EE', LTV: 'LV', PNG: 'PG', SOL: 'SB', ESRO: 'EU', EUTL: 'FR',
  NICO: 'INT', RASC: 'INT', IRID: 'US', STCT: 'SG', GHA: 'INT', USBZ: 'US', FRIT: 'FR',
  CHBZ: 'CN', SEAL: 'US', NATO: 'INT', ISS: 'US', ASRA: 'AT', PRES: 'CN', FGER: 'FR',
};

/** GCAT state codes → ISO country (or EU / INT). */
const GCAT_STATE_TO_COUNTRY: Record<string, string> = {
  UK: 'GB', J: 'JP', F: 'FR', I: 'IT', D: 'DE', E: 'ES', L: 'LU', N: 'NO', B: 'BE', T: 'TH',
  S: 'SE', P: 'PT', UAE: 'AE', BGN: 'BG', SU: 'RU', ESIB: 'ES', BM: 'GB', 'I-EU': 'EU',
  'I-ESA': 'EU', 'I-EUM': 'EU', 'I-ELDO': 'EU', 'I-ESRO': 'EU',
};

export function gcatStateToCountry(state: string | undefined): string | undefined {
  if (!state || state === '-') return undefined;
  if (GCAT_STATE_TO_COUNTRY[state]) return GCAT_STATE_TO_COUNTRY[state];
  if (state.startsWith('I-')) return 'INT';
  if (/^[A-Z]{2}$/.test(state)) return state;
  return undefined;
}

/** GCAT `Class` → sector. */
export function gcatClassToSector(cls: string | undefined): SectorId | undefined {
  switch ((cls ?? '').charAt(0)) {
    case 'B':
      return 'commercial';
    case 'C':
      return 'civil';
    case 'D':
      return 'military';
    case 'A':
      return 'academic';
    default:
      return undefined;
  }
}

/**
 * GCAT `Category` (+ Class) → mission. Defense-class satellites are counted as
 * military unless their job is navigation (GPS, BeiDou, GLONASS are dual-use
 * public utilities and are much more useful grouped as "navigation").
 */
export function gcatCategoryToMission(category: string | undefined, cls: string | undefined): MissionId | undefined {
  if (!category || category === '-') return undefined;
  const head = category.replace(/[?*]/g, '').split('/')[0];
  let mission: MissionId | undefined;
  if (head === 'COM') mission = 'comms';
  else if (head === 'NAV') mission = 'nav';
  else if (['IMG', 'IMG-R', 'EOSCI', 'MET', 'MET-RO', 'GEOD'].includes(head)) mission = 'eo';
  else if (['SIG', 'EW', 'WEAPON', 'TARG'].includes(head)) mission = 'military';
  else if (head === 'SS') mission = 'human';
  else if (['SCI', 'AST', 'MGRAV', 'BIO', 'PLAN', 'SOLAR'].includes(head)) mission = 'science';
  else if (['TECH', 'CAL', 'EDU', 'RV', 'INFO'].includes(head)) mission = 'tech';
  else mission = 'tech';
  if ((cls ?? '').startsWith('D') && mission !== 'nav' && mission !== 'human') return 'military';
  return mission;
}

/** Friendly operator names for the most common GCAT organisation codes. */
export const GCAT_OPERATOR_NAMES: Record<string, string> = {
  SPXS: 'SpaceX', SPX: 'SpaceX', ONEWEBN: 'Eutelsat OneWeb', ONEWEB: 'Eutelsat OneWeb', ONEWEBE: 'Eutelsat OneWeb',
  KUIP: 'Amazon', YUANX: 'Spacesail (Shanghai)', ZXW: 'China SatNet', ZZB: "People's Liberation Army",
  ZLZB: "People's Liberation Army", 'ZZB/CAST': "People's Liberation Army", PLAN: 'Planet', PLANQ: 'Planet', PLABST: 'Planet',
  TBELLA: 'Planet', IRIDS: 'Iridium', CNSA: 'China National Space Administration', SDA: 'Space Development Agency',
  GEESP: 'Geespace (Geely)', AFSMC: 'US Space Force', SMC: 'US Space Force', SFSSC: 'US Space Force',
  AFSPC: 'US Space Force', AFMCSW: 'US Space Force', ISRO: 'ISRO', VVKOV: 'Russian Aerospace Forces',
  VVKO: 'Russian Aerospace Forces', KVR: 'Russian Aerospace Forces', 'VVKOV/IACG': 'Russian Aerospace Forces (GLONASS)',
  'KVR/IACG': 'Russian Aerospace Forces (GLONASS)', 'VVKO/IACG': 'Russian Aerospace Forces (GLONASS)',
  MORF: 'Russian Ministry of Defence', CASC: 'China Aerospace Science & Technology Corp.', SITRO: 'Sitronics',
  CAST: 'China Academy of Space Technology', SPIRE: 'Spire Global', SPIREL: 'Spire Global', HE360: 'HawkEye 360',
  CGSTL: 'Chang Guang Satellite', GSFC: 'NASA', JPL: 'NASA', JSC: 'NASA', MSFC: 'NASA', ARC: 'NASA', LARCN: 'NASA',
  CENTI: 'Centispace (Future Navigation)', GUOG: 'Guodian Gaoke (Tianqi)', ICEYE: 'ICEYE', ICEUS: 'ICEYE',
  KINEIS: 'Kinéis', GONETS: 'Gonets', ESA: 'European Space Agency', EUTSA: 'Eutelsat', TIANMU: 'Hangtian Tianmu',
  INTELU: 'Intelsat', INTELD: 'Intelsat', GSAEU: 'EUSPA (Galileo)', EUSPA: 'EUSPA (Galileo)', SAST: 'Shanghai Academy of Spaceflight Technology',
  GLOBL: 'Globalstar', GLOB: 'Globalstar', DORBIT: 'D-Orbit', O3BS: 'SES', O3B: 'SES', SESSA: 'SES', SESSL: 'SES',
  URUGUS: 'Satellogic', B1440: 'Bureau 1440', UNSEEN: 'Unseenlabs', PLNSST: 'Plan-S', BSKG: 'Blacksky',
  'ASI/OHBI': 'Italian Space Agency (IRIDE)', 'ASI/ARGOT': 'Italian Space Agency (IRIDE)', ASI: 'Italian Space Agency',
  NSMC: 'China Meteorological Administration', GCDX: 'China (Tianhui mapping)', ORBC: 'ORBCOMM', KACST: 'KACST',
  ZZWYZ: 'China (CRESDA)', KS: 'Russian Satellite Communications Co.', KARI: 'KARI (Korea Aerospace Research Institute)',
  CNSAS: 'China (SASTIND)', AXEL: 'Axelspace', SIWEI: 'China Siwei', YYAO: 'Tianjin Yunyao', TUB: 'TU Berlin',
  KEPLER: 'Kepler Communications', TOMIO: 'Tomorrow.io', NRL: 'US Naval Research Laboratory', CNES: 'CNES',
  SPQ: 'Aprize Satellite', 'GYZ/CASC': 'China (National Satellite Ocean Application Service)', JAXA: 'JAXA', AERO: 'The Aerospace Corporation',
  'COPERN/ESA': 'ESA / Copernicus', 'NINGX/CASC': 'Ningxia Jingui', GHG: 'GHGSat', ASTS: 'AST SpaceMobile',
  STP: 'US Space Test Program', INMRL: 'Inmarsat (Viasat)', INMAR: 'Inmarsat (Viasat)', VNIIEMI: 'VNIIEM', ZFT: 'Zentrum für Telematik',
  CAPSP: 'Capella Space', QPS: 'iQPS', ORORA: 'OroraTech', 'TAU/ISA': 'Tel Aviv University', 'LOFT/EDA': 'Loft Orbital',
  LOFT: 'Loft Orbital', GEOSK: 'Geoscan', CSA: 'Canadian Space Agency', EUMET: 'EUMETSAT', SIRX: 'SiriusXM',
  CHISAE: 'China Satcom', KAIST: 'KAIST SaTReC', CMSEO: 'China Manned Space Agency', SYNSP: 'Synspective',
  SKYKR: 'Skykraft', 'ZTAIX/PIESAT': 'PIESAT', PIESAT: 'PIESAT', ARAB: 'Arabsat', CAS: 'Chinese Academy of Sciences',
  AFRL: 'US Air Force Research Lab', NSPO: 'Taiwan Space Agency', TASA: 'Taiwan Space Agency', MGU: 'Moscow State University',
  YWZB: "People's Liberation Army", ASPLB: 'Aerospacelab', SPUT: 'SPUTNIX', ARKE: 'ArkEdge Space', NSL: 'NearSpace Launch',
  DTV: 'DirecTV', ASIA: 'AsiaSat', INTA: 'INTA', TURKS: 'Türksat', TCANL: 'Telesat', TCAN: 'Telesat', TSKY: 'Telesat',
  NOAA: 'NOAA', SKPJ: 'SKY Perfect JSAT', ASAL: 'Algerian Space Agency', GWHYZ: 'China (GF-3 SAR)', LYNK: 'Lynk Global',
  MAXARI: 'Maxar Intelligence', DGLO: 'Maxar Intelligence', PIXX: 'Pixxel', BSAT: 'B-SAT', OPTS: 'Optus', STONE: 'Embratel Star One',
  VIA: 'Viasat', RESH: 'ISS Reshetnev', SPAWSD: 'US Navy', SPAWAR: 'US Navy', DAPA: 'ROK Defense Acquisition Program Administration',
  SNU: 'Seoul National University', UMBRA: 'Umbra', ACAST: 'Astrocast', FLEET: 'Fleet Space', WEINA: 'MinoSpace',
  ZHUORB: 'Zhuhai Orbita', XYUN: 'CASIC (Xingyun)', DISH: 'EchoStar', AMCS: 'SES', PARA: 'UK Ministry of Defence',
  ROSK: 'Roscosmos', RKKE: 'Roscosmos', GAZS: 'Gazprom Space Systems', KAZK: 'KazSat', MBRSC: 'MBRSC',
  RGMS: 'Roshydromet', 'RGMS/VNIIEMI': 'Roshydromet', 'RGMS/NPOLO': 'Roshydromet', NSC: 'Norwegian Space Agency',
  DGA: 'French Defence Procurement Agency', HISD: 'Hisdesat', TNOR: 'Telenor', INPE: 'INPE', PAN: 'Intelsat',
  VMFR: 'Russian Navy', MOMENT: 'Momentus', ECHOAU: 'Tyvak', TANOM: 'Tyvak', IRSA: 'Iranian Space Agency',
  STIOT: 'Sateliot', KLEOS: 'Kleos Space', 'KLEO/YUANX': 'Kleo Connect', 'SWRI/GSFC': 'NASA', ADIG: 'Kongsberg NanoAvionics',
  SECM: 'Chinese Academy of Sciences', HARB: 'Harbin Institute of Technology', TSVS: 'Russian Aerospace Forces',
  'VVKOV/VOENT': 'Russian Aerospace Forces', 'ZLZB/GCDX?': "People's Liberation Army", SMDC: 'US Army SMDC',
  HEAD: 'HEAD Aerospace', '21AT': '21AT', ZJUNI: 'Zhejiang University', CLAAC: 'AAC Clyde Space', EGYSA: 'Egyptian Space Agency',
  NPOPM: 'Roscosmos', AMNA: 'AMSAT', USNPS: 'US Naval Postgraduate School', 'NUSS/JAXA': 'Japan Cabinet Office (QZSS)',
  ESPACE: 'Exolaunch', 'S4/ZFT': 'S4 Space', 'DELSP/SPIRE': 'Spire Global', 'SPIRE/LACU': 'Spire Global',
  'SPIREL/MYRI': 'Spire Global', SP42: 'Space42', BAUM: 'Bauman MSTU', ELKED: 'OroraTech', 'ELKED/ORORA': 'OroraTech',
  SATLAN: 'Satlantis', UTIAS: 'University of Toronto', SUPA: 'SUPARCO', NCKU: 'National Cheng Kung University',
  FOSSA: 'FOSSA Systems', 'AFSMC/DISA': 'US Department of Defense', CSAD: 'Canadian Space Agency',
};

export const SECTOR_LABEL_FALLBACK: SectorId = 'unknown';
