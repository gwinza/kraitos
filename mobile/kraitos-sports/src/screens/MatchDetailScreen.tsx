import React from "react";
import { ScrollView, Text, StyleSheet, View } from "react-native";
import { NativeStackScreenProps } from "@react-navigation/native-stack";
import { SectionCard } from "../components/SectionCard";
import { EdgeBadge } from "../components/EdgeBadge";
import { theme, formatKickoff, decisionColor } from "../theme";
import { RootStackParamList } from "../../App";

type Props = NativeStackScreenProps<RootStackParamList, "MatchDetail">;

export function MatchDetailScreen({ route }: Props) {
  const item = route.params.data;

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.league}>{item.league} · {item.sport}</Text>
      <Text style={styles.match}>{item.match}</Text>
      <Text style={styles.kickoff}>Kick-off: {formatKickoff(item.kickoff_time)}</Text>

      <EdgeBadge
        decision={item.decision}
        grade={item.grade}
        edgeScore={item.edge_score}
        confidence={item.confidence}
        riskLevel={item.risk_level}
      />

      <SectionCard title="Decision" accent={decisionColor(item.decision)}>
        <Row label="Recommended Market" value={item.recommended_market ?? "—"} />
        <Row label="Decision" value={item.decision} highlight />
        <Row label="Fair Odds" value={item.fair_odds?.toFixed(2) ?? "—"} />
        <Row label="Market Odds" value={item.market_odds?.toFixed(2) ?? "—"} />
        <Row label="Expected Value" value={item.expected_value != null ? `${item.expected_value > 0 ? "+" : ""}${item.expected_value.toFixed(1)}%` : "—"} />
      </SectionCard>

      <SectionCard title="Reasoning Summary">
        <Text style={styles.body}>{item.reasoning_summary}</Text>
      </SectionCard>

      {item.prediction && (
        <SectionCard title="Kraitos Prediction" accent={theme.gold}>
          <Row label="Predicted Outcome" value={item.prediction} highlight />
          <Row
            label="Prediction Confidence"
            value={item.prediction_confidence != null ? `${item.prediction_confidence.toFixed(0)}%` : "—"}
          />
          {item.prediction_reasoning && (
            <Text style={[styles.body, { marginTop: 12 }]}>{item.prediction_reasoning}</Text>
          )}
          {item.prediction_detail?.reasons && (
            <View style={{ marginTop: 12 }}>
              <Text style={styles.subheading}>Why Kraitos predicts this:</Text>
              {(item.prediction_detail.reasons as Array<{ factor: string; impact: string; detail: string }>).map(
                (r, i) => (
                  <View key={i} style={styles.reasonRow}>
                    <Text style={styles.reasonFactor}>{r.factor}</Text>
                    <Text style={styles.reasonImpact}>{r.impact}</Text>
                    <Text style={styles.reasonDetail}>{r.detail}</Text>
                  </View>
                )
              )}
            </View>
          )}
          {item.prediction_detail?.divergence && (
            <Text style={[styles.divergence, { marginTop: 10 }]}>
              {item.prediction_detail.divergence as string}
            </Text>
          )}
          {item.prediction_detail?.caveats && (
            <View style={{ marginTop: 10 }}>
              {(item.prediction_detail.caveats as string[]).map((c, i) => (
                <Text key={i} style={styles.caveat}>⚠ {c}</Text>
              ))}
            </View>
          )}
        </SectionCard>
      )}

      <SectionCard title="Team Strength Analysis">
        <Text style={styles.body}>{item.team_strength_analysis}</Text>
      </SectionCard>

      <SectionCard title="Coach Analysis">
        <Text style={styles.body}>{item.coach_analysis || "No coach data."}</Text>
      </SectionCard>

      <SectionCard title="Form Analysis">
        <Text style={styles.body}>{item.form_analysis || "No form data."}</Text>
      </SectionCard>

      <SectionCard title="xG Analysis">
        <Text style={styles.body}>{item.xg_analysis || "No xG data."}</Text>
      </SectionCard>

      <SectionCard title="Market Intelligence">
        <Text style={styles.body}>{item.market_intelligence}</Text>
      </SectionCard>

      <SectionCard title="Context Factors">
        {item.context_factors.map((f, i) => (
          <Text key={i} style={styles.bullet}>• {f}</Text>
        ))}
      </SectionCard>

      {item.monte_carlo_results && (
        <SectionCard title="Monte Carlo Results">
          <Row label="Home Win" value={`${((item.monte_carlo_results.home_win as number) * 100).toFixed(1)}%`} />
          <Row label="Draw" value={`${((item.monte_carlo_results.draw as number) * 100).toFixed(1)}%`} />
          <Row label="Away Win" value={`${((item.monte_carlo_results.away_win as number) * 100).toFixed(1)}%`} />
          <Row label="Over 2.5" value={`${((item.monte_carlo_results.over_25 as number) * 100).toFixed(1)}%`} />
          <Row label="BTTS" value={`${((item.monte_carlo_results.btts as number) * 100).toFixed(1)}%`} />
        </SectionCard>
      )}

      {item.multi_agent_council_summary && (
        <SectionCard title="Multi-Agent Council">
          <Text style={styles.body}>{item.multi_agent_council_summary.consensus as string}</Text>
        </SectionCard>
      )}

      {item.red_team_concerns && (
        <SectionCard title="Red Team Concerns" accent={theme.danger}>
          <Text style={styles.body}>{item.red_team_concerns.summary as string}</Text>
          {(item.red_team_concerns.concerns as string[])?.map((c, i) => (
            <Text key={i} style={styles.concern}>⚠ {c}</Text>
          ))}
        </SectionCard>
      )}

      <SectionCard title="Human-in-the-Loop">
        <Text style={styles.body}>
          Kraitos provides intelligence, probabilities, evidence, and risk assessment.
          The final decision and execution belong to you. No automatic bet placement.
        </Text>
        <Text style={styles.golden}>Data → Probability → Value → Risk → Decision</Text>
      </SectionCard>

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

function Row({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <View style={styles.row}>
      <Text style={styles.label}>{label}</Text>
      <Text style={[styles.value, highlight ? { color: theme.accent, fontWeight: "700" } : null]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: theme.bg },
  content: { padding: 16 },
  league: { fontSize: 12, color: theme.accent, fontWeight: "600" },
  match: { fontSize: 22, fontWeight: "800", color: theme.text, marginTop: 4 },
  kickoff: { fontSize: 13, color: theme.textMuted, marginTop: 4, marginBottom: 8 },
  body: { fontSize: 14, color: theme.text, lineHeight: 22 },
  bullet: { fontSize: 14, color: theme.text, lineHeight: 22, marginBottom: 4 },
  concern: { fontSize: 13, color: theme.warning, marginTop: 6 },
  golden: { fontSize: 13, color: theme.gold, fontWeight: "600", marginTop: 12 },
  subheading: { fontSize: 12, color: theme.accent, fontWeight: "700", letterSpacing: 0.5, marginBottom: 8 },
  reasonRow: { marginBottom: 10, paddingLeft: 4, borderLeftWidth: 2, borderLeftColor: theme.cardBorder, paddingVertical: 4 },
  reasonFactor: { fontSize: 12, color: theme.accent, fontWeight: "700" },
  reasonImpact: { fontSize: 11, color: theme.textMuted, marginTop: 2 },
  reasonDetail: { fontSize: 13, color: theme.text, marginTop: 4, lineHeight: 20 },
  divergence: { fontSize: 13, color: theme.gold, fontStyle: "italic" },
  caveat: { fontSize: 12, color: theme.warning, marginTop: 4 },
  row: { flexDirection: "row", justifyContent: "space-between", marginBottom: 8 },
  label: { fontSize: 13, color: theme.textMuted },
  value: { fontSize: 13, color: theme.text, fontWeight: "500" },
});
