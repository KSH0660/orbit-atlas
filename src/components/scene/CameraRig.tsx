'use client';

import { CameraControls } from '@react-three/drei';
import { useFrame, useThree } from '@react-three/fiber';
import CameraControlsImpl from 'camera-controls';
import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import type { Catalog } from '@/lib/catalog/catalog';
import { simClock } from '@/lib/sim/clock';
import { latLonToScene, sceneToLatLon } from '@/lib/sim/frames';
import { runtime } from '@/lib/sim/runtime';
import { satrecFor, stateAt } from '@/lib/sim/single';
import { STYLE, useAtlas } from '@/store/atlas';

export interface InitialView {
  lat: number;
  lon: number;
  dist: number;
}

/** Default framing: the GEO ring fits on a landscape screen; your time zone faces you. */
export function defaultView(): InitialView {
  const portrait = typeof window !== 'undefined' && window.innerWidth < window.innerHeight;
  const tzLon = typeof Date !== 'undefined' ? (-new Date().getTimezoneOffset() / 60) * 15 : 0;
  return { lat: 26, lon: Math.max(-180, Math.min(180, tzLon)), dist: portrait ? 9 : 13 };
}

const PICK_RADIUS_MOUSE = 12;
const PICK_RADIUS_TOUCH = 24;

/**
 * Camera, pointer picking and "what is in view". Picking is done on the CPU
 * against the same interpolated positions the GPU draws (one pass over all
 * satellites, ~1 ms), with an Earth-occlusion test so you can't click through
 * the planet.
 */
export function CameraRig({ catalog, initial }: { catalog: Catalog; initial: InitialView }) {
  const controls = useRef<CameraControlsImpl>(null);
  const { camera, gl, size } = useThree();
  const tmp = useMemo(() => ({ v: new THREE.Vector3(), m: new THREE.Matrix4(), p: { x: 0, y: 0, z: 0 } }), []);
  const following = useRef(false);
  const lastViewReport = useRef(0);
  const lastInView = useRef(0);

  // Initial placement.
  useEffect(() => {
    const c = controls.current;
    if (!c) return;
    const [x, y, z] = latLonToScene(initial.lat, initial.lon, initial.dist, simClock.now());
    c.setLookAt(x, y, z, 0, 0, 0, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Desktop: shift the projection so the globe centers in the space between
  // the Explore column (left) and the context panel (right).
  // Mobile: when the bottom sheet is half open, lift the globe into the visible part.
  const sheet = useAtlas((s) => s.sheet);
  useEffect(() => {
    const cam = camera as THREE.PerspectiveCamera;
    const desktop = size.width >= 1024;
    const shiftX = desktop ? (368 - 224) / 2 : 0;
    const shiftY = !desktop && sheet === 'half' ? size.height * 0.24 : 0;
    if (shiftX || shiftY) cam.setViewOffset(size.width, size.height, shiftX, shiftY, size.width, size.height);
    else cam.clearViewOffset();
    cam.updateProjectionMatrix();
  }, [camera, size.width, size.height, sheet]);

  // Controls configuration.
  useEffect(() => {
    const c = controls.current;
    if (!c) return;
    c.minDistance = 1.12;
    c.maxDistance = 42;
    c.smoothTime = 0.45;
    c.draggingSmoothTime = 0.12;
    c.dollyToCursor = false;
    c.mouseButtons.right = CameraControlsImpl.ACTION.NONE;
    c.mouseButtons.middle = CameraControlsImpl.ACTION.DOLLY;
    c.mouseButtons.wheel = CameraControlsImpl.ACTION.DOLLY;
    c.touches.two = CameraControlsImpl.ACTION.TOUCH_DOLLY;
    c.touches.three = CameraControlsImpl.ACTION.NONE;
  }, []);

  // Camera commands from the UI.
  useEffect(() => {
    return useAtlas.subscribe((s, prev) => {
      const cmd = s.camera;
      const c = controls.current;
      if (!cmd || cmd === prev.camera || !c) return;
      const now = simClock.now();
      if (cmd.kind === 'home') {
        const v = defaultView();
        const [x, y, z] = latLonToScene(v.lat, v.lon, v.dist, now);
        useAtlas.getState().setFollow(false);
        void c.setLookAt(x, y, z, 0, 0, 0, true);
      } else if (cmd.kind === 'distance') {
        if (!useAtlas.getState().follow) {
          c.getPosition(tmp.v);
          tmp.v.normalize().multiplyScalar(cmd.distance);
          void c.setLookAt(tmp.v.x, tmp.v.y, tmp.v.z, 0, 0, 0, true);
        }
      } else if (cmd.kind === 'latlon') {
        const [x, y, z] = latLonToScene(cmd.lat, cmd.lon, cmd.distance, now);
        void c.setLookAt(x, y, z, 0, 0, 0, true);
      } else if (cmd.kind === 'zoom') {
        void c.dollyTo(Math.min(c.maxDistance, Math.max(c.minDistance, c.distance * cmd.factor)), true);
      } else if (cmd.kind === 'satellite') {
        const sr = satrecFor(catalog, cmd.index);
        const st = sr && stateAt(sr, now);
        if (!st) return;
        const r = Math.hypot(st.x, st.y, st.z);
        const want = cmd.distance ?? r + Math.max(1.6, r * 0.75);
        tmp.v.set(st.x, st.y, st.z).normalize();
        // Look slightly from above the orbit so the trail is visible as an ellipse.
        const up = new THREE.Vector3(0, 1, 0);
        const side = new THREE.Vector3().crossVectors(tmp.v, up).normalize();
        const camPos = tmp.v.clone().multiplyScalar(want).addScaledVector(up, want * 0.18).addScaledVector(side, want * 0.12);
        if (s.follow) void c.setLookAt(camPos.x, camPos.y, camPos.z, st.x, st.y, st.z, true);
        else void c.setLookAt(camPos.x, camPos.y, camPos.z, 0, 0, 0, true);
      }
    });
  }, [catalog, tmp]);

  // Follow mode transitions.
  useEffect(() => {
    return useAtlas.subscribe((s, prev) => {
      const c = controls.current;
      if (!c) return;
      if (s.follow && s.selected >= 0 && (!prev.follow || s.selected !== prev.selected)) {
        const sr = satrecFor(catalog, s.selected);
        const st = sr && stateAt(sr, simClock.now());
        if (!st) return;
        following.current = true;
        c.minDistance = 0.03;
        tmp.v.set(st.x, st.y, st.z).normalize();
        const off = tmp.v.clone().multiplyScalar(0.55).add(new THREE.Vector3(0, 0.25, 0));
        void c.setLookAt(st.x + off.x, st.y + off.y, st.z + off.z, st.x, st.y, st.z, true);
      } else if ((!s.follow || s.selected < 0) && following.current) {
        following.current = false;
        c.minDistance = 1.12;
        c.getPosition(tmp.v);
        const d = Math.max(tmp.v.length(), 2.2);
        tmp.v.normalize().multiplyScalar(d);
        void c.setLookAt(tmp.v.x, tmp.v.y, tmp.v.z, 0, 0, 0, true);
      }
    });
  }, [catalog, tmp]);

  // Pointer picking.
  useEffect(() => {
    const el = gl.domElement;
    let down: { x: number; y: number; t: number } | null = null;
    let raf = 0;
    let lastMove: PointerEvent | null = null;

    const pick = (clientX: number, clientY: number, radius: number): number => {
      const prop = runtime.propagation;
      const styles = runtime.styles;
      if (!prop || !styles || !prop.version) return -1;
      const rect = el.getBoundingClientRect();
      const px = clientX - rect.left;
      const py = clientY - rect.top;
      const w = rect.width;
      const h = rect.height;
      const m = tmp.m.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse).elements;
      const cx = camera.position.x;
      const cy = camera.position.y;
      const cz = camera.position.z;
      const cc = cx * cx + cy * cy + cz * cz - 1;
      const now = simClock.now();
      const r2 = radius * radius;
      let best = -1;
      let bestScore = Infinity;
      const p = tmp.p;
      for (let i = 0; i < prop.count; i++) {
        const st = styles[i];
        if (st === STYLE.HIDDEN) continue;
        if (!prop.position(i, now, p)) continue;
        const cw = m[3] * p.x + m[7] * p.y + m[11] * p.z + m[15];
        if (cw <= 0) continue;
        const sx = ((m[0] * p.x + m[4] * p.y + m[8] * p.z + m[12]) / cw + 1) * 0.5 * w;
        const sy = (1 - (m[1] * p.x + m[5] * p.y + m[9] * p.z + m[13]) / cw) * 0.5 * h;
        const d2 = (sx - px) * (sx - px) + (sy - py) * (sy - py);
        if (d2 > r2) continue;
        // Earth occlusion: does camera→satellite cross the unit sphere?
        const dx = p.x - cx;
        const dy = p.y - cy;
        const dz = p.z - cz;
        const a = dx * dx + dy * dy + dz * dz;
        const b = 2 * (cx * dx + cy * dy + cz * dz);
        const disc = b * b - 4 * a * cc;
        if (disc > 0) {
          const t1 = (-b - Math.sqrt(disc)) / (2 * a);
          if (t1 > 0 && t1 < 1) continue;
        }
        const score = d2 + (st === STYLE.GHOST ? 120 : st >= STYLE.FOCUS ? -40 : 0);
        if (score < bestScore) {
          bestScore = score;
          best = i;
          runtime.hoverScreen = { x: sx, y: sy };
        }
      }
      return best;
    };

    const onMove = (e: PointerEvent) => {
      if (e.pointerType === 'touch') return;
      lastMove = e;
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        if (!lastMove || down) return;
        const i = pick(lastMove.clientX, lastMove.clientY, PICK_RADIUS_MOUSE);
        if (i < 0) runtime.hoverScreen = null;
        useAtlas.getState().hover(i);
        el.style.cursor = i >= 0 ? 'pointer' : 'grab';
      });
    };
    const onDown = (e: PointerEvent) => {
      down = { x: e.clientX, y: e.clientY, t: performance.now() };
    };
    const onUp = (e: PointerEvent) => {
      if (!down) return;
      const moved = Math.hypot(e.clientX - down.x, e.clientY - down.y);
      const quick = performance.now() - down.t < 500;
      down = null;
      if (moved > 6 || !quick) return;
      const i = pick(e.clientX, e.clientY, e.pointerType === 'touch' ? PICK_RADIUS_TOUCH : PICK_RADIUS_MOUSE);
      const st = useAtlas.getState();
      if (i >= 0) st.select(i);
      else if (st.selected >= 0 && !st.follow) st.select(-1);
    };
    const onLeave = () => {
      runtime.hoverScreen = null;
      useAtlas.getState().hover(-1);
    };
    el.addEventListener('pointermove', onMove);
    el.addEventListener('pointerdown', onDown);
    el.addEventListener('pointerup', onUp);
    el.addEventListener('pointerleave', onLeave);
    el.style.cursor = 'grab';
    return () => {
      el.removeEventListener('pointermove', onMove);
      el.removeEventListener('pointerdown', onDown);
      el.removeEventListener('pointerup', onUp);
      el.removeEventListener('pointerleave', onLeave);
      cancelAnimationFrame(raf);
    };
  }, [gl, camera, tmp]);

  useFrame(() => {
    const c = controls.current;
    if (!c) return;
    const s = useAtlas.getState();
    const now = simClock.now();

    // Follow: keep the target glued to the satellite.
    if (s.follow && s.selected >= 0 && following.current) {
      const sr = satrecFor(catalog, s.selected);
      const st = sr && stateAt(sr, now);
      if (st) void c.moveTo(st.x, st.y, st.z, false);
    }

    // Rotation slows down near the surface so the globe doesn't whip around.
    const d = c.distance;
    const reach = following.current ? 1 : Math.min(1, Math.max(0.06, (camera.position.length() - 1) / 3));
    c.azimuthRotateSpeed = reach;
    c.polarRotateSpeed = reach;
    c.dollySpeed = following.current ? 0.6 : Math.min(1, Math.max(0.25, d / 6));

    const t = performance.now();
    // Report the view (for the URL) at most twice a second.
    if (t - lastViewReport.current > 500) {
      lastViewReport.current = t;
      const ll = sceneToLatLon(camera.position.x, camera.position.y, camera.position.z, now);
      const prev = s.cameraView;
      if (!prev || Math.abs(prev.lat - ll.lat) > 0.5 || Math.abs(prev.lon - ll.lon) > 0.5 || Math.abs(prev.dist - ll.r) > 0.05) {
        s.setCameraView({ lat: ll.lat, lon: ll.lon, dist: ll.r });
      }
    }

    // "In view": inside the frustum and above the horizon. ~3 Hz is plenty for stats.
    if (t - lastInView.current > 350) {
      lastInView.current = t;
      const prop = runtime.propagation;
      if (prop && prop.version > 0) {
        camera.updateMatrixWorld();
        const m = tmp.m.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse).elements;
        const cx = camera.position.x;
        const cy = camera.position.y;
        const cz = camera.position.z;
        const cc = cx * cx + cy * cy + cz * cz - 1;
        const out = new Uint32Array(prop.count);
        let k = 0;
        const p = tmp.p;
        for (let i = 0; i < prop.count; i++) {
          if (!prop.position(i, now, p)) continue;
          const cw = m[3] * p.x + m[7] * p.y + m[11] * p.z + m[15];
          if (cw <= 0) continue;
          const nx = (m[0] * p.x + m[4] * p.y + m[8] * p.z + m[12]) / cw;
          const ny = (m[1] * p.x + m[5] * p.y + m[9] * p.z + m[13]) / cw;
          if (nx < -1 || nx > 1 || ny < -1 || ny > 1) continue;
          const dx = p.x - cx;
          const dy = p.y - cy;
          const dz = p.z - cz;
          const a = dx * dx + dy * dy + dz * dz;
          const b = 2 * (cx * dx + cy * dy + cz * dz);
          const disc = b * b - 4 * a * cc;
          if (disc > 0) {
            const t1 = (-b - Math.sqrt(disc)) / (2 * a);
            if (t1 > 0 && t1 < 1) continue;
          }
          out[k++] = i;
        }
        const prevIn = s.inView;
        const next = out.slice(0, k);
        if (!prevIn || prevIn.length !== next.length || prevIn[0] !== next[0] || prevIn[k - 1] !== next[k - 1]) {
          s.setInView(next);
        }
      }
    }
  });

  return <CameraControls ref={controls} makeDefault />;
}
