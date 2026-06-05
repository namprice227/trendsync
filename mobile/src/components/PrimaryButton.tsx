import React from 'react';
import { View, Text, StyleSheet, Pressable, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii, shadow } from '../theme';

export function PrimaryButton({
  icon,
  label,
  onPress,
  disabled,
  tone = 'primary',
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  onPress: () => void;
  disabled?: boolean;
  tone?: 'primary' | 'light' | 'danger';
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      style={({ pressed, hovered }: any) => [
        styles.button,
        tone === 'light' && styles.buttonLight,
        tone === 'danger' && styles.buttonDanger,
        disabled && styles.buttonDisabled,
        hovered && !disabled && styles.buttonHovered,
        pressed && !disabled && styles.buttonPressed,
      ]}
    >
      <Ionicons name={icon} size={18} color={tone === 'light' ? colors.ink : colors.white} />
      <Text style={[styles.buttonText, tone === 'light' && styles.buttonTextLight]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: 48,
    borderRadius: radii.md,
    backgroundColor: colors.blue,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 8,
    paddingHorizontal: 14,
    flexGrow: 0,
    ...Platform.select({
      web: {
        transition: 'all 150ms ease-out',
        cursor: 'pointer',
      } as any,
    }),
  },
  buttonLight: {
    backgroundColor: colors.surfaceRaised,
    borderWidth: 1,
    borderColor: colors.line,
  },
  buttonDanger: {
    backgroundColor: colors.red,
  },
  buttonDisabled: {
    opacity: 0.48,
    ...Platform.select({
      web: { cursor: 'not-allowed' } as any,
    }),
  },
  buttonHovered: {
    backgroundColor: colors.blueDark,
  },
  buttonPressed: {
    transform: [{ scale: 0.98 }],
    opacity: 0.9,
  },
  buttonText: {
    color: colors.white,
    fontSize: 14,
    lineHeight: 18,
    fontWeight: '900',
  },
  buttonTextLight: {
    color: colors.ink,
  },
});
