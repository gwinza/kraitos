# Council Trade Frequency Diagnostic

**Generated:** 2026-06-12T11:41:29.576001+00:00

Rejection-path analysis for Opportunity Hunter Council expansion tuning.

## Summary

- Timeline evaluations: **5808**
- Trades emitted: **4290**
- Council allowed: **5808** (100.0%)
- Council denied: **0** (0.0%)
- Micro-harvest paths: **5808**
- Stage rejections: **3036**

## Stage rejection counts

| Stage | Count | % of evaluations |
|-------|-------|------------------|
| thesis | 1518 | 26.1% |
| entry | 1518 | 26.1% |

## Top rejection reasons (sampled)

- **2700×** Entry rejected: failed bias, risk. Bias unavailable or weak: neutral (0.35); Risk rejected: Sell stop loss must be above
- **84×** Entry rejected: failed bias, risk. Bias unavailable or weak: neutral (0.38); Risk rejected: Sell stop loss must be above
- **66×** Entry rejected: failed bias, risk. Bias unavailable or weak: neutral (0.47); Risk rejected: Sell stop loss must be above
- **62×** Entry rejected: failed bias, risk. Bias unavailable or weak: neutral (0.36); Risk rejected: Sell stop loss must be above
- **44×** Entry rejected: failed bias, risk. Bias unavailable or weak: neutral (0.46); Risk rejected: Sell stop loss must be above
- **26×** Entry rejected: failed bias, risk. Bias unavailable or weak: neutral (0.44); Risk rejected: Sell stop loss must be above
- **20×** Entry rejected: failed bias, risk. Bias unavailable or weak: neutral (0.51); Risk rejected: Sell stop loss must be above
- **12×** Entry rejected: failed bias, risk. Bias unavailable or weak: neutral (0.37); Risk rejected: Sell stop loss must be above
- **8×** Entry rejected: failed bias, risk. Bias unavailable or weak: neutral (0.52); Risk rejected: Sell stop loss must be above
- **8×** Entry rejected: failed bias, risk. Bias unavailable or weak: neutral (0.45); Risk rejected: Sell stop loss must be above
- **6×** Entry rejected: failed bias, risk. Bias unavailable or weak: neutral (0.49); Risk rejected: Sell stop loss must be above

## Gate analysis (code paths)

| Layer | Typical blocker | Expansion fix |
|-------|-----------------|---------------|
| Council | Weighted confidence < threshold | 3-of-6 / 2-of-4 voting, threshold 32 |
| Narrative | No micro-class edge | 7 micro-harvest narrative classes |
| Forecast | Pip range too wide | 1–3 pip micro harvest range |
| Harvest score | Band below conditional | Conditional from 38, council override |
| Dynamic pip | skip_trade (spread/ATR) | Micro spread-aware targets |
| Marketplace | no_trade dominance | Scalp/micro preferred in range |
| Harvest engine | Secondary < 2 | 1 secondary when council micro-harvest |
| Indicators | (confirm only) | Boost only — never block |

