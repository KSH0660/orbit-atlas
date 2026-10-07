import type * as THREE from 'three';

/**
 * Screen-space anchors written by the scene every frame and read by a single
 * DOM overlay (no per-label React roots inside the canvas).
 */
export interface ScreenAnchor {
  x: number;
  y: number;
  visible: boolean;
}

export const anchors = new Map<string, ScreenAnchor>();

/** Project a scene point to CSS pixels; hidden when off-screen or behind the Earth. */
export function projectAnchor(
  id: string,
  camera: THREE.Camera,
  width: number,
  height: number,
  x: number,
  y: number,
  z: number,
  v: THREE.Vector3,
  occlude = true,
) {
  let a = anchors.get(id);
  if (!a) {
    a = { x: 0, y: 0, visible: false };
    anchors.set(id, a);
  }
  v.set(x, y, z).project(camera);
  const onScreen = v.z > -1 && v.z < 1 && v.x > -1.05 && v.x < 1.05 && v.y > -1.05 && v.y < 1.05;
  let visible = onScreen;
  if (visible && occlude) {
    const c = camera.position;
    const dx = x - c.x;
    const dy = y - c.y;
    const dz = z - c.z;
    const qa = dx * dx + dy * dy + dz * dz;
    const qb = 2 * (c.x * dx + c.y * dy + c.z * dz);
    const qc = c.x * c.x + c.y * c.y + c.z * c.z - 1;
    const disc = qb * qb - 4 * qa * qc;
    if (disc > 0) {
      const t1 = (-qb - Math.sqrt(disc)) / (2 * qa);
      if (t1 > 0 && t1 < 1) visible = false;
    }
  }
  a.x = (v.x * 0.5 + 0.5) * width;
  a.y = (-v.y * 0.5 + 0.5) * height;
  a.visible = visible;
}

export function hideAnchor(id: string) {
  const a = anchors.get(id);
  if (a) a.visible = false;
}
