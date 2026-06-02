import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii } from '../theme';
import type { StoryPlan } from '../types';
import { MetricPill } from './MetricPill';
import { SectionHeader } from './SectionHeader';

export function SidebarStoryTab({ plan }: { plan: StoryPlan | null | undefined }) {
  const narrativeArc = Array.isArray(plan?.narrative_arc) ? plan.narrative_arc : [];
  const editNotes = Array.isArray(plan?.edit_notes) ? plan.edit_notes : [];
  const generation = plan?.generation;

  if (!plan) {
    return (
      <View style={styles.emptyState}>
        <Ionicons name="document-text-outline" size={24} color={colors.subtle} />
        <Text style={styles.emptyText}>No story plan yet</Text>
        <Text style={styles.emptyHint}>Generate a story after adding clips and context</Text>
      </View>
    );
  }

  return (
    <View style={styles.root}>
      {/* Title and metadata */}
      <View style={styles.header}>
        <Text style={styles.title} numberOfLines={2}>{plan.title || 'Narrative plan'}</Text>
        {plan.tone ? <Text style={styles.tone}>{plan.tone} tone</Text> : null}
      </View>

      {/* Generation info */}
      <View style={styles.metricRow}>
        {plan.language ? (
          <MetricPill icon="language-outline" label="Lang" value={String(plan.language).toUpperCase()} />
        ) : null}
        {generation ? (
          <MetricPill
            icon={generation.llm_used ? 'sparkles-outline' : 'alert-circle-outline'}
            label="Brain"
            value={generation.llm_used ? `${generation.llm_provider || 'LLM'}`.toUpperCase() : 'FALLBACK'}
          />
        ) : null}
      </View>

      {/* Narrative arc */}
      {narrativeArc.length > 0 ? (
        <View style={styles.section}>
          <SectionHeader icon="git-branch-outline" title="Narrative arc" meta={`${narrativeArc.length} beats`} />
          {narrativeArc.map((item, index) => (
            <View key={`arc-${index}`} style={styles.beatRow}>
              <View style={styles.beatNumber}>
                <Text style={styles.beatNumberText}>{index + 1}</Text>
              </View>
              <Text style={styles.beatText}>{String(item)}</Text>
            </View>
          ))}
        </View>
      ) : null}

      {/* Edit notes */}
      {editNotes.length > 0 ? (
        <View style={styles.section}>
          <SectionHeader icon="reader-outline" title="Edit notes" meta={`${editNotes.length}`} />
          {editNotes.map((item, index) => (
            <Text key={`note-${index}`} style={styles.noteText}>
              {index + 1}. {String(item)}
            </Text>
          ))}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    gap: 14,
  },
  emptyState: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 40,
    gap: 8,
  },
  emptyText: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: '700',
  },
  emptyHint: {
    color: colors.subtle,
    fontSize: 11,
    fontWeight: '600',
    textAlign: 'center',
  },
  header: {
    gap: 4,
  },
  title: {
    color: colors.ink,
    fontSize: 16,
    fontWeight: '900',
    lineHeight: 21,
  },
  tone: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: '600',
  },
  metricRow: {
    flexDirection: 'row',
    gap: 8,
    flexWrap: 'wrap',
  },
  section: {
    gap: 8,
    paddingTop: 6,
    borderTopWidth: 1,
    borderTopColor: colors.line,
  },
  beatRow: {
    flexDirection: 'row',
    gap: 8,
    alignItems: 'flex-start',
  },
  beatNumber: {
    width: 22,
    height: 22,
    borderRadius: radii.sm,
    backgroundColor: colors.blue,
    alignItems: 'center',
    justifyContent: 'center',
  },
  beatNumberText: {
    color: colors.white,
    fontSize: 10,
    fontWeight: '900',
  },
  beatText: {
    flex: 1,
    color: colors.graphite,
    fontSize: 12,
    lineHeight: 18,
    fontWeight: '600',
  },
  noteText: {
    color: colors.graphite,
    fontSize: 12,
    lineHeight: 18,
    fontWeight: '600',
  },
});
