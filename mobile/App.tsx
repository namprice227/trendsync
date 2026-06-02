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
  deleteSession,
  duplicateSession,
  generateStory,
  getSession,
  listSessions,
  mediaUrl,
  normalizeBaseUrl,
  renderTripVideo,
  saveTripContext,
  shareSession,
  updateProjectMetadata,
  updateVoiceoverSegments,
  uploadMedia,
} from './src/api';
import { colors, radii, shadow } from './src/theme';
import type { ClipAnalysis, MediaItem, ProjectSummary, RenderOptions, TripContext, TripPhase, TripScreen, TripSession } from './src/types';

const DEFAULT_API_URL = Platform.OS === 'android' ? 'http://10.0.2.2:8010' : 'http://localhost:8010';
const busyPhases: TripPhase[] = ['uploading', 'planning', 'rendering'];
const planningPhases: TripPhase[] = ['planning', 'rendering'];
const defaultRenderOptions: RenderOptions = {
  aspect_ratio: 'original',
  target_duration_seconds: 30,
  clip_order: [],
  favorite_clip_ids: [],
  excluded_clip_ids: [],
  burn_captions: false,
  include_title_card: true,
  include_music_bed: false,
};

const VIDEO_LENGTH_PRESETS = [15, 30, 45, 60, 90];
type AppView = 'dashboard' | 'project';
type ProjectFilter = 'all' | 'drafting' | 'ready' | 'rendering' | 'complete' | 'error';
type ProjectSort = 'recent' | 'name' | 'status';
type ProjectAction = 'rename' | 'duplicate' | 'share' | 'delete';

const projectFilters: Array<{ key: ProjectFilter; label: string }> = [
  { key: 'all', label: 'All' },
  { key: 'drafting', label: 'Drafting' },
  { key: 'ready', label: 'Ready' },
  { key: 'rendering', label: 'Rendering' },
  { key: 'complete', label: 'Complete' },
  { key: 'error', label: 'Error' },
];

const projectSorts: Array<{ key: ProjectSort; label: string }> = [
  { key: 'recent', label: 'Recent' },
  { key: 'name', label: 'Name' },
  { key: 'status', label: 'Status' },
];

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

function SectionHeader({
  icon,
  title,
  meta,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  meta?: string;
}) {
  return (
    <View style={styles.sectionHeader}>
      <View style={styles.sectionHeaderIcon}>
        <Ionicons name={icon} size={16} color={colors.blue} />
      </View>
      <View style={styles.sectionHeaderCopy}>
        <Text style={styles.sectionTitle}>{title}</Text>
        {meta ? <Text style={styles.sectionMeta}>{meta}</Text> : null}
      </View>
    </View>
  );
}

function Tag({ label, tone = 'neutral' }: { label: string; tone?: 'neutral' | 'info' | 'success' | 'warning' }) {
  return (
    <View style={[styles.tag, tone === 'info' && styles.tagInfo, tone === 'success' && styles.tagSuccess, tone === 'warning' && styles.tagWarning]}>
      <Text style={[styles.tagText, tone === 'info' && styles.tagTextInfo, tone === 'success' && styles.tagTextSuccess, tone === 'warning' && styles.tagTextWarning]}>
        {label}
      </Text>
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
        <Text style={styles.statusAction}>{session.error || session.active_job?.current_step || session.next_action}</Text>
        {session.active_job ? (
          <Text style={styles.projectMeta}>
            {session.active_job.type.replaceAll('_', ' ')} · {session.active_job.state.replaceAll('_', ' ')}
          </Text>
        ) : null}
        {session.progress_percent || session.active_job?.progress_percent ? (
          <View style={styles.progressTrack}>
            <View
              style={[
                styles.progressFill,
                { width: `${Math.min(100, Math.max(0, session.active_job?.progress_percent || session.progress_percent))}%` },
              ]}
            />
          </View>
        ) : null}
      </View>
    </View>
  );
}

function AppShell({
  session,
  showProjectChrome,
  apiUrl,
  apiDraft,
  setApiDraft,
  onReconnect,
  onRestart,
  creatingProject,
  onBackToDashboard,
  children,
}: {
  session: TripSession | null;
  showProjectChrome: boolean;
  apiUrl: string;
  apiDraft: string;
  setApiDraft: (value: string) => void;
  onReconnect: () => void;
  onRestart: () => void;
  creatingProject: boolean;
  onBackToDashboard: () => void;
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
          {showProjectChrome ? (
            <Pressable onPress={onBackToDashboard} style={styles.backButton}>
              <Ionicons name="arrow-back" size={16} color={colors.graphite} />
              <Text style={styles.backText}>Dashboard</Text>
            </Pressable>
          ) : null}
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
          <Pressable onPress={onRestart} disabled={creatingProject} style={[styles.restartButton, creatingProject && styles.buttonDisabled]}>
            <Ionicons name={creatingProject ? 'hourglass-outline' : 'add-circle-outline'} size={17} color={colors.white} />
            <Text style={styles.restartText}>{creatingProject ? 'Creating' : 'New project'}</Text>
          </Pressable>
        </View>
        <View style={styles.shellChrome}>
          {showProjectChrome && session ? <PhaseRail screen={session.screen} phase={session.phase} /> : null}
          {showProjectChrome && session ? <StatusStrip session={session} /> : null}
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

function fallbackSegmentId(index: number): string {
  return `seg_${String(index + 1).padStart(3, '0')}`;
}

function segmentForDecision(
  segments: NonNullable<TripSession['story_plan']>['voiceover_segments'] | undefined,
  decision: NonNullable<NonNullable<TripSession['story_plan']>['edit_decisions']>[number],
  index: number
) {
  const segmentId = decision.segment_id || fallbackSegmentId(index);
  return segments?.find((segment) => segment.segment_id === segmentId) || segments?.[index] || null;
}

function windowForDecision(mediaItems: MediaItem[], decision: NonNullable<NonNullable<TripSession['story_plan']>['edit_decisions']>[number]) {
  const item = mediaItems.find((media) => media.id === decision.clip_id || media.filename === decision.clip);
  return item?.analysis?.smart_windows?.find((window) => window.window_id === decision.window_id) || null;
}

function ClipIntelligence({ clips }: { clips: ClipAnalysis[] }) {
  if (!clips.length) return null;
  return (
    <View style={styles.insightPanel}>
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
  );
}

function projectTitle(project: ProjectSummary): string {
  return (project.title || project.destination || 'Untitled trip').trim();
}

function sessionTitle(session: TripSession): string {
  return (session.metadata?.title || session.trip_context.destination || 'Untitled trip').trim();
}

function phaseLabel(phase: TripPhase): string {
  return phase.replaceAll('_', ' ');
}

function phaseFilter(phase: TripPhase): ProjectFilter {
  if (phase === 'complete') return 'complete';
  if (phase === 'error') return 'error';
  if (phase === 'planning' || phase === 'rendering') return 'rendering';
  if (phase === 'ready_to_plan' || phase === 'ready_to_render') return 'ready';
  return 'drafting';
}

function phaseTone(phase: TripPhase): 'neutral' | 'info' | 'success' | 'warning' {
  if (phase === 'complete') return 'success';
  if (phase === 'error') return 'warning';
  if (phase === 'ready_to_plan' || phase === 'ready_to_render' || phase === 'planning' || phase === 'rendering') return 'info';
  return 'neutral';
}

function formatUpdatedAt(value: number): string {
  const timestamp = value < 10000000000 ? value * 1000 : value;
  const elapsed = Math.max(0, Date.now() - timestamp);
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;
  if (elapsed < minute) return 'Just now';
  if (elapsed < hour) return `${Math.floor(elapsed / minute)}m ago`;
  if (elapsed < day) return `${Math.floor(elapsed / hour)}h ago`;
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(new Date(timestamp));
}

function ProjectActionButton({
  icon,
  label,
  onPress,
  disabled,
  busy,
  danger,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  onPress: () => void;
  disabled?: boolean;
  busy?: boolean;
  danger?: boolean;
}) {
  return (
    <Pressable
      accessibilityLabel={label}
      onPress={onPress}
      disabled={disabled || busy}
      style={({ pressed }) => [
        styles.projectActionButton,
        danger && styles.projectActionDanger,
        (disabled || busy) && styles.projectActionDisabled,
        pressed && !disabled && !busy && styles.buttonPressed,
      ]}
    >
      {busy ? <ActivityIndicator size="small" color={danger ? colors.red : colors.blue} /> : <Ionicons name={icon} size={16} color={danger ? colors.red : colors.graphite} />}
    </Pressable>
  );
}

function DashboardScreen({
  projects,
  loading,
  creating,
  onOpen,
  onNew,
  onRename,
  onDuplicate,
  onDelete,
  onShare,
}: {
  projects: ProjectSummary[];
  loading: boolean;
  creating: boolean;
  onOpen: (sessionId: string) => void;
  onNew: () => void;
  onRename: (sessionId: string, title: string) => Promise<void>;
  onDuplicate: (sessionId: string) => Promise<TripSession>;
  onDelete: (sessionId: string) => Promise<void>;
  onShare: (sessionId: string) => Promise<string>;
}) {
  const { width } = useWindowDimensions();
  const compact = width < 860;
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<ProjectFilter>('all');
  const [sort, setSort] = useState<ProjectSort>('recent');
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState('');
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [action, setAction] = useState<{ id: string; type: ProjectAction } | null>(null);

  const visibleProjects = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    const statusOrder: Record<TripPhase, number> = {
      collecting_context: 0,
      uploading: 0,
      ready_to_plan: 1,
      ready_to_render: 1,
      planning: 2,
      rendering: 2,
      complete: 3,
      error: 4,
    };
    return [...projects]
      .filter((project) => {
        if (filter !== 'all' && phaseFilter(project.phase) !== filter) return false;
        if (!normalizedQuery) return true;
        return `${projectTitle(project)} ${project.destination}`.toLowerCase().includes(normalizedQuery);
      })
      .sort((left, right) => {
        if (sort === 'name') return projectTitle(left).localeCompare(projectTitle(right));
        if (sort === 'status') return statusOrder[left.phase] - statusOrder[right.phase] || right.updated_at - left.updated_at;
        return right.updated_at - left.updated_at;
      });
  }, [filter, projects, query, sort]);

  const busy = Boolean(action) || creating;

  const startRename = (project: ProjectSummary) => {
    setNotice(null);
    setConfirmDeleteId(null);
    setRenamingId(project.id);
    setRenameDraft(projectTitle(project));
  };

  const commitRename = async (project: ProjectSummary) => {
    const nextTitle = renameDraft.trim();
    if (!nextTitle || nextTitle === projectTitle(project)) {
      setRenamingId(null);
      return;
    }
    setAction({ id: project.id, type: 'rename' });
    try {
      await onRename(project.id, nextTitle);
      setRenamingId(null);
      setNotice(`Renamed to ${nextTitle}`);
    } catch (renameError) {
      setNotice(renameError instanceof Error ? renameError.message : 'Rename failed');
    } finally {
      setAction(null);
    }
  };

  const duplicateProject = async (project: ProjectSummary) => {
    setAction({ id: project.id, type: 'duplicate' });
    setNotice(null);
    try {
      const duplicate = await onDuplicate(project.id);
      setNotice(`Duplicated as ${sessionTitle(duplicate)}`);
    } catch (duplicateError) {
      setNotice(duplicateError instanceof Error ? duplicateError.message : 'Duplicate failed');
    } finally {
      setAction(null);
    }
  };

  const deleteProject = async (project: ProjectSummary) => {
    setAction({ id: project.id, type: 'delete' });
    setNotice(null);
    try {
      await onDelete(project.id);
      setConfirmDeleteId(null);
      setNotice(`${projectTitle(project)} deleted`);
    } catch (deleteError) {
      setNotice(deleteError instanceof Error ? deleteError.message : 'Delete failed');
    } finally {
      setAction(null);
    }
  };

  const shareProject = async (project: ProjectSummary) => {
    setAction({ id: project.id, type: 'share' });
    setNotice(null);
    try {
      const url = await onShare(project.id);
      setNotice(`Share link: ${url}`);
    } catch (shareError) {
      setNotice(shareError instanceof Error ? shareError.message : 'Share failed');
    } finally {
      setAction(null);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.dashboardScreen}>
      <View style={styles.dashboardBand}>
        <View style={[styles.dashboardHeader, compact && styles.dashboardHeaderCompact]}>
          <SectionHeader icon="albums-outline" title="Projects" meta={`${projects.length} saved`} />
          <PrimaryButton icon={creating ? 'hourglass-outline' : 'add-circle-outline'} label={creating ? 'Creating' : 'New project'} onPress={onNew} disabled={busy} />
        </View>

        <View style={[styles.dashboardToolbar, compact && styles.dashboardToolbarCompact]}>
          <View style={styles.searchBox}>
            <Ionicons name="search-outline" size={16} color={colors.muted} />
            <TextInput
              value={query}
              onChangeText={setQuery}
              placeholder="Search destination or title"
              placeholderTextColor={colors.muted}
              style={styles.searchInput}
            />
          </View>
          <View style={styles.segmentGroup}>
            {projectFilters.map((item) => {
              const active = filter === item.key;
              return (
                <Pressable key={item.key} onPress={() => setFilter(item.key)} style={[styles.segmentChip, active && styles.segmentChipActive]}>
                  <Text style={[styles.segmentText, active && styles.segmentTextActive]}>{item.label}</Text>
                </Pressable>
              );
            })}
          </View>
          <View style={styles.segmentGroup}>
            {projectSorts.map((item) => {
              const active = sort === item.key;
              return (
                <Pressable key={item.key} onPress={() => setSort(item.key)} style={[styles.segmentChip, active && styles.segmentChipActive]}>
                  <Text style={[styles.segmentText, active && styles.segmentTextActive]}>{item.label}</Text>
                </Pressable>
              );
            })}
          </View>
        </View>

        {notice ? (
          <View style={styles.dashboardNotice}>
            <Ionicons name="information-circle-outline" size={16} color={colors.blue} />
            <Text style={styles.dashboardNoticeText}>{notice}</Text>
          </View>
        ) : null}

        {loading && !projects.length ? (
          <View style={styles.projectList}>
            {[0, 1, 2].map((item) => (
              <View key={item} style={styles.projectSkeletonRow}>
                <View style={styles.skeletonTitle} />
                <View style={styles.skeletonMeta} />
              </View>
            ))}
          </View>
        ) : null}

        {!loading && !projects.length ? (
          <View style={styles.dashboardEmpty}>
            <Ionicons name="folder-open-outline" size={28} color={colors.subtle} />
            <Text style={styles.emptyText}>No projects yet. Create a project to start a TripStory workflow.</Text>
          </View>
        ) : null}

        {!loading && projects.length > 0 && !visibleProjects.length ? (
          <View style={styles.dashboardEmpty}>
            <Ionicons name="funnel-outline" size={24} color={colors.subtle} />
            <Text style={styles.emptyText}>No projects match the current search and filters.</Text>
          </View>
        ) : null}

        {visibleProjects.length ? (
          <View style={styles.projectList}>
            {visibleProjects.map((project) => {
              const title = projectTitle(project);
              const rowAction = (type: ProjectAction) => action?.id === project.id && action.type === type;
              return (
                <View key={project.id} style={[styles.dashboardProjectRow, compact && styles.dashboardProjectRowCompact]}>
                  <View style={styles.dashboardProjectMain}>
                    {renamingId === project.id ? (
                      <View style={styles.renameRow}>
                        <TextInput
                          value={renameDraft}
                          onChangeText={setRenameDraft}
                          autoFocus
                          onSubmitEditing={() => commitRename(project)}
                          placeholder="Project title"
                          placeholderTextColor={colors.muted}
                          style={[styles.input, styles.renameInput]}
                        />
                        <ProjectActionButton icon="checkmark" label="Save rename" onPress={() => commitRename(project)} busy={rowAction('rename')} disabled={busy && !rowAction('rename')} />
                        <ProjectActionButton icon="close" label="Cancel rename" onPress={() => setRenamingId(null)} disabled={busy} />
                      </View>
                    ) : (
                      <Pressable onPress={() => onOpen(project.id)} disabled={busy} style={styles.projectOpenTarget}>
                        <Text style={styles.dashboardProjectTitle}>{title}</Text>
                        <Text style={styles.dashboardProjectSubtitle}>{project.destination}</Text>
                      </Pressable>
                    )}
                  </View>

                  <View style={styles.projectFacts}>
                    <Tag label={phaseLabel(project.phase)} tone={phaseTone(project.phase)} />
                    <View style={styles.projectFact}>
                      <Ionicons name="videocam-outline" size={14} color={colors.muted} />
                      <Text style={styles.projectFactText}>{project.media_count}</Text>
                    </View>
                    <Tag label={project.final_video_url ? 'Render ready' : 'No render'} tone={project.final_video_url ? 'success' : 'neutral'} />
                    <Tag label={project.share_token ? 'Shared' : 'Private'} tone={project.share_token ? 'info' : 'neutral'} />
                    <View style={styles.projectFact}>
                      <Ionicons name="time-outline" size={14} color={colors.muted} />
                      <Text style={styles.projectFactText}>{formatUpdatedAt(project.updated_at)}</Text>
                    </View>
                  </View>

                  {confirmDeleteId === project.id ? (
                    <View style={styles.deleteConfirmRow}>
                      <Text style={styles.deleteConfirmText}>Delete permanently?</Text>
                      <Pressable onPress={() => setConfirmDeleteId(null)} disabled={busy} style={styles.confirmButton}>
                        <Text style={styles.confirmButtonText}>Cancel</Text>
                      </Pressable>
                      <Pressable onPress={() => deleteProject(project)} disabled={busy} style={[styles.confirmButton, styles.confirmButtonDanger]}>
                        {rowAction('delete') ? <ActivityIndicator size="small" color={colors.white} /> : <Text style={[styles.confirmButtonText, styles.confirmButtonTextDanger]}>Delete</Text>}
                      </Pressable>
                    </View>
                  ) : (
                    <View style={styles.projectActions}>
                      <ProjectActionButton icon="open-outline" label="Open project" onPress={() => onOpen(project.id)} disabled={busy} />
                      <ProjectActionButton icon="create-outline" label="Rename project" onPress={() => startRename(project)} disabled={busy} />
                      <ProjectActionButton icon="copy-outline" label="Duplicate project" onPress={() => duplicateProject(project)} busy={rowAction('duplicate')} disabled={busy && !rowAction('duplicate')} />
                      <ProjectActionButton icon="share-outline" label="Share project" onPress={() => shareProject(project)} busy={rowAction('share')} disabled={busy && !rowAction('share')} />
                      <ProjectActionButton icon="trash-outline" label="Delete project" onPress={() => setConfirmDeleteId(project.id)} disabled={busy} danger />
                    </View>
                  )}
                </View>
              );
            })}
          </View>
        ) : null}
      </View>
    </ScrollView>
  );
}

function ContextScreen({
  session,
  onSave,
  onUpload,
  onGenerate,
}: {
  session: TripSession;
  onSave: (context: TripContext) => void;
  onUpload: () => void;
  onGenerate: (context: TripContext) => void;
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

          <View style={styles.heroActions}>
            <PrimaryButton icon="save-outline" label="Save context" onPress={() => onSave(context)} tone="light" />
            <PrimaryButton icon="sparkles-outline" label="Generate plan" onPress={() => onGenerate(context)} disabled={!canGenerate} />
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

function PlanScreen({
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
      const currentExcluded = new Set(current.excluded_clip_ids || []);
      if (currentFavorites.has(clipId)) {
        currentFavorites.delete(clipId);
      } else {
        currentFavorites.add(clipId);
        currentExcluded.delete(clipId); // Ensure mutually exclusive
      }
      return { ...current, favorite_clip_ids: Array.from(currentFavorites), excluded_clip_ids: Array.from(currentExcluded) };
    });
  };

  const toggleExclude = (clipId: string) => {
    setOptions((current) => {
      const currentExcluded = new Set(current.excluded_clip_ids || []);
      const currentFavorites = new Set(current.favorite_clip_ids || []);
      if (currentExcluded.has(clipId)) {
        currentExcluded.delete(clipId);
      } else {
        currentExcluded.add(clipId);
        currentFavorites.delete(clipId); // Ensure mutually exclusive
      }
      return { ...current, excluded_clip_ids: Array.from(currentExcluded), favorite_clip_ids: Array.from(currentFavorites) };
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
              const favorite = options.favorite_clip_ids?.includes(item.id);
              const excluded = options.excluded_clip_ids?.includes(item.id);
              return (
                <View key={item.id} style={styles.timelineControl}>
                  <Pressable onPress={() => toggleFavorite(item.id)} style={styles.iconButton}>
                    <Ionicons name={favorite ? 'star' : 'star-outline'} size={17} color={favorite ? colors.amber : colors.muted} />
                  </Pressable>
                  <Pressable onPress={() => toggleExclude(item.id)} style={styles.iconButton}>
                    <Ionicons name={excluded ? 'close-circle' : 'close-circle-outline'} size={17} color={excluded ? colors.red : colors.muted} />
                  </Pressable>
                  <View style={[styles.projectRowCopy, excluded && { opacity: 0.5 }]}>
                    <Text style={[styles.insightTitle, excluded && { textDecorationLine: 'line-through' }]}>{item.filename}</Text>
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
  const [view, setView] = useState<AppView>('dashboard');
  const [session, setSession] = useState<TripSession | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [creatingProject, setCreatingProject] = useState(false);

  const refreshProjects = useCallback(async (baseUrl: string) => {
    const items = await listSessions(baseUrl);
    setProjects(items);
    return items;
  }, []);

  const connect = useCallback(async () => {
    const nextUrl = normalizeBaseUrl(apiDraft);
    setLoadingProjects(true);
    try {
      setError(null);
      setApiUrl(nextUrl);
      await refreshProjects(nextUrl);
      setSession(null);
      setView('dashboard');
    } catch (connectError) {
      setSession(null);
      setProjects([]);
      setView('dashboard');
      setError(connectError instanceof Error ? connectError.message : 'Could not reach TripStory API');
    } finally {
      setLoadingProjects(false);
    }
  }, [apiDraft, refreshProjects]);

  useEffect(() => {
    connect();
  }, [connect]);

  useEffect(() => {
    if (!session || view !== 'project') return;
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
  }, [apiUrl, refreshProjects, session?.id, session?.phase, view]);

  const onOpenProject = useCallback(
    async (sessionId: string) => {
      try {
        setError(null);
        const opened = await getSession(apiUrl, sessionId);
        setSession(opened);
        setView('project');
      } catch (openError) {
        setError(openError instanceof Error ? openError.message : 'Could not open project');
      }
    },
    [apiUrl]
  );

  const onNewProject = useCallback(async () => {
    setCreatingProject(true);
    try {
      setError(null);
      const created = await createSession(apiUrl);
      setSession(created);
      setView('project');
      await refreshProjects(apiUrl);
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : 'Could not create project');
    } finally {
      setCreatingProject(false);
    }
  }, [apiUrl, refreshProjects]);

  const onBackToDashboard = useCallback(() => {
    setView('dashboard');
    refreshProjects(apiUrl).catch(() => undefined);
  }, [apiUrl, refreshProjects]);

  const onRenameProject = useCallback(
    async (sessionId: string, title: string) => {
      try {
        setError(null);
        const updated = await updateProjectMetadata(apiUrl, sessionId, { title });
        if (session?.id === sessionId) {
          setSession(updated);
        }
        await refreshProjects(apiUrl);
      } catch (renameError) {
        setError(renameError instanceof Error ? renameError.message : 'Could not rename project');
        throw renameError;
      }
    },
    [apiUrl, refreshProjects, session?.id]
  );

  const onDuplicateProject = useCallback(
    async (sessionId: string) => {
      try {
        setError(null);
        const duplicate = await duplicateSession(apiUrl, sessionId);
        await refreshProjects(apiUrl);
        return duplicate;
      } catch (duplicateError) {
        setError(duplicateError instanceof Error ? duplicateError.message : 'Could not duplicate project');
        throw duplicateError;
      }
    },
    [apiUrl, refreshProjects]
  );

  const onDeleteProject = useCallback(
    async (sessionId: string) => {
      try {
        setError(null);
        await deleteSession(apiUrl, sessionId);
        await refreshProjects(apiUrl);
        if (session?.id === sessionId) {
          setSession(null);
          setView('dashboard');
        }
      } catch (deleteError) {
        setError(deleteError instanceof Error ? deleteError.message : 'Could not delete project');
        throw deleteError;
      }
    },
    [apiUrl, refreshProjects, session?.id]
  );

  const onShareProject = useCallback(
    async (sessionId: string) => {
      try {
        setError(null);
        const shared = await shareSession(apiUrl, sessionId);
        if (session?.id === sessionId) {
          setSession(shared.session);
        }
        await refreshProjects(apiUrl);
        return `${apiUrl}${shared.share_url}`;
      } catch (shareError) {
        setError(shareError instanceof Error ? shareError.message : 'Could not share project');
        throw shareError;
      }
    },
    [apiUrl, refreshProjects, session?.id]
  );

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

  const onSaveVoiceoverSegments = useCallback(async (segments: Array<{ segment_id: string; voiceover: string; caption?: string }>) => {
    if (!session) return;
    try {
      setError(null);
      const updated = await updateVoiceoverSegments(apiUrl, session.id, segments);
      setSession(updated);
      await refreshProjects(apiUrl);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Could not save segment scripts');
      throw saveError;
    }
  }, [apiUrl, refreshProjects, session]);

  const onShare = useCallback(async () => {
    if (!session) return;
    try {
      const url = await onShareProject(session.id);
      setError(`Share link: ${url}`);
    } catch (shareError) {
      setError(shareError instanceof Error ? shareError.message : 'Could not share project');
    }
  }, [onShareProject, session]);

  const content = useMemo(() => {
    if (view === 'dashboard' && (!error || projects.length || loadingProjects)) {
      return (
        <DashboardScreen
          projects={projects}
          loading={loadingProjects}
          creating={creatingProject}
          onOpen={onOpenProject}
          onNew={onNewProject}
          onRename={onRenameProject}
          onDuplicate={onDuplicateProject}
          onDelete={onDeleteProject}
          onShare={onShareProject}
        />
      );
    }
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
      return <PlanScreen session={session} onGenerate={onGenerate} onRender={onRender} onSaveVoiceoverSegments={onSaveVoiceoverSegments} />;
    }
    if (session.screen === 'output') {
      return <OutputScreen apiUrl={apiUrl} session={session} onRender={onRender} onShare={onShare} />;
    }
    return (
      <ContextScreen
        session={session}
        onSave={onSaveContext}
        onUpload={onUpload}
        onGenerate={onGenerateFromContext}
      />
    );
  }, [
    apiUrl,
    connect,
    creatingProject,
    error,
    loadingProjects,
    onDeleteProject,
    onDuplicateProject,
    onGenerate,
    onGenerateFromContext,
    onNewProject,
    onOpenProject,
    onRenameProject,
    onRender,
    onSaveContext,
    onSaveVoiceoverSegments,
    onShare,
    onShareProject,
    onUpload,
    projects,
    session,
    view,
  ]);

  return (
    <AppShell
      session={session}
      showProjectChrome={view === 'project' && Boolean(session)}
      apiUrl={apiUrl}
      apiDraft={apiDraft}
      setApiDraft={setApiDraft}
      onReconnect={connect}
      onRestart={onNewProject}
      creatingProject={creatingProject}
      onBackToDashboard={onBackToDashboard}
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
    paddingTop: 12,
    paddingBottom: 12,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 16,
    borderBottomWidth: 1,
    borderBottomColor: colors.line,
    backgroundColor: colors.surface,
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
  backButton: {
    minHeight: 38,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surfaceRaised,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 7,
    paddingHorizontal: 11,
  },
  backText: {
    color: colors.graphite,
    fontSize: 13,
    lineHeight: 17,
    fontWeight: '900',
  },
  brandMark: {
    width: 38,
    height: 38,
    borderRadius: radii.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.blueDark,
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
    backgroundColor: colors.surfaceRaised,
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
    paddingTop: 12,
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
    ...shadow,
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
    backgroundColor: colors.surfaceRaised,
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
    paddingHorizontal: 14,
    paddingVertical: 13,
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
    backgroundColor: colors.blueSoft,
    borderColor: '#c4dde2',
  },
  statusDone: {
    backgroundColor: colors.greenSoft,
    borderColor: '#c5ddcb',
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
    paddingTop: 14,
    paddingBottom: 32,
    gap: 16,
  },
  dashboardScreen: {
    width: '100%',
    alignSelf: 'center',
    paddingHorizontal: 22,
    paddingTop: 14,
    paddingBottom: 34,
  },
  dashboardBand: {
    width: '100%',
    maxWidth: 1180,
    alignSelf: 'center',
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surface,
    padding: 16,
    gap: 14,
  },
  dashboardHeader: {
    minHeight: 48,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 14,
  },
  dashboardHeaderCompact: {
    alignItems: 'stretch',
    flexDirection: 'column',
  },
  dashboardToolbar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    flexWrap: 'wrap',
  },
  dashboardToolbarCompact: {
    alignItems: 'stretch',
  },
  searchBox: {
    minHeight: 42,
    minWidth: 240,
    flexGrow: 1,
    flexBasis: 280,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surfaceRaised,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 12,
  },
  searchInput: {
    flex: 1,
    minHeight: 40,
    color: colors.ink,
    fontSize: 13,
    lineHeight: 17,
    fontWeight: '700',
  },
  segmentGroup: {
    minHeight: 42,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surfaceRaised,
    padding: 3,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 3,
  },
  segmentChip: {
    minHeight: 34,
    borderRadius: radii.sm,
    justifyContent: 'center',
    paddingHorizontal: 10,
  },
  segmentChipActive: {
    backgroundColor: colors.blue,
  },
  segmentText: {
    color: colors.graphite,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '900',
  },
  segmentTextActive: {
    color: colors.white,
  },
  dashboardNotice: {
    minHeight: 40,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: '#c4dde2',
    backgroundColor: colors.blueSoft,
    paddingHorizontal: 12,
    paddingVertical: 9,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  dashboardNoticeText: {
    flex: 1,
    color: colors.blueDark,
    fontSize: 12,
    lineHeight: 17,
    fontWeight: '800',
  },
  projectList: {
    gap: 8,
  },
  projectSkeletonRow: {
    minHeight: 74,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surfaceRaised,
    padding: 14,
    gap: 10,
  },
  skeletonTitle: {
    width: '42%',
    height: 14,
    borderRadius: radii.sm,
    backgroundColor: colors.mist,
  },
  skeletonMeta: {
    width: '68%',
    height: 12,
    borderRadius: radii.sm,
    backgroundColor: colors.mist,
  },
  dashboardEmpty: {
    minHeight: 146,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surfaceRaised,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    padding: 18,
  },
  dashboardProjectRow: {
    minHeight: 76,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surfaceRaised,
    paddingHorizontal: 12,
    paddingVertical: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  dashboardProjectRowCompact: {
    alignItems: 'stretch',
    flexDirection: 'column',
  },
  dashboardProjectMain: {
    flex: 1.2,
    minWidth: 220,
  },
  projectOpenTarget: {
    minHeight: 48,
    justifyContent: 'center',
    gap: 3,
  },
  dashboardProjectTitle: {
    color: colors.ink,
    fontSize: 15,
    lineHeight: 20,
    fontWeight: '900',
  },
  dashboardProjectSubtitle: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '700',
  },
  renameRow: {
    minHeight: 48,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  renameInput: {
    flex: 1,
    minHeight: 42,
  },
  projectFacts: {
    flex: 1,
    minWidth: 260,
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 7,
  },
  projectFact: {
    minHeight: 26,
    borderRadius: radii.round,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surface,
    paddingHorizontal: 9,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  projectFactText: {
    color: colors.graphite,
    fontSize: 11,
    lineHeight: 14,
    fontWeight: '800',
  },
  projectActions: {
    minWidth: 196,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: 6,
  },
  projectActionButton: {
    width: 34,
    height: 34,
    borderRadius: radii.md,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surface,
  },
  projectActionDanger: {
    borderColor: '#ebc2ba',
    backgroundColor: colors.redSoft,
  },
  projectActionDisabled: {
    opacity: 0.48,
  },
  deleteConfirmRow: {
    minWidth: 260,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    flexWrap: 'wrap',
    gap: 8,
  },
  deleteConfirmText: {
    color: colors.red,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '900',
  },
  confirmButton: {
    minHeight: 34,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 10,
  },
  confirmButtonDanger: {
    minWidth: 72,
    borderColor: colors.red,
    backgroundColor: colors.red,
  },
  confirmButtonText: {
    color: colors.graphite,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '900',
  },
  confirmButtonTextDanger: {
    color: colors.white,
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
    backgroundColor: colors.surfaceRaised,
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
  sectionTitle: {
    color: colors.ink,
    fontSize: 16,
    lineHeight: 21,
    fontWeight: '900',
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
  },
  sectionHeaderIcon: {
    width: 32,
    height: 32,
    borderRadius: radii.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.blueSoft,
    borderWidth: 1,
    borderColor: '#c4dde2',
  },
  sectionHeaderCopy: {
    flex: 1,
  },
  sectionMeta: {
    marginTop: 1,
    color: colors.subtle,
    fontSize: 11,
    lineHeight: 15,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0,
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
    backgroundColor: colors.surfaceRaised,
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
    backgroundColor: colors.blueSoft,
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
    backgroundColor: colors.surfaceRaised,
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
    gap: 7,
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
  tagRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  tag: {
    minHeight: 26,
    borderRadius: radii.round,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surfaceRaised,
    paddingHorizontal: 9,
    justifyContent: 'center',
  },
  tagInfo: {
    borderColor: '#c4dde2',
    backgroundColor: colors.blueSoft,
  },
  tagSuccess: {
    borderColor: '#c5ddcb',
    backgroundColor: colors.greenSoft,
  },
  tagWarning: {
    borderColor: '#ead4b5',
    backgroundColor: colors.amberSoft,
  },
  tagText: {
    color: colors.graphite,
    fontSize: 11,
    lineHeight: 14,
    fontWeight: '800',
  },
  tagTextInfo: {
    color: colors.blueDark,
  },
  tagTextSuccess: {
    color: colors.green,
  },
  tagTextWarning: {
    color: colors.amber,
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
  projectRow: {
    minHeight: 52,
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
  projectRowActive: {
    borderColor: colors.blue,
    backgroundColor: colors.blueSoft,
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
    backgroundColor: colors.surfaceRaised,
    paddingHorizontal: 10,
    paddingVertical: 8,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
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
  planSide: {
    gap: 16,
  },
  planSideDesktop: {
    width: 380,
    flexShrink: 0,
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
    borderColor: '#ebc2ba',
    backgroundColor: colors.redSoft,
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
});
