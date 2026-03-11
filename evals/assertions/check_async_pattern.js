/**
 * Checks that the output contains an async function definition
 * and a corresponding _sync wrapper function.
 */
module.exports = (output, context) => {
  const hasAsyncDef = /async\s+def\s+\w+/.test(output);
  const hasSyncWrapper = /_sync\s*\(/.test(output) || /def\s+\w+_sync\s*\(/.test(output);
  const hasAsyncioRun = /asyncio\.run\s*\(/.test(output);

  const pass = hasAsyncDef && (hasSyncWrapper || hasAsyncioRun);

  const reasons = [];
  if (!hasAsyncDef) reasons.push('No async def found');
  if (!hasSyncWrapper && !hasAsyncioRun) reasons.push('No _sync wrapper or asyncio.run() found');

  return {
    pass,
    score: pass ? 1.0 : 0.0,
    reason: pass
      ? 'Async-first pattern with sync wrapper detected'
      : `Missing async-first pattern: ${reasons.join(', ')}`,
  };
};
