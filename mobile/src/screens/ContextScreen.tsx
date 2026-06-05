import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, Pressable, TextInput, ActivityIndicator, ScrollView, KeyboardAvoidingView, Platform, SafeAreaView, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii, shadow } from '../theme';
import type { TripScreen, TripPhase, TripSession, ClipAnalysis, TripContext, RenderOptions, ProjectSummary } from '../types';
import { absoluteUrl } from '../api';
import { VideoView, useVideoPlayer } from 'expo-video';
import { planningPhases, providerModelPlaceholders, tripContextFields, sessionTitle } from "../utils/helpers";
import { PrimaryButton } from "../components/PrimaryButton";
import { MetricPill } from "../components/MetricPill";
import { SectionHeader } from "../components/SectionHeader";
import { Tag } from "../components/Tag";
import { ClipIntelligence } from "../components/ClipIntelligence";
import { ProducerBriefPanel } from "../components/ProducerBriefPanel";
import { Field } from "../components/Field";
import { LanguagePicker } from "../components/LanguagePicker";
import { ProviderPicker } from "../components/ProviderPicker";

export function ContextScreen({
  session,
  onSave,
  onUpload,
  onDraftCreativeBrief,
  onUpdateCreativeBrief,
  onApproveCreativeBrief,
  onGenerate,
}: {
  session: TripSession;
  onSave: (context: TripContext) => void;
  onUpload: () => void;
  onDraftCreativeBrief: (context: TripContext) => Promise<void>;
  onUpdateCreativeBrief: (patch: { selected_direction_id?: string | null; answers?: Array<{ question_id: string; answer: string }>; notes?: string | null }) => Promise<void>;
  onApproveCreativeBrief: (patch: { selected_direction_id?: string | null; answers?: Array<{ question_id: string; answer: string }>; notes?: string | null }) => Promise<void>;
  onGenerate: () => void;
}) {
  const { width } = useWindowDimensions();
  const [context, setContext] = useState<TripContext>(session.trip_context);
  const hasMedia = session.media_items.length > 0;
  const desktop = width >= 920;

  useEffect(() => {
    setContext(session.trip_context);
  }, [session.id]);

  const update = (key: keyof TripContext, value: string) => {
    setContext((current) => ({ ...current, [key]: value }));
  };

  return (
    <ScrollView contentContainerStyle={styles.screen}>
      <View style={[styles.contextLayout, desktop && styles.contextLayoutDesktop]}>
        <View style={[styles.studioPanel, desktop && styles.studioPanelDesktop]}>
          <View style={styles.heroPanel}>
            <View style={styles.heroTopline}>
              <Text style={styles.eyebrow}>Current project</Text>
              <Tag label={session.phase.replaceAll('_', ' ')} tone={session.phase === 'complete' ? 'success' : session.phase === 'error' ? 'warning' : 'info'} />
            </View>
            <Text style={styles.heroTitle}>{sessionTitle(session)}</Text>
            <Text style={styles.heroCopy}>{context.highlights || context.places_visited || 'Add a destination, moments, and clips to build the edit.'}</Text>
          </View>

          <View style={styles.metricsGrid}>
            <MetricPill icon="videocam-outline" label="Uploaded clips" value={`${session.media_items.length}`} />
            <MetricPill icon="language-outline" label="Voiceover" value={context.language.toUpperCase()} />
          </View>

          <Pressable onPress={onUpload} style={({ pressed }) => [styles.uploadZone, pressed && styles.uploadZonePressed]}>
            <View style={styles.uploadIcon}>
              <Ionicons name="cloud-upload-outline" size={28} color={colors.blue} />
            </View>
            <Text style={styles.uploadTitle}>Add trip videos</Text>
            <Text style={styles.uploadCopy}>Select one or more clips. The renderer stitches uploaded video in order for this MVP.</Text>
          </Pressable>

          <ClipIntelligence clips={session.clip_analysis || []} />

          <ProducerBriefPanel
            session={session}
            context={context}
            disabled={planningPhases.includes(session.phase)}
            onDraft={() => onDraftCreativeBrief(context)}
            onSave={onUpdateCreativeBrief}
            onApprove={onApproveCreativeBrief}
            onGenerate={onGenerate}
          />

          <View style={styles.heroActions}>
            <PrimaryButton icon="save-outline" label="Save context" onPress={() => onSave(context)} tone="light" />
          </View>
          {!hasMedia ? <Text style={styles.muted}>Upload at least one video before generating the story.</Text> : null}
        </View>

        <View style={[styles.panel, styles.formPanel]}>
          <View style={styles.panelHeading}>
            <SectionHeader icon="create-outline" title="Story inputs" meta="Trip context and model settings" />
          </View>
          <View style={styles.formGrid}>
            {tripContextFields.map((field) => (
              <Field
                key={field.key}
                label={field.label}
                value={context[field.key]}
                onChangeText={(value) => update(field.key, value)}
                placeholder={field.placeholder}
                multiline={field.multiline}
                wide={field.wide}
              />
            ))}
            <View style={styles.fieldWide}>
              <Text style={styles.fieldLabel}>Voiceover language</Text>
              <LanguagePicker value={context.language} onChange={(value) => update('language', value)} />
            </View>
            <View style={styles.fieldWide}>
              <Text style={styles.fieldLabel}>AI provider</Text>
              <ProviderPicker value={context.llm_provider || 'local'} onChange={(value) => update('llm_provider', value)} />
            </View>
            <Field
              label="Model override"
              value={context.llm_model}
              onChangeText={(value) => update('llm_model', value)}
              placeholder={providerModelPlaceholders[context.llm_provider] || 'Optional model name from your provider'}
              wide
            />
          </View>
        </View>
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
  contextLayout: {
    gap: 16,
  },
  contextLayoutDesktop: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  studioPanel: {
    gap: 12,
  },
  studioPanelDesktop: {
    width: 350,
    flexShrink: 0,
  },
  heroPanel: {
    minHeight: 206,
    backgroundColor: colors.blueDark,
    borderRadius: radii.md,
    padding: 18,
    gap: 12,
    justifyContent: 'space-between',
    overflow: 'hidden',
  },
  heroTopline: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  eyebrow: {
    color: '#a9d8dc',
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
    letterSpacing: 0,
  },
  heroTitle: {
    color: colors.white,
    fontSize: 28,
    lineHeight: 33,
    fontWeight: '900',
  },
  heroCopy: {
    color: '#dce8df',
    fontSize: 14,
    lineHeight: 21,
    fontWeight: '600',
  },
  metricsGrid: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
  },
  uploadZone: {
    minHeight: 178,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: '#bfd9df',
    backgroundColor: colors.blueSoft,
    padding: 18,
    justifyContent: 'center',
    gap: 10,
  },
  uploadZonePressed: {
    transform: [{ scale: 0.995 }],
  },
  uploadIcon: {
    width: 56,
    height: 56,
    borderRadius: radii.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surfaceRaised,
  },
  uploadTitle: {
    color: colors.ink,
    fontSize: 19,
    lineHeight: 24,
    fontWeight: '900',
  },
  uploadCopy: {
    color: colors.graphite,
    fontSize: 13,
    lineHeight: 19,
    fontWeight: '600',
  },
  heroActions: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
  },
  muted: {
    color: colors.muted,
    fontSize: 13,
    lineHeight: 18,
    fontWeight: '600',
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
  formPanel: {
    flex: 1,
  },
  panelHeading: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 14,
    flexWrap: 'wrap',
  },
  formGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
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
});
