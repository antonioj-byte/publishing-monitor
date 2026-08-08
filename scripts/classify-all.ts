import './load-env';
import { classifyBatch } from '../lib/ai/classify-batch';

async function main() {
  const maxRuns = parseInt(process.argv[2] ?? '50', 10);
  let totalClassified = 0;
  let totalFailed = 0;

  for (let i = 0; i < maxRuns; i++) {
    const result = await classifyBatch();
    totalClassified += result.classified;
    totalFailed += result.failed;

    console.log(
      `Run ${i + 1}: classified=${result.classified} failed=${result.failed} remaining=${result.remaining}`,
    );

    if (result.remaining === 0) break;
    if (result.classified === 0 && result.failed === 0) break;
  }

  console.log(`\nDone: ${totalClassified} classified, ${totalFailed} failed`);
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
