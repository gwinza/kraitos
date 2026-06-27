# Thesis Discrimination Audit

**Generated:** 2026-06-12T11:51:59.353733+00:00

## Question

Validation showed **5808 theses built, 5808 tradeable, 0 rejected**. Is this legitimate or overly permissive?

## Verdict

**Partially legitimate, structurally permissive.** Every evaluation in this synthetic run produced `story_clear=True` (5808/5808). The thesis engine only rejects on geometry, spread, pre-trade R:R (<0.8), or genuinely unclear synthesis — and **`story_clear` bypasses R:R and target-liquidity checks**. With 100% story-clear inputs, **0 runtime rejections is expected**, not evidence of perfect thesis quality.

## Runtime rejection pathways (code)

| Pathway | Condition | Fired this run |
|---------|-----------|----------------|
| Unclear story | synthesis unclear AND NOT story_clear | 0 |
| Stop geometry | SL wrong side of entry | 0 |
| Invalidation undefined | inv_pips < 1 | 0 |
| Spread | spread > limit | 0 |
| Poor R:R | rr < 0.8 AND NOT story_clear | 0 (all story_clear) |
| Unclear target | target_dist <= 0 AND NOT story_clear | 0 |

**Story-clear override activations:** all **5808** evaluations.
**Would fail R:R without override:** **0** (0.0%)

## Independent classification (audit heuristics — not doctrine)

Classified each **opened position** (n=4290):

| Class | Count | % | Meaning |
|-------|-------|---|---------|
| A — Correctly tradeable | 4290 | 100.0% | Coherent thesis, R:R ≥ 0.8, adequate target |
| B — Borderline | 0 | 0.0% | Low R:R, tight target, or weak confidence |
| C — Should have been rejected | 0 | 0.0% | Missing thesis markers or sub-minimum geometry |

- **Actual runtime rejection rate:** 0.0%
- **Recommended rejection rate (audit):** 0.0% strict + 0.0% borderline review
- **Borderline rate:** 0.0%

## Quality concerns

1. **Weak stories upgraded:** All narratives marked story-clear in synthetic trending data.
2. **Unclear targets accepted:** 8–10 pip structural fallback targets pass when story_clear.
3. **Override bypasses scrutiny:** R:R gate disabled for 100% of theses in this validation.
4. **Thesis built before entry gate:** 5808 theses vs 4290 entries — thesis stage is not the funnel bottleneck.

### Strongest theses (Class A examples)

- **EURUSD** R:R=2.21, conf=0.84, risk=47p → reward=103p
- **GBPUSD** R:R=2.23, conf=0.84, risk=46p → reward=104p
- **AUDUSD** R:R=2.24, conf=0.84, risk=46p → reward=104p

### Weakest accepted (Class B examples)


### Should not have passed (Class C examples)


## DO NOT tighten (audit instruction honoured)

No doctrine changes applied. Findings inform future **safe** calibration only.

