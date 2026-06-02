import React from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii } from '../theme';
import type { TripSession, MediaItem, RenderOptions, StoryPlan } from '../types';
import { formatTimestamp, fallbackSegmentId, segmentForDecision, windowForDecision } from '../utils/helpers';

export function TimelineStrip({
  session,
  options,
  scriptDrafts,
  onScriptChange,
  onMoveClip,
}: {
  session: TripSession;
  options: RenderOptions;
  scriptDrafts: Record<string, { voiceover: string; caption: string }>;
  onScriptChange: (segmentId: string, field: 'voiceover' | 'caption', value: string) => void;
  onMoveClip: (clipId: string, direction: -1 | 1) => void;
}) {
  const plan = session.story_plan;
  const editDecisions = Array.isArray(plan?.edit_decisions) ? plan.edit_decisions : [];
  const voiceoverSegments = Array.isArray(plan?.voiceover_segments) ? plan.voiceover_segments : [];
  const hasDecisions = editDecisions.length > 0;

  // If we have edit decisions, show them as the timeline.
  // Otherwise, show media items as clips.
  const items = hasDecisions
    ? editDecisions.map((decision, index) => {
        const segment = segmentForDecision(voiceoverSegments, decision, index);
        const selectedWindow = windowForDecision(session.media_items, decision);
        const segmentId = decision.segment_id || segment?.segment_id || fallbackSegmentId(index);
        const draft = scriptDrafts[segmentId] || {
          voiceover: String(segment?.voiceover || ''),
          caption: String(segment?.caption || decision.caption || ''),
        };
        return { type: 'decision' as const, decision, segment, selectedWindow, segmentId, draft, index };
      })
    : session.media_items.map((item, index) => ({
        type: 'clip' as const,
        item,
        index,
      }));

  if (items.length === 0) {
    return (
      <View style={styles.emptyRoot}>
        <Ionicons name="film-outline" size={20} color={colors.subtle} />
        <Text style={styles.emptyText}>Timeline is empty — upload clips to build your story</Text>
      </View>
    );
  }

  return (
    <View style={styles.root}>
      <View style={styles.header}>
        <Text style={styles.headerLabel}>
          <Ionicons name="time-outline" size={12} color={colors.muted} />
          {' '}Timeline
        </Text>
        <Text style={styles.headerMeta}>
          {hasDecisions ? `${editDecisions.length} segments` : `${session.media_items.length} clips`}
        </Text>
      </View>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}
      >
        {items.map((entry, idx) => {
          if (entry.type === 'decision') {
            const { decision, segmentId, draft, index } = entry;
            return (
              <View key={`${segmentId}-${index}`} style={styles.segmentCard}>
                <View style={styles.segmentHeader}>
                  <View style={styles.segmentBadge}>
                    <Text style={styles.segmentBadgeText}>{index + 1}</Text>
                  </View>
                  <View style={styles.segmentMeta}>
                    <Text style={styles.segmentClipName} numberOfLines={1}>
                      {decision.clip || decision.clip_id || `Segment ${index + 1}`}
                    </Text>
                    <Text style={styles.segmentDetail}>
                      {formatTimestamp(decision.start_time || 0)} · {Math.round(decision.duration || 0)}s · {decision.transition || 'cut'}
                    </Text>
                  </View>
                </View>
                <TextInput
                  value={draft.voiceover}
                  onChangeText={(val) => onScriptChange(segmentId, 'voiceover', val)}
                  multiline
                  placeholder="Narration..."
                  placeholderTextColor={colors.subtle}
                  style={styles.scriptInput}
                />
                <TextInput
                  value={draft.caption}
                  onChangeText={(val) => onScriptChange(segmentId, 'caption', val)}
                  placeholder="Caption"
                  placeholderTextColor={colors.subtle}
                  style={styles.captionInput}
                />
              </View>
            );
          }
          // Plain clip card
          const { item, index } = entry;
          return (
            <View key={item.id} style={styles.clipCard}>
              <View style={styles.clipCardHeader}>
                <View style={styles.segmentBadge}>
                  <Text style={styles.segmentBadgeText}>{index + 1}</Text>
                </View>
                <Text style={styles.clipCardName} numberOfLines={1}>{item.filename}</Text>
              </View>
              <Text style={styles.segmentDetail}>
                {item.analysis?.duration_seconds ? `${Math.round(item.analysis.duration_seconds)}s` : 'Video'}
              </Text>
              <View style={styles.clipCardActions}>
                <Pressable onPress={() => onMoveClip(item.id, -1)} style={styles.moveBtn}>
                  <Ionicons name="chevron-back" size={14} color={colors.graphite} />
                </Pressable>
                <Pressable onPress={() => onMoveClip(item.id, 1)} style={styles.moveBtn}>
                  <Ionicons name="chevron-forward" size={14} color={colors.graphite} />
                </Pressable>
              </View>
            </View>
          );
        })}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    padding: 10,
    gap: 6,
  },
  emptyRoot: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    padding: 16,
  },
  emptyText: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: '700',
    textAlign: 'center',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 4,
  },
  headerLabel: {
    color: colors.graphite,
    fontSize: 12,
    fontWeight: '800',
  },
  headerMeta: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: '700',
  },
  scrollContent: {
    gap: 8,
    paddingRight: 12,
    alignItems: 'stretch',
  },
  // --- Segment card (edit decisions) ---
  segmentCard: {
    width: 240,
    borderRadius: radii.md,
    backgroundColor: colors.surfaceRaised,
    borderWidth: 1,
    borderColor: colors.line,
    padding: 10,
    gap: 6,
    ...(Platform.OS === 'web' ? ({ transition: 'border-color 120ms ease' } as any) : {}),
  },
  segmentHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  segmentBadge: {
    width: 22,
    height: 22,
    borderRadius: radii.xs,
    backgroundColor: colors.blue,
    alignItems: 'center',
    justifyContent: 'center',
  },
  segmentBadgeText: {
    color: colors.white,
    fontSize: 10,
    fontWeight: '900',
  },
  segmentMeta: {
    flex: 1,
    minWidth: 0,
  },
  segmentClipName: {
    color: colors.ink,
    fontSize: 12,
    fontWeight: '800',
  },
  segmentDetail: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: '700',
  },
  scriptInput: {
    minHeight: 48,
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.paper,
    paddingHorizontal: 8,
    paddingVertical: 6,
    color: colors.ink,
    fontSize: 11,
    lineHeight: 16,
    fontWeight: '600',
    textAlignVertical: 'top',
  },
  captionInput: {
    height: 28,
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.paper,
    paddingHorizontal: 8,
    color: colors.ink,
    fontSize: 11,
    fontWeight: '600',
  },
  // --- Plain clip card ---
  clipCard: {
    width: 160,
    borderRadius: radii.md,
    backgroundColor: colors.surfaceRaised,
    borderWidth: 1,
    borderColor: colors.line,
    padding: 10,
    gap: 6,
    justifyContent: 'space-between',
  },
  clipCardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  clipCardName: {
    flex: 1,
    color: colors.ink,
    fontSize: 12,
    fontWeight: '800',
  },
  clipCardActions: {
    flexDirection: 'row',
    gap: 4,
    justifyContent: 'flex-end',
  },
  moveBtn: {
    width: 24,
    height: 24,
    borderRadius: radii.xs,
    backgroundColor: colors.paper,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
