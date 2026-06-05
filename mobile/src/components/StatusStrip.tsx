import React from 'react';
import { View, Text, StyleSheet, Pressable, TextInput, ActivityIndicator, ScrollView, KeyboardAvoidingView, Platform, SafeAreaView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii, shadow } from '../theme';
import type { TripScreen, TripPhase, TripSession, ClipAnalysis, TripContext, RenderOptions, ProjectSummary } from '../types';
import { absoluteUrl } from '../api';
import { VideoView, useVideoPlayer } from 'expo-video';


export function StatusStrip({ session }: { session: TripSession }) {
  const toneStyle =
    session.phase === 'error'
      ? styles.statusError
      : session.phase === 'complete'
        ? styles.statusDone
        : session.phase === 'ready_to_render'
          ? styles.statusInfo
          : styles.statusNeutral;

  return (
    <View style={[styles.statusStrip, toneStyle]}>
      <View style={styles.statusIcon}>
        <Ionicons
          name={session.phase === 'complete' ? 'checkmark' : session.phase === 'error' ? 'warning-outline' : 'pulse-outline'}
          size={16}
          color={session.phase === 'error' ? colors.red : session.phase === 'complete' ? colors.green : colors.blue}
        />
      </View>
      <View style={styles.statusCopy}>
        <Text style={styles.statusLabel}>{session.progress_label}</Text>
        <Text style={styles.statusAction}>{session.error || session.active_job?.current_step || session.next_action}</Text>
        {session.active_job ? (
          <Text style={styles.projectMeta}>
            {session.active_job.type.replaceAll('_', ' ')} · {session.active_job.state.replaceAll('_', ' ')}
          </Text>
        ) : null}
        {session.progress_percent || session.active_job?.progress_percent ? (
          <View style={styles.progressTrack}>
            <View
              style={[
                styles.progressFill,
                { width: `${Math.min(100, Math.max(0, session.active_job?.progress_percent || session.progress_percent))}%` },
              ]}
            />
          </View>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  statusError: {
    backgroundColor: colors.redSoft,
    borderColor: '#ebc2ba',
  },
  statusDone: {
    backgroundColor: colors.greenSoft,
    borderColor: '#c5ddcb',
  },
  statusInfo: {
    backgroundColor: colors.blueSoft,
    borderColor: '#c4dde2',
  },
  statusNeutral: {
    backgroundColor: colors.surface,
    borderColor: colors.line,
  },
  statusStrip: {
    marginBottom: 10,
    borderRadius: radii.md,
    paddingHorizontal: 14,
    paddingVertical: 13,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 10,
    alignItems: 'center',
  },
  statusIcon: {
    width: 34,
    height: 34,
    borderRadius: radii.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surfaceRaised,
  },
  statusCopy: {
    flex: 1,
  },
  statusLabel: {
    color: colors.ink,
    fontSize: 13,
    lineHeight: 17,
    fontWeight: '800',
  },
  statusAction: {
    marginTop: 2,
    color: colors.graphite,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '600',
  },
  projectMeta: {
    color: colors.muted,
    fontSize: 11,
    lineHeight: 15,
    fontWeight: '700',
  },
  progressTrack: {
    height: 5,
    marginTop: 8,
    borderRadius: 999,
    overflow: 'hidden',
    backgroundColor: colors.line,
  },
  progressFill: {
    height: 5,
    borderRadius: 999,
    backgroundColor: colors.blue,
  },
});
