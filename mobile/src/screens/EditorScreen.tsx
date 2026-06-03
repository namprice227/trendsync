import React, { useState, useEffect, useCallback } from 'react';
import { View, StyleSheet } from 'react-native';
import { colors } from '../theme';
import type {
  TripSession,
  TripContext,
  RenderOptions,
  TimelineSegmentUpdate,
  SidebarTab,
  PropertiesTab,
  UploadProgress,
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
  uploadProgress,
  onSaveContext,
  onUpload,
  onDraftCreativeBrief,
  onUpdateCreativeBrief,
  onApproveCreativeBrief,
  onGenerate,
  onRender,
  onSaveVoiceoverSegments,
  onSaveTimelineSegments,
  onShare,
}: {
  apiUrl: string;
  session: TripSession;
  uploadProgress: UploadProgress | null;
  onSaveContext: (context: TripContext) => void;
  onUpload: () => void;
  onDraftCreativeBrief: (context: TripContext) => Promise<void>;
  onUpdateCreativeBrief: (patch: { selected_direction_id?: string | null; answers?: Array<{ question_id: string; answer: string }>; notes?: string | null }) => Promise<void>;
  onApproveCreativeBrief: (patch: { selected_direction_id?: string | null; answers?: Array<{ question_id: string; answer: string }>; notes?: string | null }) => Promise<void>;
  onGenerate: (options?: RenderOptions) => void;
  onRender: (options: RenderOptions) => void;
  onSaveVoiceoverSegments: (segments: Array<{ segment_id: string; voiceover: string; caption?: string }>) => Promise<void>;
  onSaveTimelineSegments: (segments: TimelineSegmentUpdate[], segmentOrder: string[]) => Promise<void>;
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
  const [timelineDrafts, setTimelineDrafts] = useState<Record<string, { start_time: number; duration: number }>>({});
  const [timelineOrder, setTimelineOrder] = useState<string[]>([]);
  const [savingScripts, setSavingScripts] = useState(false);
  const [savingTimeline, setSavingTimeline] = useState(false);

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
  const timelineSource = editDecisions.map((decision, index) => {
    const segment = segmentForDecision(voiceoverSegments, decision, index);
    const segmentId = decision.segment_id || segment?.segment_id || fallbackSegmentId(index);
    return {
      segmentId,
      start_time: Number(decision.start_time ?? segment?.start_time ?? 0),
      duration: Number(decision.duration ?? segment?.duration ?? 1),
    };
  });
  const baseTimelineOrder = timelineSource.map((item) => item.segmentId);
  const baseTimelineOrderKey = baseTimelineOrder.join('|');
  const effectiveTimelineOrder = timelineOrder.length ? timelineOrder : baseTimelineOrder;
  const effectiveTimelineOrderKey = effectiveTimelineOrder.join('|');
  const timelineSourceFingerprint = timelineSource
    .map((item) => `${item.segmentId}:${item.start_time.toFixed(2)}:${item.duration.toFixed(2)}`)
    .join('|');

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

  useEffect(() => {
    const nextDrafts: Record<string, { start_time: number; duration: number }> = {};
    timelineSource.forEach((item) => {
      nextDrafts[item.segmentId] = {
        start_time: item.start_time,
        duration: item.duration,
      };
    });
    setTimelineDrafts(nextDrafts);
    setTimelineOrder(baseTimelineOrder);
  }, [session.id, timelineSourceFingerprint]);

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

  const handleTimelineChange = useCallback((segmentId: string, patch: Partial<{ start_time: number; duration: number }>) => {
    setTimelineDrafts((current) => ({
      ...current,
      [segmentId]: {
        ...(current[segmentId] || { start_time: 0, duration: 1 }),
        ...patch,
      },
    }));
  }, []);

  const handleMoveSegment = useCallback((segmentId: string, direction: -1 | 1) => {
    setTimelineOrder((current) => {
      const base = current.length ? [...current] : [...baseTimelineOrder];
      const index = base.indexOf(segmentId);
      const nextIndex = index + direction;
      if (index < 0 || nextIndex < 0 || nextIndex >= base.length) return current.length ? current : base;
      const next = [...base];
      [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
      return next;
    });
  }, [baseTimelineOrderKey]);

  const handleToggleFavorite = useCallback((clipId: string) => {
    setOptions((current) => {
      const favorites = new Set(current.favorite_clip_ids || []);
      const excluded = new Set(current.excluded_clip_ids || []);
      if (excluded.has(clipId)) return current;
      if (favorites.has(clipId)) {
        favorites.delete(clipId);
      } else {
        favorites.add(clipId);
      }
      return { ...current, favorite_clip_ids: Array.from(favorites) };
    });
  }, []);

  const handleToggleExclude = useCallback((clipId: string) => {
    setOptions((current) => {
      const excluded = new Set(current.excluded_clip_ids || []);
      const favorites = new Set(current.favorite_clip_ids || []);
      if (excluded.has(clipId)) {
        excluded.delete(clipId);
      } else {
        excluded.add(clipId);
        favorites.delete(clipId);
      }
      return {
        ...current,
        favorite_clip_ids: Array.from(favorites),
        excluded_clip_ids: Array.from(excluded),
      };
    });
  }, []);

  const handleTogglePinScene = useCallback((sceneId: string) => {
    setOptions((current) => {
      const pinned = new Set(current.pinned_scene_ids || []);
      const excluded = new Set(current.excluded_scene_ids || []);
      if (excluded.has(sceneId)) return current;
      if (pinned.has(sceneId)) {
        pinned.delete(sceneId);
      } else {
        pinned.add(sceneId);
      }
      return { ...current, pinned_scene_ids: Array.from(pinned) };
    });
  }, []);

  const handleToggleExcludeScene = useCallback((sceneId: string) => {
    setOptions((current) => {
      const excluded = new Set(current.excluded_scene_ids || []);
      const pinned = new Set(current.pinned_scene_ids || []);
      if (excluded.has(sceneId)) {
        excluded.delete(sceneId);
      } else {
        excluded.add(sceneId);
        pinned.delete(sceneId);
      }
      return {
        ...current,
        pinned_scene_ids: Array.from(pinned),
        excluded_scene_ids: Array.from(excluded),
      };
    });
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

  const hasTimelineChanges = (() => {
    if (baseTimelineOrder.length !== effectiveTimelineOrder.length) return false;
    const orderChanged = baseTimelineOrder.some((segmentId, index) => segmentId !== effectiveTimelineOrder[index]);
    const timingChanged = timelineSource.some((item) => {
      const draft = timelineDrafts[item.segmentId];
      if (!draft) return false;
      return Math.abs(draft.start_time - item.start_time) >= 0.01 || Math.abs(draft.duration - item.duration) >= 0.01;
    });
    return orderChanged || timingChanged;
  })();

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

  const saveTimelineEdits = useCallback(async () => {
    const sourceById = new Map(timelineSource.map((item) => [item.segmentId, item]));
    const segmentOrder = effectiveTimelineOrder.filter((segmentId) => sourceById.has(segmentId));
    const payload = segmentOrder.map((segmentId) => {
      const source = sourceById.get(segmentId);
      const draft = timelineDrafts[segmentId] || source || { start_time: 0, duration: 1 };
      return {
        segment_id: segmentId,
        start_time: Math.max(0, Math.round(Number(draft.start_time || 0) * 100) / 100),
        duration: Math.max(1, Math.round(Number(draft.duration || 1) * 100) / 100),
      };
    });
    if (!payload.length) return;
    setSavingTimeline(true);
    try {
      await onSaveTimelineSegments(payload, segmentOrder);
    } finally {
      setSavingTimeline(false);
    }
  }, [timelineSourceFingerprint, effectiveTimelineOrderKey, timelineDrafts, onSaveTimelineSegments]);

  const videoUrl = mediaUrl(apiUrl, session.final_video_url);
  const orderedMediaItems = (() => {
    const byId = new Map(session.media_items.map((item) => [item.id, item]));
    const ordered = (options.clip_order || [])
      .map((clipId) => byId.get(clipId))
      .filter(Boolean) as typeof session.media_items;
    for (const item of session.media_items) {
      if (!ordered.some((orderedItem) => orderedItem.id === item.id)) {
        ordered.push(item);
      }
    }
    return ordered;
  })();

  // --- Sidebar content ---
  const sidebarContent = (() => {
    switch (sidebarTab) {
      case 'media':
        return (
          <SidebarMediaTab
            mediaItems={orderedMediaItems}
            favoriteClipIds={options.favorite_clip_ids}
            excludedClipIds={options.excluded_clip_ids}
            uploadProgress={uploadProgress}
            onUpload={onUpload}
            onToggleFavorite={handleToggleFavorite}
            onToggleExclude={handleToggleExclude}
            onMoveClip={handleMoveClip}
          />
        );
      case 'story':
        return <SidebarStoryTab plan={plan} />;
      case 'intelligence':
        return (
          <ClipIntelligence
            clips={session.clip_analysis || []}
            sceneMemories={session.scene_memories || []}
            pinnedSceneIds={options.pinned_scene_ids || []}
            excludedSceneIds={options.excluded_scene_ids || []}
            onTogglePinScene={handleTogglePinScene}
            onToggleExcludeScene={handleToggleExcludeScene}
          />
        );
      case 'brief':
        return (
          <ProducerBriefPanel
            session={session}
            context={context}
            disabled={session.phase === 'planning' || session.phase === 'rendering'}
            onDraft={() => onDraftCreativeBrief(context)}
            onSave={onUpdateCreativeBrief}
            onApprove={onApproveCreativeBrief}
            onGenerate={() => onGenerate(options)}
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
            scriptDrafts={scriptDrafts}
            timelineDrafts={timelineDrafts}
            timelineOrder={effectiveTimelineOrder}
            onScriptChange={handleScriptChange}
            onTimelineChange={handleTimelineChange}
            onMoveSegment={handleMoveSegment}
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
              hasTimelineChanges={hasTimelineChanges}
              savingScripts={savingScripts}
              savingTimeline={savingTimeline}
              onSaveContext={() => onSaveContext(context)}
              onDraftBrief={() => onDraftCreativeBrief(context)}
              onGenerate={() => onGenerate(options)}
              onRender={() => onRender(options)}
              onSaveScripts={saveScriptEdits}
              onSaveTimeline={saveTimelineEdits}
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
