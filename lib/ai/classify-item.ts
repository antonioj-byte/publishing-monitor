import Anthropic from '@anthropic-ai/sdk';
import type { ClassificationOutput, SourceCategory, Region } from '@/lib/types';

const MODEL = 'claude-sonnet-4-6';
const FALLBACK_MODEL = 'claude-sonnet-4-20250514';

const SYSTEM_PROMPT = `Eres analista de inteligencia editorial. Evalúa titular + resumen para un equipo que busca señales de mercado del sector del libro.

Puntúa relevance_score de 1 a 5:
- 5: implicación comercial, cultural o estratégica clara (adquisiciones, fusiones, cambios regulatorios, tendencias de mercado, movimientos editoriales relevantes)
- 4: señal relevante con impacto moderado
- 3: interesante pero impacto limitado
- 2: marginal, poco actionable
- 1: ruido, reseña menor, contenido sin implicación estratégica

Responde SOLO con JSON válido, sin markdown ni texto adicional:
{"relevance_score": number, "ai_summary_es": string, "ai_tags": string[]}

Reglas:
- ai_summary_es: máximo 2 líneas en español
- ai_tags: 2-5 tags en español, lowercase, sin #`;

function parseClassification(text: string): ClassificationOutput {
  const cleaned = text.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
  const parsed = JSON.parse(cleaned) as ClassificationOutput;

  if (
    typeof parsed.relevance_score !== 'number' ||
    parsed.relevance_score < 1 ||
    parsed.relevance_score > 5 ||
    typeof parsed.ai_summary_es !== 'string' ||
    !Array.isArray(parsed.ai_tags)
  ) {
    throw new Error('Invalid classification JSON shape');
  }

  return {
    relevance_score: Math.round(parsed.relevance_score),
    ai_summary_es: parsed.ai_summary_es.trim(),
    ai_tags: parsed.ai_tags.map((t) => String(t).trim().toLowerCase()).filter(Boolean),
  };
}

export interface ClassifyItemInput {
  title: string;
  summary: string | null;
  sourceName: string;
  category: SourceCategory;
  region: Region;
}

export async function classifyItem(input: ClassifyItemInput): Promise<ClassificationOutput> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) throw new Error('Missing ANTHROPIC_API_KEY');

  const client = new Anthropic({ apiKey });

  const userMessage = [
    `Titular: ${input.title}`,
    `Resumen: ${input.summary ?? '(sin resumen)'}`,
    `Fuente: ${input.sourceName}`,
    `Categoría: ${input.category}`,
    `Región: ${input.region}`,
  ].join('\n');

  async function callModel(model: string) {
    const response = await client.messages.create({
      model,
      max_tokens: 512,
      system: SYSTEM_PROMPT,
      messages: [{ role: 'user', content: userMessage }],
    });

    const block = response.content.find((b) => b.type === 'text');
    if (!block || block.type !== 'text') {
      throw new Error('No text response from Claude');
    }

    return parseClassification(block.text);
  }

  try {
    return await callModel(MODEL);
  } catch (err) {
    if (err instanceof Anthropic.APIError && err.status === 404) {
      return callModel(FALLBACK_MODEL);
    }
    throw err;
  }
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export { sleep };
