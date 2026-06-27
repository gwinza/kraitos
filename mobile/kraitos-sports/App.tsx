import React, { useEffect } from "react";
import { NavigationContainer, DarkTheme } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { StatusBar } from "expo-status-bar";
import { HomeScreen } from "./src/screens/HomeScreen";
import { MatchDetailScreen } from "./src/screens/MatchDetailScreen";
import { SettingsScreen } from "./src/screens/SettingsScreen";
import { Opportunity } from "./src/api/client";
import { theme } from "./src/theme";
import { registerForPushNotifications, startEdgePolling, stopEdgePolling } from "./src/services/notifications";

export type RootStackParamList = {
  Home: undefined;
  Settings: undefined;
  MatchDetail: { matchId: string; data: Opportunity };
};

const Stack = createNativeStackNavigator<RootStackParamList>();

const navTheme = {
  ...DarkTheme,
  colors: {
    ...DarkTheme.colors,
    background: theme.bg,
    card: theme.card,
    text: theme.text,
    border: theme.cardBorder,
    primary: theme.accent,
  },
};

export default function App() {
  useEffect(() => {
    registerForPushNotifications().then((ok) => {
      if (ok) startEdgePolling();
    });
    return () => stopEdgePolling();
  }, []);

  return (
    <NavigationContainer theme={navTheme}>
      <StatusBar style="light" />
      <Stack.Navigator
        screenOptions={{
          headerStyle: { backgroundColor: theme.bg },
          headerTintColor: theme.accent,
          headerTitleStyle: { fontWeight: "700" },
          contentStyle: { backgroundColor: theme.bg },
        }}
      >
        <Stack.Screen
          name="Home"
          component={HomeScreen}
          options={{ headerShown: false }}
        />
        <Stack.Screen
          name="Settings"
          component={SettingsScreen}
          options={{ title: "Live Markets" }}
        />
        <Stack.Screen
          name="MatchDetail"
          component={MatchDetailScreen}
          options={{ title: "Match Intelligence" }}
        />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
