import React, { useEffect, useRef, useState } from "react";
import { Animated, Easing, ViewStyle } from "react-native";

// useRef(new Animated.Value()).current trips react-hooks/refs; a lazy
// useState gives the same stable instance without the ref read in render.
function useAnimatedValue(initial: number): Animated.Value {
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
