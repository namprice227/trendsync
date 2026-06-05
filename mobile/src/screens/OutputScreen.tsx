import React from 'react';
import { View, Text, StyleSheet, Pressable, TextInput, ActivityIndicator, ScrollView, KeyboardAvoidingView, Platform, SafeAreaView, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii, shadow } from '../theme';
import type { TripScreen, TripPhase, TripSession, ClipAnalysis, TripContext, RenderOptions, ProjectSummary } from '../types';
import { absoluteUrl, mediaUrl } from '../api';
import { VideoView, useVideoPlayer } from 'expo-video';
import { defaultRenderOptions } from "../utils/helpers";
import { PrimaryButton } from "../components/PrimaryButton";

export function OutputScreen({
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
  const { width } = useWindowDimensions();
  const finalUrl = mediaUrl(apiUrl, session.final_video_url);
  const voiceoverUrl = mediaUrl(apiUrl, session.voiceover_audio_url);
  const captionUrl = mediaUrl(apiUrl, session.caption_vtt_url || session.caption_srt_url);
  const waiting = session.phase === 'rendering';
  const desktop = width >= 920;

  return (
    <ScrollView contentContainerStyle={styles.screen}>
      <View style={[styles.outputLayout, desktop && styles.outputLayoutDesktop]}>
        <View style={[styles.panel, styles.mainPanel]}>
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
          <View style={[styles.panel, styles.sidePanel, desktop && styles.sidePanelDesktop]}>
            <Text style={styles.sectionTitle}>Voiceover script</Text>
            <Text style={styles.script}>{session.script}</Text>
          </View>
        ) : null}
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
  outputLayout: {
    gap: 16,
  },
  outputLayoutDesktop: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  mainPanel: {
    flex: 1,
    minWidth: 0,
  },
  sidePanel: {
    width: '100%',
    flexShrink: 0,
  },
  sidePanelDesktop: {
    width: 400,
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
  actionRow: {
    flexDirection: 'row',
    gap: 10,
    flexWrap: 'wrap',
  },
  sectionTitle: {
    color: colors.ink,
    fontSize: 16,
    lineHeight: 21,
    fontWeight: '900',
  },
  script: {
    color: colors.graphite,
    fontSize: 15,
    lineHeight: 23,
    fontWeight: '600',
  },
  video: {
    width: '100%',
    aspectRatio: 9 / 16,
    borderRadius: radii.md,
    backgroundColor: colors.camera,
    overflow: 'hidden',
  }
});

function OutputVideo({ source }: { source: string }) {
  const player = useVideoPlayer(source, (instance) => {
    instance.loop = false;
  });

  return <VideoView player={player} style={styles.video} allowsFullscreen contentFit="contain" />;
}
