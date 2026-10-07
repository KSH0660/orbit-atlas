/// <reference lib="webworker" />
import { json2satrec, type SatRec, sgp4 } from './sgp4-lib';
import type { PropagatorRequest, PropagatorResponse } from './propagator-protocol';

/**
 * SGP4 worker. Holds one SatRec per satellite and answers "where is
 * everything at time t" with a Float32Array of scene-frame positions
 * (Earth radii, Y-up ECI). Failed propagations (decayed, bad elements) are
 * written as (0,0,0) so the shader can discard them.
 */
const SCENE_UNIT_KM = 6371;
let satrecs: (SatRec | null)[] = [];
let epochs: Float64Array = new Float64Array(0);

function propagateAll(t: number, out: Float32Array) {
  for (let i = 0; i < satrecs.length; i++) {
    const s = satrecs[i];
    const o = i * 3;
    if (!s) {
      out[o] = out[o + 1] = out[o + 2] = 0;
      continue;
    }
    const pv = sgp4(s, (t - epochs[i]) / 60000);
    const p = pv?.position;
    if (!p || typeof p === 'boolean' || !Number.isFinite(p.x)) {
      out[o] = out[o + 1] = out[o + 2] = 0;
      continue;
    }
    out[o] = p.x / SCENE_UNIT_KM;
    out[o + 1] = p.z / SCENE_UNIT_KM;
    out[o + 2] = -p.y / SCENE_UNIT_KM;
  }
}

self.onmessage = (ev: MessageEvent<PropagatorRequest>) => {
  const msg = ev.data;
  if (msg.type === 'init') {
    satrecs = msg.omm.map((o) => {
      try {
        const s = json2satrec(o);
        return s.error ? null : s;
      } catch {
        return null;
      }
    });
    epochs = Float64Array.from(msg.omm, (o) => Date.parse(o.EPOCH));
    const res: PropagatorResponse = { type: 'ready', count: satrecs.length, failed: satrecs.filter((s) => !s).length };
    (self as unknown as Worker).postMessage(res);
    return;
  }
  if (msg.type === 'propagate') {
    const buf = msg.buffer && msg.buffer.length === satrecs.length * 3 ? msg.buffer : new Float32Array(satrecs.length * 3);
    propagateAll(msg.time, buf);
    const res: PropagatorResponse = { type: 'positions', id: msg.id, time: msg.time, positions: buf };
    (self as unknown as Worker).postMessage(res, [buf.buffer]);
  }
};
