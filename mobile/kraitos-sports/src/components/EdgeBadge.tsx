import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { theme, decisionColor, gradeColor } from "../theme";

interface Props {
  decision: string;
  grade: string;
  edgeScore: number;
  confidence: number;
  riskLevel: string;
}

export function EdgeBadge({ decision, grade, edgeScore, confidence, riskLevel }: Props) {
  return (
    <View style={styles.row}>
      <View style={[styles.badge, { borderColor: decisionColor(decision) }]}>
        <Text style={[styles.decision, { color: decisionColor(decision) }]}>{decision}</Text>
      </View>
      <View style={[styles.grade, { backgroundColor: gradeColor(grade) + "22" }]}>
        <Text style={[styles.gradeText, { color: gradeColor(grade) }]}>{grade}</Text>
      </View>
      <Text style={styles.meta}>Edge {edgeScore.toFixed(0)} · Conf {confidence.toFixed(0)} · {riskLevel}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: 8, marginTop: 8 },
  badge: { borderWidth: 1, borderRadius: 6, paddingHorizontal: 10, paddingVertical: 4 },
  decision: { fontSize: 12, fontWeight: "700", letterSpacing: 0.5 },
  grade: { borderRadius: 6, paddingHorizontal: 8, paddingVertical: 4 },
  gradeText: { fontSize: 13, fontWeight: "800" },
  meta: { fontSize: 11, color: theme.textMuted },
});
