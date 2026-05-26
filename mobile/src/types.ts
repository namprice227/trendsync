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

export type MediaItem = {
  id: string;
  filename: string;
  kind: string;
  url: string;
  size_bytes: number;
};

export type StoryPlan = {
  title?: string;
  language?: string;
  tone?: string;
  narrative_arc?: string[];
  voiceover_script?: string;
  edit_notes?: string[];
  clip_plan?: Array<{
    clip?: string;
    role?: string;
    suggested_use?: string;
  }>;
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
  trip_context: TripContext;
  media_items: MediaItem[];
  recorded_clips: string[];
  story_plan?: StoryPlan | null;
  script?: string | null;
  final_video_url?: string | null;
  story_json_url?: string | null;
  llm_provider: string;
  llm_model: string;
};
