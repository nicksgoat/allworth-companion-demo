import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import * as LocalAuthentication from "expo-local-authentication";
import React, { useCallback, useEffect, useState } from "react";
import { Platform, Pressable, StyleSheet, Text, View } from "react-native";
import { useAuth } from "../auth";
import { AllworthMark } from "../components/Wordmark";
import { colors, fonts, space } from "../theme";

// Biometric gate on app relaunch (fintech-quality mandate): a returning
// session unlocks with Face ID before the app renders. Devices without
// biometrics — and web — pass straight through; the lock must never be the
// thing that bricks a demo.
export function LockScreen({ onUnlocked }: { onUnlocked: () => void }) {
  const { session, logout } = useAuth();
  const [failed, setFailed] = useState(false);

  const attempt = useCallback(async () => {
    setFailed(false);
    try {
      if (Platform.OS === "web") {
        onUnlocked();
        return;
      }
      const [hasHardware, enrolled] = await Promise.all([
        LocalAuthentication.hasHardwareAsync(),
        LocalAuthentication.isEnrolledAsync(),
      ]);
      if (!hasHardware || !enrolled) {
        onUnlocked();
        return;
      }
      const result = await LocalAuthentication.authenticateAsync({
        promptMessage: "Unlock Allworth",
        cancelLabel: "Cancel",
      });
      if (result.success) {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        onUnlocked();
      } else {
        setFailed(true);
      }
    } catch {
      onUnlocked();
    }
  }, [onUnlocked]);

  useEffect(() => {
    attempt();
  }, [attempt]);

  const firstName = session?.contactName?.split(",")[0]?.split(" ")[0];

  return (
    <View style={styles.screen}>
      <View style={styles.center}>
        <View style={styles.markWrap}>
          <AllworthMark size={34} color="#FFFFFF" />
        </View>
        <Text style={styles.welcome}>Welcome back{firstName ? `, ${firstName}` : ""}</Text>
        <Text style={styles.sub}>Your account is locked</Text>
      </View>

      <View style={styles.footer}>
        <Pressable
          onPress={attempt}
          style={({ pressed }) => [styles.unlockBtn, pressed && { opacity: 0.85 }]}
        >
          <Ionicons name="lock-open-outline" size={18} color={colors.allworthNavy} />
          <Text style={styles.unlockText}>{failed ? "Try Face ID again" : "Unlock with Face ID"}</Text>
        </Pressable>
        <Pressable onPress={logout} hitSlop={8}>
          <Text style={styles.altText}>Sign in with email instead</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.surfaceHero,
    justifyContent: "space-between",
    paddingBottom: space[12],
  },
  center: { flex: 1, alignItems: "center", justifyContent: "center", gap: space[3] },
  markWrap: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: "rgba(255,255,255,0.08)",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: space[2],
  },
  welcome: { fontFamily: fonts.displayMedium, fontSize: 28, color: "#FFFFFF" },
  sub: { fontFamily: fonts.sans, fontSize: 14, color: "rgba(255,255,255,0.65)" },
  footer: { alignItems: "center", gap: space[4], paddingHorizontal: space[5] },
  unlockBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: space[2],
    backgroundColor: "#FFFFFF",
    borderRadius: 999,
    paddingVertical: space[3],
    alignSelf: "stretch",
  },
  unlockText: { fontSize: 15, fontFamily: fonts.sansBold, color: colors.allworthNavy },
  altText: { fontSize: 13, fontFamily: fonts.sans, color: "rgba(255,255,255,0.7)" },
});
