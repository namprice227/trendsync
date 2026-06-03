import { ProjectSummary, TripSession, TripPhase, ProjectFilter, ProjectSort, ProjectAction, RenderOptions, TripContext, MediaItem, ClipAnalysis } from "../types";

export const busyPhases: TripPhase[] = ['uploading', 'planning', 'rendering'];
export const planningPhases: TripPhase[] = ['planning', 'rendering'];
export const defaultRenderOptions: RenderOptions = {
    aspect_ratio: 'original',
    target_duration_seconds: 30,
    clip_order: [],
    favorite_clip_ids: [],
    excluded_clip_ids: [],
    pinned_scene_ids: [],
    excluded_scene_ids: [],
    burn_captions: false,
    include_title_card: true,
    include_music_bed: false,
};
export const VIDEO_LENGTH_PRESETS = [15, 30, 45, 60, 90];
export const projectFilters: Array<{ key: ProjectFilter; label: string }> = [
    { key: 'all', label: 'All' },
    { key: 'drafting', label: 'Drafting' },
    { key: 'ready', label: 'Ready' },
    { key: 'rendering', label: 'Rendering' },
    { key: 'complete', label: 'Complete' },
    { key: 'error', label: 'Error' },
];
export const projectSorts: Array<{ key: ProjectSort; label: string }> = [
    { key: 'recent', label: 'Recent' },
    { key: 'name', label: 'Name' },
    { key: 'status', label: 'Status' },
];
export const LANGUAGES = [
    { code: 'en', label: 'English' },
    { code: 'vi', label: 'Vietnamese' },
    { code: 'fr', label: 'French' },
    { code: 'es', label: 'Spanish' },
    { code: 'ja', label: 'Japanese' },
    { code: 'ko', label: 'Korean' },
    { code: 'zh', label: 'Chinese' },
];
export const LLM_PROVIDERS = [
    { code: 'local', label: 'Local', detail: 'No backend key' },
    { code: 'openai', label: 'OpenAI', detail: 'OPENAI_API_KEY' },
    { code: 'gemini', label: 'Gemini', detail: 'GEMINI_API_KEY' },
    { code: 'deepseek', label: 'DeepSeek', detail: 'DEEPSEEK_API_KEY' },
];
export const providerModelPlaceholders: Record<string, string> = {
    local: 'Uses the built-in fallback',
    openai: 'Optional, default: gpt-4o-mini',
    gemini: 'Optional, default: gemini-2.0-flash',
    deepseek: 'Optional, default: deepseek-v4-pro',
};
export const tripContextFields: Array<{
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

export function formatTimestamp(value: number): string {
    const minutes = Math.floor(value / 60);
    const seconds = Math.floor(value % 60);
    return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

export function fallbackSegmentId(index: number): string {
    return `seg_${String(index + 1).padStart(3, '0')}`;
}

export function segmentForDecision(segments: NonNullable<TripSession['story_plan']>['voiceover_segments'] | undefined, decision: NonNullable<NonNullable<TripSession['story_plan']>['edit_decisions']>[number], index: number) {
    const segmentId = decision.segment_id || fallbackSegmentId(index);
    return segments?.find((segment) => segment.segment_id === segmentId) || segments?.[index] || null;
}

export function windowForDecision(mediaItems: MediaItem[], decision: NonNullable<NonNullable<TripSession['story_plan']>['edit_decisions']>[number]) {
    const item = mediaItems.find((media) => media.id === decision.clip_id || media.filename === decision.clip);
    return item?.analysis?.smart_windows?.find((window) => window.window_id === decision.window_id) || null;
}

export function projectTitle(project: ProjectSummary): string {
    return (project.title || project.destination || 'Untitled trip').trim();
}

export function sessionTitle(session: TripSession): string {
    return (session.metadata?.title || session.trip_context.destination || 'Untitled trip').trim();
}

export function phaseLabel(phase: TripPhase): string {
    return phase.replaceAll('_', ' ');
}

export function phaseFilter(phase: TripPhase): ProjectFilter {
    if (phase === 'complete') return 'complete';
    if (phase === 'error') return 'error';
    if (phase === 'planning' || phase === 'rendering') return 'rendering';
    if (phase === 'ready_to_plan' || phase === 'ready_to_render') return 'ready';
    return 'drafting';
}

export function phaseTone(phase: TripPhase): 'neutral' | 'info' | 'success' | 'warning' {
    if (phase === 'complete') return 'success';
    if (phase === 'error') return 'warning';
    if (phase === 'ready_to_plan' || phase === 'ready_to_render' || phase === 'planning' || phase === 'rendering') return 'info';
    return 'neutral';
}

export function formatUpdatedAt(value: number): string {
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
