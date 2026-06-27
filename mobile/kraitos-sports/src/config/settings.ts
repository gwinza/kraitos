import AsyncStorage from "@react-native-async-storage/async-storage";
import Constants from "expo-constants";

const KEYS = {
  oddsApiKey: "kraitos.odds_api_key",
  apiBaseUrl: "kraitos.api_base_url",
} as const;

export type DataMode = "live" | "backend" | "demo";

export interface AppSettings {
  oddsApiKey: string;
  apiBaseUrl: string;
}

function extraValue(name: "oddsApiKey" | "apiBaseUrl"): string {
  const extra = Constants.expoConfig?.extra as Record<string, string> | undefined;
  return extra?.[name]?.trim() ?? "";
}

export async function loadSettings(): Promise<AppSettings> {
  const [storedKey, storedUrl] = await Promise.all([
    AsyncStorage.getItem(KEYS.oddsApiKey),
    AsyncStorage.getItem(KEYS.apiBaseUrl),
  ]);

  return {
    oddsApiKey: storedKey?.trim() || extraValue("oddsApiKey"),
    apiBaseUrl: storedUrl?.trim() || extraValue("apiBaseUrl"),
  };
}

export async function saveSettings(settings: Partial<AppSettings>): Promise<AppSettings> {
  const current = await loadSettings();
  const next: AppSettings = {
    oddsApiKey: settings.oddsApiKey?.trim() ?? current.oddsApiKey,
    apiBaseUrl: settings.apiBaseUrl?.trim() ?? current.apiBaseUrl,
  };

  await Promise.all([
    AsyncStorage.setItem(KEYS.oddsApiKey, next.oddsApiKey),
    AsyncStorage.setItem(KEYS.apiBaseUrl, next.apiBaseUrl),
  ]);

  return next;
}
