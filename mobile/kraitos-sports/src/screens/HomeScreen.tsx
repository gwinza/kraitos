import React, { useCallback, useState } from "react";
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  RefreshControl,
  ActivityIndicator,
} from "react-native";
import { useFocusEffect } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { LinearGradient } from "expo-linear-gradient";
import {
  DataSourceMode,
  fetchOpportunitiesWithSource,
  Opportunity,
  refreshFixtures,
} from "../api/client";
import { DEMO_OPPORTUNITIES } from "../api/demoData";
import { EdgeBadge } from "../components/EdgeBadge";
import { theme, formatKickoff } from "../theme";
import { RootStackParamList } from "../../App";

type Props = {
  navigation: NativeStackNavigationProp<RootStackParamList, "Home">;
};

export function HomeScreen({ navigation }: Props) {
  const [data, setData] = useState<Opportunity[]>([]);
  const [loading, setLoading] = useState(true);
  const [dataMode, setDataMode] = useState<DataSourceMode>("demo");
  const [statusMessage, setStatusMessage] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      await refreshFixtures().catch(() => {});
      const result = await fetchOpportunitiesWithSource();
      if (result.opportunities.length > 0) {
        setData(result.opportunities);
        setDataMode(result.mode);
        setStatusMessage(result.message ?? "");
      } else {
        setData(DEMO_OPPORTUNITIES);
        setDataMode("demo");
        setStatusMessage(result.message ?? "Demo mode — configure live markets in Settings.");
      }
    } catch {
      setData(DEMO_OPPORTUNITIES);
      setDataMode("demo");
      setStatusMessage("Demo mode — could not load live markets.");
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const edges = data.filter((d) => d.decision !== "Pass");
  const passes = data.filter((d) => d.decision === "Pass");

  return (
    <View style={styles.container}>
      <LinearGradient colors={["#0a0e17", "#141b2d"]} style={styles.header}>
        <Text style={styles.logo}>KRAITOS SPORTS</Text>
        <Text style={styles.tagline}>Kraitos does not pick winners. Kraitos finds edges.</Text>
        <Text
          style={[
            styles.status,
            dataMode === "live" || dataMode === "backend" ? styles.statusLive : styles.statusDemo,
          ]}
        >
          {dataMode === "live"
            ? "Live markets"
            : dataMode === "backend"
              ? "Full Kraitos API"
              : "Demo mode"}
          {statusMessage ? ` — ${statusMessage}` : ""}
        </Text>
        <TouchableOpacity style={styles.settingsBtn} onPress={() => navigation.navigate("Settings")}>
          <Text style={styles.settingsBtnText}>Settings</Text>
        </TouchableOpacity>
        <View style={styles.statsRow}>
          <Stat label="Scanned" value={data.length} />
          <Stat label="Edges" value={edges.length} color={theme.success} />
          <Stat label="Pass" value={passes.length} color={theme.pass} />
        </View>
      </LinearGradient>

      {loading ? (
        <ActivityIndicator color={theme.accent} style={{ marginTop: 40 }} />
      ) : (
        <FlatList
          data={data}
          keyExtractor={(item) => item.match_id}
          refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={theme.accent} />}
          contentContainerStyle={styles.list}
          ListHeaderComponent={<Text style={styles.sectionTitle}>OPPORTUNITY RANKING</Text>}
          renderItem={({ item }) => (
            <TouchableOpacity
              style={styles.card}
              onPress={() => navigation.navigate("MatchDetail", { matchId: item.match_id, data: item })}
              activeOpacity={0.8}
            >
              <Text style={styles.league}>{item.league} · {item.sport}</Text>
              <Text style={styles.match}>{item.match}</Text>
              <Text style={styles.kickoff}>{formatKickoff(item.kickoff_time)}</Text>
              <EdgeBadge
                decision={item.decision}
                grade={item.grade}
                edgeScore={item.edge_score}
                confidence={item.confidence}
                riskLevel={item.risk_level}
              />
              {item.expected_value != null && item.decision !== "Pass" && (
                <Text style={styles.ev}>EV {item.expected_value > 0 ? "+" : ""}{item.expected_value?.toFixed(1)}%</Text>
              )}
              {item.decision === "Pass" && (
                <Text style={styles.passReason}>{item.pass_reason}</Text>
              )}
              {item.prediction && (
                <Text style={styles.prediction}>
                  Prediction: {item.prediction}
                  {item.prediction_confidence != null ? ` (${item.prediction_confidence.toFixed(0)}%)` : ""}
                </Text>
              )}
            </TouchableOpacity>
          )}
        />
      )}
    </View>
  );
}

function Stat({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <View style={styles.stat}>
      <Text style={[styles.statValue, color ? { color } : null]}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: theme.bg },
  header: { paddingTop: 56, paddingHorizontal: 20, paddingBottom: 20 },
  logo: { fontSize: 22, fontWeight: "900", color: theme.accent, letterSpacing: 3 },
  tagline: { fontSize: 12, color: theme.textMuted, marginTop: 6, fontStyle: "italic" },
  status: { fontSize: 11, marginTop: 8, lineHeight: 16 },
  statusLive: { color: theme.success },
  statusDemo: { color: theme.warning },
  settingsBtn: {
    alignSelf: "flex-start",
    marginTop: 12,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: theme.accent,
  },
  settingsBtnText: { color: theme.accent, fontSize: 12, fontWeight: "700" },
  statsRow: { flexDirection: "row", marginTop: 20, gap: 24 },
  stat: { alignItems: "center" },
  statValue: { fontSize: 24, fontWeight: "800", color: theme.text },
  statLabel: { fontSize: 11, color: theme.textMuted, marginTop: 2 },
  list: { padding: 16, paddingBottom: 40 },
  sectionTitle: { color: theme.textMuted, fontSize: 11, letterSpacing: 2, marginBottom: 12 },
  card: {
    backgroundColor: theme.card,
    borderRadius: 14,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: theme.cardBorder,
  },
  league: { fontSize: 11, color: theme.accent, fontWeight: "600", letterSpacing: 0.5 },
  match: { fontSize: 17, fontWeight: "700", color: theme.text, marginTop: 4 },
  kickoff: { fontSize: 12, color: theme.textMuted, marginTop: 4 },
  ev: { fontSize: 14, color: theme.success, fontWeight: "700", marginTop: 8 },
  passReason: { fontSize: 12, color: theme.pass, marginTop: 8, fontStyle: "italic" },
  prediction: { fontSize: 12, color: theme.gold, marginTop: 6, fontWeight: "600" },
});
