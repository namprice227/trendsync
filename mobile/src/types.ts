export type TrendPhase =
  | 'awaiting_reference'
  | 'analyzing'
  | 'ready_to_film'
  | 'needs_adjustment'
  | 'ready_to_record'
  | 'uploading'
  | 'rendering_ready'
  | 'rendering'
  | 'evaluating'
  | 'complete'
  | 'error';

export type TrendScreen = 'analyze' | 'studio' | 'output';

export type StyleProfile = {
  video_type?: string;
  narrative?: string;
  clothing?: string | string[];
  setting?: string | string[];
  camera_angle?: string | string[];
  key_transition?: string;
  recreation_tips?: string;
};

export type ContextSummary = {
  bpm?: number;
  shots: number;
  duration?: number;
  beats: number;
  beat_synced_cuts: number;
  total_cuts: number;
  camera_motion: Record<string, number>;
};

export type TrendSession = {
  id: string;
  phase: TrendPhase;
  screen: TrendScreen;
  next_action: string;
  created_at: number;
  updated_at: number;
  error?: string | null;
  progress_label: string;
  style?: StyleProfile | null;
  context_summary?: ContextSummary | null;
  script?: string | null;
  skill_dir?: string | null;
  required_shots: number;
  current_shot_idx: number;
  current_shot_duration: number;
  recorded_clips: string[];
  feedback: string[];
  director_feedback: string;
  final_video_url?: string | null;
  evaluation?: string | null;
};
