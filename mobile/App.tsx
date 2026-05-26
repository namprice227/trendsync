import { Ionicons } from '@expo/vector-icons';
import * as DocumentPicker from 'expo-document-picker';
import { useVideoPlayer, VideoView } from 'expo-video';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  SafeAreaView,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  TextInput,
  useWindowDimensions,
  View,
} from 'react-native';

import {
  createSession,
  generateStory,
  getSession,
  listSessions,
  mediaUrl,
  normalizeBaseUrl,
  renderTripVideo,
  saveTripContext,
  shareSession,
  uploadMedia,
} from './src/api';
import { colors, radii, shadow } from './src/theme';
import type { ClipAnalysis, ProjectSummary, RenderOptions, TripContext, TripPhase, TripScreen, TripSession } from './src/types';

const DEFAULT_API_URL = Platform.OS === 'android' ? 'http://10.0.2.2:8010' : 'http://localhost:8010';
const busyPhases: TripPhase[] = ['uploading', 'planning', 'rendering'];
const planningPhases: TripPhase[] = ['planning', 'rendering'];
const defaultRenderOptions: RenderOptions = {
  aspect_ratio: 'original',
  clip_order: [],
  favorite_clip_ids: [],
  burn_captions: false,
  include_title_card: true,
  include_music_bed: false,
};

const LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'vi', label: 'Vietnamese' },
  { code: 'fr', label: 'French' },
  { code: 'es', label: 'Spanish' },
  { code: 'ja', label: 'Japanese' },
  { code: 'ko', label: 'Korean' },
  { code: 'zh', label: 'Chinese' },
];

const LLM_PROVIDERS = [
  { code: 'local', label: 'Local', detail: 'No backend key' },
  { code: 'openai', label: 'OpenAI', detail: 'OPENAI_API_KEY' },
  { code: 'gemini', label: 'Gemini', detail: 'GEMINI_API_KEY' },
  { code: 'deepseek', label: 'DeepSeek', detail: 'DEEPSEEK_API_KEY' },
];

const providerModelPlaceholders: Record<string, string> = {
  local: 'Uses the built-in fallback',
  openai: 'Optional, default: gpt-4o-mini',
  gemini: 'Optional, default: gemini-2.0-flash',
  deepseek: 'Optional, default: deepseek-chat',
};

const tripContextFields: Array<{
  key: keyof TripContext;
  label: string;
  placeholder: string;
  multiline?: boolean;
  wide?: boolean;
}> = [
  { key: 'destination', label: 'Destination', placeholder: 'Kyoto, Da Nang, Iceland...' },
  { key: 'duration', label: 'Trip length', placeholder: '5 days, long weekend, 2 weeks...' },
  { key: 'travel_dates', label: 'Travel dates', placeholder: 'April 2026, summer break...' },
  { key: 'companions', label: 'People', placeholder: 'Solo, family, partner, friends...' },
  { key: 'places_visited', label: 'Places visited', placeholder: 'Old town, beach, mountain pass, night market...', multiline: true, wide: true },
  { key: 'highlights', label: 'Best moments', placeholder: 'Food, sunset, funny moment, surprise stop...', multiline: true, wide: true },
  { key: 'mood', label: 'Tone', placeholder: 'Warm, funny, reflective, cinematic...' },
  { key: 'audience', label: 'Audience', placeholder: 'Friends, family, Instagram, private archive...' },
  { key: 'notes', label: 'Extra notes', placeholder: 'Anything to avoid, inside jokes, must-use clips...', multiline: true, wide: true },
];

function PrimaryButton({
  icon,
  label,
  onPress,
  disabled,
  tone = 'primary',
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  onPress: () => void;
  disabled?: boolean;
  tone?: 'primary' | 'light' | 'danger';
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [
        styles.button,
        tone === 'light' && styles.buttonLight,
        tone === 'danger' && styles.buttonDanger,
        disabled && styles.buttonDisabled,
        pressed && !disabled && styles.buttonPressed,
      ]}
    >
      <Ionicons name={icon} size={18} color={tone === 'light' ? colors.ink : colors.white} />
      <Text style={[styles.buttonText, tone === 'light' && styles.buttonTextLight]}>{label}</Text>
    </Pressable>
  );
}

function MetricPill({
  icon,
  label,
  value,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  value: string;
}) {
  return (
    <View style={styles.metricPill}>
      <Ionicons name={icon} size={16} color={colors.blue} />
      <View style={styles.metricTextWrap}>
        <Text style={styles.metricValue}>{value}</Text>
        <Text style={styles.metricLabel}>{label}</Text>
      </View>
    </View>
  );
}

function PhaseRail({ screen, phase }: { screen: TripScreen; phase: TripPhase }) {
  const steps: { key: TripScreen; label: string; icon: keyof typeof Ionicons.glyphMap }[] = [
    { key: 'context', label: 'Context', icon: 'chatbubble-ellipses-outline' },
    { key: 'upload', label: 'Media', icon: 'cloud-upload-outline' },
    { key: 'plan', label: 'Story', icon: 'sparkles-outline' },
    { key: 'output', label: 'Video', icon: 'film-outline' },
  ];
  const activeIndex = steps.findIndex((step) => step.key === screen);

  return (
    <View style={styles.phaseRail}>
      {steps.map((step, index) => {
        const active = index === activeIndex;
        const done = index < activeIndex || phase === 'complete';
        return (
          <View key={step.key} style={styles.phaseItem}>
            <View style={[styles.phaseIcon, active && styles.phaseIconActive, done && styles.phaseIconDone]}>
              <Ionicons name={done ? 'checkmark' : step.icon} size={15} color={active || done ? colors.white : colors.muted} />
            </View>
            <Text style={[styles.phaseText, active && styles.phaseTextActive]}>{step.label}</Text>
          </View>
        );
      })}
    </View>
  );
}

function StatusStrip({ session }: { session: TripSession }) {
  const toneStyle =
    session.phase === 'error'
      ? styles.statusError
      : session.phase === 'complete'
        ? styles.statusDone
        : session.phase === 'ready_to_render'
          ? styles.statusInfo
          : styles.statusNeutral;

  return (
    <View style={[styles.statusStrip, toneStyle]}>
      <View style={styles.statusIcon}>
        <Ionicons
          name={session.phase === 'complete' ? 'checkmark' : session.phase === 'error' ? 'warning-outline' : 'pulse-outline'}
          size={16}
          color={session.phase === 'error' ? colors.red : session.phase === 'complete' ? colors.green : colors.blue}
        />
      </View>
      <View style={styles.statusCopy}>
        <Text style={styles.statusLabel}>{session.progress_label}</Text>
        <Text style={styles.statusAction}>{session.error || session.next_action}</Text>
        {session.progress_percent ? (
          <View style={styles.progressTrack}>
            <View style={[styles.progressFill, { width: `${Math.min(100, Math.max(0, session.progress_percent))}%` }]} />
          </View>
        ) : null}
      </View>
    </View>
  );
}

function AppShell({
  session,
  apiUrl,
  apiDraft,
  setApiDraft,
  onReconnect,
  onRestart,
  children,
}: {
  session: TripSession | null;
  apiUrl: string;
  apiDraft: string;
  setApiDraft: (value: string) => void;
  onReconnect: () => void;
  onRestart: () => void;
  children: React.ReactNode;
}) {
  const { width } = useWindowDimensions();
  const compact = width < 760;

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar barStyle="dark-content" />
      <KeyboardAvoidingView style={styles.root} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={[styles.header, compact && styles.headerCompact]}>
          <View style={styles.brandLockup}>
            <View style={styles.brandMark}>
              <Ionicons name="film-outline" size={18} color={colors.white} />
            </View>
            <View>
              <Text style={styles.brand}>TripStory</Text>
              <Text style={styles.brandSub}>Holiday narrative studio</Text>
            </View>
          </View>
          <View style={styles.serverBox}>
            <TextInput
              value={apiDraft}
              onChangeText={setApiDraft}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
              style={styles.serverInput}
              placeholder={apiUrl}
              placeholderTextColor={colors.muted}
            />
            <Pressable onPress={onReconnect} style={styles.serverButton}>
              <Ionicons name="sync" size={16} color={colors.blue} />
            </Pressable>
          </View>
          <Pressable onPress={onRestart} style={styles.restartButton}>
            <Ionicons name="add-circle-outline" size={17} color={colors.white} />
            <Text style={styles.restartText}>New project</Text>
          </Pressable>
        </View>
        <View style={styles.shellChrome}>
          {session ? <PhaseRail screen={session.screen} phase={session.phase} /> : null}
          {session ? <StatusStrip session={session} /> : null}
        </View>
        {children}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function Field({
  label,
  value,
  onChangeText,
  placeholder,
  multiline,
  wide,
}: {
  label: string;
  value: string;
  onChangeText: (value: string) => void;
  placeholder: string;
  multiline?: boolean;
  wide?: boolean;
}) {
  return (
    <View style={[styles.field, wide ? styles.fieldWide : styles.fieldHalf]}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={colors.muted}
        multiline={multiline}
        style={[styles.input, multiline && styles.inputTall]}
      />
    </View>
  );
}

function LanguagePicker({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <View style={styles.chipRow}>
      {LANGUAGES.map((language) => {
        const active = value === language.code;
        return (
          <Pressable key={language.code} onPress={() => onChange(language.code)} style={[styles.chip, active && styles.chipActive]}>
            <Text style={[styles.chipText, active && styles.chipTextActive]}>{language.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

function ProviderPicker({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <View style={styles.providerGrid}>
      {LLM_PROVIDERS.map((provider) => {
        const active = value === provider.code;
        return (
          <Pressable
            key={provider.code}
            onPress={() => onChange(provider.code)}
            style={[styles.providerCard, active && styles.providerCardActive]}
          >
            <View style={[styles.providerIcon, active && styles.providerIconActive]}>
              <Ionicons name={active ? 'checkmark' : 'key-outline'} size={15} color={active ? colors.white : colors.blue} />
            </View>
            <View style={styles.providerCopy}>
              <Text style={[styles.providerName, active && styles.providerNameActive]}>{provider.label}</Text>
              <Text style={[styles.providerDetail, active && styles.providerDetailActive]}>{provider.detail}</Text>
            </View>
          </Pressable>
        );
      })}
    </View>
  );
}

function formatTimestamp(value: number): string {
  const minutes = Math.floor(value / 60);
  const seconds = Math.floor(value % 60);
  return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

function ClipIntelligence({ clips }: { clips: ClipAnalysis[] }) {
  if (!clips.length) return null;
  return (
    <View style={styles.insightPanel}>
      <Text style={styles.sectionTitle}>Clip intelligence</Text>
      {clips.map((clip, index) => (
        <View key={`${clip.filename}-${index}`} style={styles.insightItem}>
          <View style={styles.insightHead}>
            <Text style={styles.insightTitle}>{clip.filename}</Text>
            <Text style={styles.insightBadge}>{clip.quality_label || 'unknown'}</Text>
          </View>
          <Text style={styles.listItem}>{clip.summary || 'Analysis unavailable.'}</Text>
          {clip.semantic_summary ? <Text style={styles.listItem}>Seen in clip: {clip.semantic_summary}</Text> : null}
          {clip.locations_or_scenes?.length ? (
            <Text style={styles.listItem}>Scenes: {clip.locations_or_scenes.join(', ')}</Text>
          ) : null}
          {clip.visible_subjects?.length ? (
            <Text style={styles.listItem}>Subjects: {clip.visible_subjects.join(', ')}</Text>
          ) : null}
          {clip.best_moment_descriptions?.length ? (
            <Text style={styles.listItem}>
              Smart moments: {clip.best_moment_descriptions.map((moment) => `${formatTimestamp(moment.timestamp)} ${moment.description}`).join(' · ')}
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

function ProjectLibrary({
  projects,
  activeId,
  onOpen,
  onNew,
}: {
  projects: ProjectSummary[];
  activeId: string;
  onOpen: (sessionId: string) => void;
  onNew: () => void;
}) {
  return (
    <View style={styles.insightPanel}>
      <View style={styles.insightHead}>
        <Text style={styles.sectionTitle}>Projects</Text>
        <Pressable onPress={onNew} style={styles.iconButton}>
          <Ionicons name="add" size={17} color={colors.blue} />
        </Pressable>
      </View>
      {projects.slice(0, 5).map((project) => {
        const active = project.id === activeId;
        return (
          <Pressable key={project.id} onPress={() => onOpen(project.id)} style={[styles.projectRow, active && styles.projectRowActive]}>
            <View style={styles.projectRowCopy}>
              <Text style={styles.insightTitle}>{project.destination}</Text>
              <Text style={styles.projectMeta}>{project.media_count} clips · {project.phase.replaceAll('_', ' ')}</Text>
            </View>
            {active ? <Ionicons name="checkmark" size={16} color={colors.blue} /> : null}
          </Pressable>
        );
      })}
    </View>
  );
}

function ContextScreen({
  session,
  projects,
  onSave,
  onUpload,
  onGenerate,
  onOpenProject,
  onNewProject,
}: {
  session: TripSession;
  projects: ProjectSummary[];
  onSave: (context: TripContext) => void;
  onUpload: () => void;
  onGenerate: (context: TripContext) => void;
  onOpenProject: (sessionId: string) => void;
  onNewProject: () => void;
}) {
  const { width } = useWindowDimensions();
  const [context, setContext] = useState<TripContext>(session.trip_context);
  const hasMedia = session.media_items.length > 0;
  const canGenerate = hasMedia && context.destination.trim().length > 0 && session.phase !== 'planning';
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
          <ProjectLibrary projects={projects} activeId={session.id} onOpen={onOpenProject} onNew={onNewProject} />
          <View style={styles.heroPanel}>
            <Text style={styles.eyebrow}>Trip brief</Text>
            <Text style={styles.heroTitle}>Shape a recap people will actually want to watch.</Text>
            <Text style={styles.heroCopy}>
              Add the memory cues, upload the raw clips, then generate a story plan with voiceover and edit notes.
            </Text>
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

          <View style={styles.heroActions}>
            <PrimaryButton icon="save-outline" label="Save context" onPress={() => onSave(context)} tone="light" />
            <PrimaryButton icon="sparkles-outline" label="Generate plan" onPress={() => onGenerate(context)} disabled={!canGenerate} />
          </View>
          {!hasMedia ? <Text style={styles.muted}>Upload at least one video before generating the story.</Text> : null}
        </View>

        <View style={[styles.panel, styles.formPanel]}>
          <View style={styles.panelHeading}>
            <View>
              <Text style={styles.title}>Story inputs</Text>
              <Text style={styles.muted}>Keep it specific. Names, places, and tiny moments make the generated script feel personal.</Text>
            </View>
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

function PlanScreen({
  session,
  onGenerate,
  onRender,
}: {
  session: TripSession;
  onGenerate: () => void;
  onRender: (options: RenderOptions) => void;
}) {
  const plan = session.story_plan;
  const busy = session.phase === 'planning' || session.phase === 'rendering';
  const generation = plan?.generation;
  const narrativeArc = Array.isArray(plan?.narrative_arc) ? plan.narrative_arc : [];
  const editNotes = Array.isArray(plan?.edit_notes) ? plan.edit_notes : [];
  const editDecisions = Array.isArray(plan?.edit_decisions) ? plan.edit_decisions : [];
  const voiceoverSegments = Array.isArray(plan?.voiceover_segments) ? plan.voiceover_segments : [];
  const [options, setOptions] = useState<RenderOptions>({ ...defaultRenderOptions, ...(session.render_options || {}) });

  useEffect(() => {
    setOptions({ ...defaultRenderOptions, ...(session.render_options || {}) });
  }, [session.id]);

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

  return (
    <ScrollView contentContainerStyle={styles.screen}>
      <View style={styles.panel}>
        <View style={styles.panelHeading}>
          <View>
            <Text style={styles.title}>{plan?.title || 'Narrative plan'}</Text>
            <Text style={styles.muted}>{plan?.tone ? `${plan.tone} tone` : 'Generate a voiceover and edit structure from your trip brief.'}</Text>
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
          <View style={styles.statusStrip}>
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
        {plan?.voiceover_script ? (
          <>
            <Text style={styles.sectionTitle}>Voiceover</Text>
            <Text style={styles.script}>{String(plan.voiceover_script)}</Text>
          </>
        ) : (
          <Text style={styles.muted}>Generate a narrative plan to see the voiceover script.</Text>
        )}
      </View>

      {narrativeArc.length ? (
        <View style={styles.panel}>
          <Text style={styles.sectionTitle}>Narrative arc</Text>
          {narrativeArc.map((item, index) => (
            <View key={`${item}-${index}`} style={styles.timelineItem}>
              <Text style={styles.timelineNumber}>{index + 1}</Text>
              <Text style={styles.timelineText}>{String(item)}</Text>
            </View>
          ))}
        </View>
      ) : null}

      {editNotes.length ? (
        <View style={styles.panel}>
          <Text style={styles.sectionTitle}>Edit notes</Text>
          {editNotes.map((item, index) => (
            <Text key={`${item}-${index}`} style={styles.listItem}>• {String(item)}</Text>
          ))}
        </View>
      ) : null}

      {editDecisions.length ? (
        <View style={styles.panel}>
          <Text style={styles.sectionTitle}>Smart edit decisions</Text>
          {editDecisions.map((decision, index) => (
            <View key={`${decision.clip || 'clip'}-${index}`} style={styles.timelineControl}>
              <Text style={styles.timelineNumber}>{index + 1}</Text>
              <View style={styles.projectRowCopy}>
                <Text style={styles.insightTitle}>{decision.clip || decision.clip_id || 'Selected clip'}</Text>
                <Text style={styles.projectMeta}>
                  {formatTimestamp(decision.start_time || 0)} · {Math.round(decision.duration || 0)}s · {decision.transition || 'cut'}
                </Text>
                <Text style={styles.listItem}>{decision.reason || decision.role || 'Selected by the smart edit planner.'}</Text>
                {voiceoverSegments[index]?.voiceover ? (
                  <Text style={styles.listItem}>Voiceover: {voiceoverSegments[index].voiceover}</Text>
                ) : null}
              </View>
            </View>
          ))}
        </View>
      ) : null}

      <View style={styles.panel}>
        <Text style={styles.sectionTitle}>Timeline and export</Text>
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
                <Ionicons name={favorite ? 'star' : 'star-outline'} size={17} color={favorite ? colors.blue : colors.muted} />
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

      <View style={styles.actionRow}>
        <PrimaryButton icon="refresh-outline" label="Regenerate" onPress={onGenerate} disabled={busy || session.media_items.length === 0} tone="light" />
        <PrimaryButton icon="film-outline" label="Render video" onPress={() => onRender(options)} disabled={busy || !plan || session.recorded_clips.length === 0} />
      </View>
    </ScrollView>
  );
}

function OutputVideo({ source }: { source: string }) {
  const player = useVideoPlayer(source, (instance) => {
    instance.loop = false;
  });

  return <VideoView player={player} style={styles.video} allowsFullscreen contentFit="contain" />;
}

function OutputScreen({
  apiUrl,
  session,
  onRender,
  onShare,
}: {
  apiUrl: string;
  session: TripSession;
  onRender: (options: RenderOptions) => void;
  onShare: () => void;
}) {
  const finalUrl = mediaUrl(apiUrl, session.final_video_url);
  const voiceoverUrl = mediaUrl(apiUrl, session.voiceover_audio_url);
  const captionUrl = mediaUrl(apiUrl, session.caption_vtt_url || session.caption_srt_url);
  const waiting = session.phase === 'rendering';

  return (
    <ScrollView contentContainerStyle={styles.screen}>
      <View style={styles.panel}>
        <View style={styles.panelHeading}>
          <View>
            <Text style={styles.title}>Holiday recap</Text>
            <Text style={styles.muted}>Preview the rendered stitch with AI-generated narration when TTS is configured.</Text>
          </View>
        </View>
        {waiting ? (
          <View style={styles.waitPanel}>
            <ActivityIndicator color={colors.blue} />
            <Text style={styles.waitText}>Rendering uploaded clips.</Text>
          </View>
        ) : null}
        {finalUrl ? <OutputVideo source={finalUrl} /> : <Text style={styles.muted}>Render the video after generating a story plan.</Text>}
        {voiceoverUrl ? <Text style={styles.muted}>AI-generated voiceover audio is mixed into this render.</Text> : null}
        {session.edit_decisions_url ? <Text style={styles.muted}>Smart edit decision JSON saved with the render.</Text> : null}
        {captionUrl ? <Text style={styles.muted}>Subtitle file saved with the render.</Text> : null}
        <View style={styles.actionRow}>
          <PrimaryButton icon="film-outline" label="Render again" onPress={() => onRender(session.render_options || defaultRenderOptions)} disabled={waiting || !session.story_plan} tone="light" />
          <PrimaryButton icon="share-outline" label="Share project" onPress={onShare} disabled={waiting} tone="light" />
        </View>
      </View>

      {session.script ? (
        <View style={styles.panel}>
          <Text style={styles.sectionTitle}>Voiceover script</Text>
          <Text style={styles.script}>{session.script}</Text>
        </View>
      ) : null}
    </ScrollView>
  );
}

export default function App() {
  const [apiDraft, setApiDraft] = useState(DEFAULT_API_URL);
  const [apiUrl, setApiUrl] = useState(DEFAULT_API_URL);
  const [session, setSession] = useState<TripSession | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refreshProjects = useCallback(async (baseUrl: string) => {
    const items = await listSessions(baseUrl);
    setProjects(items);
    return items;
  }, []);

  const connect = useCallback(async () => {
    const nextUrl = normalizeBaseUrl(apiDraft);
    try {
      setError(null);
      setApiUrl(nextUrl);
      const existing = await refreshProjects(nextUrl);
      if (existing.length) {
        const opened = await getSession(nextUrl, existing[0].id);
        setSession(opened);
      } else {
        const created = await createSession(nextUrl);
        setSession(created);
        await refreshProjects(nextUrl);
      }
    } catch (connectError) {
      setSession(null);
      setError(connectError instanceof Error ? connectError.message : 'Could not reach TripStory API');
    }
  }, [apiDraft, refreshProjects]);

  useEffect(() => {
    connect();
  }, []);

  useEffect(() => {
    if (!session) return;
    const intervalMs = busyPhases.includes(session.phase) ? 1500 : 4500;
    const timer = setInterval(async () => {
      try {
        const updated = await getSession(apiUrl, session.id);
        setSession(updated);
        if (!busyPhases.includes(updated.phase)) {
          refreshProjects(apiUrl).catch(() => undefined);
        }
      } catch (pollError) {
        setError(pollError instanceof Error ? pollError.message : 'Lost server connection');
      }
    }, intervalMs);
    return () => clearInterval(timer);
  }, [apiUrl, refreshProjects, session?.id, session?.phase]);

  const onOpenProject = useCallback(
    async (sessionId: string) => {
      try {
        setError(null);
        const opened = await getSession(apiUrl, sessionId);
        setSession(opened);
      } catch (openError) {
        setError(openError instanceof Error ? openError.message : 'Could not open project');
      }
    },
    [apiUrl]
  );

  const onNewProject = useCallback(async () => {
    try {
      setError(null);
      const created = await createSession(apiUrl);
      setSession(created);
      await refreshProjects(apiUrl);
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : 'Could not create project');
    }
  }, [apiUrl, refreshProjects]);

  const onSaveContext = useCallback(
    async (context: TripContext) => {
      if (!session) return;
      try {
        setError(null);
        const updated = await saveTripContext(apiUrl, session.id, context);
        setSession(updated);
        await refreshProjects(apiUrl);
      } catch (saveError) {
        setError(saveError instanceof Error ? saveError.message : 'Could not save context');
      }
    },
    [apiUrl, refreshProjects, session]
  );

  const onUpload = useCallback(async () => {
    if (!session) return;
    const result = await DocumentPicker.getDocumentAsync({
      type: 'video/*',
      copyToCacheDirectory: true,
      multiple: true,
    });
    if (result.canceled || !result.assets?.length) return;
    try {
      setError(null);
      const updated = await uploadMedia(apiUrl, session.id, result.assets);
      setSession(updated);
      await refreshProjects(apiUrl);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : 'Upload failed');
    }
  }, [apiUrl, refreshProjects, session]);

  const onGenerate = useCallback(async () => {
    if (!session || planningPhases.includes(session.phase)) return;
    try {
      setError(null);
      const updated = await generateStory(apiUrl, session.id);
      setSession(updated);
    } catch (generateError) {
      setError(generateError instanceof Error ? generateError.message : 'Story generation failed');
    }
  }, [apiUrl, session]);

  const onGenerateFromContext = useCallback(
    async (context: TripContext) => {
      if (!session || planningPhases.includes(session.phase)) return;
      try {
        setError(null);
        const saved = await saveTripContext(apiUrl, session.id, context);
        setSession(saved);
        const updated = await generateStory(apiUrl, saved.id);
        setSession(updated);
      } catch (generateError) {
        setError(generateError instanceof Error ? generateError.message : 'Story generation failed');
      }
    },
    [apiUrl, session]
  );

  const onRender = useCallback(async (options: RenderOptions) => {
    if (!session) return;
    try {
      setError(null);
      const updated = await renderTripVideo(apiUrl, session.id, options);
      setSession(updated);
    } catch (renderError) {
      setError(renderError instanceof Error ? renderError.message : 'Render failed');
    }
  }, [apiUrl, session]);

  const onShare = useCallback(async () => {
    if (!session) return;
    try {
      setError(null);
      const shared = await shareSession(apiUrl, session.id);
      setSession(shared.session);
      setError(`Share link: ${apiUrl}${shared.share_url}`);
      await refreshProjects(apiUrl);
    } catch (shareError) {
      setError(shareError instanceof Error ? shareError.message : 'Could not share project');
    }
  }, [apiUrl, refreshProjects, session]);

  const content = useMemo(() => {
    if (!session) {
      return (
        <View style={styles.screen}>
          <View style={styles.panel}>
            <Text style={styles.title}>Connect server</Text>
            <Text style={styles.muted}>{error || 'TripStory API is not connected.'}</Text>
            <PrimaryButton icon="sync" label="Reconnect" onPress={connect} />
          </View>
        </View>
      );
    }
    if (session.screen === 'plan') {
      return <PlanScreen session={session} onGenerate={onGenerate} onRender={onRender} />;
    }
    if (session.screen === 'output') {
      return <OutputScreen apiUrl={apiUrl} session={session} onRender={onRender} onShare={onShare} />;
    }
    return (
      <ContextScreen
        session={session}
        projects={projects}
        onSave={onSaveContext}
        onUpload={onUpload}
        onGenerate={onGenerateFromContext}
        onOpenProject={onOpenProject}
        onNewProject={onNewProject}
      />
    );
  }, [apiUrl, connect, error, onGenerate, onGenerateFromContext, onNewProject, onOpenProject, onRender, onSaveContext, onShare, onUpload, projects, session]);

  return (
    <AppShell
      session={session}
      apiUrl={apiUrl}
      apiDraft={apiDraft}
      setApiDraft={setApiDraft}
      onReconnect={connect}
      onRestart={onNewProject}
    >
      {error && session?.phase !== 'error' ? (
        <View style={styles.inlineError}>
          <Ionicons name="warning-outline" size={16} color={colors.red} />
          <Text style={styles.inlineErrorText}>{error}</Text>
        </View>
      ) : null}
      {content}
    </AppShell>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: colors.paper,
  },
  root: {
    flex: 1,
    backgroundColor: colors.paper,
  },
  header: {
    paddingHorizontal: 22,
    paddingTop: 14,
    paddingBottom: 12,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 16,
  },
  headerCompact: {
    alignItems: 'stretch',
    flexDirection: 'column',
  },
  brandLockup: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  brandMark: {
    width: 38,
    height: 38,
    borderRadius: radii.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.ink,
  },
  brand: {
    color: colors.ink,
    fontSize: 24,
    lineHeight: 29,
    fontWeight: '900',
  },
  brandSub: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '700',
  },
  serverBox: {
    flex: 1,
    maxWidth: 340,
    minWidth: 220,
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radii.md,
    backgroundColor: colors.surface,
  },
  serverInput: {
    flex: 1,
    height: 42,
    paddingHorizontal: 12,
    color: colors.ink,
    fontSize: 13,
    fontWeight: '600',
  },
  serverButton: {
    width: 42,
    height: 42,
    alignItems: 'center',
    justifyContent: 'center',
  },
  restartButton: {
    minHeight: 42,
    borderRadius: radii.md,
    backgroundColor: colors.blue,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 7,
    paddingHorizontal: 12,
  },
  restartText: {
    color: colors.white,
    fontSize: 13,
    lineHeight: 17,
    fontWeight: '900',
  },
  shellChrome: {
    paddingHorizontal: 22,
    gap: 10,
  },
  phaseRail: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 10,
    borderRadius: radii.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.line,
  },
  phaseItem: {
    flex: 1,
    alignItems: 'center',
    gap: 5,
  },
  phaseIcon: {
    width: 28,
    height: 28,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.white,
  },
  phaseIconActive: {
    backgroundColor: colors.blue,
    borderColor: colors.blue,
  },
  phaseIconDone: {
    backgroundColor: colors.green,
    borderColor: colors.green,
  },
  phaseText: {
    color: colors.muted,
    fontSize: 11,
    lineHeight: 14,
    fontWeight: '700',
  },
  phaseTextActive: {
    color: colors.ink,
  },
  statusStrip: {
    marginBottom: 10,
    borderRadius: radii.md,
    paddingHorizontal: 12,
    paddingVertical: 12,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 10,
    alignItems: 'center',
  },
  statusNeutral: {
    backgroundColor: colors.surface,
    borderColor: colors.line,
  },
  statusInfo: {
    backgroundColor: '#edf6f7',
    borderColor: '#c8dcdf',
  },
  statusDone: {
    backgroundColor: '#edf6ef',
    borderColor: '#c9dfce',
  },
  statusError: {
    backgroundColor: '#fff2ee',
    borderColor: '#f0c5ba',
  },
  statusIcon: {
    width: 34,
    height: 34,
    borderRadius: radii.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.white,
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
  progressTrack: {
    height: 5,
    marginTop: 8,
    borderRadius: 999,
    overflow: 'hidden',
    backgroundColor: colors.line,
  },
  progressFill: {
    height: 5,
    borderRadius: 999,
    backgroundColor: colors.blue,
  },
  screen: {
    width: '100%',
    maxWidth: 1180,
    alignSelf: 'center',
    paddingHorizontal: 22,
    paddingTop: 8,
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
    minHeight: 230,
    backgroundColor: colors.ink,
    borderRadius: radii.md,
    padding: 20,
    gap: 14,
    justifyContent: 'flex-end',
    overflow: 'hidden',
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
    fontSize: 30,
    lineHeight: 35,
    fontWeight: '900',
  },
  heroCopy: {
    color: '#dce8df',
    fontSize: 14,
    lineHeight: 21,
    fontWeight: '600',
  },
  heroActions: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
  },
  metricsGrid: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
  },
  metricPill: {
    minHeight: 56,
    flexGrow: 1,
    flexBasis: 150,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radii.md,
    paddingHorizontal: 12,
    backgroundColor: colors.surface,
  },
  metricTextWrap: {
    flex: 1,
  },
  metricValue: {
    color: colors.ink,
    fontSize: 15,
    lineHeight: 19,
    fontWeight: '900',
  },
  metricLabel: {
    color: colors.muted,
    fontSize: 11,
    lineHeight: 15,
    fontWeight: '700',
  },
  uploadZone: {
    minHeight: 178,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.mist,
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
    backgroundColor: colors.white,
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
  title: {
    color: colors.ink,
    fontSize: 23,
    lineHeight: 29,
    fontWeight: '900',
  },
  sectionTitle: {
    color: colors.ink,
    fontSize: 16,
    lineHeight: 21,
    fontWeight: '900',
  },
  muted: {
    color: colors.muted,
    fontSize: 13,
    lineHeight: 18,
    fontWeight: '600',
  },
  formGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
  },
  field: {
    minWidth: 220,
    gap: 6,
  },
  fieldHalf: {
    flexGrow: 1,
    flexBasis: 260,
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
    backgroundColor: colors.white,
  },
  inputTall: {
    minHeight: 104,
    textAlignVertical: 'top',
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
    backgroundColor: colors.white,
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
  providerGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  providerCard: {
    minHeight: 66,
    flexGrow: 1,
    flexBasis: 160,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.white,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  providerCardActive: {
    borderColor: colors.blue,
    backgroundColor: '#edf6f7',
  },
  providerIcon: {
    width: 30,
    height: 30,
    borderRadius: radii.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.mist,
  },
  providerIconActive: {
    backgroundColor: colors.blue,
  },
  providerCopy: {
    flex: 1,
  },
  providerName: {
    color: colors.ink,
    fontSize: 13,
    lineHeight: 17,
    fontWeight: '900',
  },
  providerNameActive: {
    color: colors.ink,
  },
  providerDetail: {
    marginTop: 2,
    color: colors.muted,
    fontSize: 11,
    lineHeight: 15,
    fontWeight: '700',
  },
  providerDetailActive: {
    color: colors.graphite,
  },
  button: {
    minHeight: 48,
    borderRadius: radii.md,
    backgroundColor: colors.blue,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 8,
    paddingHorizontal: 14,
    flexGrow: 0,
  },
  buttonLight: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.line,
  },
  buttonDanger: {
    backgroundColor: colors.red,
  },
  buttonDisabled: {
    opacity: 0.48,
  },
  buttonPressed: {
    transform: [{ scale: 0.99 }],
  },
  buttonText: {
    color: colors.white,
    fontSize: 14,
    lineHeight: 18,
    fontWeight: '900',
  },
  buttonTextLight: {
    color: colors.ink,
  },
  waitPanel: {
    backgroundColor: colors.mist,
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
  script: {
    color: colors.graphite,
    fontSize: 15,
    lineHeight: 23,
    fontWeight: '600',
  },
  listItem: {
    color: colors.graphite,
    fontSize: 13,
    lineHeight: 19,
    fontWeight: '600',
  },
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
    gap: 5,
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
  insightBadge: {
    color: colors.blue,
    fontSize: 11,
    lineHeight: 15,
    fontWeight: '900',
  },
  iconButton: {
    width: 34,
    height: 34,
    borderRadius: radii.md,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.white,
  },
  projectRow: {
    minHeight: 52,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.white,
    paddingHorizontal: 10,
    paddingVertical: 8,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  projectRowActive: {
    borderColor: colors.blue,
    backgroundColor: '#edf6f7',
  },
  projectRowCopy: {
    flex: 1,
  },
  projectMeta: {
    color: colors.muted,
    fontSize: 11,
    lineHeight: 15,
    fontWeight: '700',
  },
  toggleRow: {
    minHeight: 38,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  timelineControl: {
    minHeight: 58,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.white,
    paddingHorizontal: 10,
    paddingVertical: 8,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  actionRow: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
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
  video: {
    width: '100%',
    aspectRatio: 9 / 16,
    borderRadius: radii.md,
    backgroundColor: colors.camera,
    overflow: 'hidden',
  },
  inlineError: {
    marginHorizontal: 22,
    marginBottom: 10,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: '#f0c5ba',
    backgroundColor: '#fff2ee',
    paddingHorizontal: 12,
    paddingVertical: 9,
    flexDirection: 'row',
    gap: 8,
    alignItems: 'center',
  },
  inlineErrorText: {
    flex: 1,
    color: colors.red,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '700',
  },
});
