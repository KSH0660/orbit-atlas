# Orbit Atlas — product research & interaction model

_Short survey done before writing code (Oct 2026). Goal: learn what existing
trackers do well and badly, then design an interaction model that is not a
clone._

## What exists

| Product | What it does well | Where it falls short for a first-time visitor |
|---|---|---|
| **Stuff in Space** (WebGL, 2015, now offline/forks) | Iconic "everything at once" dot cloud; colors by object type (payload / rocket body / debris); click → orbit line | No meaning beyond type colors; no owner/mission data; no stats; the dot cloud is the whole product |
| **KeepTrack.space** | Most complete dataset; dozens of plugins (sensors, FOV, conjunctions, satellite view) | Built for analysts: many menus, icons and modes before you see anything useful; deep catalog vocabulary |
| **satellitemap.space** | Constellation-first (Starlink by default), shells, launch history by country | Busy UI; facts are spread across pages and lists rather than answering a question in the current view |
| **LeoLabs visualization** | Beautiful LEO debris/density storytelling | Narrow scope (LEO, debris); little free exploration or per-satellite detail |
| **CelesTrak / N2YO / Heavens-Above** | Authoritative data, pass predictions | Table/2D-map oriented; built for people who already know a NORAD ID |
| **Cesium/STK demos** | Precise, professional | Heavy, engineering UI; not meant for the general public |

### Patterns they share
1. A 3D globe with every object drawn the same way, plus a name/NORAD search box.
2. Filters are **catalog checkboxes** (object type, country code like `PRC`/`CIS`), not questions.
3. Selecting one object shows a long property table.
4. Statistics, when they exist, live on a separate page and describe the whole
   catalog, not what you are looking at.
5. Altitude is drawn to scale, so all of LEO is a thin shell hugging the Earth.
   Without a reference you cannot tell 550 km from 1,200 km, or see that one
   altitude band holds most of the traffic.
6. Little or no shareable state, weak mobile support.

### The gap
Nobody answers **"what am I looking at, and why does it matter?"** in the
current view. The data is there; the meaning isn't.

## Orbit Atlas interaction model

**Principle: one query, many entry points.** Everything the user does produces
or refines a single **Lens**, a declarative query (constellation, country,
operator, mission, orbit regime, altitude band, launch recency). The globe,
the stats and the URL all derive from the active lens.

```
                 ┌────────────── entry points ───────────────┐
 Explore chips · ⌘K command bar · click a stat bar · click a
 satellite attribute ("SpaceX") · brush the altitude histogram
                 └──────────────────────┬────────────────────┘
                                        ▼
                         Lens  (+ mode: highlight | only)
                         Compare (Lens A vs Lens B)
                         Selection (one satellite) · Follow
                                        │
            ┌───────────────┬───────────┴────────┬──────────────┐
            ▼               ▼                    ▼              ▼
        3D globe      In-view stats        Insight strip     URL state
      (GPU styles)  (frustum + horizon)   (numbers, clicks)  (shareable)
```

### Progressive disclosure (three levels)
1. **Overview (no lens, no selection):** pattern only. Points are tiny and
   colored by mission; regime rings label LEO / MEO / GEO. The side panel shows
   one headline number, an altitude histogram (where satellites concentrate),
   *who* (owner country) and *what* (mission) bars, plus 2–3 insights.
2. **Lens (constellation / country / mission / altitude band):** matching
   satellites brighten and grow (bloom); everything else drops to a dim ghost
   layer that keeps context. "Only show this" hides the rest. Small
   constellations (GPS, Galileo, BeiDou, GLONASS) draw every orbit so the
   orbital-plane structure is visible.
3. **Selection:** one satellite gets a bright orbit trail, a pulsing marker,
   a nadir line and a ground track. The panel switches to the satellite card
   (operator, country, mission, live altitude/speed, launch date) and
   orbit-shell facts ("1 of 3,412 satellites within ±25 km of this altitude").

Zoom adds detail too: labels for notable objects appear when close, and hover
tooltips work at any zoom.

### Decisions that differ from existing tools
- **Questions over categories.** Explore presets are phrased as the things
  people actually ask: *Starlink, GPS & GNSS, Space stations, Earth imaging,
  Military, Korea, China, GEO belt, Launched this year*.
- **Stats scoped to the view.** "In view" counts only satellites inside the
  camera frustum and above the horizon, and refresh as you orbit or zoom.
  Rotate to Asia and the panel tells you how many Korean satellites are
  overhead there.
- **The altitude histogram is a control.** Its log scale makes the 550 km
  Starlink shells, the 20,200 km GNSS shell and the GEO spike all visible, and
  dragging across it filters by altitude band.
- **Highlight by default, "Only" on demand.** Context is never lost unless the
  user asks for it.
- **Compare is first-class.** Two lenses get two colors (amber vs. cyan) and a
  side-by-side number table: *Starlink vs Kuiper*, *United States vs China*,
  *GPS vs BeiDou*.
- **Everything is a link.** Lens, mode, compare, selection, follow, color mode,
  camera and time warp are all in the URL.
- **Insights are numbers, not prose.** Each insight is a value plus a short
  label (and usually a click that applies a lens). There is no generated
  narrative.

### Visual encoding (each effect has a job)
| Effect | Purpose |
|---|---|
| Point color | Mission (default), owner bloc, or orbit regime: switchable, and the legend doubles as a filter |
| Point size/brightness | Lens membership and selection (focus vs. context) |
| Bloom | Only on highlighted and selected objects, so focus "glows" and the ghost layer stays quiet |
| Regime rings | Altitude reference for LEO / MEO / GNSS / GEO |
| Orbit trail + ground track | Where the selected satellite goes and what it flies over |
| Day/night shading & city lights | Real sun position; shows local time and which side is lit |
| Atmosphere glow & stars | Depth cue and limb definition; kept subtle |
| Smooth camera fly-to | Keeps users oriented when a lens or selection moves the view |

## Rendering technology choice

| Option | Pros | Cons |
|---|---|---|
| CesiumJS | Geodesy built in, terrain/imagery, time-dynamic | ~4 MB+ runtime, asset copying, ion token for default imagery, limited shader control for a custom look, per-object primitives get slow above ~20k moving points |
| deck.gl GlobeView | Great 2D/2.5D data layers | Globe view is limited for 3D orbits above the surface |
| **Three.js + react-three-fiber** | Full shader control, one draw call for all satellites, small bundle, React-friendly state | We build the Earth, atmosphere and frames ourselves |

**Chosen: Three.js via react-three-fiber.** All satellites are a single
`THREE.Points` draw call with a custom shader. SGP4 runs in a Web Worker that
returns two position snapshots (t₀, t₁). The vertex shader interpolates
between them every frame, so motion is smooth at 60 fps while the CPU only
propagates once per second. Per-satellite styling (lens / compare / selection
/ hidden) is a small attribute buffer updated only when the query changes.
This scales to well over 50,000 objects.
