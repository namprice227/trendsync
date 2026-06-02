import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, Pressable, TextInput, ActivityIndicator, ScrollView, KeyboardAvoidingView, Platform, SafeAreaView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii, shadow } from '../theme';
import type { TripScreen, TripPhase, TripSession, ClipAnalysis, TripContext, RenderOptions, ProjectSummary } from '../types';
import { absoluteUrl } from '../api';
import { VideoView, useVideoPlayer } from 'expo-video';
import { PrimaryButton } from "./PrimaryButton";
import { SectionHeader } from "./SectionHeader";
import { Tag } from "./Tag";

export function ProducerBriefPanel({
  session,
  context,
  disabled,
  onDraft,
  onSave,
  onApprove,
  onGenerate,
}: {
  session: TripSession;
  context: TripContext;
  disabled: boolean;
  onDraft: () => Promise<void>;
  onSave: (patch: { selected_direction_id?: string | null; answers?: Array<{ question_id: string; answer: string }>; notes?: string | null }) => Promise<void>;
  onApprove: (patch: { selected_direction_id?: string | null; answers?: Array<{ question_id: string; answer: string }>; notes?: string | null }) => Promise<void>;
  onGenerate: () => void;
}) {
  const brief = session.creative_brief;
  const status = session.creative_brief_status;
  const [selectedDirectionId, setSelectedDirectionId] = useState<string | null>(brief?.selected_direction_id || brief?.recommended_direction_id || null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<'draft' | 'save' | 'approve' | null>(null);
  const hasMedia = session.media_items.length > 0;
  const canDraft = hasMedia && context.destination.trim().length > 0 && !disabled;

  useEffect(() => {
    setSelectedDirectionId(brief?.selected_direction_id || session.selected_creative_direction_id || brief?.recommended_direction_id || null);
    const nextAnswers: Record<string, string> = { ...(session.creative_brief_answers || {}) };
    (brief?.questions || []).forEach((question) => {
      nextAnswers[question.id] = nextAnswers[question.id] || question.answer || '';
    });
    setAnswers(nextAnswers);
  }, [brief?.title, brief?.selected_direction_id, session.id, session.selected_creative_direction_id, session.creative_brief_status]);

  const patch = () => ({
    selected_direction_id: selectedDirectionId,
    answers: Object.entries(answers).map(([question_id, answer]) => ({ question_id, answer })),
  });

  const saveBrief = async () => {
    if (!brief) return;
    setSaving('save');
    try {
      await onSave(patch());
    } finally {
      setSaving(null);
    }
  };

  const approveBrief = async () => {
    if (!brief) return;
    setSaving('approve');
    try {
      await onApprove(patch());
    } finally {
      setSaving(null);
    }
  };

  const draftBrief = async () => {
    setSaving('draft');
    try {
      await onDraft();
    } finally {
      setSaving(null);
    }
  };

  return (
    <View style={styles.producerPanel}>
      <View style={styles.panelHeading}>
        <SectionHeader
          icon="sparkles-outline"
          title="AI producer brief"
          meta={status === 'approved' ? 'Approved' : status === 'stale' ? 'Needs refresh' : brief ? 'Draft' : 'Before story generation'}
        />
        {brief ? <Tag label={status === 'approved' ? 'Approved' : status === 'stale' ? 'Stale' : 'Draft'} tone={status === 'approved' ? 'success' : status === 'stale' ? 'warning' : 'info'} /> : null}
      </View>

      {!brief ? (
        <View style={styles.briefEmpty}>
          <Text style={styles.listItem}>Draft a focused brief from the clip intelligence before generating the final story plan.</Text>
          <PrimaryButton icon={saving === 'draft' ? 'hourglass-outline' : 'bulb-outline'} label={saving === 'draft' ? 'Drafting' : 'Draft brief'} onPress={draftBrief} disabled={!canDraft || saving !== null} />
          {!hasMedia ? <Text style={styles.projectMeta}>Upload at least one clip first.</Text> : null}
          {hasMedia && !context.destination.trim() ? <Text style={styles.projectMeta}>Add a destination first.</Text> : null}
        </View>
      ) : (
        <>
          <Text style={styles.listItem}>{brief.summary}</Text>
          {brief.generation && !brief.generation.llm_used ? (
            <View style={[styles.statusStrip, styles.statusError]}>
              <View style={styles.statusIcon}>
                <Ionicons name="warning-outline" size={16} color={colors.red} />
              </View>
              <View style={styles.statusCopy}>
                <Text style={styles.statusLabel}>Producer fallback was used</Text>
                <Text style={styles.statusAction}>{brief.generation.fallback_reason || 'Check backend provider settings.'}</Text>
              </View>
            </View>
          ) : null}
          {status === 'stale' ? (
            <View style={[styles.statusStrip, styles.statusInfo]}>
              <View style={styles.statusIcon}>
                <Ionicons name="refresh-outline" size={16} color={colors.blue} />
              </View>
              <View style={styles.statusCopy}>
                <Text style={styles.statusLabel}>Context changed after approval</Text>
                <Text style={styles.statusAction}>Refresh or approve the brief again before generating.</Text>
              </View>
            </View>
          ) : null}

          <View style={styles.briefDirectionList}>
            {(brief.directions || []).map((direction) => {
              const active = selectedDirectionId === direction.id;
              const recommended = direction.id === brief.recommended_direction_id;
              return (
                <Pressable key={direction.id} onPress={() => setSelectedDirectionId(direction.id)} style={[styles.briefDirection, active && styles.briefDirectionActive]}>
                  <View style={styles.insightHead}>
                    <Text style={styles.insightTitle}>{direction.title}</Text>
                    {recommended ? <Tag label="Recommended" tone="info" /> : null}
                  </View>
                  <Text style={styles.listItem}>{direction.angle}</Text>
                  {direction.why ? <Text style={styles.projectMeta}>{direction.why}</Text> : null}
                  {direction.key_beats?.length ? (
                    <View style={styles.briefBeatList}>
                      {direction.key_beats.slice(0, 3).map((beat, index) => (
                        <Text key={`${direction.id}-${index}`} style={styles.projectMeta}>{index + 1}. {beat}</Text>
                      ))}
                    </View>
                  ) : null}
                </Pressable>
              );
            })}
          </View>

          <View style={styles.briefQuestionList}>
            {(brief.questions || []).map((question) => (
              <View key={question.id} style={styles.fieldWide}>
                <Text style={styles.fieldLabel}>{question.label}</Text>
                <Text style={styles.projectMeta}>{question.question}</Text>
                <TextInput
                  value={answers[question.id] || ''}
                  onChangeText={(value) => setAnswers((current) => ({ ...current, [question.id]: value }))}
                  placeholder={question.why || 'Answer before approving'}
                  placeholderTextColor={colors.muted}
                  multiline
                  style={[styles.input, styles.briefAnswerInput]}
                />
              </View>
            ))}
          </View>

          {Boolean(brief.must_use?.length || brief.avoid?.length) ? (
            <View style={styles.briefEvidenceGrid}>
              {brief.must_use?.length ? (
                <View style={styles.briefEvidenceColumn}>
                  <Text style={styles.fieldLabel}>Must-use evidence</Text>
                  {brief.must_use.slice(0, 4).map((item, index) => (
                    <Text key={`${item.clip_id || item.clip}-${index}`} style={styles.projectMeta}>{item.clip || item.clip_id || 'Clip'}: {item.reason || item.window_id || 'Suggested moment'}</Text>
                  ))}
                </View>
              ) : null}
              {brief.avoid?.length ? (
                <View style={styles.briefEvidenceColumn}>
                  <Text style={styles.fieldLabel}>Avoid</Text>
                  {brief.avoid.slice(0, 4).map((item, index) => (
                    <Text key={`${item}-${index}`} style={styles.projectMeta}>{item}</Text>
                  ))}
                </View>
              ) : null}
            </View>
          ) : null}

          <View style={styles.actionRow}>
            <PrimaryButton icon={saving === 'draft' ? 'hourglass-outline' : 'refresh-outline'} label={saving === 'draft' ? 'Refreshing' : 'Refresh brief'} onPress={draftBrief} disabled={!canDraft || saving !== null} tone="light" />
            {status !== 'approved' ? (
              <>
                <PrimaryButton icon={saving === 'save' ? 'hourglass-outline' : 'save-outline'} label={saving === 'save' ? 'Saving' : 'Save brief'} onPress={saveBrief} disabled={disabled || saving !== null || !selectedDirectionId} tone="light" />
                <PrimaryButton icon={saving === 'approve' ? 'hourglass-outline' : 'checkmark-circle-outline'} label={saving === 'approve' ? 'Approving' : 'Approve brief'} onPress={approveBrief} disabled={disabled || saving !== null || !selectedDirectionId} />
              </>
            ) : (
              <PrimaryButton icon="document-text-outline" label="Generate story plan" onPress={onGenerate} disabled={disabled || saving !== null || !hasMedia} />
            )}
          </View>
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  producerPanel: {
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surface,
    padding: 14,
    gap: 12,
  },
  panelHeading: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 14,
    flexWrap: 'wrap',
  },
  briefEmpty: {
    gap: 10,
  },
  listItem: {
    color: colors.graphite,
    fontSize: 13,
    lineHeight: 19,
    fontWeight: '600',
  },
  projectMeta: {
    color: colors.muted,
    fontSize: 11,
    lineHeight: 15,
    fontWeight: '700',
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
  statusInfo: {
    backgroundColor: colors.blueSoft,
    borderColor: '#c4dde2',
  },
  briefDirectionList: {
    gap: 8,
  },
  briefDirection: {
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surfaceRaised,
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 7,
  },
  briefDirectionActive: {
    borderColor: colors.blue,
    backgroundColor: colors.blueSoft,
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
  briefBeatList: {
    gap: 3,
  },
  briefQuestionList: {
    gap: 12,
  },
  fieldWide: {
    width: '100%',
    gap: 6,
  },
  fieldLabel: {
    color: colors.graphite,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '900',
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
  briefAnswerInput: {
    minHeight: 78,
    textAlignVertical: 'top',
  },
  briefEvidenceGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  briefEvidenceColumn: {
    flexGrow: 1,
    flexBasis: 190,
    gap: 6,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surfaceRaised,
    padding: 10,
  },
  actionRow: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
  },
});
