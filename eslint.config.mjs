import nextCoreWebVitals from 'eslint-config-next/core-web-vitals';
import nextTypescript from 'eslint-config-next/typescript';

const config = [
  ...nextCoreWebVitals,
  ...nextTypescript,
  {
    // three.js geometries, materials and camera-controls are mutable GPU-side
    // objects by design; R3F updates them in place from effects and useFrame.
    files: ['src/components/scene/**/*.tsx'],
    rules: { 'react-hooks/immutability': 'off' },
  },
  { ignores: ['.next/**', 'node_modules/**', 'public/**', 'next-env.d.ts'] },
];

export default config;
