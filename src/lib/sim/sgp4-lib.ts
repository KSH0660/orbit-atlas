/**
 * The pure-JS SGP4 pieces of satellite.js.
 *
 * Imported by file path on purpose: the package root also re-exports its
 * optional WebAssembly runtimes, and the multi-threaded build spawns a
 * self-referencing `new Worker(new URL('index.js', import.meta.url))` that
 * stalls production bundling. Orbit Atlas has its own worker and does not
 * need them.
 */
export { json2satrec } from '../../../node_modules/satellite.js/dist/io.js';
export { sgp4 } from '../../../node_modules/satellite.js/dist/propagation/sgp4.js';
export { gstime } from '../../../node_modules/satellite.js/dist/propagation/gstime.js';
export { eciToGeodetic } from '../../../node_modules/satellite.js/dist/transforms.js';
export type { SatRec } from '../../../node_modules/satellite.js/dist/propagation/SatRec.js';
