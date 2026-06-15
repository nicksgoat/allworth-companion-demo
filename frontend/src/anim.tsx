import React, { useEffect, useRef, useState } from "react";
import { Animated, Easing, ViewStyle } from "react-native";

// useRef(new Animated.Value()).current trips react-hooks/refs; a lazy
// useState gives the same stable instance without the ref read in render.
export function useAnimatedValue(initial: number): Animated.Value {
  const [value] = useState(() => new Animated.Value(initial));
  return value;
}

// rAF-driven because Animated can't interpolate rendered text.
export function useCountUp(value: number, duration = 550): number {
  const [displayed, setDisplayed] = useState(Math.round(value * 0.97));
  const raf = useRef<number>(0);

  useEffect(() => {
    const from = Math.round(value * 0.97);
    const start = Date.now();
    setDisplayed(from);
    const tick = () => {
      const t = Math.min(1, (Date.now() - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplayed(Math.round(from + (value - from) * eased));
      if (t < 1) raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [value, duration]);

  return displayed;
}

// Looping opacity pulse — for "thinking" indicators and the typing cursor.
export function usePulse(min = 0.35, max = 1, duration = 700): Animated.Value {
  const value = useAnimatedValue(max);
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(value, {
          toValue: min,
          duration,
          easing: Easing.inOut(Easing.quad),
          useNativeDriver: false,
        }),
        Animated.timing(value, {
          toValue: max,
          duration,
          easing: Easing.inOut(Easing.quad),
          useNativeDriver: false,
        }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [value, min, max, duration]);
  return value;
}

// Soft fade + scale entrance — for tool chips appearing one at a time.
export function FadeScaleIn({
  children,
  style,
}: {
  children: React.ReactNode;
  style?: ViewStyle;
}) {
  const progress = useAnimatedValue(0);
  useEffect(() => {
    Animated.timing(progress, {
      toValue: 1,
      duration: 300,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: false,
    }).start();
  }, [progress]);
  return (
    <Animated.View
      style={[
        style,
        {
          opacity: progress,
          transform: [
            { scale: progress.interpolate({ inputRange: [0, 1], outputRange: [0.9, 1] }) },
          ],
        },
      ]}
    >
      {children}
    </Animated.View>
  );
}

export function RiseIn({
  children,
  delay = 0,
  style,
}: {
  children: React.ReactNode;
  delay?: number;
  style?: ViewStyle;
}) {
  const progress = useAnimatedValue(0);

  useEffect(() => {
    Animated.timing(progress, {
      toValue: 1,
      duration: 420,
      delay,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: false,
    }).start();
  }, [progress, delay]);

  return (
    <Animated.View
      style={[
        style,
        {
          opacity: progress,
          transform: [
            { translateY: progress.interpolate({ inputRange: [0, 1], outputRange: [14, 0] }) },
          ],
        },
      ]}
    >
      {children}
    </Animated.View>
  );
}
