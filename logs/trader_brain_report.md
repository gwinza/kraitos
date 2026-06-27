# Trader Brain Report

**Generated:** 2026-06-12T11:41:30.758534+00:00

## DNA

The Trader Brain understands markets, forecasts outcomes, discovers opportunities
and executes decisively. Conservative execution does NOT apply here.

## Responsibilities

- Scan all assets
- Market story (`market_story_engine`)
- Forecast (`story_forecast_engine`)
- Opportunity identification (harvest, price action, volume, structure)
- Strategy selection and entry candidates
- Trade management signals (partial exits, runners — trader-side intent)
- Indicator assist ONLY (boost, never veto)

## Separation guarantees

- Does NOT import `backtesting.execution_model`
- Does NOT import `validation.conservative_validation`
- Does NOT apply validation gates or strategy quality filters
- Does NOT use next-bar / closed-candle conservative assumptions

## Last scan stats

- No scan stats recorded this session.