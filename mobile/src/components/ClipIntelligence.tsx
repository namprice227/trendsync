import React from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii } from '../theme';
import type { ClipAnalysis, SceneMemory } from '../types';
import { formatTimestamp } from "../utils/helpers";
import { SectionHeader } from "./SectionHeader";
import { Tag } from "./Tag";

function sceneTimeLabel(scene: SceneMemory): string {
  const start = scene.time_range?.start_sec ?? 0;
  const end = scene.time_range?.end_sec ?? start;
  return `${formatTimestamp(start)}-${formatTimestamp(end)}`;
}

export function ClipIntelligence({
  clips,
  sceneMemories = [],
  pinnedSceneIds = [],
  excludedSceneIds = [],
  onTogglePinScene,
  onToggleExcludeScene,
}: {
  clips: ClipAnalysis[];
  sceneMemories?: SceneMemory[];
  pinnedSceneIds?: string[];
  excludedSceneIds?: string[];
  onTogglePinScene?: (sceneId: string) => void;
  onToggleExcludeScene?: (sceneId: string) => void;
}) {
  if (!clips.length && !sceneMemories.length) return null;
  return (
    <View style={styles.insightPanel}>
      {sceneMemories.length ? (
        <View style={styles.section}>
          <SectionHeader icon="albums-outline" title="Scene memory" meta={`${sceneMemories.length} scenes`} />
          {sceneMemories.map((scene) => {
            const pinned = pinnedSceneIds.includes(scene.scene_id);
            const excluded = excludedSceneIds.includes(scene.scene_id);
            return (
              <View key={scene.scene_id} style={[styles.insightItem, excluded && styles.insightItemMuted]}>
                <View style={styles.insightHead}>
                  <View style={styles.titleBlock}>
                    <Text style={styles.insightTitle} numberOfLines={1}>{scene.clip_filename || scene.clip_id}</Text>
                    <Text style={styles.sceneMeta}>{sceneTimeLabel(scene)}</Text>
                  </View>
                  <View style={styles.actionRow}>
                    <Pressable
                      onPress={() => onTogglePinScene?.(scene.scene_id)}
                      disabled={excluded || !onTogglePinScene}
                      accessibilityLabel={pinned ? 'Unpin scene' : 'Pin scene'}
                      style={[styles.iconButton, (excluded || !onTogglePinScene) && styles.iconButtonDisabled]}
                    >
                      <Ionicons name={pinned ? 'star' : 'star-outline'} size={15} color={pinned ? colors.amber : colors.subtle} />
                    </Pressable>
                    <Pressable
                      onPress={() => onToggleExcludeScene?.(scene.scene_id)}
                      disabled={!onToggleExcludeScene}
                      accessibilityLabel={excluded ? 'Include scene' : 'Exclude scene'}
                      style={[styles.iconButton, !onToggleExcludeScene && styles.iconButtonDisabled]}
                    >
                      <Ionicons name={excluded ? 'eye-off' : 'eye-outline'} size={15} color={excluded ? colors.amber : colors.subtle} />
                    </Pressable>
                  </View>
                </View>
                <Text style={styles.listItem} numberOfLines={3}>{scene.visual_summary || scene.transcript || 'Scene evidence unavailable.'}</Text>
                <View style={styles.tagRow}>
                  {scene.location ? <Tag label={scene.location} tone="info" /> : null}
                  {scene.audio_value ? <Tag label={`audio ${scene.audio_value}`} /> : null}
                  {scene.visual_value ? <Tag label={`visual ${scene.visual_value}`} /> : null}
                  {pinned ? <Tag label="pinned" tone="success" /> : null}
                  {excluded ? <Tag label="excluded" tone="warning" /> : null}
                  {scene.narrative_role_candidates?.slice(0, 2).map((role) => <Tag key={`${scene.scene_id}-${role}`} label={role} />)}
                </View>
                {scene.transcript ? <Text style={styles.listItem} numberOfLines={2}>Speech: {scene.transcript}</Text> : null}
              </View>
            );
          })}
        </View>
      ) : null}

      {clips.length ? (
        <View style={styles.section}>
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
      ) : null}
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
    gap: 14,
  },
  section: {
    gap: 10,
  },
  insightItem: {
    borderTopWidth: 1,
    borderTopColor: colors.line,
    paddingTop: 10,
    gap: 7,
  },
  insightItemMuted: {
    opacity: 0.62,
  },
  insightHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  titleBlock: {
    flex: 1,
    minWidth: 0,
  },
  insightTitle: {
    flex: 1,
    color: colors.ink,
    fontSize: 13,
    lineHeight: 17,
    fontWeight: '900',
  },
  sceneMeta: {
    color: colors.muted,
    fontSize: 10,
    lineHeight: 14,
    fontWeight: '800',
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
  actionRow: {
    flexDirection: 'row',
    gap: 4,
  },
  iconButton: {
    width: 28,
    height: 28,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radii.sm,
    backgroundColor: colors.surfaceRaised,
  },
  iconButtonDisabled: {
    opacity: 0.45,
  },
});
