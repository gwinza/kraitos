import React, { useCallback, useEffect, useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  Linking,
} from "react-native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { loadSettings, saveSettings } from "../config/settings";
import { theme } from "../theme";
import { RootStackParamList } from "../../App";

type Props = {
  navigation: NativeStackNavigationProp<RootStackParamList, "Settings">;
};

export function SettingsScreen({ navigation }: Props) {
  const [oddsApiKey, setOddsApiKey] = useState("");
  const [apiBaseUrl, setApiBaseUrl] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    loadSettings().then((settings) => {
      setOddsApiKey(settings.oddsApiKey);
      setApiBaseUrl(settings.apiBaseUrl);
      setLoading(false);
    });
  }, []);

  const onSave = useCallback(async () => {
    setSaving(true);
    setSaved(false);
    try {
      await saveSettings({ oddsApiKey, apiBaseUrl });
      setSaved(true);
      setTimeout(() => navigation.goBack(), 600);
    } finally {
      setSaving(false);
    }
  }, [apiBaseUrl, navigation, oddsApiKey]);

  if (loading) {
    return <ActivityIndicator color={theme.accent} style={{ marginTop: 80 }} />;
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.title}>Live Markets</Text>
      <Text style={styles.body}>
        Kraitos scans live bookmaker prices through The Odds API. Add your free API key to unlock
        real markets directly on your phone — no PC backend required.
      </Text>

      <Text style={styles.label}>The Odds API Key</Text>
      <TextInput
        style={styles.input}
        value={oddsApiKey}
        onChangeText={setOddsApiKey}
        placeholder="Paste your API key"
        placeholderTextColor={theme.textMuted}
        autoCapitalize="none"
        autoCorrect={false}
      />
      <TouchableOpacity onPress={() => Linking.openURL("https://the-odds-api.com")}>
        <Text style={styles.link}>Get a free key at the-odds-api.com</Text>
      </TouchableOpacity>

      <Text style={[styles.label, { marginTop: 24 }]}>Kraitos API URL (optional)</Text>
      <TextInput
        style={styles.input}
        value={apiBaseUrl}
        onChangeText={setApiBaseUrl}
        placeholder="http://192.168.1.10:8000"
        placeholderTextColor={theme.textMuted}
        autoCapitalize="none"
        autoCorrect={false}
      />
      <Text style={styles.hint}>
        Only needed for full 17-engine analysis. Leave blank to use on-device live market scanning.
      </Text>

      <TouchableOpacity style={styles.button} onPress={onSave} disabled={saving}>
        <Text style={styles.buttonText}>{saving ? "Saving..." : "Save & Refresh"}</Text>
      </TouchableOpacity>

      {saved && <Text style={styles.saved}>Saved. Returning to scanner...</Text>}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: theme.bg },
  content: { padding: 20, paddingBottom: 40 },
  title: { fontSize: 22, fontWeight: "800", color: theme.text, marginBottom: 10 },
  body: { fontSize: 14, color: theme.textMuted, lineHeight: 20, marginBottom: 20 },
  label: { fontSize: 12, color: theme.accent, fontWeight: "700", letterSpacing: 1, marginBottom: 8 },
  input: {
    backgroundColor: theme.card,
    borderWidth: 1,
    borderColor: theme.cardBorder,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: theme.text,
    fontSize: 15,
  },
  link: { color: theme.accent, marginTop: 10, fontSize: 13 },
  hint: { color: theme.textMuted, fontSize: 12, marginTop: 8, lineHeight: 18 },
  button: {
    marginTop: 28,
    backgroundColor: theme.accent,
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: "center",
  },
  buttonText: { color: "#041018", fontWeight: "800", fontSize: 15 },
  saved: { color: theme.success, marginTop: 12, textAlign: "center" },
});
