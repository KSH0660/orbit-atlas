/**
 * Simulation clock. Mutable singleton read every frame (no React re-renders):
 *   simNow = simBase + (perfNow − realBase) × warp
 */
type Listener = () => void;

class SimClock {
  private realBase = typeof performance !== 'undefined' ? performance.now() : 0;
  private simBase = Date.now();
  private _warp = 1;
  private _paused = false;
  private listeners = new Set<Listener>();

  now(): number {
    if (this._paused) return this.simBase;
    return this.simBase + (performance.now() - this.realBase) * this._warp;
  }

  get warp() {
    return this._warp;
  }
  get paused() {
    return this._paused;
  }

  /** True when the clock shows (approximately) the real current time. */
  isLive(): boolean {
    return !this._paused && this._warp === 1 && Math.abs(this.now() - Date.now()) < 5000;
  }

  setWarp(warp: number) {
    this.rebase();
    this._warp = warp;
    this.emit();
  }

  setPaused(paused: boolean) {
    this.rebase();
    this._paused = paused;
    this.emit();
  }

  /** Jump to a sim time (ms). */
  set(ms: number) {
    this.realBase = performance.now();
    this.simBase = ms;
    this.emit();
  }

  goLive() {
    this._warp = 1;
    this._paused = false;
    this.set(Date.now());
  }

  /** Bumped on discontinuities so the propagator can drop stale windows. */
  epoch = 0;

  private rebase() {
    this.simBase = this.now();
    this.realBase = performance.now();
  }

  subscribe(fn: Listener) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private emit() {
    this.epoch++;
    this.listeners.forEach((l) => l());
  }
}

export const simClock = new SimClock();
