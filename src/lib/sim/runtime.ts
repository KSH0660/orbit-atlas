import type { PropagationManager } from './propagation';

/**
 * Non-React runtime objects shared by the scene and the UI. Kept out of the
 * store because they change every frame or hold large buffers.
 */
export const runtime: {
  propagation: PropagationManager | null;
  /** Current per-satellite style buffer (see STYLE in the store). */
  styles: Uint8Array | null;
  /** Screen position (CSS px, canvas-relative) of the hovered satellite. */
  hoverScreen: { x: number; y: number } | null;
} = {
  propagation: null,
  styles: null,
  hoverScreen: null,
};
