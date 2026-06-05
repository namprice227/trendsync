import { Ionicons } from '@expo/vector-icons';
import * as DocumentPicker from 'expo-document-picker';
import React, { useCallback, useEffect, useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  SafeAreaView,
  StatusBar,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import {
  absoluteUrl,
  approveCreativeBrief,
  createSession,
  deleteSession,
  draftCreativeBrief,
  duplicateSession,
  generateStory,
  getSession,
  listSessions,
  normalizeBaseUrl,
  renderTripVideo,
  saveTripContext,
  shareSession,
  updateCreativeBrief,
  updateTimelineSegments,
  updateProjectMetadata,
  updateVoiceoverSegments,
  uploadMedia,
} from './src/api';
import { colors, radii, layout } from './src/theme';
import type { ProjectSummary, RenderOptions, TimelineSegmentUpdate, TripContext, TripSession, AppView, UploadProgress } from './src/types';
import { PrimaryButton } from './src/components/PrimaryButton';
import { DashboardScreen } from './src/screens/DashboardScreen';
import { EditorScreen } from './src/screens/EditorScreen';
import { busyPhases, planningPhases, sessionTitle } from './src/utils/helpers';

declare const process: { env?: Record<string, string | undefined> };

function defaultApiUrl(): string {
  const configuredDefaultApiUrl = typeof process !== 'undefined' ? process.env?.EXPO_PUBLIC_API_URL?.trim() : '';
  if (configuredDefaultApiUrl) return configuredDefaultApiUrl;

  if (Platform.OS === 'web') {
    const loc = typeof globalThis !== 'undefined' ? (globalThis as { location?: { hostname?: string; protocol?: string } }).location : undefined;
    const host = loc?.hostname || '';
    const protocol = loc?.protocol || 'http:';

    if (host === 'mangasmith.com' || host === 'www.mangasmith.com') {
      return 'https://api.mangasmith.com';
    }
    if (host.endsWith('.mangasmith.com')) {
      return `https://api.${host.replace(/^www\./, '')}`;
    }
    // For any other host (localhost, IP, custom domain), point to the same host on port 8010
    if (host) {
      return `${protocol}//${host}:8010`;
    }
  }

  return Platform.OS === 'android' ? 'http://10.0.2.2:8010' : 'http://localhost:8010';
}

const DEFAULT_API_URL = defaultApiUrl();

// --- Slim top bar for the editor view ---
function EditorTopBar({
  session,
  apiUrl,
  apiDraft,
  setApiDraft,
  onReconnect,
  onRestart,
  creatingProject,
  onBackToDashboard,
}: {
  session: TripSession;
  apiUrl: string;
  apiDraft: string;
  setApiDraft: (value: string) => void;
  onReconnect: () => void;
  onRestart: () => void;
  creatingProject: boolean;
  onBackToDashboard: () => void;
}) {
  return (
    <View style={styles.editorTopBar}>
      {/* Left: back + brand */}
      <View style={styles.topBarLeft}>
        <Pressable onPress={onBackToDashboard} style={styles.backButton}>
          <Ionicons name="chevron-back" size={16} color={colors.graphite} />
        </Pressable>
        <View style={styles.brandMark}>
          <Ionicons name="film-outline" size={14} color={colors.white} />
        </View>
        <Text style={styles.topBarTitle} numberOfLines={1}>{sessionTitle(session)}</Text>
      </View>

      {/* Center: API URL (compact) */}
      <View style={styles.topBarCenter}>
        <TextInput
          value={apiDraft}
          onChangeText={setApiDraft}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          style={styles.serverInputCompact}
          placeholder={apiUrl}
          placeholderTextColor={colors.subtle}
        />
        <Pressable onPress={onReconnect} style={styles.serverSync}>
          <Ionicons name="sync" size={13} color={colors.blue} />
        </Pressable>
      </View>

      {/* Right: actions */}
      <View style={styles.topBarRight}>
        <Pressable onPress={onRestart} disabled={creatingProject} style={[styles.newProjectBtn, creatingProject && styles.btnDisabled]}>
          <Ionicons name={creatingProject ? 'hourglass-outline' : 'add'} size={15} color={colors.blue} />
        </Pressable>
      </View>
    </View>
  );
}

// --- Dashboard top bar ---
function DashboardTopBar({
  apiUrl,
  apiDraft,
  setApiDraft,
  onReconnect,
  onRestart,
  creatingProject,
}: {
  apiUrl: string;
  apiDraft: string;
  setApiDraft: (value: string) => void;
  onReconnect: () => void;
  onRestart: () => void;
  creatingProject: boolean;
}) {
  return (
    <View style={styles.dashboardTopBar}>
      <View style={styles.brandLockup}>
        <View style={styles.brandMarkLg}>
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

      <Pressable onPress={onRestart} disabled={creatingProject} style={[styles.restartButton, creatingProject && styles.btnDisabled]}>
        <Ionicons name={creatingProject ? 'hourglass-outline' : 'add-circle-outline'} size={17} color={colors.white} />
        <Text style={styles.restartText}>{creatingProject ? 'Creating' : 'New project'}</Text>
      </Pressable>
    </View>
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
  const [uploadProgress, setUploadProgress] = useState<UploadProgress | null>(null);

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
        return absoluteUrl(apiUrl, shared.share_url);
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
    if (!session || uploadProgress) return;
    const result = await DocumentPicker.getDocumentAsync({
      type: 'video/*',
      copyToCacheDirectory: true,
      multiple: true,
    });
    if (result.canceled || !result.assets?.length) return;
    const fileCount = result.assets.length;
    try {
      setError(null);
      setUploadProgress({
        phase: 'uploading',
        fileCount,
        loadedBytes: 0,
        totalBytes: null,
        percent: 0,
      });
      const updated = await uploadMedia(apiUrl, session.id, result.assets, (progress) => {
        setUploadProgress({
          phase: progress.percent !== null && progress.percent >= 100 ? 'processing' : 'uploading',
          fileCount,
          loadedBytes: progress.loadedBytes,
          totalBytes: progress.totalBytes,
          percent: progress.percent,
        });
      });
      setSession(updated);
      await refreshProjects(apiUrl);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : 'Upload failed');
    } finally {
      setUploadProgress(null);
    }
  }, [apiUrl, refreshProjects, session, uploadProgress]);

  const onDraftCreativeBrief = useCallback(async (context: TripContext) => {
    if (!session || planningPhases.includes(session.phase)) return;
    try {
      setError(null);
      const saved = await saveTripContext(apiUrl, session.id, context);
      setSession(saved);
      const updated = await draftCreativeBrief(apiUrl, saved.id);
      setSession(updated);
      await refreshProjects(apiUrl);
    } catch (briefError) {
      setError(briefError instanceof Error ? briefError.message : 'Could not draft producer brief');
      throw briefError;
    }
  }, [apiUrl, refreshProjects, session]);

  const onUpdateCreativeBrief = useCallback(async (patch: { selected_direction_id?: string | null; answers?: Array<{ question_id: string; answer: string }>; notes?: string | null }) => {
    if (!session) return;
    try {
      setError(null);
      const updated = await updateCreativeBrief(apiUrl, session.id, patch);
      setSession(updated);
      await refreshProjects(apiUrl);
    } catch (briefError) {
      setError(briefError instanceof Error ? briefError.message : 'Could not save producer brief');
      throw briefError;
    }
  }, [apiUrl, refreshProjects, session]);

  const onApproveCreativeBrief = useCallback(async (patch: { selected_direction_id?: string | null; answers?: Array<{ question_id: string; answer: string }>; notes?: string | null }) => {
    if (!session) return;
    try {
      setError(null);
      const updated = await approveCreativeBrief(apiUrl, session.id, patch);
      setSession(updated);
      await refreshProjects(apiUrl);
    } catch (briefError) {
      setError(briefError instanceof Error ? briefError.message : 'Could not approve producer brief');
      throw briefError;
    }
  }, [apiUrl, refreshProjects, session]);

  const onGenerate = useCallback(async (options?: RenderOptions) => {
    if (!session || planningPhases.includes(session.phase)) return;
    try {
      setError(null);
      const updated = await generateStory(apiUrl, session.id, options);
      setSession(updated);
    } catch (generateError) {
      setError(generateError instanceof Error ? generateError.message : 'Story generation failed');
    }
  }, [apiUrl, session]);

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

  const onSaveTimelineSegments = useCallback(async (segments: TimelineSegmentUpdate[], segmentOrder: string[]) => {
    if (!session) return;
    try {
      setError(null);
      const updated = await updateTimelineSegments(apiUrl, session.id, segments, segmentOrder);
      setSession(updated);
      await refreshProjects(apiUrl);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Could not save timeline edits');
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

  // --- Render ---

  // Dashboard view
  if (view === 'dashboard') {
    return (
      <SafeAreaView style={styles.safe}>
        <StatusBar barStyle="light-content" />
        <KeyboardAvoidingView style={styles.root} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <DashboardTopBar
            apiUrl={apiUrl}
            apiDraft={apiDraft}
            setApiDraft={setApiDraft}
            onReconnect={connect}
            onRestart={onNewProject}
            creatingProject={creatingProject}
          />
          {error ? (
            <View style={styles.inlineError}>
              <Ionicons name="warning-outline" size={16} color={colors.red} />
              <Text style={styles.inlineErrorText}>{error}</Text>
            </View>
          ) : null}
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
        </KeyboardAvoidingView>
      </SafeAreaView>
    );
  }

  // No session fallback
  if (!session) {
    return (
      <SafeAreaView style={styles.safe}>
        <StatusBar barStyle="light-content" />
        <View style={styles.connectScreen}>
          <Text style={styles.connectTitle}>Connect server</Text>
          <Text style={styles.connectMuted}>{error || 'TripStory API is not connected.'}</Text>
          <PrimaryButton icon="sync" label="Reconnect" onPress={connect} />
        </View>
      </SafeAreaView>
    );
  }

  // Editor view
  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar barStyle="light-content" />
      <KeyboardAvoidingView style={styles.root} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <EditorTopBar
          session={session}
          apiUrl={apiUrl}
          apiDraft={apiDraft}
          setApiDraft={setApiDraft}
          onReconnect={connect}
          onRestart={onNewProject}
          creatingProject={creatingProject}
          onBackToDashboard={onBackToDashboard}
        />
        {error && session.phase !== 'error' ? (
          <View style={styles.inlineError}>
            <Ionicons name="warning-outline" size={16} color={colors.red} />
            <Text style={styles.inlineErrorText}>{error}</Text>
          </View>
        ) : null}
        <EditorScreen
          apiUrl={apiUrl}
          session={session}
          uploadProgress={uploadProgress}
          onSaveContext={onSaveContext}
          onUpload={onUpload}
          onDraftCreativeBrief={onDraftCreativeBrief}
          onUpdateCreativeBrief={onUpdateCreativeBrief}
          onApproveCreativeBrief={onApproveCreativeBrief}
          onGenerate={onGenerate}
          onRender={onRender}
          onSaveVoiceoverSegments={onSaveVoiceoverSegments}
          onSaveTimelineSegments={onSaveTimelineSegments}
          onShare={onShare}
        />
      </KeyboardAvoidingView>
    </SafeAreaView>
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

  // --- Editor top bar ---
  editorTopBar: {
    height: layout.topBarHeight,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    gap: 10,
    borderBottomWidth: 1,
    borderBottomColor: colors.line,
    backgroundColor: colors.surface,
  },
  topBarLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    minWidth: 180,
  },
  backButton: {
    width: 32,
    height: 32,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surfaceRaised,
    ...(Platform.OS === 'web' ? ({ cursor: 'pointer' } as any) : {}),
  },
  brandMark: {
    width: 28,
    height: 28,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.blueDark,
  },
  topBarTitle: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: '800',
    maxWidth: 200,
  },
  topBarCenter: {
    flex: 1,
    maxWidth: 300,
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surfaceRaised,
    height: 32,
  },
  serverInputCompact: {
    flex: 1,
    height: 30,
    paddingHorizontal: 10,
    color: colors.muted,
    fontSize: 11,
    fontWeight: '600',
  },
  serverSync: {
    width: 30,
    height: 30,
    alignItems: 'center',
    justifyContent: 'center',
  },
  topBarRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  newProjectBtn: {
    width: 32,
    height: 32,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surfaceRaised,
    borderWidth: 1,
    borderColor: colors.line,
    ...(Platform.OS === 'web' ? ({ cursor: 'pointer' } as any) : {}),
  },

  // --- Dashboard top bar ---
  dashboardTopBar: {
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
  brandLockup: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  brandMarkLg: {
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
  btnDisabled: {
    opacity: 0.48,
  },

  // --- Error ---
  inlineError: {
    marginHorizontal: 12,
    marginVertical: 6,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: 'rgba(239, 68, 68, 0.25)',
    backgroundColor: colors.redSoft,
    paddingHorizontal: 12,
    paddingVertical: 8,
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

  // --- Connect screen ---
  connectScreen: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 14,
    padding: 24,
  },
  connectTitle: {
    color: colors.ink,
    fontSize: 23,
    fontWeight: '900',
  },
  connectMuted: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: '600',
    textAlign: 'center',
  },
});
