import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii } from '../theme';
import type { TripSession, TripContext, RenderOptions, PropertiesTab } from '../types';
import { tripContextFields, providerModelPlaceholders, VIDEO_LENGTH_PRESETS, defaultRenderOptions } from '../utils/helpers';
import { Field } from './Field';
import { LanguagePicker } from './LanguagePicker';
import { ProviderPicker } from './ProviderPicker';

const TABS: { key: PropertiesTab; icon: keyof typeof Ionicons.glyphMap; label: string }[] = [
  { key: 'context', icon: 'create-outline', label: 'Context' },
  { key: 'export', icon: 'options-outline', label: 'Export' },
  { key: 'script', icon: 'document-text-outline', label: 'Script' },
];

export function PropertiesPanel({
  session,
  context,
  options,
  activeTab,
  onTabChange,
  onContextChange,
  onOptionsChange,
}: {
  session: TripSession;
  context: TripContext;
  options: RenderOptions;
  activeTab: PropertiesTab;
  onTabChange: (tab: PropertiesTab) => void;
  onContextChange: (key: keyof TripContext, value: string) => void;
  onOptionsChange: (updater: (current: RenderOptions) => RenderOptions) => void;
}) {
  return (
    <View style={styles.root}>
      {/* Tab bar */}
      <View style={styles.tabBar}>
        {TABS.map((tab) => {
          const active = activeTab === tab.key;
          return (
            <Pressable
              key={tab.key}
              onPress={() => onTabChange(tab.key)}
              style={[styles.tab, active && styles.tabActive]}
            >
              <Ionicons name={tab.icon} size={14} color={active ? colors.blue : colors.muted} />
              <Text style={[styles.tabText, active && styles.tabTextActive]}>{tab.label}</Text>
            </Pressable>
          );
        })}
      </View>

      {/* Tab content */}
      <ScrollView
        style={styles.content}
        contentContainerStyle={styles.contentInner}
        showsVerticalScrollIndicator={false}
      >
        {activeTab === 'context' ? (
          <ContextTab context={context} onContextChange={onContextChange} />
        ) : activeTab === 'export' ? (
          <ExportTab options={options} onOptionsChange={onOptionsChange} session={session} />
        ) : (
          <ScriptTab session={session} />
        )}
      </ScrollView>
    </View>
  );
}

// --- Context Tab ---
function ContextTab({
  context,
  onContextChange,
}: {
  context: TripContext;
  onContextChange: (key: keyof TripContext, value: string) => void;
}) {
  return (
    <View style={styles.tabContent}>
      <Text style={styles.sectionTitle}>Trip details</Text>
      {tripContextFields.map((field) => (
        <Field
          key={field.key}
          label={field.label}
          value={context[field.key]}
          onChangeText={(value) => onContextChange(field.key, value)}
          placeholder={field.placeholder}
          multiline={field.multiline}
          wide
        />
      ))}
      <View style={styles.fieldGroup}>
        <Text style={styles.fieldLabel}>Voiceover language</Text>
        <LanguagePicker value={context.language} onChange={(value) => onContextChange('language', value)} />
      </View>
      <View style={styles.fieldGroup}>
        <Text style={styles.fieldLabel}>AI provider</Text>
        <ProviderPicker value={context.llm_provider || 'local'} onChange={(value) => onContextChange('llm_provider', value)} />
      </View>
      <Field
        label="Model override"
        value={context.llm_model}
        onChangeText={(value) => onContextChange('llm_model', value)}
        placeholder={providerModelPlaceholders[context.llm_provider] || 'Optional model name'}
        wide
      />
    </View>
  );
}

// --- Export Tab ---
function ExportTab({
  options,
  onOptionsChange,
  session,
}: {
  options: RenderOptions;
  onOptionsChange: (updater: (current: RenderOptions) => RenderOptions) => void;
  session: TripSession;
}) {
  return (
    <View style={styles.tabContent}>
      <Text style={styles.sectionTitle}>Export settings</Text>

      <Text style={styles.fieldLabel}>Duration</Text>
      <View style={styles.chipRow}>
        {VIDEO_LENGTH_PRESETS.map((seconds) => {
          const active = (options.target_duration_seconds || 30) === seconds;
          return (
            <Pressable
              key={seconds}
              onPress={() => onOptionsChange((c) => ({ ...c, target_duration_seconds: seconds }))}
              style={[styles.chip, active && styles.chipActive]}
            >
              <Text style={[styles.chipText, active && styles.chipTextActive]}>{seconds}s</Text>
            </Pressable>
          );
        })}
      </View>

      <Text style={styles.fieldLabel}>Aspect ratio</Text>
      <View style={styles.chipRow}>
        {['original', 'portrait', 'landscape', 'square'].map((ratio) => {
          const active = options.aspect_ratio === ratio;
          return (
            <Pressable
              key={ratio}
              onPress={() => onOptionsChange((c) => ({ ...c, aspect_ratio: ratio }))}
              style={[styles.chip, active && styles.chipActive]}
            >
              <Text style={[styles.chipText, active && styles.chipTextActive]}>{ratio}</Text>
            </Pressable>
          );
        })}
      </View>

      <Pressable
        onPress={() => onOptionsChange((c) => ({ ...c, include_title_card: !c.include_title_card }))}
        style={styles.toggleRow}
      >
        <Ionicons name={options.include_title_card ? 'checkbox' : 'square-outline'} size={16} color={colors.blue} />
        <Text style={styles.toggleText}>Title / date card</Text>
      </Pressable>

      <Pressable
        onPress={() => onOptionsChange((c) => ({ ...c, burn_captions: !c.burn_captions }))}
        style={styles.toggleRow}
      >
        <Ionicons name={options.burn_captions ? 'checkbox' : 'square-outline'} size={16} color={colors.blue} />
        <Text style={styles.toggleText}>Generate subtitles</Text>
      </Pressable>

      {/* Render artifacts info */}
      {session.voiceover_audio_url ? (
        <View style={styles.infoRow}>
          <Ionicons name="mic-outline" size={14} color={colors.green} />
          <Text style={styles.infoText}>AI voiceover mixed into render</Text>
        </View>
      ) : null}
      {session.edit_decisions_url ? (
        <View style={styles.infoRow}>
          <Ionicons name="code-slash-outline" size={14} color={colors.muted} />
          <Text style={styles.infoText}>Edit decisions JSON saved</Text>
        </View>
      ) : null}
      {session.caption_srt_url || session.caption_vtt_url ? (
        <View style={styles.infoRow}>
          <Ionicons name="text-outline" size={14} color={colors.muted} />
          <Text style={styles.infoText}>Subtitle files saved</Text>
        </View>
      ) : null}
    </View>
  );
}

// --- Script Tab ---
function ScriptTab({ session }: { session: TripSession }) {
  if (!session.script) {
    return (
      <View style={styles.emptyState}>
        <Ionicons name="document-text-outline" size={24} color={colors.subtle} />
        <Text style={styles.emptyText}>Generate a story plan to see the voiceover script</Text>
      </View>
    );
  }

  return (
    <View style={styles.tabContent}>
      <Text style={styles.sectionTitle}>Voiceover script</Text>
      <Text style={styles.scriptText}>{session.script}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    flexDirection: 'column',
  },
  tabBar: {
    flexDirection: 'row',
    borderBottomWidth: 1,
    borderBottomColor: colors.line,
    backgroundColor: colors.paper,
  },
  tab: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
    paddingVertical: 10,
    ...(Platform.OS === 'web' ? ({ cursor: 'pointer', transition: 'all 120ms ease' } as any) : {}),
  },
  tabActive: {
    borderBottomWidth: 2,
    borderBottomColor: colors.blue,
  },
  tabText: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: '800',
  },
  tabTextActive: {
    color: colors.blue,
  },
  content: {
    flex: 1,
  },
  contentInner: {
    padding: 14,
    paddingBottom: 100,
  },
  tabContent: {
    gap: 12,
  },
  sectionTitle: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: '900',
    marginBottom: 2,
  },
  fieldGroup: {
    gap: 6,
    width: '100%',
  },
  fieldLabel: {
    color: colors.graphite,
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
    letterSpacing: 0.3,
  },
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  chip: {
    minHeight: 32,
    justifyContent: 'center',
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surfaceRaised,
    paddingHorizontal: 10,
    ...(Platform.OS === 'web' ? ({ cursor: 'pointer', transition: 'all 120ms ease' } as any) : {}),
  },
  chipActive: {
    backgroundColor: colors.blue,
    borderColor: colors.blue,
  },
  chipText: {
    color: colors.graphite,
    fontSize: 11,
    fontWeight: '800',
  },
  chipTextActive: {
    color: colors.white,
  },
  toggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    minHeight: 32,
    ...(Platform.OS === 'web' ? ({ cursor: 'pointer' } as any) : {}),
  },
  toggleText: {
    color: colors.graphite,
    fontSize: 12,
    fontWeight: '700',
  },
  infoRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 2,
  },
  infoText: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: '600',
  },
  scriptText: {
    color: colors.graphite,
    fontSize: 13,
    lineHeight: 21,
    fontWeight: '600',
  },
  emptyState: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 40,
    gap: 8,
  },
  emptyText: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: '700',
    textAlign: 'center',
    maxWidth: 220,
  },
});
