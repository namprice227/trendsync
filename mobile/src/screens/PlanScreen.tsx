import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, Pressable, TextInput, ActivityIndicator, ScrollView, KeyboardAvoidingView, Platform, SafeAreaView, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii, shadow } from '../theme';
import type { TripScreen, TripPhase, TripSession, ClipAnalysis, TripContext, RenderOptions, ProjectSummary } from '../types';
import { absoluteUrl } from '../api';
import { VideoView, useVideoPlayer } from 'expo-video';
import { defaultRenderOptions, VIDEO_LENGTH_PRESETS, formatTimestamp, fallbackSegmentId, segmentForDecision, windowForDecision } from "../utils/helpers";
import { PrimaryButton } from "../components/PrimaryButton";
import { MetricPill } from "../components/MetricPill";
import { SectionHeader } from "../components/SectionHeader";

export function PlanScreen({
  session,
  onGenerate,
  onRender,
  onSaveVoiceoverSegments,
}: {
  session: TripSession;
  onGenerate: () => void;
  onRender: (options: RenderOptions) => void;
  onSaveVoiceoverSegments: (segments: Array<{ segment_id: string; voiceover: string; caption?: string }>) => Promise<void>;
}) {
  const { width } = useWindowDimensions();
  const plan = session.story_plan;
  const busy = session.phase === 'planning' || session.phase === 'rendering';
  const generation = plan?.generation;
  const narrativeArc = Array.isArray(plan?.narrative_arc) ? plan.narrative_arc : [];
  const editNotes = Array.isArray(plan?.edit_notes) ? plan.edit_notes : [];
  const editDecisions = Array.isArray(plan?.edit_decisions) ? plan.edit_decisions : [];
  const voiceoverSegments = Array.isArray(plan?.voiceover_segments) ? plan.voiceover_segments : [];
  const [options, setOptions] = useState<RenderOptions>({ ...defaultRenderOptions, ...(session.render_options || {}) });
  const [scriptDrafts, setScriptDrafts] = useState<Record<string, { voiceover: string; caption: string }>>({});
  const [savingScripts, setSavingScripts] = useState(false);
  const desktop = width >= 920;

  useEffect(() => {
    setOptions({ ...defaultRenderOptions, ...(session.render_options || {}) });
  }, [session.id]);

  useEffect(() => {
    const nextDrafts: Record<string, { voiceover: string; caption: string }> = {};
    editDecisions.forEach((decision, index) => {
      const segment = segmentForDecision(voiceoverSegments, decision, index);
      const segmentId = decision.segment_id || segment?.segment_id || fallbackSegmentId(index);
      nextDrafts[segmentId] = {
        voiceover: String(segment?.voiceover || ''),
        caption: String(segment?.caption || decision.caption || ''),
      };
    });
    setScriptDrafts(nextDrafts);
  }, [session.id, plan?.voiceover_script, editDecisions.length, voiceoverSegments.length]);

  const toggleFavorite = (clipId: string) => {
    setOptions((current) => {
      const currentFavorites = new Set(current.favorite_clip_ids || []);
      if (currentFavorites.has(clipId)) {
        currentFavorites.delete(clipId);
      } else {
        currentFavorites.add(clipId);
      }
      return { ...current, favorite_clip_ids: Array.from(currentFavorites) };
    });
  };

  const moveClip = (clipId: string, direction: -1 | 1) => {
    setOptions((current) => {
      const base = current.clip_order.length ? [...current.clip_order] : session.media_items.map((item) => item.id);
      const index = base.indexOf(clipId);
      const nextIndex = index + direction;
      if (index < 0 || nextIndex < 0 || nextIndex >= base.length) return current;
      const next = [...base];
      [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
      return { ...current, clip_order: next };
    });
  };

  const segmentRows = editDecisions.map((decision, index) => {
    const segment = segmentForDecision(voiceoverSegments, decision, index);
    const selectedWindow = windowForDecision(session.media_items, decision);
    const segmentId = decision.segment_id || segment?.segment_id || fallbackSegmentId(index);
    const draft = scriptDrafts[segmentId] || {
      voiceover: String(segment?.voiceover || ''),
      caption: String(segment?.caption || decision.caption || ''),
    };
    return { decision, segment, selectedWindow, segmentId, draft, index };
  });

  const hasScriptChanges = segmentRows.some(({ segment, decision, draft }) => {
    const sourceVoiceover = String(segment?.voiceover || '');
    const sourceCaption = String(segment?.caption || decision.caption || '');
    return draft.voiceover !== sourceVoiceover || draft.caption !== sourceCaption;
  });

  const saveScriptEdits = async () => {
    const payload = segmentRows
      .filter(({ segment, decision, draft }) => {
        const sourceVoiceover = String(segment?.voiceover || '');
        const sourceCaption = String(segment?.caption || decision.caption || '');
        return draft.voiceover !== sourceVoiceover || draft.caption !== sourceCaption;
      })
      .map(({ segmentId, draft, segment, decision }) => ({
        segment_id: segmentId,
        voiceover: draft.voiceover.trim(),
        caption: (draft.caption.trim() || String(segment?.caption || decision.caption || draft.voiceover).trim()).slice(0, 180),
      }));
    if (!payload.length) return;
    setSavingScripts(true);
    try {
      await onSaveVoiceoverSegments(payload);
    } finally {
      setSavingScripts(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.screen}>
      <View style={[styles.planLayout, desktop && styles.planLayoutDesktop]}>
        <View style={[styles.planMain, desktop && styles.planMainDesktop]}>
          <View style={styles.panel}>
            <View style={styles.panelHeading}>
              <View style={styles.headingCopy}>
                <Text style={styles.title}>{plan?.title || 'Narrative plan'}</Text>
                <Text style={styles.muted}>{plan?.tone ? `${plan.tone} tone` : 'Waiting for story generation.'}</Text>
              </View>
              {plan?.language ? <MetricPill icon="language-outline" label="Language" value={String(plan.language).toUpperCase()} /> : null}
              {generation ? (
                <MetricPill
                  icon={generation.llm_used ? 'sparkles-outline' : 'alert-circle-outline'}
                  label="Story brain"
                  value={generation.llm_used ? `${generation.llm_provider || 'LLM'}`.toUpperCase() : 'FALLBACK'}
                />
              ) : null}
            </View>
            {generation && !generation.llm_used ? (
              <View style={[styles.statusStrip, styles.statusError]}>
                <View style={styles.statusIcon}>
                  <Ionicons name="warning-outline" size={16} color={colors.red} />
                </View>
                <View style={styles.statusCopy}>
                  <Text style={styles.statusLabel}>LLM was not used</Text>
                  <Text style={styles.statusAction}>{generation.fallback_reason || 'Check backend .env provider settings.'}</Text>
                </View>
              </View>
            ) : null}
            {busy && session.phase === 'planning' ? (
              <View style={styles.waitPanel}>
                <ActivityIndicator color={colors.blue} />
                <Text style={styles.waitText}>Writing voiceover and edit notes.</Text>
              </View>
            ) : null}
            {!plan && !busy ? (
              <View style={styles.emptyState}>
                <Ionicons name="document-text-outline" size={22} color={colors.subtle} />
                <Text style={styles.emptyText}>No voiceover script yet.</Text>
              </View>
            ) : null}
          </View>

          {narrativeArc.length ? (
            <View style={styles.panel}>
              <SectionHeader icon="git-branch-outline" title="Narrative arc" meta={`${narrativeArc.length} beats`} />
              {narrativeArc.map((item, index) => (
                <View key={`${item}-${index}`} style={styles.timelineItem}>
                  <Text style={styles.timelineNumber}>{index + 1}</Text>
                  <Text style={styles.timelineText}>{String(item)}</Text>
                </View>
              ))}
            </View>
          ) : null}
        </View>

        <View style={[styles.planSide, desktop && styles.planSideDesktop]}>
          <View style={styles.panel}>
            <SectionHeader icon="options-outline" title="Timeline and export" meta={`${options.target_duration_seconds || 30}s · ${options.aspect_ratio}`} />
            <Text style={styles.fieldLabel}>Output length</Text>
            <View style={styles.chipRow}>
              {VIDEO_LENGTH_PRESETS.map((seconds) => {
                const active = (options.target_duration_seconds || 30) === seconds;
                return (
                  <Pressable
                    key={seconds}
                    onPress={() => setOptions((current) => ({ ...current, target_duration_seconds: seconds }))}
                    style={[styles.chip, active && styles.chipActive]}
                  >
                    <Text style={[styles.chipText, active && styles.chipTextActive]}>{seconds}s</Text>
                  </Pressable>
                );
              })}
            </View>
            <Text style={styles.fieldLabel}>Frame</Text>
            <View style={styles.chipRow}>
              {['original', 'portrait', 'landscape', 'square'].map((ratio) => {
                const active = options.aspect_ratio === ratio;
                return (
                  <Pressable key={ratio} onPress={() => setOptions((current) => ({ ...current, aspect_ratio: ratio }))} style={[styles.chip, active && styles.chipActive]}>
                    <Text style={[styles.chipText, active && styles.chipTextActive]}>{ratio}</Text>
                  </Pressable>
                );
              })}
            </View>
            <Pressable
              onPress={() => setOptions((current) => ({ ...current, include_title_card: !current.include_title_card }))}
              style={styles.toggleRow}
            >
              <Ionicons name={options.include_title_card ? 'checkbox' : 'square-outline'} size={18} color={colors.blue} />
              <Text style={styles.listItem}>Opening title/date card</Text>
            </Pressable>
            <Pressable
              onPress={() => setOptions((current) => ({ ...current, burn_captions: !current.burn_captions }))}
              style={styles.toggleRow}
            >
              <Ionicons name={options.burn_captions ? 'checkbox' : 'square-outline'} size={18} color={colors.blue} />
              <Text style={styles.listItem}>Generate subtitle files</Text>
            </Pressable>
            {session.media_items.map((item, index) => {
              const favorite = options.favorite_clip_ids.includes(item.id);
              return (
                <View key={item.id} style={styles.timelineControl}>
                  <Pressable onPress={() => toggleFavorite(item.id)} style={styles.iconButton}>
                    <Ionicons name={favorite ? 'star' : 'star-outline'} size={17} color={favorite ? colors.amber : colors.muted} />
                  </Pressable>
                  <View style={styles.projectRowCopy}>
                    <Text style={styles.insightTitle}>{item.filename}</Text>
                    <Text style={styles.projectMeta}>{item.analysis?.summary || `Clip ${index + 1}`}</Text>
                  </View>
                  <Pressable onPress={() => moveClip(item.id, -1)} style={styles.iconButton}>
                    <Ionicons name="arrow-up" size={16} color={colors.graphite} />
                  </Pressable>
                  <Pressable onPress={() => moveClip(item.id, 1)} style={styles.iconButton}>
                    <Ionicons name="arrow-down" size={16} color={colors.graphite} />
                  </Pressable>
                </View>
              );
            })}
          </View>
        </View>
      </View>

      {editNotes.length ? (
        <View style={styles.panel}>
          <SectionHeader icon="reader-outline" title="Edit notes" meta={`${editNotes.length} notes`} />
          {editNotes.map((item, index) => (
            <Text key={`${item}-${index}`} style={styles.listItem}>{index + 1}. {String(item)}</Text>
          ))}
        </View>
      ) : null}

      {editDecisions.length ? (
        <View style={styles.panel}>
          <View style={styles.panelHeading}>
            <SectionHeader icon="cut-outline" title="Smart edit decisions" meta={`${editDecisions.length} segments`} />
            <PrimaryButton
              icon={savingScripts ? 'hourglass-outline' : 'save-outline'}
              label={savingScripts ? 'Saving' : 'Save script edits'}
              onPress={saveScriptEdits}
              disabled={busy || savingScripts || !hasScriptChanges}
              tone="light"
            />
          </View>
          {segmentRows.map(({ decision, selectedWindow, segmentId, draft, index }) => (
            <View key={`${segmentId}-${decision.clip || 'clip'}-${index}`} style={styles.segmentEditor}>
              <Text style={styles.timelineNumber}>{index + 1}</Text>
              <View style={styles.segmentEditorBody}>
                <Text style={styles.insightTitle}>{decision.clip || decision.clip_id || 'Selected clip'}</Text>
                <Text style={styles.projectMeta}>
                  {decision.window_id || selectedWindow?.window_id || 'window'} · {formatTimestamp(decision.start_time || 0)} · {Math.round(decision.duration || 0)}s · {decision.transition || 'cut'}
                </Text>
                <Text style={styles.listItem}>
                  {selectedWindow?.visual_evidence || decision.reason || decision.role || 'Selected by the smart edit planner.'}
                </Text>
                {decision.reason && selectedWindow?.visual_evidence ? <Text style={styles.projectMeta}>{decision.reason}</Text> : null}
                <TextInput
                  value={draft.voiceover}
                  onChangeText={(value) =>
                    setScriptDrafts((current) => ({
                      ...current,
                      [segmentId]: { ...(current[segmentId] || draft), voiceover: value },
                    }))
                  }
                  multiline
                  placeholder="Write this segment's narration"
                  placeholderTextColor={colors.muted}
                  style={[styles.input, styles.segmentVoiceInput]}
                />
                <TextInput
                  value={draft.caption}
                  onChangeText={(value) =>
                    setScriptDrafts((current) => ({
                      ...current,
                      [segmentId]: { ...(current[segmentId] || draft), caption: value },
                    }))
                  }
                  placeholder="Caption"
                  placeholderTextColor={colors.muted}
                  style={[styles.input, styles.segmentCaptionInput]}
                />
              </View>
            </View>
          ))}
        </View>
      ) : null}

      <View style={styles.actionRow}>
        <PrimaryButton icon="refresh-outline" label="Regenerate" onPress={onGenerate} disabled={busy || session.media_items.length === 0} tone="light" />
        <PrimaryButton icon="film-outline" label="Render video" onPress={() => onRender(options)} disabled={busy || savingScripts || hasScriptChanges || !plan || session.recorded_clips.length === 0} />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: {
    width: '100%',
    maxWidth: 1180,
    alignSelf: 'center',
    paddingHorizontal: 22,
    paddingTop: 14,
    paddingBottom: 32,
    gap: 16,
  },
  planLayout: {
    gap: 16,
  },
  planLayoutDesktop: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  planMain: {
    gap: 16,
  },
  planMainDesktop: {
    flex: 1,
    minWidth: 0,
  },
  panel: {
    backgroundColor: colors.surface,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    padding: 18,
    gap: 14,
    ...shadow,
  },
  panelHeading: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 14,
    flexWrap: 'wrap',
  },
  headingCopy: {
    flex: 1,
    minWidth: 220,
  },
  title: {
    color: colors.ink,
    fontSize: 23,
    lineHeight: 29,
    fontWeight: '900',
  },
  muted: {
    color: colors.muted,
    fontSize: 13,
    lineHeight: 18,
    fontWeight: '600',
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
  statusError: {
    backgroundColor: colors.redSoft,
    borderColor: '#ebc2ba',
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
  waitPanel: {
    backgroundColor: colors.blueSoft,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    padding: 18,
    alignItems: 'center',
    gap: 10,
  },
  waitText: {
    color: colors.graphite,
    fontSize: 13,
    lineHeight: 18,
    fontWeight: '700',
  },
  emptyState: {
    minHeight: 72,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surfaceRaised,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    padding: 14,
  },
  emptyText: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '700',
    textAlign: 'center',
  },
  timelineItem: {
    flexDirection: 'row',
    gap: 10,
    alignItems: 'flex-start',
  },
  timelineNumber: {
    width: 28,
    height: 28,
    borderRadius: radii.md,
    overflow: 'hidden',
    textAlign: 'center',
    textAlignVertical: 'center',
    color: colors.white,
    backgroundColor: colors.blue,
    fontSize: 12,
    lineHeight: 28,
    fontWeight: '900',
  },
  timelineText: {
    flex: 1,
    color: colors.graphite,
    fontSize: 14,
    lineHeight: 21,
    fontWeight: '600',
  },
  planSide: {
    gap: 16,
  },
  planSideDesktop: {
    width: 380,
    flexShrink: 0,
  },
  fieldLabel: {
    color: colors.graphite,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '900',
  },
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  chip: {
    minHeight: 38,
    justifyContent: 'center',
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surfaceRaised,
    paddingHorizontal: 12,
  },
  chipActive: {
    backgroundColor: colors.blue,
    borderColor: colors.blue,
  },
  chipText: {
    color: colors.graphite,
    fontSize: 12,
    fontWeight: '800',
  },
  chipTextActive: {
    color: colors.white,
  },
  toggleRow: {
    minHeight: 38,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  listItem: {
    color: colors.graphite,
    fontSize: 13,
    lineHeight: 19,
    fontWeight: '600',
  },
  timelineControl: {
    minHeight: 58,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surfaceRaised,
    paddingHorizontal: 10,
    paddingVertical: 8,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  iconButton: {
    width: 34,
    height: 34,
    borderRadius: radii.md,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surfaceRaised,
  },
  projectRowCopy: {
    flex: 1,
  },
  insightTitle: {
    flex: 1,
    color: colors.ink,
    fontSize: 13,
    lineHeight: 17,
    fontWeight: '900',
  },
  projectMeta: {
    color: colors.muted,
    fontSize: 11,
    lineHeight: 15,
    fontWeight: '700',
  },
  segmentEditor: {
    minHeight: 58,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surfaceRaised,
    paddingHorizontal: 10,
    paddingVertical: 10,
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
  },
  segmentEditorBody: {
    flex: 1,
    gap: 8,
  },
  input: {
    minHeight: 48,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: colors.ink,
    fontSize: 14,
    fontWeight: '700',
    backgroundColor: colors.surfaceRaised,
  },
  segmentVoiceInput: {
    minHeight: 86,
    textAlignVertical: 'top',
    fontSize: 14,
    lineHeight: 20,
  },
  segmentCaptionInput: {
    minHeight: 42,
  },
  actionRow: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
  },
});
