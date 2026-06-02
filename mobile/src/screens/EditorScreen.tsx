import React, { useState, useEffect, useCallback } from 'react';
import { View, StyleSheet } from 'react-native';
import { colors } from '../theme';
import type {
  TripSession,
  TripContext,
  RenderOptions,
  SidebarTab,
  PropertiesTab,
} from '../types';
import { defaultRenderOptions, fallbackSegmentId, segmentForDecision } from '../utils/helpers';
import { mediaUrl } from '../api';
import { EditorLayout } from '../components/EditorLayout';
import { Sidebar } from '../components/Sidebar';
import { SidebarMediaTab } from '../components/SidebarMediaTab';
import { SidebarStoryTab } from '../components/SidebarStoryTab';
import { ClipIntelligence } from '../components/ClipIntelligence';
import { ProducerBriefPanel } from '../components/ProducerBriefPanel';
import { PreviewPanel } from '../components/PreviewPanel';
import { TimelineStrip } from '../components/TimelineStrip';
import { PropertiesPanel } from '../components/PropertiesPanel';
import { ActionBar } from '../components/ActionBar';

export function EditorScreen({
  apiUrl,
  session,
  onSaveContext,
  onUpload,
  onDraftCreativeBrief,
  onUpdateCreativeBrief,
  onApproveCreativeBrief,
  onGenerate,
  onRender,
  onSaveVoiceoverSegments,
  onShare,
}: {
  apiUrl: string;
  session: TripSession;
  onSaveContext: (context: TripContext) => void;
  onUpload: () => void;
  onDraftCreativeBrief: (context: TripContext) => Promise<void>;
  onUpdateCreativeBrief: (patch: { selected_direction_id?: string | null; answers?: Array<{ question_id: string; answer: string }>; notes?: string | null }) => Promise<void>;
  onApproveCreativeBrief: (patch: { selected_direction_id?: string | null; answers?: Array<{ question_id: string; answer: string }>; notes?: string | null }) => Promise<void>;
  onGenerate: () => void;
  onRender: (options: RenderOptions) => void;
  onSaveVoiceoverSegments: (segments: Array<{ segment_id: string; voiceover: string; caption?: string }>) => Promise<void>;
  onShare: () => void;
}) {
  // --- State ---
  const [sidebarTab, setSidebarTab] = useState<SidebarTab>('media');
  const [propertiesTab, setPropertiesTab] = useState<PropertiesTab>('context');
  const [context, setContext] = useState<TripContext>(session.trip_context);
  const [options, setOptions] = useState<RenderOptions>({
    ...defaultRenderOptions,
    ...(session.render_options || {}),
  });
  const [scriptDrafts, setScriptDrafts] = useState<Record<string, { voiceover: string; caption: string }>>({});
  const [savingScripts, setSavingScripts] = useState(false);

  // Sync context from session on session change
  useEffect(() => {
    setContext(session.trip_context);
  }, [session.id]);

  useEffect(() => {
    setOptions({ ...defaultRenderOptions, ...(session.render_options || {}) });
  }, [session.id]);

  // Sync script drafts
  const plan = session.story_plan;
  const editDecisions = Array.isArray(plan?.edit_decisions) ? plan.edit_decisions : [];
  const voiceoverSegments = Array.isArray(plan?.voiceover_segments) ? plan.voiceover_segments : [];

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

  // Auto-switch sidebar/properties based on phase
  useEffect(() => {
    if (session.screen === 'plan' || session.screen === 'output') {
      if (sidebarTab === 'media') setSidebarTab('story');
      if (propertiesTab === 'context') setPropertiesTab('export');
    }
  }, [session.screen]);

  // --- Handlers ---
  const handleContextChange = useCallback((key: keyof TripContext, value: string) => {
    setContext((current) => ({ ...current, [key]: value }));
  }, []);

  const handleScriptChange = useCallback((segmentId: string, field: 'voiceover' | 'caption', value: string) => {
    setScriptDrafts((current) => ({
      ...current,
      [segmentId]: {
        ...(current[segmentId] || { voiceover: '', caption: '' }),
        [field]: value,
      },
    }));
  }, []);

  const handleMoveClip = useCallback((clipId: string, direction: -1 | 1) => {
    setOptions((current) => {
      const base = current.clip_order.length ? [...current.clip_order] : session.media_items.map((item) => item.id);
      const index = base.indexOf(clipId);
      const nextIndex = index + direction;
      if (index < 0 || nextIndex < 0 || nextIndex >= base.length) return current;
      const next = [...base];
      [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
      return { ...current, clip_order: next };
    });
  }, [session.media_items]);

  const handleToggleFavorite = useCallback((clipId: string) => {
    setOptions((current) => {
      const favorites = new Set(current.favorite_clip_ids || []);
      if (favorites.has(clipId)) {
        favorites.delete(clipId);
      } else {
        favorites.add(clipId);
      }
      return { ...current, favorite_clip_ids: Array.from(favorites) };
    });
  }, []);

  // Check for unsaved script changes
  const hasScriptChanges = editDecisions.some((decision, index) => {
    const segment = segmentForDecision(voiceoverSegments, decision, index);
    const segmentId = decision.segment_id || segment?.segment_id || fallbackSegmentId(index);
    const draft = scriptDrafts[segmentId];
    if (!draft) return false;
    const sourceVoiceover = String(segment?.voiceover || '');
    const sourceCaption = String(segment?.caption || decision.caption || '');
    return draft.voiceover !== sourceVoiceover || draft.caption !== sourceCaption;
  });

  const saveScriptEdits = useCallback(async () => {
    const payload = editDecisions
      .map((decision, index) => {
        const segment = segmentForDecision(voiceoverSegments, decision, index);
        const segmentId = decision.segment_id || segment?.segment_id || fallbackSegmentId(index);
        const draft = scriptDrafts[segmentId];
        if (!draft) return null;
        const sourceVoiceover = String(segment?.voiceover || '');
        const sourceCaption = String(segment?.caption || decision.caption || '');
        if (draft.voiceover === sourceVoiceover && draft.caption === sourceCaption) return null;
        return {
          segment_id: segmentId,
          voiceover: draft.voiceover.trim(),
          caption: (draft.caption.trim() || String(segment?.caption || decision.caption || draft.voiceover).trim()).slice(0, 180),
        };
      })
      .filter(Boolean) as Array<{ segment_id: string; voiceover: string; caption?: string }>;
    if (!payload.length) return;
    setSavingScripts(true);
    try {
      await onSaveVoiceoverSegments(payload);
    } finally {
      setSavingScripts(false);
    }
  }, [editDecisions, voiceoverSegments, scriptDrafts, onSaveVoiceoverSegments]);

  const videoUrl = mediaUrl(apiUrl, session.final_video_url);

  // --- Sidebar content ---
  const sidebarContent = (() => {
    switch (sidebarTab) {
      case 'media':
        return (
          <SidebarMediaTab
            mediaItems={session.media_items}
            favoriteClipIds={options.favorite_clip_ids}
            onUpload={onUpload}
            onToggleFavorite={handleToggleFavorite}
          />
        );
      case 'story':
        return <SidebarStoryTab plan={plan} />;
      case 'intelligence':
        return <ClipIntelligence clips={session.clip_analysis || []} />;
      case 'brief':
        return (
          <ProducerBriefPanel
            session={session}
            context={context}
            disabled={session.phase === 'planning' || session.phase === 'rendering'}
            onDraft={() => onDraftCreativeBrief(context)}
            onSave={onUpdateCreativeBrief}
            onApprove={onApproveCreativeBrief}
            onGenerate={onGenerate}
          />
        );
      default:
        return null;
    }
  })();

  return (
    <View style={styles.root}>
      <EditorLayout
        sidebar={
          <Sidebar activeTab={sidebarTab} onTabChange={setSidebarTab}>
            {sidebarContent}
          </Sidebar>
        }
        center={
          <PreviewPanel session={session} videoUrl={videoUrl} />
        }
        timeline={
          <TimelineStrip
            session={session}
            options={options}
            scriptDrafts={scriptDrafts}
            onScriptChange={handleScriptChange}
            onMoveClip={handleMoveClip}
          />
        }
        properties={
          <View style={styles.propertiesContainer}>
            <PropertiesPanel
              session={session}
              context={context}
              options={options}
              activeTab={propertiesTab}
              onTabChange={setPropertiesTab}
              onContextChange={handleContextChange}
              onOptionsChange={setOptions}
            />
            <ActionBar
              session={session}
              options={options}
              hasScriptChanges={hasScriptChanges}
              savingScripts={savingScripts}
              onSaveContext={() => onSaveContext(context)}
              onDraftBrief={() => onDraftCreativeBrief(context)}
              onGenerate={onGenerate}
              onRender={() => onRender(options)}
              onSaveScripts={saveScriptEdits}
              onShare={onShare}
            />
          </View>
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.paper,
  },
  propertiesContainer: {
    flex: 1,
    flexDirection: 'column',
  },
});
