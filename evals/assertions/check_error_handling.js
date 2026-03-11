/**
 * Checks that the output includes error handling patterns:
 * - try/except blocks
 * - Custom EarthForgeError subclasses (not bare Exception)
 * - No bare except: clauses
 */
module.exports = (output, context) => {
  const hasTryExcept = /try\s*:/.test(output) && /except\s/.test(output);
  const hasCustomException = /EarthForgeError|class\s+\w+Error\(EarthForgeError\)/.test(output);
  const hasBareExcept = /except\s*:/.test(output);
  const hasRaise = /raise\s+\w+Error/.test(output);

  const pass = hasTryExcept && hasCustomException && !hasBareExcept;

  const reasons = [];
  if (!hasTryExcept) reasons.push('No try/except blocks found');
  if (!hasCustomException) reasons.push('No EarthForgeError subclass defined or referenced');
  if (hasBareExcept) reasons.push('Contains bare except: clause (must catch specific exceptions)');
  if (!hasRaise) reasons.push('No raise statement with typed exception');

  return {
    pass,
    score: pass ? 1.0 : (hasTryExcept ? 0.3 : 0.0),
    reason: pass
      ? 'Proper error handling with custom exceptions detected'
      : `Error handling issues: ${reasons.join(', ')}`,
  };
};
