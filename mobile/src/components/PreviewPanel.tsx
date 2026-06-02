import React from 'react';
import { View, Text, StyleSheet, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii } from '../theme';
import { VideoView, useVideoPlayer } from 'expo-video';
import type { TripSession } from '../types';
import { Tag } from './Tag';

function PreviewVideo({ source }: { source: string }) {
  const player = useVideoPlayer(source, (instance) => {
    instance.loop = false;
  });
  return <VideoView player={player} style={styles.video} allowsFullscreen contentFit="contain" />;
}

export function PreviewPanel({
  session,
  videoUrl,
}: {
  session: TripSession;
  videoUrl: string | null;
}) {
  const busy = session.phase === 'planning' || session.phase === 'rendering';
  const progress = session.active_job?.progress_percent || session.progress_percent || 0;

  return (
    <View style={styles.root}>
      {/* Status badge */}
      <View style={styles.statusRow}>
        <View style={styles.statusBadge}>
          <View style={[styles.statusDot, {
            backgroundColor: session.phase === 'complete' ? colors.green
              : session.phase === 'error' ? colors.red
              : busy ? colors.blue
              : colors.subtle,
          }]} />
          <Text style={styles.statusText}>
            {session.progress_label || session.phase.replaceAll('_', ' ')}
          </Text>
        </View>
        {session.phase !== 'collecting_context' ? (
          <Tag
            label={session.phase.replaceAll('_', ' ')}
            tone={session.phase === 'complete' ? 'success' : session.phase === 'error' ? 'warning' : 'info'}
          />
        ) : null}
      </View>

      {/* Video or placeholder */}
      <View style={styles.videoContainer}>
        {videoUrl ? (
          <PreviewVideo source={videoUrl} />
        ) : (
          <View style={styles.placeholder}>
            {busy ? (
              <View style={styles.busyOverlay}>
                <ActivityIndicator color={colors.blue} size="large" />
                <Text style={styles.busyText}>
                  {session.phase === 'planning' ? 'Generating story plan...' : 'Rendering video...'}
                </Text>
                {progress > 0 ? (
                  <View style={styles.progressTrack}>
                    <View style={[styles.progressFill, { width: `${Math.min(100, progress)}%` }]} />
                  </View>
                ) : null}
                {session.active_job?.current_step ? (
                  <Text style={styles.stepText}>{session.active_job.current_step}</Text>
                ) : null}
              </View>
            ) : (
              <>
                <View style={styles.placeholderIcon}>
                  <Ionicons name="play-circle-outline" size={48} color={colors.subtle} />
                </View>
                <Text style={styles.placeholderTitle}>
                  {session.media_items.length === 0
                    ? 'Upload clips to get started'
                    : session.story_plan
                      ? 'Ready to render'
                      : 'Add context and generate a story'}
                </Text>
                <Text style={styles.placeholderSub}>
                  {session.next_action || 'Your holiday recap preview will appear here'}
                </Text>
              </>
            )}
          </View>
        )}
      </View>

      {/* Error message */}
      {session.error && session.phase === 'error' ? (
        <View style={styles.errorBanner}>
          <Ionicons name="warning-outline" size={14} color={colors.red} />
          <Text style={styles.errorText} numberOfLines={2}>{session.error}</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.paper,
    padding: 12,
    gap: 10,
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  statusBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  statusText: {
    color: colors.graphite,
    fontSize: 12,
    fontWeight: '700',
  },
  videoContainer: {
    flex: 1,
    borderRadius: radii.lg,
    overflow: 'hidden',
    backgroundColor: colors.camera,
  },
  video: {
    width: '100%',
    height: '100%',
  },
  placeholder: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
    padding: 24,
  },
  placeholderIcon: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: colors.surfaceRaised,
    alignItems: 'center',
    justifyContent: 'center',
  },
  placeholderTitle: {
    color: colors.ink,
    fontSize: 16,
    fontWeight: '800',
    textAlign: 'center',
  },
  placeholderSub: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: '600',
    textAlign: 'center',
    maxWidth: 320,
  },
  busyOverlay: {
    alignItems: 'center',
    justifyContent: 'center',
    gap: 14,
    padding: 24,
  },
  busyText: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: '800',
  },
  stepText: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: '600',
  },
  progressTrack: {
    width: 200,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.surfaceRaised,
    overflow: 'hidden',
  },
  progressFill: {
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.blue,
  },
  errorBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderRadius: radii.md,
    backgroundColor: colors.redSoft,
    borderWidth: 1,
    borderColor: 'rgba(239, 68, 68, 0.25)',
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  errorText: {
    flex: 1,
    color: colors.red,
    fontSize: 12,
    fontWeight: '700',
  },
});
