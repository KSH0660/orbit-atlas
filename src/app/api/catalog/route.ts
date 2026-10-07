import { getCatalog } from '@/lib/data/server-catalog';

// Incremental Static Regeneration: prerendered at build, refreshed in the
// background at most every 2 hours (CelesTrak's requested courtesy interval).
export const dynamic = 'force-static';
export const revalidate = 7200;
export const maxDuration = 30;

export async function GET() {
  const payload = await getCatalog();
  return Response.json(payload, {
    headers: {
      'X-Orbit-Atlas-Source': payload.source.mode,
      'X-Orbit-Atlas-Count': String(payload.count),
    },
  });
}
