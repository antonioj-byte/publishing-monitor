import { NextRequest, NextResponse } from 'next/server';
import { ingestAllSources } from '@/lib/rss/ingest';

function authorize(request: NextRequest): boolean {
  const secret = process.env.CRON_SECRET;
  if (!secret) return false;

  const auth = request.headers.get('authorization');
  return auth === `Bearer ${secret}`;
}

export async function GET(request: NextRequest) {
  if (!authorize(request)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const result = await ingestAllSources();
    console.log('Ingest complete:', result);
    return NextResponse.json(result);
  } catch (err) {
    console.error('Ingest failed:', err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : 'Ingest failed' },
      { status: 500 },
    );
  }
}

export const maxDuration = 60;
