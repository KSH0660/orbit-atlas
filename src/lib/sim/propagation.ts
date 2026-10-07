import { type Catalog, ommFor } from '../catalog/catalog';
import { simClock } from './clock';
import type { PropagatorRequest, PropagatorResponse } from './propagator-protocol';

/**
 * Main-thread side of the SGP4 worker.
 *
 * Keeps a window [tA, tB] of two position snapshots plus one prefetched
 * snapshot tC. The vertex shader blends A→B with `mix(t)`, so 60 fps motion
 * costs one worker propagation per window (≈1 s real time). The window's sim
 * length is capped at 60 s so the linear blend never cuts visibly inside the
 * orbit arc (chord error < 4 km for LEO) even at high time warp.
 */
export class PropagationManager {
  readonly count: number;
  a: Float32Array;
  b: Float32Array;
  tA = 0;
  tB = 0;
  /** Increments whenever A/B change — consumers re-upload GPU buffers. */
  version = 0;
  ready = false;
  failed = 0;

  private worker: Worker;
  private nextId = 1;
  private inflight = new Map<number, number>(); // id → time
  private prefetch?: { time: number; positions: Float32Array };
  private pool: Float32Array[] = [];
  private clockEpoch = -1;
  private pendingReset?: { idA: number; idB: number; a?: Float32Array; b?: Float32Array; tA: number; tB: number };
  private disposed = false;

  constructor(cat: Catalog) {
    this.count = cat.count;
    this.a = new Float32Array(cat.count * 3);
    this.b = new Float32Array(cat.count * 3);
    this.worker = new Worker(new URL('./propagator.worker.ts', import.meta.url), { type: 'module' });
    this.worker.onmessage = (ev: MessageEvent<PropagatorResponse>) => this.onMessage(ev.data);
    const omm = Array.from({ length: cat.count }, (_, i) => ommFor(cat, i));
    this.post({ type: 'init', omm });
  }

  dispose() {
    this.disposed = true;
    this.worker.terminate();
  }

  /** Sim-time span covered by one window. */
  static windowMs(warp: number): number {
    return Math.min(Math.max(warp, 1) * 1000, 60_000);
  }

  private post(msg: PropagatorRequest, transfer: Transferable[] = []) {
    if (!this.disposed) this.worker.postMessage(msg, transfer);
  }

  private request(time: number): number {
    const id = this.nextId++;
    this.inflight.set(id, time);
    const buffer = this.pool.pop();
    this.post({ type: 'propagate', id, time, buffer }, buffer ? [buffer.buffer] : []);
    return id;
  }

  private recycle(buf: Float32Array) {
    if (buf.length === this.count * 3 && this.pool.length < 3) this.pool.push(buf);
  }

  private onMessage(msg: PropagatorResponse) {
    if (msg.type === 'ready') {
      this.ready = true;
      this.failed = msg.failed;
      return;
    }
    const time = this.inflight.get(msg.id);
    this.inflight.delete(msg.id);
    if (time === undefined) return;

    const r = this.pendingReset;
    if (r && (msg.id === r.idA || msg.id === r.idB)) {
      if (msg.id === r.idA) r.a = msg.positions;
      else r.b = msg.positions;
      if (r.a && r.b) {
        this.recycle(this.a);
        this.recycle(this.b);
        this.a = r.a;
        this.b = r.b;
        this.tA = r.tA;
        this.tB = r.tB;
        this.pendingReset = undefined;
        if (this.prefetch) this.recycle(this.prefetch.positions);
        this.prefetch = undefined;
        this.version++;
      }
      return;
    }
    if (this.pendingReset) {
      this.recycle(msg.positions);
      return;
    }
    if (this.prefetch) this.recycle(this.prefetch.positions);
    this.prefetch = { time, positions: msg.positions };
  }

  private reset(now: number) {
    const span = PropagationManager.windowMs(simClock.warp);
    const tA = now;
    const tB = now + (simClock.paused ? 1 : span);
    this.pendingReset = { idA: this.request(tA), idB: this.request(tB), tA, tB };
  }

  /** Call once per frame. */
  tick(now: number) {
    if (!this.ready) return;
    if (this.clockEpoch !== simClock.epoch || this.version === 0) {
      if (!this.pendingReset) {
        this.clockEpoch = simClock.epoch;
        this.reset(now);
      }
      return;
    }
    if (this.pendingReset) return;

    const span = PropagationManager.windowMs(simClock.warp);
    // Prefetch the next snapshot as soon as the current window starts.
    if (!this.prefetch && this.inflight.size === 0 && !simClock.paused) {
      this.request(this.tB + span);
    }
    if (now >= this.tB && this.prefetch) {
      if (this.prefetch.time <= this.tB) {
        this.recycle(this.prefetch.positions);
        this.prefetch = undefined;
        return;
      }
      this.recycle(this.a);
      this.a = this.b;
      this.tA = this.tB;
      this.b = this.prefetch.positions;
      this.tB = this.prefetch.time;
      this.prefetch = undefined;
      this.version++;
      // Fell far behind (tab was hidden)? Start over at the current time.
      if (now > this.tB + span) this.clockEpoch = -1;
    }
  }

  mix(now: number): number {
    if (this.tB <= this.tA) return 0;
    return Math.min(1, Math.max(0, (now - this.tA) / (this.tB - this.tA)));
  }

  /** Interpolated scene position of satellite i. Returns false when invalid. */
  position(i: number, now: number, out: { x: number; y: number; z: number }): boolean {
    const m = this.mix(now);
    const o = i * 3;
    const ax = this.a[o];
    const ay = this.a[o + 1];
    const az = this.a[o + 2];
    if (ax === 0 && ay === 0 && az === 0) return false;
    out.x = ax + (this.b[o] - ax) * m;
    out.y = ay + (this.b[o + 1] - ay) * m;
    out.z = az + (this.b[o + 2] - az) * m;
    return true;
  }
}
