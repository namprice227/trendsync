import { View, Text, StyleSheet, Pressable, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii } from '../theme';

export function ProjectActionButton({
  icon,
  label,
  onPress,
  disabled,
  busy,
  danger,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  onPress: () => void;
  disabled?: boolean;
  busy?: boolean;
  danger?: boolean;
}) {
  return (
    <Pressable
      accessibilityLabel={label}
      onPress={onPress}
      disabled={disabled || busy}
      style={({ pressed, hovered }: any) => [
        styles.projectActionButton,
        danger && styles.projectActionDanger,
        (disabled || busy) && styles.projectActionDisabled,
        hovered && !disabled && !busy && styles.buttonHovered,
        pressed && !disabled && !busy && styles.buttonPressed,
      ]}
    >
      {busy ? <ActivityIndicator size="small" color={danger ? colors.red : colors.blue} /> : <Ionicons name={icon} size={16} color={danger ? colors.red : colors.graphite} />}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  projectActionButton: {
    width: 34,
    height: 34,
    borderRadius: radii.sm,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.line,
    ...Platform.select({
      web: {
        transition: 'all 150ms ease-out',
        cursor: 'pointer',
      } as any,
    }),
  },
  projectActionDanger: {
    backgroundColor: colors.surfaceRaised,
    borderColor: colors.redSoft,
  },
  projectActionDisabled: {
    opacity: 0.5,
    ...Platform.select({
      web: { cursor: 'not-allowed' } as any,
    }),
  },
  buttonHovered: {
    backgroundColor: colors.surfaceRaised,
    borderColor: colors.lineStrong,
  },
  buttonPressed: {
    transform: [{ scale: 0.95 }],
    backgroundColor: colors.line,
  },
});
