/**
 * Checks that generated code does not directly import third-party libraries
 * that should be accessed through earthforge.core wrappers.
 *
 * Forbidden direct imports in domain code:
 * - httpx (use earthforge.core.http)
 * - obstore (use earthforge.core.storage)
 * - boto3 / botocore (use earthforge.core.storage)
 * - rich (use earthforge.core.output)
 * - requests / urllib3 (use earthforge.core.http)
 */
module.exports = (output, context) => {
  // Extract code blocks only — don't flag imports mentioned in prose explanations
  const codeBlocks = output.match(/```[\s\S]*?```/g) || [];
  const codeContent = codeBlocks.join('\n');

  const forbidden = [
    { pattern: /^import httpx/m, lib: 'httpx', wrapper: 'earthforge.core.http' },
    { pattern: /^from httpx/m, lib: 'httpx', wrapper: 'earthforge.core.http' },
    { pattern: /^import obstore/m, lib: 'obstore', wrapper: 'earthforge.core.storage' },
    { pattern: /^from obstore/m, lib: 'obstore', wrapper: 'earthforge.core.storage' },
    { pattern: /^import boto3/m, lib: 'boto3', wrapper: 'earthforge.core.storage' },
    { pattern: /^from boto3/m, lib: 'boto3', wrapper: 'earthforge.core.storage' },
    { pattern: /^import requests/m, lib: 'requests', wrapper: 'earthforge.core.http' },
    { pattern: /^from requests/m, lib: 'requests', wrapper: 'earthforge.core.http' },
    { pattern: /^from rich\b/m, lib: 'rich', wrapper: 'earthforge.core.output' },
    { pattern: /^import rich/m, lib: 'rich', wrapper: 'earthforge.core.output' },
  ];

  const violations = forbidden
    .filter(f => f.pattern.test(codeContent))
    .map(f => `Direct import of ${f.lib} (should use ${f.wrapper})`);

  const pass = violations.length === 0;

  return {
    pass,
    score: pass ? 1.0 : 0.0,
    reason: pass
      ? 'No forbidden direct imports in code blocks'
      : `Forbidden imports found: ${violations.join('; ')}`,
  };
};
