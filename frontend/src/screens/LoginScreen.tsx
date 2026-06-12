import { Ionicons } from "@expo/vector-icons";
import React, { useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useAuth } from "../auth";
import { colors, fonts } from "../theme";

export function LoginScreen() {
  const insets = useSafeAreaInsets();
  const { loginWithEmail } = useAuth();
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

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

  return (
    <KeyboardAvoidingView
      style={[styles.container, { paddingTop: insets.top + 60 }]}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={styles.header}>
        <Text style={styles.brandMark}>Allworth</Text>
        <Text style={styles.subtitle}>Financial Companion</Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Sign In</Text>
        <Text style={styles.cardDescription}>
          Enter the email address associated with your account.
        </Text>

        <View style={styles.inputWrapper}>
          <Ionicons
            name="mail-outline"
            size={20}
            color={colors.inkTertiary}
            style={styles.inputIcon}
          />
          <TextInput
            style={styles.input}
            placeholder="your.email@example.com"
            placeholderTextColor={colors.inkTertiary}
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

        {error && (
          <View style={styles.errorRow}>
            <Ionicons name="alert-circle" size={16} color={colors.loss} />
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}

        <Pressable
          style={[styles.button, loading && styles.buttonDisabled]}
          onPress={handleLogin}
          disabled={loading}
        >
          {loading ? (
            <ActivityIndicator color="#fff" size="small" />
          ) : (
            <Text style={styles.buttonText}>Continue</Text>
          )}
        </Pressable>
      </View>

      <Text style={styles.footer}>
        Don't have access? Contact your financial advisor.
      </Text>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.surfacePrimary,
    paddingHorizontal: 24,
  },
  header: {
    alignItems: "center",
    marginBottom: 48,
  },
  brandMark: {
    fontFamily: fonts.display,
    fontSize: 36,
    color: colors.allworthNavy,
  },
  subtitle: {
    fontFamily: fonts.sans,
    fontSize: 14,
    color: colors.inkTertiary,
    marginTop: 4,
  },
  card: {
    backgroundColor: colors.surfaceCard,
    borderRadius: 16,
    padding: 24,
    shadowColor: "#000",
    shadowOpacity: 0.06,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 4 },
    elevation: 3,
  },
  cardTitle: {
    fontFamily: fonts.displayMedium,
    fontSize: 22,
    color: colors.inkPrimary,
    marginBottom: 6,
  },
  cardDescription: {
    fontFamily: fonts.sans,
    fontSize: 14,
    color: colors.inkSecondary,
    lineHeight: 20,
    marginBottom: 20,
  },
  inputWrapper: {
    flexDirection: "row",
    alignItems: "center",
    borderWidth: 1,
    borderColor: colors.hairline,
    borderRadius: 10,
    backgroundColor: colors.surfacePrimary,
    paddingHorizontal: 12,
    height: 48,
    marginBottom: 12,
  },
  inputIcon: {
    marginRight: 8,
  },
  input: {
    flex: 1,
    fontFamily: fonts.sans,
    fontSize: 16,
    color: colors.inkPrimary,
  },
  errorRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginBottom: 12,
  },
  errorText: {
    fontFamily: fonts.sans,
    fontSize: 13,
    color: colors.loss,
    flex: 1,
  },
  button: {
    backgroundColor: colors.allworthNavy,
    borderRadius: 10,
    height: 48,
    alignItems: "center",
    justifyContent: "center",
    marginTop: 8,
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  buttonText: {
    fontFamily: fonts.sansBold,
    fontSize: 16,
    color: "#fff",
  },
  footer: {
    fontFamily: fonts.sans,
    fontSize: 12,
    color: colors.inkTertiary,
    textAlign: "center",
    marginTop: 24,
  },
});
