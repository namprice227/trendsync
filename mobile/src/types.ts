export type TripPhase =
  | 'collecting_context'
  | 'uploading'
  | 'ready_to_plan'
  | 'planning'
  | 'ready_to_render'
  | 'rendering'
  | 'complete'
  | 'error';

export type TripScreen = 'context' | 'upload' | 'plan' | 'output';

export type TripContext = {
  destination: string;
  duration: string;
  places_visited: string;
  travel_dates: string;
  companions: string;
  highlights: string;
  mood: string;
  audience: string;
  language: string;
  notes: string;
  llm_provider: string;
  llm_model: string;
};

export type ClipAnalysis = {
  filename: string;
  status?: string;
  duration_seconds?: number;
  width?: number;
  height?: number;
  scene_count?: number;
  face_count?: number;
  quality_label?: string;
  has_audio?: boolean;
  speech_detected?: boolean;
  mean_volume_db?: number | null;
  best_moment_timestamps?: number[];
  landmark_candidate_timestamps?: number[];
  smart_windows?: Array<{
    window_id: string;
    start_time: number;
    duration: number;
    score: number;
    frame_timestamps: number[];
    visual_evidence?: string;
    semantic_source?: string;
    visible_subjects?: string[];
    locations_or_scenes?: string[];
    visible_actions?: string[];
    visual_mood?: string;
    avoid_reasons?: string[];
    best_moment_description?: {
      timestamp: number;
      description: string;
    };
  }>;
  named_landmarks?: Array<{
    name: string;
    timestamp: number;
    confidence: number;
    source: string;
  }>;
  semantic_source?: string;
  semantic_summary?: string;
  visible_subjects?: string[];
  locations_or_scenes?: string[];
  visible_actions?: string[];
  visual_mood?: string;
  avoid_reasons?: string[];
  best_moment_descriptions?: Array<{
    timestamp: number;
    description: string;
  }>;
  transcript?: string | null;
  summary?: string;
};

export type MediaItem = {
  id: string;
  filename: string;
  kind: string;
  url: string;
  size_bytes: number;
  analysis?: ClipAnalysis;
};

export type StoryPlan = {
  title?: string;
  language?: string;
  tone?: string;
  narrative_arc?: string[];
  voiceover_script?: string;
  voiceover_segments?: Array<{
    segment_id?: string;
    clip_id?: string;
    clip?: string;
    window_id?: string;
    start_time?: number;
    duration?: number;
    voiceover?: string;
    caption?: string;
    purpose?: string;
  }>;
  edit_notes?: string[];
  clip_plan?: Array<{
    clip_id?: string;
    clip?: string;
    role?: string;
    suggested_use?: string;
  }>;
  edit_decisions?: Array<{
    segment_id?: string;
    clip_id?: string;
    clip?: string;
    window_id?: string;
    start_time?: number;
    duration?: number;
    role?: string;
    reason?: string;
    transition?: string;
    caption?: string;
    audio_strategy?: string;
  }>;
  generation?: {
    llm_used?: boolean;
    llm_provider?: string;
    llm_model?: string;
    llm_configured?: boolean;
    fallback_reason?: string | null;
  };
};

export type CreativeBriefEvidence = {
  clip_id?: string;
  clip?: string;
  window_id?: string;
  start_time?: number;
  reason?: string;
  quality?: string;
};

export type CreativeBriefDirection = {
  id: string;
  title: string;
  angle: string;
  tone?: string;
  audience?: string;
  why?: string;
  key_beats?: string[];
  supporting_evidence?: CreativeBriefEvidence[];
};

export type CreativeBriefQuestion = {
  id: string;
  label: string;
  question: string;
  why?: string;
  answer?: string;
};

export type CreativeBrief = {
  title: string;
  summary: string;
  recommended_direction_id?: string;
  selected_direction_id?: string;
  directions: CreativeBriefDirection[];
  questions: CreativeBriefQuestion[];
  must_use?: CreativeBriefEvidence[];
  avoid?: string[];
  missing_context?: string[];
  notes?: string;
  generation?: {
    llm_used?: boolean;
    llm_provider?: string;
    llm_model?: string;
    llm_configured?: boolean;
    fallback_reason?: string | null;
  };
};

export type RenderOptions = {
  aspect_ratio: string;
  target_duration_seconds: number;
  clip_order: string[];
  favorite_clip_ids: string[];
  excluded_clip_ids: string[];
  burn_captions: boolean;
  include_title_card: boolean;
  include_music_bed: boolean;
};

export type JobSummary = {
  id: string;
  session_id: string;
  type: string;
  state: string;
  progress_percent: number;
  current_step: string;
  error?: string | null;
  rq_job_id?: string | null;
  attempts: number;
  created_at: number;
  updated_at: number;
};

export type ProjectSummary = {
  id: string;
  title?: string;
  destination: string;
  phase: TripPhase;
  updated_at: number;
  media_count: number;
  final_video_url?: string | null;
  share_token?: string | null;
};

export type TripSession = {
  id: string;
  phase: TripPhase;
  screen: TripScreen;
  next_action: string;
  created_at: number;
  updated_at: number;
  error?: string | null;
  progress_label: string;
  progress_percent: number;
  events: Array<{ at: number; level: string; label: string }>;
  active_job?: JobSummary | null;
  metadata?: {
    title?: string;
  };
  trip_context: TripContext;
  media_items: MediaItem[];
  recorded_clips: string[];
  clip_analysis: ClipAnalysis[];
  creative_brief?: CreativeBrief | null;
  creative_brief_status?: 'draft' | 'approved' | 'stale' | null;
  creative_brief_answers?: Record<string, string>;
  selected_creative_direction_id?: string | null;
  story_plan?: StoryPlan | null;
  script?: string | null;
  final_video_url?: string | null;
  voiceover_audio_url?: string | null;
  story_json_url?: string | null;
  edit_decisions_url?: string | null;
  caption_srt_url?: string | null;
  caption_vtt_url?: string | null;
  render_options: RenderOptions;
  llm_provider: string;
  llm_model: string;
};
export type AppView = 'dashboard' | 'project';
export type ProjectFilter = 'all' | 'drafting' | 'ready' | 'rendering' | 'complete' | 'error';
export type ProjectSort = 'recent' | 'name' | 'status';
export type ProjectAction = 'rename' | 'duplicate' | 'share' | 'delete';

// --- CapCut-style editor layout types ---
export type SidebarTab = 'media' | 'story' | 'intelligence' | 'brief';
export type PropertiesTab = 'context' | 'export' | 'script';
