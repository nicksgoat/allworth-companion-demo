import { Lato_400Regular, Lato_700Bold } from "@expo-google-fonts/lato";
import {
  PlayfairDisplay_600SemiBold,
  PlayfairDisplay_700Bold,
} from "@expo-google-fonts/playfair-display";
import { Ionicons } from "@expo/vector-icons";
import { NavigationContainer } from "@react-navigation/native";
import * as Haptics from "expo-haptics";
import { useFonts } from "expo-font";
import { StatusBar } from "expo-status-bar";
import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaProvider, useSafeAreaInsets } from "react-native-safe-area-context";
import { AppProvider, ClientTab, useApp } from "./src/state";
import { colors } from "./src/theme";
import { AdvisorNavigator } from "./src/screens/AdvisorScreens";
import { ChatScreen } from "./src/screens/ChatScreen";
import { DashboardScreen } from "./src/screens/DashboardScreen";
import { DemoControlSheet } from "./src/screens/DemoControlSheet";
import { ProfileScreen } from "./src/screens/ProfileScreen";
import { VisionScreen } from "./src/screens/VisionScreen";

export default function App() {
  const [fontsLoaded] = useFonts({
    Lato_400Regular,
    Lato_700Bold,
    PlayfairDisplay_600SemiBold,
    PlayfairDisplay_700Bold,
  });
  if (!fontsLoaded) return null;
  return (
    <SafeAreaProvider>
      <AppProvider>
        <NavigationContainer>
          <Root />
        </NavigationContainer>
      </AppProvider>
    </SafeAreaProvider>
  );
}

function Root() {
  const app = useApp();
  return (
    <View style={{ flex: 1, backgroundColor: colors.surfacePrimary }}>
      <StatusBar style={app.mode === "vision" ? "light" : "dark"} />
      {app.mode === "client" ? (
        <ClientTabs />
      ) : app.mode === "advisor" ? (
        <AdvisorNavigator />
      ) : (
        <VisionScreen />
      )}
      <DemoControlSheet />
    </View>
  );
}

const TABS: {
  tab: ClientTab;
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  iconActive: keyof typeof Ionicons.glyphMap;
}[] = [
  { tab: "home", label: "Home", icon: "home-outline", iconActive: "home" },
  { tab: "chat", label: "Chat", icon: "chatbubbles-outline", iconActive: "chatbubbles" },
  { tab: "profile", label: "Profile", icon: "person-outline", iconActive: "person" },
];

function ClientTabs() {
  const app = useApp();
  const insets = useSafeAreaInsets();

  return (
    <View style={{ flex: 1 }}>
      <View style={{ flex: 1 }}>
        {app.selectedTab === "home" ? (
          <DashboardScreen />
        ) : app.selectedTab === "chat" ? (
          <ChatScreen />
        ) : (
          <ProfileScreen />
        )}
      </View>
      <View style={[styles.tabBar, { paddingBottom: insets.bottom }]}>
        {TABS.map(({ tab, label, icon, iconActive }) => {
          const active = app.selectedTab === tab;
          return (
            <Pressable
              key={tab}
              style={styles.tabItem}
              onPress={() => {
                if (!active) Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                app.setSelectedTab(tab);
              }}
            >
              <Ionicons
                name={active ? iconActive : icon}
                size={24}
                color={active ? colors.allworthNavy : colors.inkTertiary}
              />
              <Text
                style={[
                  styles.tabLabel,
                  { color: active ? colors.allworthNavy : colors.inkTertiary },
                ]}
              >
                {label}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  tabBar: {
    flexDirection: "row",
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.hairline,
    backgroundColor: "#fff",
  },
  tabItem: { flex: 1, alignItems: "center", paddingTop: 8, gap: 2 },
  tabLabel: { fontSize: 10, fontWeight: "500" },
});
