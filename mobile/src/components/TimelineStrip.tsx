import React from 'react';
import { View, Text, StyleSheet, ScrollView, TextInput, Platform, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii } from '../theme';
import type { TripSession } from '../types';
import { formatTimestamp, fallbackSegmentId, segmentForDecision } from '../utils/helpers';

type TimelineTiming = { start_time: number; duration: number };

const STEP_SECONDS = 0.5;
const MIN_SECTION_SECONDS = 1;
const MAX_SECTION_SECONDS = 10;

function numberOr(value: unknown, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function roundTimelineValue(value: number): number {
  return Math.round(value * 10) / 10;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function formatDuration(value: number): string {
  const rounded = roundTimelineValue(value);
  return Number.isInteger(rounded) ? `${rounded}s` : `${rounded.toFixed(1)}s`;
}

function clipDurationForDecision(
  session: TripSession,
  decision: NonNullable<NonNullable<TripSession['story_plan']>['edit_decisions']>[number]
): number | null {
  const clip = session.media_items.find((item) => item.id === decision.clip_id || item.filename === decision.clip);
  const duration = numberOr(clip?.analysis?.duration_seconds, 0);
  return duration > 0 ? duration : null;
}

function maxStartForTiming(timing: TimelineTiming, clipDuration: number | null): number {
  if (!clipDuration) return 86400;
  const duration = clamp(timing.duration, MIN_SECTION_SECONDS, Math.min(MAX_SECTION_SECONDS, clipDuration));
  return Math.max(0, clipDuration - duration);
}

function maxDurationForTiming(timing: TimelineTiming, clipDuration: number | null): number {
  if (!clipDuration) return MAX_SECTION_SECONDS;
  return Math.min(MAX_SECTION_SECONDS, Math.max(MIN_SECTION_SECONDS, clipDuration - timing.start_time));
}

function adjustStart(timing: TimelineTiming, clipDuration: number | null, delta: number): number {
  return roundTimelineValue(clamp(timing.start_time + delta, 0, maxStartForTiming(timing, clipDuration)));
}

function adjustDuration(timing: TimelineTiming, clipDuration: number | null, delta: number): number {
  return roundTimelineValue(clamp(timing.duration + delta, MIN_SECTION_SECONDS, maxDurationForTiming(timing, clipDuration)));
}

function TimelineIconButton({
  icon,
  disabled,
  label,
  onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  disabled?: boolean;
  label: string;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed, hovered }: any) => [
        styles.iconButton,
        hovered && !disabled && styles.iconButtonHovered,
        pressed && !disabled && styles.iconButtonPressed,
        disabled && styles.iconButtonDisabled,
      ]}
    >
      <Ionicons name={icon} size={14} color={disabled ? colors.subtle : colors.graphite} />
    </Pressable>
  );
}

export function TimelineStrip({
  session,
  scriptDrafts,
  timelineDrafts,
  timelineOrder,
  onScriptChange,
  onTimelineChange,
  onMoveSegment,
}: {
  session: TripSession;
  scriptDrafts: Record<string, { voiceover: string; caption: string }>;
  timelineDrafts: Record<string, TimelineTiming>;
  timelineOrder: string[];
  onScriptChange: (segmentId: string, field: 'voiceover' | 'caption', value: string) => void;
  onTimelineChange: (segmentId: string, patch: Partial<TimelineTiming>) => void;
  onMoveSegment: (segmentId: string, direction: -1 | 1) => void;
}) {
  const plan = session.story_plan;
  const editDecisions = Array.isArray(plan?.edit_decisions) ? plan.edit_decisions : [];
  const voiceoverSegments = Array.isArray(plan?.voiceover_segments) ? plan.voiceover_segments : [];
  const hasDecisions = editDecisions.length > 0;

  const baseItems = hasDecisions
    ? editDecisions.map((decision, index) => {
      const segment = segmentForDecision(voiceoverSegments, decision, index);
      const segmentId = decision.segment_id || segment?.segment_id || fallbackSegmentId(index);
      const draft = scriptDrafts[segmentId] || {
        voiceover: String(segment?.voiceover || ''),
        caption: String(segment?.caption || decision.caption || ''),
      };
      const sourceTiming = {
        start_time: numberOr(decision.start_time ?? segment?.start_time, 0),
        duration: numberOr(decision.duration ?? segment?.duration, MIN_SECTION_SECONDS),
      };
      return {
        decision,
        segmentId,
        draft,
        timing: timelineDrafts[segmentId] || sourceTiming,
        sourceIndex: index,
        clipDuration: clipDurationForDecision(session, decision),
      };
    })
    : [];
  const itemsById = new Map(baseItems.map((item) => [item.segmentId, item]));
  const orderedIds = timelineOrder.length ? timelineOrder : baseItems.map((item) => item.segmentId);
  const items = orderedIds
    .map((segmentId) => itemsById.get(segmentId))
    .filter(Boolean) as typeof baseItems;

  if (items.length === 0) {
    const hasMedia = session.media_items.length > 0;
    return (
      <View style={styles.emptyRoot}>
        <Ionicons name={hasMedia ? 'sparkles-outline' : 'film-outline'} size={20} color={colors.subtle} />
        <Text style={styles.emptyText}>
          {hasMedia
            ? 'Timeline appears after the story plan selects clip moments'
            : 'Timeline is empty. Upload clips to start'}
        </Text>
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
          {`${editDecisions.length} segment${editDecisions.length === 1 ? '' : 's'}`}
        </Text>
      </View>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}
      >
        {items.map((entry, idx) => {
          const { decision, segmentId, draft, timing, sourceIndex, clipDuration } = entry;
          const maxStart = maxStartForTiming(timing, clipDuration);
          const maxDuration = maxDurationForTiming(timing, clipDuration);
          const durationFill = `${clamp((timing.duration / MAX_SECTION_SECONDS) * 100, 8, 100)}%` as `${number}%`;
          return (
            <View key={`${segmentId}-${sourceIndex}`} style={styles.segmentCard}>
              <View style={styles.segmentHeader}>
                <View style={styles.segmentBadge}>
                  <Text style={styles.segmentBadgeText}>{idx + 1}</Text>
                </View>
                <View style={styles.segmentMeta}>
                  <Text style={styles.segmentClipName} numberOfLines={1}>
                    {decision.clip || decision.clip_id || `Segment ${idx + 1}`}
                  </Text>
                  <Text style={styles.segmentDetail}>
                    {formatTimestamp(timing.start_time)} · {formatDuration(timing.duration)} · {decision.transition || 'cut'}
                  </Text>
                </View>
                <View style={styles.orderControls}>
                  <TimelineIconButton
                    icon="chevron-back"
                    label="Move segment earlier"
                    disabled={idx === 0}
                    onPress={() => onMoveSegment(segmentId, -1)}
                  />
                  <TimelineIconButton
                    icon="chevron-forward"
                    label="Move segment later"
                    disabled={idx === items.length - 1}
                    onPress={() => onMoveSegment(segmentId, 1)}
                  />
                </View>
              </View>
              <View style={styles.durationTrack}>
                <View style={[styles.durationFill, { width: durationFill }]} />
              </View>
              <View style={styles.timingGrid}>
                <View style={styles.timingGroup}>
                  <Text style={styles.controlLabel}>Start</Text>
                  <View style={styles.stepper}>
                    <TimelineIconButton
                      icon="play-back"
                      label="Move source start earlier"
                      disabled={timing.start_time <= 0}
                      onPress={() => onTimelineChange(segmentId, { start_time: adjustStart(timing, clipDuration, -STEP_SECONDS) })}
                    />
                    <Text style={styles.timeValue}>{formatTimestamp(timing.start_time)}</Text>
                    <TimelineIconButton
                      icon="play-forward"
                      label="Move source start later"
                      disabled={timing.start_time >= maxStart}
                      onPress={() => onTimelineChange(segmentId, { start_time: adjustStart(timing, clipDuration, STEP_SECONDS) })}
                    />
                  </View>
                </View>
                <View style={styles.timingGroup}>
                  <Text style={styles.controlLabel}>Length</Text>
                  <View style={styles.stepper}>
                    <TimelineIconButton
                      icon="remove"
                      label="Shorten segment"
                      disabled={timing.duration <= MIN_SECTION_SECONDS}
                      onPress={() => onTimelineChange(segmentId, { duration: adjustDuration(timing, clipDuration, -STEP_SECONDS) })}
                    />
                    <Text style={styles.timeValue}>{formatDuration(timing.duration)}</Text>
                    <TimelineIconButton
                      icon="add"
                      label="Extend segment"
                      disabled={timing.duration >= maxDuration}
                      onPress={() => onTimelineChange(segmentId, { duration: adjustDuration(timing, clipDuration, STEP_SECONDS) })}
                    />
                  </View>
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
        })}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    padding: 8,
    gap: 5,
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
    width: 286,
    borderRadius: radii.md,
    backgroundColor: colors.surfaceRaised,
    borderWidth: 1,
    borderColor: colors.line,
    padding: 9,
    gap: 5,
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
  orderControls: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  iconButton: {
    width: 26,
    height: 26,
    borderRadius: radii.xs,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.lineStrong,
    ...(Platform.OS === 'web' ? ({ cursor: 'pointer' } as any) : {}),
  },
  iconButtonHovered: {
    borderColor: colors.blue,
    backgroundColor: colors.blueSoft,
  },
  iconButtonPressed: {
    transform: [{ scale: 0.96 }],
  },
  iconButtonDisabled: {
    opacity: 0.42,
    ...(Platform.OS === 'web' ? ({ cursor: 'not-allowed' } as any) : {}),
  },
  durationTrack: {
    height: 4,
    borderRadius: radii.round,
    backgroundColor: colors.surface,
    overflow: 'hidden',
  },
  durationFill: {
    height: 4,
    borderRadius: radii.round,
    backgroundColor: colors.blue,
  },
  timingGrid: {
    flexDirection: 'row',
    gap: 6,
  },
  timingGroup: {
    flex: 1,
    minWidth: 0,
    gap: 3,
  },
  controlLabel: {
    color: colors.subtle,
    fontSize: 9,
    lineHeight: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  stepper: {
    height: 28,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.paper,
    paddingHorizontal: 3,
  },
  timeValue: {
    flex: 1,
    color: colors.graphite,
    fontSize: 11,
    lineHeight: 14,
    fontWeight: '900',
    textAlign: 'center',
  },
  scriptInput: {
    minHeight: 40,
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.paper,
    paddingHorizontal: 8,
    paddingVertical: 6,
    color: colors.ink,
    fontSize: 11,
    lineHeight: 15,
    fontWeight: '600',
    textAlignVertical: 'top',
  },
  captionInput: {
    height: 26,
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.paper,
    paddingHorizontal: 8,
    color: colors.ink,
    fontSize: 11,
    fontWeight: '600',
  },
});
