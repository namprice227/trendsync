import React from 'react';
import { View, Text, StyleSheet, Pressable, TextInput, ActivityIndicator, ScrollView, KeyboardAvoidingView, Platform, SafeAreaView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii, shadow } from '../theme';
import type { TripScreen, TripPhase, TripSession, ClipAnalysis, TripContext, RenderOptions, ProjectSummary } from '../types';
import { absoluteUrl } from '../api';
import { VideoView, useVideoPlayer } from 'expo-video';
import { formatTimestamp } from "../utils/helpers";
import { SectionHeader } from "./SectionHeader";
import { Tag } from "./Tag";

export function ClipIntelligence({ clips }: { clips: ClipAnalysis[] }) {
  if (!clips.length) return null;
  return (
    <View style={styles.insightPanel}>
      <SectionHeader icon="analytics-outline" title="Clip intelligence" meta={`${clips.length} analyzed`} />
      {clips.map((clip, index) => (
        <View key={`${clip.filename}-${index}`} style={styles.insightItem}>
          <View style={styles.insightHead}>
            <Text style={styles.insightTitle}>{clip.filename}</Text>
            <Tag label={clip.quality_label || 'unknown'} tone={clip.quality_label === 'dark' || clip.quality_label === 'soft or shaky' ? 'warning' : 'info'} />
          </View>
          <Text style={styles.listItem}>{clip.semantic_summary || clip.summary || 'Analysis unavailable.'}</Text>
          <View style={styles.tagRow}>
            {clip.locations_or_scenes?.slice(0, 3).map((scene) => <Tag key={scene} label={scene} />)}
            {clip.visible_subjects?.slice(0, 3).map((subject) => <Tag key={subject} label={subject} tone="success" />)}
          </View>
          {clip.best_moment_descriptions?.length ? (
            <Text style={styles.listItem}>
              {clip.best_moment_descriptions.map((moment) => `${formatTimestamp(moment.timestamp)} ${moment.description}`).join(' · ')}
            </Text>
          ) : null}
          {clip.best_moment_timestamps?.length ? (
            <Text style={styles.listItem}>Best moments: {clip.best_moment_timestamps.map(formatTimestamp).join(', ')}</Text>
          ) : null}
          {clip.landmark_candidate_timestamps?.length ? (
            <Text style={styles.listItem}>Scenic candidates: {clip.landmark_candidate_timestamps.map(formatTimestamp).join(', ')}</Text>
          ) : null}
          {clip.named_landmarks?.length ? (
            <Text style={styles.listItem}>Named places: {clip.named_landmarks.map((landmark) => landmark.name).join(', ')}</Text>
          ) : null}
          {clip.transcript ? <Text style={styles.listItem}>Speech: {clip.transcript}</Text> : null}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  insightPanel: {
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surface,
    padding: 14,
    gap: 10,
  },
  insightItem: {
    borderTopWidth: 1,
    borderTopColor: colors.line,
    paddingTop: 10,
    gap: 7,
  },
  insightHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  insightTitle: {
    flex: 1,
    color: colors.ink,
    fontSize: 13,
    lineHeight: 17,
    fontWeight: '900',
  },
  listItem: {
    color: colors.graphite,
    fontSize: 13,
    lineHeight: 19,
    fontWeight: '600',
  },
  tagRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
});
