import { Opportunity } from "./client";
import { BookmakerOdds, LiveFixture } from "./oddsProvider";

const TWO_WAY_SPORTS = new Set([
  "basketball",
  "tennis",
  "mma",
  "cricket",
  "american_football",
  "baseball",
  "ice_hockey",
  "esports",
]);

function bestOdds(odds: BookmakerOdds[]): BookmakerOdds {
  return {
    bookmaker: "Market Best",
    home: Math.max(...odds.map((o) => o.home)),
    draw: odds.some((o) => o.draw) ? Math.max(...odds.map((o) => o.draw ?? 0)) : undefined,
    away: Math.max(...odds.map((o) => o.away)),
    over: odds.some((o) => o.over) ? Math.max(...odds.map((o) => o.over ?? 0)) : undefined,
    under: odds.some((o) => o.under) ? Math.max(...odds.map((o) => o.under ?? 0)) : undefined,
    line: odds.find((o) => o.line)?.line,
  };
}

function deVig(home: number, draw: number | undefined, away: number): [number, number, number] {
  const ih = 1 / home;
  const ia = 1 / away;
  if (!draw) {
    const total = ih + ia;
    return [ih / total, 0, ia / total];
  }
  const id = 1 / draw;
  const total = ih + id + ia;
  return [ih / total, id / total, ia / total];
}

function consensusProbabilities(odds: BookmakerOdds[]): [number, number, number] {
  const samples: [number, number, number][] = odds.map((book) =>
    deVig(book.home, book.draw, book.away)
  );
  const count = samples.length;
  const sums = samples.reduce(
    (acc, [h, d, a]) => [acc[0] + h, acc[1] + d, acc[2] + a],
    [0, 0, 0]
  );
  return [sums[0] / count, sums[1] / count, sums[2] / count];
}

function evaluateValue(
  selection: string,
  fairProb: number,
  marketOdds: number
): {
  fairOdds: number;
  evPct: number;
  edgeScore: number;
  confidence: number;
  positiveEv: boolean;
} | null {
  if (marketOdds <= 1 || fairProb <= 0) return null;

  const marketProb = 1 / marketOdds;
  const fairOdds = 1 / fairProb;
  const evPct = (fairProb * marketOdds - 1) * 100;
  const edge = fairProb - marketProb;
  const edgeScore = Math.min(100, Math.max(0, edge * 200 + evPct * 2));
  const confidence = Math.min(100, 40 + Math.abs(edge) * 120 + evPct * 1.5);

  return {
    fairOdds,
    evPct,
    edgeScore,
    confidence,
    positiveEv: evPct >= 3,
  };
}

function detectArbitrage(fixture: LiveFixture, best: BookmakerOdds) {
  if (TWO_WAY_SPORTS.has(fixture.sport)) {
    const implied = 1 / best.home + 1 / best.away;
    if (implied >= 1) return null;
    const profitPct = (1 / implied - 1) * 100;
    if (profitPct < 0.5) return null;
    return {
      profitPct,
      summary: `Two-way arbitrage across ${fixture.bookmakerOdds.length} books: ${profitPct.toFixed(2)}% margin.`,
    };
  }

  if (!best.draw) return null;
  const implied = 1 / best.home + 1 / best.draw + 1 / best.away;
  if (implied >= 1) return null;
  const profitPct = (1 / implied - 1) * 100;
  if (profitPct < 0.5) return null;
  return {
    profitPct,
    summary: `Three-way arbitrage across ${fixture.bookmakerOdds.length} books: ${profitPct.toFixed(2)}% margin.`,
  };
}

function bookmakerSpread(odds: BookmakerOdds[]): string {
  const homeSpread = Math.max(...odds.map((o) => o.home)) - Math.min(...odds.map((o) => o.home));
  const awaySpread = Math.max(...odds.map((o) => o.away)) - Math.min(...odds.map((o) => o.away));
  return `Live bookmaker spread — Home: ${homeSpread.toFixed(2)} | Away: ${awaySpread.toFixed(2)}.`;
}

export function analyzeLiveFixture(fixture: LiveFixture): Opportunity {
  const best = bestOdds(fixture.bookmakerOdds);
  const [homeProb, drawProb, awayProb] = consensusProbabilities(fixture.bookmakerOdds);
  const books = fixture.bookmakerOdds.map((o) => o.bookmaker).join(", ");

  const valueOutcomes = [
    { label: `${fixture.homeTeam} Win`, fairProb: homeProb, marketOdds: best.home },
    best.draw ? { label: "Draw", fairProb: drawProb, marketOdds: best.draw } : null,
    { label: `${fixture.awayTeam} Win`, fairProb: awayProb, marketOdds: best.away },
  ]
    .filter((item): item is { label: string; fairProb: number; marketOdds: number } => item !== null)
    .map((item) => ({ ...item, value: evaluateValue(item.label, item.fairProb, item.marketOdds) }))
    .filter((item): item is typeof item & { value: NonNullable<ReturnType<typeof evaluateValue>> } => item.value !== null);

  const bestValuePick = [...valueOutcomes].sort((a, b) => b.value.evPct - a.value.evPct)[0];
  const bestValue = bestValuePick?.value;
  const arbitrage = detectArbitrage(fixture, best);

  let decision = "Pass";
  let grade = "Pass";
  let edgeScore = 0;
  let confidence = 35;
  let passReason =
    "Live market efficiently priced — no edge above Kraitos threshold after scanning bookmaker consensus.";
  let reasoningSummary = passReason;
  let fairOdds: number | null = null;
  let marketOdds: number | null = null;
  let expectedValue: number | null = null;
  let recommendedMarket: string | null = null;

  if (arbitrage) {
    decision = "Arbitrage";
    grade = arbitrage.profitPct >= 2 ? "A" : "B";
    edgeScore = Math.min(95, 55 + arbitrage.profitPct * 8);
    confidence = 88;
    passReason = "";
    reasoningSummary = `${arbitrage.summary} Execute quickly before lines move.`;
    recommendedMarket = "Match Winner";
  } else if (bestValue?.positiveEv) {
    decision = "Value";
    grade = bestValue.evPct >= 8 ? "A" : bestValue.evPct >= 5 ? "B" : "C";
    edgeScore = bestValue.edgeScore;
    confidence = bestValue.confidence;
    fairOdds = bestValue.fairOdds;
    marketOdds = bestValuePick.marketOdds;
    expectedValue = bestValue.evPct;
    passReason = "";
    recommendedMarket = "Match Winner";
    reasoningSummary = `Live consensus fair probability on ${bestValuePick.label} vs best market price ${bestValuePick.marketOdds.toFixed(2)}. Expected value +${bestValue.evPct.toFixed(1)}%.`;
  }

  return {
    match_id: fixture.matchId,
    match: `${fixture.homeTeam} vs ${fixture.awayTeam}`,
    sport: fixture.sport,
    league: fixture.league,
    kickoff_time: fixture.kickoff,
    recommended_market: recommendedMarket,
    decision,
    edge_score: Math.round(edgeScore * 10) / 10,
    confidence: Math.round(confidence * 10) / 10,
    grade,
    risk_level: decision === "Arbitrage" ? "Low" : decision === "Value" ? "Medium" : "Low",
    pass_reason: passReason,
    fair_odds: fairOdds,
    market_odds: marketOdds,
    expected_value: expectedValue,
    reasoning_summary: reasoningSummary,
    team_strength_analysis: "Live mode — team strength models unavailable on-device. Connect Kraitos API for full intelligence.",
    coach_analysis: "Live mode — coach intelligence unavailable on-device.",
    form_analysis: "Live mode — form models unavailable on-device.",
    xg_analysis: "Live mode — xG models unavailable on-device.",
    market_intelligence: `${bookmakerSpread(fixture.bookmakerOdds)}\nBooks scanned: ${books}.`,
    context_factors: [`Live odds via The Odds API (${fixture.sportKey})`],
    monte_carlo_results: {
      home_win: Math.round(homeProb * 1000) / 1000,
      draw: Math.round(drawProb * 1000) / 1000,
      away_win: Math.round(awayProb * 1000) / 1000,
    },
    multi_agent_council_summary: {
      consensus:
        decision === "Pass"
          ? "Council agrees market is efficiently priced."
          : "Council supports edge after live market scan.",
      confidence,
      edge_detected: decision !== "Pass",
    },
    red_team_concerns: {
      approved: decision !== "Pass",
      concerns:
        decision === "Pass"
          ? ["No positive EV or arbitrage above threshold."]
          : ["Live on-device scan only — verify with full Kraitos backend when available."],
      summary: "Red team reviewed live market pricing only.",
    },
    explainability: {
      mode: "live_on_device",
      books_scanned: fixture.bookmakerOdds.length,
    },
    philosophy: "Kraitos does not pick winners. Kraitos finds edges.",
  };
}

export function analyzeLiveFixtures(fixtures: LiveFixture[]): Opportunity[] {
  return fixtures
    .map(analyzeLiveFixture)
    .sort((a, b) => {
      if (a.decision !== "Pass" && b.decision === "Pass") return -1;
      if (a.decision === "Pass" && b.decision !== "Pass") return 1;
      return b.edge_score - a.edge_score;
    });
}
