import { Ionicons } from '@expo/vector-icons';
import { CameraView, useCameraPermissions, useMicrophonePermissions } from 'expo-camera';
import * as DocumentPicker from 'expo-document-picker';
import { useVideoPlayer, VideoView } from 'expo-video';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
  View,
} from 'react-native';

import {
  createSession,
  getSession,
  mediaUrl,
  normalizeBaseUrl,
  sendPreflightFrame,
  startAnalysis,
  uploadClip,
} from './src/api';
import { colors, radii, shadow } from './src/theme';
import type { TrendPhase, TrendScreen, TrendSession } from './src/types';

const DEFAULT_API_URL = Platform.OS === 'android' ? 'http://10.0.2.2:8010' : 'http://localhost:8010';

const busyPhases: TrendPhase[] = ['analyzing', 'uploading', 'rendering_ready', 'rendering', 'evaluating'];
const studioPhases: TrendPhase[] = ['ready_to_film', 'needs_adjustment', 'ready_to_record'];

function formatValue(value?: string | string[] | number | null): string {
  if (Array.isArray(value)) return value.join(', ');
  if (value === undefined || value === null || value === '') return 'Pending';
  return String(value);
}

function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

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

function PhaseRail({ screen, phase }: { screen: TrendScreen; phase: TrendPhase }) {
  const steps: { key: TrendScreen; label: string; icon: keyof typeof Ionicons.glyphMap }[] = [
    { key: 'analyze', label: 'Analyze', icon: 'link-outline' },
    { key: 'studio', label: 'Film', icon: 'videocam-outline' },
    { key: 'output', label: 'Finish', icon: 'checkmark-circle-outline' },
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

function StatusStrip({ session }: { session: TrendSession }) {
  const toneStyle =
    session.phase === 'error'
      ? styles.statusError
      : session.phase === 'complete'
        ? styles.statusDone
        : session.phase === 'needs_adjustment'
          ? styles.statusWarn
          : styles.statusInfo;

  return (
    <View style={[styles.statusStrip, toneStyle]}>
      <Text style={styles.statusLabel}>{session.progress_label}</Text>
      <Text style={styles.statusAction}>{session.error || session.next_action}</Text>
    </View>
  );
}

function AppShell({
  session,
  apiUrl,
  apiDraft,
  setApiDraft,
  onReconnect,
  children,
}: {
  session: TrendSession | null;
  apiUrl: string;
  apiDraft: string;
  setApiDraft: (value: string) => void;
  onReconnect: () => void;
  children: React.ReactNode;
}) {
  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar barStyle="dark-content" />
      <KeyboardAvoidingView style={styles.root} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={styles.header}>
          <View>
            <Text style={styles.brand}>TrendFlow</Text>
            <Text style={styles.brandSub}>AI Director</Text>
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
        </View>
        {session ? <PhaseRail screen={session.screen} phase={session.phase} /> : null}
        {session ? <StatusStrip session={session} /> : null}
        {children}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function AnalyzeScreen({
  session,
  onAnalyze,
}: {
  session: TrendSession;
  onAnalyze: (url: string) => void;
}) {
  const [url, setUrl] = useState('');
  const isBusy = session.phase === 'analyzing';

  return (
    <ScrollView contentContainerStyle={styles.screen}>
      <View style={styles.panel}>
        <Text style={styles.title}>Reference trend</Text>
        <TextInput
          value={url}
          onChangeText={setUrl}
          editable={!isBusy}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          placeholder="https://www.tiktok.com/@user/video/..."
          placeholderTextColor={colors.muted}
          style={styles.urlInput}
        />
        <PrimaryButton
          icon={isBusy ? 'hourglass-outline' : 'sparkles-outline'}
          label={isBusy ? 'Analyzing' : 'Analyze Trend'}
          onPress={() => onAnalyze(url)}
          disabled={isBusy || url.trim().length < 6}
        />
      </View>

      {isBusy ? (
        <View style={styles.waitPanel}>
          <ActivityIndicator color={colors.blue} />
          <Text style={styles.waitText}>Extracting beats, cuts, motion, pose, and style.</Text>
        </View>
      ) : null}
    </ScrollView>
  );
}

function FieldRow({ label, value }: { label: string; value?: string | string[] | number | null }) {
  return (
    <View style={styles.fieldRow}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <Text style={styles.fieldValue}>{formatValue(value)}</Text>
    </View>
  );
}

function StudioScreen({
  apiUrl,
  session,
  setSession,
  setError,
}: {
  apiUrl: string;
  session: TrendSession;
  setSession: (session: TrendSession) => void;
  setError: (message: string | null) => void;
}) {
  const cameraRef = useRef<any>(null);
  const preflightBusyRef = useRef(false);
  const recordingKeysRef = useRef(new Set<string>());
  const [cameraPermission, requestCameraPermission] = useCameraPermissions();
  const [micPermission, requestMicPermission] = useMicrophonePermissions();
  const [cameraReady, setCameraReady] = useState(false);
  const [facing, setFacing] = useState<'front' | 'back'>('front');
  const [cameraMode, setCameraMode] = useState<'picture' | 'video'>('picture');
  const [countdown, setCountdown] = useState<number | null>(null);
  const [recording, setRecording] = useState(false);
  const [localStatus, setLocalStatus] = useState<string | null>(null);

  const permissionsGranted = Boolean(cameraPermission?.granted && micPermission?.granted);
  const canGuide = studioPhases.includes(session.phase) && session.phase !== 'ready_to_record';

  const requestPermissions = useCallback(async () => {
    await requestCameraPermission();
    await requestMicPermission();
  }, [requestCameraPermission, requestMicPermission]);

  const runPreflight = useCallback(async () => {
    if (!cameraRef.current || preflightBusyRef.current || recording || countdown !== null || cameraMode !== 'picture') {
      return;
    }
    preflightBusyRef.current = true;
    try {
      setLocalStatus('Checking frame');
      const picture = await cameraRef.current.takePictureAsync({
        base64: true,
        quality: 0.36,
        skipProcessing: true,
      });
      if (picture?.base64) {
        const updated = await sendPreflightFrame(apiUrl, session.id, picture.base64);
        setSession(updated);
      }
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Pre-flight failed');
    } finally {
      preflightBusyRef.current = false;
      setLocalStatus(null);
    }
  }, [apiUrl, cameraMode, countdown, recording, session.id, setError, setSession]);

  const startAutoRecord = useCallback(async () => {
    const key = `${session.id}:${session.current_shot_idx}`;
    if (recordingKeysRef.current.has(key) || !cameraRef.current) return;
    recordingKeysRef.current.add(key);
    try {
      setCameraMode('video');
      await delay(450);
      for (let value = 3; value > 0; value -= 1) {
        setCountdown(value);
        await delay(850);
      }
      setCountdown(null);
      setRecording(true);
      setLocalStatus(`Recording shot ${session.current_shot_idx + 1}`);
      const result = await cameraRef.current.recordAsync({
        maxDuration: Math.max(1, Math.ceil(session.current_shot_duration)),
      });
      if (!result?.uri) {
        throw new Error('Camera did not return a recorded clip.');
      }
      setLocalStatus('Uploading clip');
      const updated = await uploadClip(apiUrl, session.id, result.uri, { fullTake: false });
      setSession(updated);
    } catch (error) {
      recordingKeysRef.current.delete(key);
      setError(error instanceof Error ? error.message : 'Recording failed');
    } finally {
      setRecording(false);
      setCountdown(null);
      setCameraMode('picture');
      setLocalStatus(null);
    }
  }, [apiUrl, session.current_shot_duration, session.current_shot_idx, session.id, setError, setSession]);

  const pickFullTake = useCallback(async () => {
    const result = await DocumentPicker.getDocumentAsync({
      type: 'video/*',
      copyToCacheDirectory: true,
      multiple: false,
    });
    if (result.canceled || !result.assets?.[0]) return;
    try {
      setLocalStatus('Uploading full take');
      const updated = await uploadClip(apiUrl, session.id, result.assets[0].uri, { fullTake: true });
      setSession(updated);
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Upload failed');
    } finally {
      setLocalStatus(null);
    }
  }, [apiUrl, session.id, setError, setSession]);

  useEffect(() => {
    if (!permissionsGranted || !cameraReady || !canGuide || recording || countdown !== null) return;
    runPreflight();
    const timer = setInterval(runPreflight, 3600);
    return () => clearInterval(timer);
  }, [canGuide, cameraReady, countdown, permissionsGranted, recording, runPreflight]);

  useEffect(() => {
    if (session.phase === 'ready_to_record' && permissionsGranted && cameraReady && !recording) {
      startAutoRecord();
    }
  }, [cameraReady, permissionsGranted, recording, session.phase, startAutoRecord]);

  if (!permissionsGranted) {
    return (
      <View style={styles.screen}>
        <View style={styles.panel}>
          <Text style={styles.title}>Studio access</Text>
          <PrimaryButton icon="camera-outline" label="Enable Camera + Mic" onPress={requestPermissions} />
        </View>
      </View>
    );
  }

  return (
    <View style={styles.studioRoot}>
      <CameraView
        ref={cameraRef}
        style={styles.camera}
        facing={facing}
        mode={cameraMode}
        mirror={facing === 'front'}
        mute={false}
        videoQuality="720p"
        onCameraReady={() => setCameraReady(true)}
      />
      <View style={styles.cameraTopBar}>
        <View>
          <Text style={styles.cameraMeta}>
            Shot {Math.min(session.current_shot_idx + 1, session.required_shots)} / {session.required_shots || 1}
          </Text>
          <Text style={styles.cameraTitle}>{localStatus || session.progress_label}</Text>
        </View>
        <Pressable onPress={() => setFacing((current) => (current === 'front' ? 'back' : 'front'))} style={styles.roundIconButton}>
          <Ionicons name="camera-reverse-outline" size={20} color={colors.white} />
        </Pressable>
      </View>

      {countdown !== null ? (
        <View style={styles.countdownBadge}>
          <Text style={styles.countdownText}>{countdown}</Text>
        </View>
      ) : null}

      <View style={styles.directorPanel}>
        {localStatus === 'Checking frame' ? <ActivityIndicator color={colors.white} /> : null}
        <Text style={styles.directorLabel}>{session.director_feedback || 'Aligning frame'}</Text>
        {session.feedback.slice(0, 3).map((item) => (
          <Text key={item} style={styles.directorHint}>
            {item}
          </Text>
        ))}
        <View style={styles.cameraActions}>
          <PrimaryButton icon="cloud-upload-outline" label="Full Take" onPress={pickFullTake} tone="light" disabled={recording} />
        </View>
      </View>
    </View>
  );
}

function OutputVideo({ source }: { source: string }) {
  const player = useVideoPlayer(source, (instance) => {
    instance.loop = false;
  });

  return <VideoView player={player} style={styles.video} allowsFullscreen contentFit="contain" />;
}

function OutputScreen({ apiUrl, session }: { apiUrl: string; session: TrendSession }) {
  const finalUrl = mediaUrl(apiUrl, session.final_video_url);
  const waiting = session.phase === 'rendering' || session.phase === 'evaluating' || session.phase === 'rendering_ready';

  return (
    <ScrollView contentContainerStyle={styles.screen}>
      <View style={styles.panel}>
        <Text style={styles.title}>Final cut</Text>
        {waiting ? (
          <View style={styles.waitPanelCompact}>
            <ActivityIndicator color={colors.blue} />
            <Text style={styles.waitText}>{session.progress_label}</Text>
          </View>
        ) : null}
        {finalUrl ? <OutputVideo source={finalUrl} /> : null}
      </View>

      {session.evaluation ? (
        <View style={styles.panel}>
          <Text style={styles.sectionTitle}>AI Judge</Text>
          <Text style={styles.evaluation}>{session.evaluation}</Text>
        </View>
      ) : null}
    </ScrollView>
  );
}

function SummaryDrawer({ session }: { session: TrendSession }) {
  if (!session.style && !session.context_summary) return null;
  return (
    <View style={styles.summary}>
      <FieldRow label="Shots" value={session.context_summary?.shots ?? session.required_shots} />
      <FieldRow label="BPM" value={session.context_summary?.bpm ? Math.round(session.context_summary.bpm) : null} />
      <FieldRow label="Wear" value={session.style?.clothing} />
      <FieldRow label="Place" value={session.style?.setting} />
      <FieldRow label="Frame" value={session.style?.camera_angle} />
    </View>
  );
}

export default function App() {
  const [apiDraft, setApiDraft] = useState(DEFAULT_API_URL);
  const [apiUrl, setApiUrl] = useState(DEFAULT_API_URL);
  const [session, setSession] = useState<TrendSession | null>(null);
  const [error, setError] = useState<string | null>(null);

  const connect = useCallback(async () => {
    const nextUrl = normalizeBaseUrl(apiDraft);
    try {
      setError(null);
      setApiUrl(nextUrl);
      const created = await createSession(nextUrl);
      setSession(created);
    } catch (connectError) {
      setSession(null);
      setError(connectError instanceof Error ? connectError.message : 'Could not reach TrendFlow API');
    }
  }, [apiDraft]);

  useEffect(() => {
    connect();
  }, []);

  useEffect(() => {
    if (!session) return;
    const intervalMs = busyPhases.includes(session.phase) ? 1800 : 4200;
    const timer = setInterval(async () => {
      try {
        const updated = await getSession(apiUrl, session.id);
        setSession(updated);
      } catch (pollError) {
        setError(pollError instanceof Error ? pollError.message : 'Lost server connection');
      }
    }, intervalMs);
    return () => clearInterval(timer);
  }, [apiUrl, session?.id, session?.phase]);

  const onAnalyze = useCallback(
    async (url: string) => {
      if (!session) return;
      try {
        setError(null);
        const updated = await startAnalysis(apiUrl, session.id, url.trim());
        setSession(updated);
      } catch (analyzeError) {
        setError(analyzeError instanceof Error ? analyzeError.message : 'Analysis failed');
      }
    },
    [apiUrl, session]
  );

  const content = useMemo(() => {
    if (!session) {
      return (
        <View style={styles.screen}>
          <View style={styles.panel}>
            <Text style={styles.title}>Connect server</Text>
            <Text style={styles.muted}>{error || 'TrendFlow API is not connected.'}</Text>
            <PrimaryButton icon="sync" label="Reconnect" onPress={connect} />
          </View>
        </View>
      );
    }
    if (session.screen === 'studio') {
      return <StudioScreen apiUrl={apiUrl} session={session} setSession={setSession} setError={setError} />;
    }
    if (session.screen === 'output') {
      return <OutputScreen apiUrl={apiUrl} session={session} />;
    }
    return <AnalyzeScreen session={session} onAnalyze={onAnalyze} />;
  }, [apiUrl, connect, error, onAnalyze, session]);

  return (
    <AppShell
      session={session}
      apiUrl={apiUrl}
      apiDraft={apiDraft}
      setApiDraft={setApiDraft}
      onReconnect={connect}
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
    paddingHorizontal: 18,
    paddingTop: 12,
    paddingBottom: 10,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
  },
  brand: {
    color: colors.ink,
    fontSize: 24,
    lineHeight: 29,
    fontWeight: '800',
  },
  brandSub: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '700',
  },
  serverBox: {
    flex: 1,
    maxWidth: 220,
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radii.md,
    backgroundColor: colors.white,
  },
  serverInput: {
    flex: 1,
    height: 36,
    paddingHorizontal: 10,
    color: colors.ink,
    fontSize: 12,
    fontWeight: '600',
  },
  serverButton: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  phaseRail: {
    marginHorizontal: 18,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 8,
  },
  phaseItem: {
    flex: 1,
    alignItems: 'center',
    gap: 5,
  },
  phaseIcon: {
    width: 28,
    height: 28,
    borderRadius: radii.round,
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
    marginHorizontal: 18,
    marginBottom: 10,
    borderRadius: radii.md,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderWidth: 1,
  },
  statusInfo: {
    backgroundColor: '#eef4ff',
    borderColor: '#c9dafd',
  },
  statusWarn: {
    backgroundColor: '#fff7ed',
    borderColor: '#fed7aa',
  },
  statusDone: {
    backgroundColor: '#ecfdf3',
    borderColor: '#bbf7d0',
  },
  statusError: {
    backgroundColor: '#fff1f2',
    borderColor: '#fecdd3',
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
  screen: {
    padding: 18,
    gap: 14,
  },
  panel: {
    backgroundColor: colors.white,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    padding: 14,
    gap: 12,
    ...shadow,
  },
  title: {
    color: colors.ink,
    fontSize: 20,
    lineHeight: 25,
    fontWeight: '800',
  },
  sectionTitle: {
    color: colors.ink,
    fontSize: 15,
    lineHeight: 19,
    fontWeight: '800',
  },
  muted: {
    color: colors.muted,
    fontSize: 13,
    lineHeight: 18,
    fontWeight: '600',
  },
  urlInput: {
    minHeight: 48,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    paddingHorizontal: 12,
    color: colors.ink,
    fontSize: 14,
    fontWeight: '700',
    backgroundColor: colors.paper,
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
    fontWeight: '800',
  },
  buttonTextLight: {
    color: colors.ink,
  },
  waitPanel: {
    backgroundColor: colors.white,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    padding: 18,
    alignItems: 'center',
    gap: 10,
  },
  waitPanelCompact: {
    minHeight: 86,
    borderRadius: radii.md,
    backgroundColor: colors.paper,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  waitText: {
    color: colors.muted,
    fontSize: 13,
    lineHeight: 18,
    fontWeight: '700',
    textAlign: 'center',
  },
  studioRoot: {
    flex: 1,
    backgroundColor: colors.camera,
  },
  camera: {
    ...StyleSheet.absoluteFillObject,
  },
  cameraTopBar: {
    position: 'absolute',
    top: 12,
    left: 14,
    right: 14,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: colors.cameraPanel,
    borderRadius: radii.md,
    padding: 10,
  },
  cameraMeta: {
    color: '#a8b3c7',
    fontSize: 11,
    lineHeight: 15,
    fontWeight: '800',
  },
  cameraTitle: {
    color: colors.white,
    fontSize: 16,
    lineHeight: 21,
    fontWeight: '800',
  },
  roundIconButton: {
    width: 42,
    height: 42,
    borderRadius: radii.round,
    backgroundColor: 'rgba(255,255,255,0.14)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  countdownBadge: {
    position: 'absolute',
    alignSelf: 'center',
    top: '37%',
    width: 116,
    height: 116,
    borderRadius: radii.round,
    backgroundColor: 'rgba(35,100,232,0.86)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  countdownText: {
    color: colors.white,
    fontSize: 62,
    lineHeight: 72,
    fontWeight: '900',
  },
  directorPanel: {
    position: 'absolute',
    left: 14,
    right: 14,
    bottom: 14,
    backgroundColor: colors.cameraPanel,
    borderRadius: radii.md,
    padding: 12,
    gap: 7,
  },
  directorLabel: {
    color: colors.white,
    fontSize: 18,
    lineHeight: 23,
    fontWeight: '900',
  },
  directorHint: {
    color: '#d7deea',
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '700',
  },
  cameraActions: {
    marginTop: 8,
    flexDirection: 'row',
  },
  fieldRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 12,
    paddingVertical: 6,
    borderBottomWidth: 1,
    borderBottomColor: '#e8ebf1',
  },
  fieldLabel: {
    width: 68,
    color: colors.muted,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '800',
  },
  fieldValue: {
    flex: 1,
    color: colors.ink,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '700',
    textAlign: 'right',
  },
  summary: {
    position: 'absolute',
    left: 18,
    right: 18,
    bottom: 18,
    backgroundColor: colors.white,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.line,
    paddingHorizontal: 12,
    paddingVertical: 6,
    maxHeight: 190,
  },
  video: {
    width: '100%',
    aspectRatio: 9 / 16,
    borderRadius: radii.md,
    backgroundColor: colors.camera,
  },
  evaluation: {
    color: colors.graphite,
    fontSize: 13,
    lineHeight: 19,
    fontWeight: '600',
  },
  inlineError: {
    marginHorizontal: 18,
    marginBottom: 8,
    borderRadius: radii.md,
    backgroundColor: '#fff1f2',
    borderWidth: 1,
    borderColor: '#fecdd3',
    paddingHorizontal: 10,
    paddingVertical: 8,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
  },
  inlineErrorText: {
    flex: 1,
    color: colors.red,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '700',
  },
});
