/**
 * Checks that the output defines a structured return type (dataclass or Pydantic model)
 * and does not use -> dict as a return type annotation.
 */
module.exports = (output, context) => {
  const hasDataclass = /@dataclass/.test(output) || /class\s+\w+\(BaseModel\)/.test(output);
  const hasRawDictReturn = /->\s*dict\b/.test(output);
  const hasStructuredReturn = /->\s*\w+(Result|Info|Response|Output|Report)\b/.test(output);

  const pass = hasDataclass && !hasRawDictReturn;

  const reasons = [];
  if (!hasDataclass) reasons.push('No dataclass or Pydantic model defined');
  if (hasRawDictReturn) reasons.push('Uses -> dict return type (should be structured type)');
  if (!hasStructuredReturn) reasons.push('Return type does not follow naming convention (*Result, *Info, etc.)');

  return {
    pass,
    score: pass ? 1.0 : (hasDataclass ? 0.5 : 0.0),
    reason: pass
      ? 'Structured return type with dataclass/Pydantic model detected'
      : `Structured return issues: ${reasons.join(', ')}`,
  };
};
