import { loadSettings } from "../config/settings";
import { analyzeLiveFixtures } from "./liveAnalyzer";
import { fetchLiveFixtures } from "./oddsProvider";

export type DataSourceMode = "backend" | "live" | "demo";

export interface FetchResult {
  opportunities: Opportunity[];
  mode: DataSourceMode;
  message?: string;
}

export interface Fixture {
  match_id: string;
  sport: string;
  league: string;
  home_team: string;
  away_team: string;
  kickoff: string;
}

export interface EdgeAlert {
  match_id: string;
  match: string;
  decision: string;
  grade: string;
  edge_score: number;
  ev_pct: number | null;
  message: string;
  is_new: boolean;
}

export interface Opportunity {
  match_id: string;
  match: string;
  sport: string;
  league: string;
  kickoff_time: string;
  recommended_market: string | null;
  decision: string;
  edge_score: number;
  confidence: number;
  grade: string;
  risk_level: string;
  pass_reason: string;
  fair_odds: number | null;
  market_odds: number | null;
  expected_value: number | null;
  reasoning_summary: string;
  team_strength_analysis: string;
  coach_analysis: string;
  form_analysis: string;
  xg_analysis: string;
  market_intelligence: string;
  context_factors: string[];
  monte_carlo_results: Record<string, unknown> | null;
  multi_agent_council_summary: Record<string, unknown> | null;
  red_team_concerns: Record<string, unknown> | null;
  explainability: Record<string, unknown>;
  philosophy: string;
  prediction?: string | null;
  prediction_confidence?: number | null;
  prediction_reasoning?: string | null;
  prediction_detail?: Record<string, unknown> | null;
  is_lower_league?: boolean;
  league_tier?: number | null;
}

async function resolveApiBase(): Promise<string> {
  const settings = await loadSettings();
  return settings.apiBaseUrl;
}

async function backendFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const base = await resolveApiBase();
  if (!base) {
    throw new Error("No backend URL configured");
  }

  const res = await fetch(`${base.replace(/\/$/, "")}${path}`, init);
  if (!res.ok) {
    throw new Error(`Backend request failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export async function fetchOpportunitiesWithSource(): Promise<FetchResult> {
  const settings = await loadSettings();

  if (settings.apiBaseUrl) {
    try {
      const data = await backendFetch<{ opportunities: Opportunity[] }>("/analyze");
      return {
        opportunities: data.opportunities,
        mode: "backend",
        message: "Connected to Kraitos API with full intelligence.",
      };
    } catch {
      // Fall through to on-device live odds.
    }
  }

  if (settings.oddsApiKey) {
    try {
      const fixtures = await fetchLiveFixtures(settings.oddsApiKey);
      return {
        opportunities: analyzeLiveFixtures(fixtures),
        mode: "live",
        message: `Live markets — ${fixtures.length} fixtures scanned across bookmakers.`,
      };
    } catch (error) {
      const message = error instanceof Error ? error.message : "Live odds fetch failed";
      return {
        opportunities: [],
        mode: "demo",
        message,
      };
    }
  }

  return {
    opportunities: [],
    mode: "demo",
    message: "Add your Odds API key in Settings to unlock live markets.",
  };
}

export async function fetchOpportunities(): Promise<Opportunity[]> {
  const result = await fetchOpportunitiesWithSource();
  return result.opportunities;
}

export async function fetchAlerts(): Promise<EdgeAlert[]> {
  try {
    const data = await backendFetch<{ alerts: EdgeAlert[] }>("/alerts");
    return data.alerts ?? [];
  } catch {
    return [];
  }
}

export async function fetchMatchAnalysis(matchId: string): Promise<Opportunity> {
  try {
    return await backendFetch<Opportunity>(`/analyze/${matchId}`);
  } catch {
    const result = await fetchOpportunitiesWithSource();
    const match = result.opportunities.find((item) => item.match_id === matchId);
    if (!match) {
      throw new Error("Match not found");
    }
    return match;
  }
}

export async function fetchFixtures(): Promise<Fixture[]> {
  try {
    const data = await backendFetch<{ fixtures: Fixture[] }>("/fixtures");
    return data.fixtures;
  } catch {
    const settings = await loadSettings();
    if (!settings.oddsApiKey) return [];
    const fixtures = await fetchLiveFixtures(settings.oddsApiKey);
    return fixtures.map((fixture) => ({
      match_id: fixture.matchId,
      sport: fixture.sport,
      league: fixture.league,
      home_team: fixture.homeTeam,
      away_team: fixture.awayTeam,
      kickoff: fixture.kickoff,
    }));
  }
}

export async function fetchLowerLeaguePredictions(): Promise<Opportunity[]> {
  try {
    const data = await backendFetch<{ predictions: Opportunity[] }>("/analyze/lower-leagues");
    return data.predictions;
  } catch {
    return [];
  }
}

export async function fetchHealth(): Promise<Record<string, unknown>> {
  return backendFetch<Record<string, unknown>>("/health");
}

export async function refreshFixtures(): Promise<void> {
  try {
    await backendFetch("/refresh", { method: "POST" });
  } catch {
    // On-device live mode refreshes on every pull.
  }
}
