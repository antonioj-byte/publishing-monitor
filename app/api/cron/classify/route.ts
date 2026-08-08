import { NextRequest, NextResponse } from 'next/server';
import { classifyBatch } from '@/lib/ai/classify-batch';

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

  if (!process.env.ANTHROPIC_API_KEY) {
    return NextResponse.json({ error: 'Missing ANTHROPIC_API_KEY' }, { status: 500 });
  }

  try {
    const result = await classifyBatch();
    console.log('Classify complete:', result);
    return NextResponse.json(result);
  } catch (err) {
    console.error('Classify failed:', err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : 'Classify failed' },
      { status: 500 },
    );
  }
}

export const maxDuration = 60;
