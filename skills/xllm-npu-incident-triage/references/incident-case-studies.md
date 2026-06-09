# Incident Case Studies

Historical cases are kept outside the main incident skill. Load this file only
when the user asks for similar known incidents or wants examples of report
formatting.

## MTP AddRmsNorm Shape Crash

Observed symptom:

- xLLM MTP mode crashed during generation.
- `aclnnAddRmsNorm` returned an invalid shape error.
- The failure blocked MTP vs baseline benchmark execution.

Representative stack signal:

```text
NPU function error: call aclnnAddRmsNorm failed, error code is 561002
Input x2/x1 shape invalid, shape is not equal x1 shape.
AddRmsNorm do tiling failed
```

Triage lesson:

- Preserve the full service log and NPU error stack first.
- Classify it as a runtime/kernel shape issue, not a benchmark failure.
- Fall back to baseline mode only as a temporary workaround.
- Re-run the MTP benchmark only after the shape path is fixed and a smoke
  request passes.
