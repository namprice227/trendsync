import React from 'react';
import { View, StyleSheet, Platform } from 'react-native';
import { colors, radii } from '../theme';
import type { TripSession, RenderOptions } from '../types';
import { planningPhases, defaultRenderOptions } from '../utils/helpers';
import { PrimaryButton } from './PrimaryButton';

export function ActionBar({
  session,
  options,
  hasScriptChanges,
  hasTimelineChanges,
  savingScripts,
  savingTimeline,
  onSaveContext,
  onDraftBrief,
  onGenerate,
  onRender,
  onSaveScripts,
  onSaveTimeline,
  onShare,
}: {
  session: TripSession;
  options: RenderOptions;
  hasScriptChanges: boolean;
  hasTimelineChanges: boolean;
  savingScripts: boolean;
  savingTimeline: boolean;
  onSaveContext: () => void;
  onDraftBrief: () => void;
  onGenerate: () => void;
  onRender: () => void;
  onSaveScripts: () => void;
  onSaveTimeline: () => void;
  onShare: () => void;
}) {
  const busy = planningPhases.includes(session.phase);
  const hasMedia = session.media_items.length > 0;
  const hasStory = Boolean(session.story_plan);
  const hasClips = session.recorded_clips.length > 0;
  const briefStatus = session.creative_brief_status;
  const hasBrief = Boolean(session.creative_brief);
  const briefApproved = briefStatus === 'approved';

  return (
    <View style={styles.root}>
      {/* Context-phase actions */}
      <PrimaryButton icon="save-outline" label="Save" onPress={onSaveContext} tone="light" />

      {/* Brief draft */}
      {hasMedia && !hasBrief ? (
        <PrimaryButton icon="bulb-outline" label="Draft brief" onPress={onDraftBrief} disabled={busy} tone="light" />
      ) : null}

      {/* Script save */}
      {hasScriptChanges ? (
        <PrimaryButton
          icon={savingScripts ? 'hourglass-outline' : 'save-outline'}
          label={savingScripts ? 'Saving...' : 'Save scripts'}
          onPress={onSaveScripts}
          disabled={busy || savingScripts}
          tone="light"
        />
      ) : null}

      {/* Timeline save */}
      {hasTimelineChanges ? (
        <PrimaryButton
          icon={savingTimeline ? 'hourglass-outline' : 'time-outline'}
          label={savingTimeline ? 'Saving...' : 'Save timeline'}
          onPress={onSaveTimeline}
          disabled={busy || savingTimeline}
          tone="light"
        />
      ) : null}

      {/* Generate */}
      {hasMedia && (!hasBrief || briefApproved) ? (
        <PrimaryButton
          icon="sparkles-outline"
          label="Generate"
          onPress={onGenerate}
          disabled={busy || !hasMedia || (hasBrief && !briefApproved)}
        />
      ) : null}

      {/* Render */}
      {hasStory && hasClips ? (
        <PrimaryButton
          icon="film-outline"
          label="Render"
          onPress={onRender}
          disabled={busy || savingScripts || savingTimeline || hasScriptChanges || hasTimelineChanges || !hasStory || !hasClips}
        />
      ) : null}

      {/* Share */}
      {session.phase === 'complete' ? (
        <PrimaryButton icon="share-outline" label="Share" onPress={onShare} tone="light" />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderTopWidth: 1,
    borderTopColor: colors.line,
    backgroundColor: colors.paper,
  },
});
