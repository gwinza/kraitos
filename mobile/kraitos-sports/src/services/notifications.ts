import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";
import { fetchAlerts, EdgeAlert } from "../api/client";

const POLL_MS = 5 * 60 * 1000;

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
  }),
});

let pollTimer: ReturnType<typeof setInterval> | null = null;
let lastAlertKeys = new Set<string>();

export async function registerForPushNotifications(): Promise<boolean> {
  if (!Device.isDevice && Platform.OS === "android") {
    // Emulator — still allow local notifications
  }

  const { status: existing } = await Notifications.getPermissionsAsync();
  let finalStatus = existing;
  if (existing !== "granted") {
    const { status } = await Notifications.requestPermissionsAsync();
    finalStatus = status;
  }

  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync("edges", {
      name: "Edge Alerts",
      importance: Notifications.AndroidImportance.HIGH,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: "#00d4aa",
    });
  }

  return finalStatus === "granted";
}

export async function notifyEdgeAlerts(alerts: EdgeAlert[]): Promise<number> {
  let sent = 0;
  for (const alert of alerts) {
    const key = `${alert.match_id}-${alert.edge_score}`;
    if (lastAlertKeys.has(key)) continue;
    lastAlertKeys.add(key);

    await Notifications.scheduleNotificationAsync({
      content: {
        title: "Kraitos Edge Detected",
        body: alert.message,
        data: { matchId: alert.match_id },
        sound: true,
      },
      trigger: null,
    });
    sent += 1;
  }
  return sent;
}

export function startEdgePolling(onAlerts?: (alerts: EdgeAlert[]) => void): void {
  stopEdgePolling();

  const poll = async () => {
    try {
      const alerts = await fetchAlerts();
      if (alerts.length > 0) {
        await notifyEdgeAlerts(alerts);
        onAlerts?.(alerts);
      }
    } catch {
      // API offline — silent
    }
  };

  poll();
  pollTimer = setInterval(poll, POLL_MS);
}

export function stopEdgePolling(): void {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}
