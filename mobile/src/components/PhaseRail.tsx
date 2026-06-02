import React from 'react';
import { View, Text, StyleSheet, Pressable, TextInput, ActivityIndicator, ScrollView, KeyboardAvoidingView, Platform, SafeAreaView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii, shadow } from '../theme';
import type { TripScreen, TripPhase, TripSession, ClipAnalysis, TripContext, RenderOptions, ProjectSummary } from '../types';
import { absoluteUrl } from '../api';
import { VideoView, useVideoPlayer } from 'expo-video';


export function PhaseRail({ screen, phase }: { screen: TripScreen; phase: TripPhase }) {
  const steps: { key: TripScreen; label: string; icon: keyof typeof Ionicons.glyphMap }[] = [
    { key: 'context', label: 'Context', icon: 'chatbubble-ellipses-outline' },
    { key: 'upload', label: 'Media', icon: 'cloud-upload-outline' },
    { key: 'plan', label: 'Story', icon: 'sparkles-outline' },
    { key: 'output', label: 'Video', icon: 'film-outline' },
  ];
  const activeIndex = steps.findIndex((step) => step.key === screen);

  return (
    <View style={styles.phaseRail}>
      {steps.map((step, index) => {
        const active = index === activeIndex;
        const done = index < activeIndex || phase === 'complete';
        return (
          <View key={step.key} style={styles.phaseItem}>
            <View style={[styles.phaseIcon, active && styles.phaseIconActive, done && styles.phaseIconDone]}>
              <Ionicons name={done ? 'checkmark' : step.icon} size={15} color={active || done ? colors.white : colors.muted} />
            </View>
            <Text style={[styles.phaseText, active && styles.phaseTextActive]}>{step.label}</Text>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  phaseRail: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 10,
    borderRadius: radii.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.line,
    ...shadow,
  },
  phaseItem: {
    flex: 1,
    alignItems: 'center',
    gap: 5,
  },
  phaseIcon: {
    width: 28,
    height: 28,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surfaceRaised,
  },
  phaseIconActive: {
    backgroundColor: colors.blue,
    borderColor: colors.blue,
  },
  phaseIconDone: {
    backgroundColor: colors.green,
    borderColor: colors.green,
  },
  phaseText: {
    color: colors.muted,
    fontSize: 11,
    lineHeight: 14,
    fontWeight: '700',
  },
  phaseTextActive: {
    color: colors.ink,
  },
});
