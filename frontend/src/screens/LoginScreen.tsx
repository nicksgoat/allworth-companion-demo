import { Ionicons } from "@expo/vector-icons";
import React, { useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  LayoutChangeEvent,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Svg, { Defs, LinearGradient, RadialGradient, Rect, Stop } from "react-native-svg";
import { AllworthLogo } from "../components/Wordmark";
import { useAuth } from "../auth";
import { colors, fonts } from "../theme";

export function LoginScreen() {
  const insets = useSafeAreaInsets();
  const { loginWithEmail } = useAuth();
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [bg, setBg] = useState({ w: 0, h: 0 });

  const handleLogin = async () => {
    const trimmed = email.trim().toLowerCase();
    if (!trimmed || !trimmed.includes("@")) {
      setError("Please enter a valid email address.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      await loginWithEmail(trimmed);
    } catch (e: any) {
      setError(e.message || "Login failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const onLayout = (e: LayoutChangeEvent) =>
    setBg({ w: e.nativeEvent.layout.width, h: e.nativeEvent.layout.height });

  return (
    <View style={styles.container} onLayout={onLayout}>
      {/* Premium hero surface: Night Blue → Indigo gradient with a soft
          cerulean glow behind the lockup (brand deck p.7). */}
      {bg.w > 0 ? (
        <Svg style={StyleSheet.absoluteFill} width={bg.w} height={bg.h}>
          <Defs>
            <LinearGradient id="loginBg" x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor={colors.chartNightBlue} />
              <Stop offset="1" stopColor={colors.allworthNavy} />
            </LinearGradient>
            <RadialGradient id="loginGlow" cx="50%" cy="26%" r="60%">
              <Stop offset="0" stopColor={colors.allworthAccent} stopOpacity={0.32} />
              <Stop offset="1" stopColor={colors.allworthAccent} stopOpacity={0} />
            </RadialGradient>
          </Defs>
          <Rect x={0} y={0} width={bg.w} height={bg.h} fill="url(#loginBg)" />
          <Rect x={0} y={0} width={bg.w} height={bg.h} fill="url(#loginGlow)" />
        </Svg>
      ) : null}

      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <View
          style={[
            styles.content,
            { paddingTop: insets.top + 96, paddingBottom: insets.bottom + 20 },
          ]}
        >
          {/* Brand lockup + promise */}
          <View style={styles.brand}>
            <AllworthLogo light width={208} />
            <Text style={styles.tagline}>You get a financial ally for life.</Text>
          </View>

          {/* Sign in */}
          <View style={styles.signIn}>
            <Text style={styles.heading}>Welcome back</Text>
            <Text style={styles.subhead}>Enter the email linked to your account.</Text>

            <View style={styles.inputWrapper}>
              <Ionicons
                name="mail-outline"
                size={20}
                color="rgba(255,255,255,0.55)"
                style={styles.inputIcon}
              />
              <TextInput
                style={styles.input}
                placeholder="your.email@example.com"
                placeholderTextColor="rgba(255,255,255,0.45)"
                value={email}
                onChangeText={(t) => {
                  setEmail(t);
                  if (error) setError(null);
                }}
                keyboardType="email-address"
                autoCapitalize="none"
                autoCorrect={false}
                autoComplete="email"
                returnKeyType="go"
                onSubmitEditing={handleLogin}
                editable={!loading}
              />
            </View>

            {error ? (
              <View style={styles.errorRow}>
                <Ionicons name="alert-circle" size={16} color={colors.loss} />
                <Text style={styles.errorText}>{error}</Text>
              </View>
            ) : null}

            <Pressable
              style={({ pressed }) => [
                styles.button,
                pressed && { opacity: 0.85 },
                loading && styles.buttonDisabled,
              ]}
              onPress={handleLogin}
              disabled={loading}
            >
              {loading ? (
                <ActivityIndicator color={colors.allworthNavy} size="small" />
              ) : (
                <Text style={styles.buttonText}>Continue</Text>
              )}
            </Pressable>
          </View>

          <View style={styles.flex} />

          <Text style={styles.footer}>Don{"'"}t have access? Contact your financial advisor.</Text>
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.chartNightBlue },
  flex: { flex: 1 },
  content: { flex: 1, paddingHorizontal: 28 },
  brand: { alignItems: "center", gap: 18 },
  tagline: {
    fontFamily: fonts.displayItalic,
    fontSize: 17,
    color: "rgba(255,255,255,0.82)",
    textAlign: "center",
  },
  signIn: { marginTop: 56 },
  heading: { fontFamily: fonts.displayMedium, fontSize: 26, color: "#FFFFFF" },
  subhead: {
    fontFamily: fonts.sans,
    fontSize: 15,
    color: "rgba(255,255,255,0.7)",
    marginTop: 6,
    marginBottom: 22,
  },
  inputWrapper: {
    flexDirection: "row",
    alignItems: "center",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.2)",
    borderRadius: 12,
    backgroundColor: "rgba(255,255,255,0.08)",
    paddingHorizontal: 14,
    height: 54,
  },
  inputIcon: { marginRight: 10 },
  input: { flex: 1, fontFamily: fonts.sans, fontSize: 16, color: "#FFFFFF" },
  errorRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 12 },
  errorText: { fontFamily: fonts.sans, fontSize: 13, color: colors.loss, flex: 1 },
  button: {
    backgroundColor: "#FFFFFF",
    borderRadius: 12,
    height: 54,
    alignItems: "center",
    justifyContent: "center",
    marginTop: 18,
  },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { fontFamily: fonts.sansBold, fontSize: 16, color: colors.allworthNavy },
  footer: {
    fontFamily: fonts.sans,
    fontSize: 12.5,
    color: "rgba(255,255,255,0.55)",
    textAlign: "center",
  },
});
