import type { ommFor } from '../catalog/catalog';

export type OMM = ReturnType<typeof ommFor>;

export type PropagatorRequest =
  | { type: 'init'; omm: OMM[] }
  | { type: 'propagate'; id: number; time: number; buffer?: Float32Array };

export type PropagatorResponse =
  | { type: 'ready'; count: number; failed: number }
  | { type: 'positions'; id: number; time: number; positions: Float32Array };
