import type { JobSummary, ProjectSummary, RenderOptions, TripContext, TripSession } from './types';

export type CreativeBriefPatch = {
  selected_direction_id?: string | null;
  answers?: Array<{ question_id: string; answer: string }>;
  notes?: string | null;
};

export function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.trim().replace(/\/+$/, '');
}

function joinUrl(baseUrl: string, path: string): string {
  return `${normalizeBaseUrl(baseUrl)}${path}`;
}

async function readJson<T>(response: Response): Promise<T> {
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    const detail =
      typeof data?.detail === 'string'
        ? data.detail
        : Array.isArray(data?.detail)
          ? data.detail.map((item: { msg?: string; loc?: string[] }) => `${item.loc?.join('.') || 'request'}: ${item.msg || 'invalid'}`).join('; ')
          : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return data as T;
}

export function mediaUrl(baseUrl: string, path?: string | null): string | null {
  if (!path) return null;
  if (path.startsWith('http://') || path.startsWith('https://')) return path;
  return joinUrl(baseUrl, path);
}

export function absoluteUrl(baseUrl: string, pathOrUrl: string): string {
  if (pathOrUrl.startsWith('http://') || pathOrUrl.startsWith('https://')) {
    return pathOrUrl;
  }
  return joinUrl(baseUrl, pathOrUrl);
}

export async function createSession(baseUrl: string): Promise<TripSession> {
  const response = await fetch(joinUrl(baseUrl, '/sessions'), { method: 'POST' });
  return readJson<TripSession>(response);
}

export async function listSessions(baseUrl: string): Promise<ProjectSummary[]> {
  const response = await fetch(joinUrl(baseUrl, '/sessions'));
  const data = await readJson<{ sessions: ProjectSummary[] }>(response);
  return data.sessions;
}

export async function getSession(baseUrl: string, sessionId: string): Promise<TripSession> {
  const response = await fetch(joinUrl(baseUrl, `/sessions/${sessionId}`));
  return readJson<TripSession>(response);
}

export async function updateProjectMetadata(baseUrl: string, sessionId: string, metadata: { title?: string | null }): Promise<TripSession> {
  const response = await fetch(joinUrl(baseUrl, `/sessions/${sessionId}/metadata`), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(metadata),
  });
  return readJson<TripSession>(response);
}

export async function duplicateSession(baseUrl: string, sessionId: string): Promise<TripSession> {
  const response = await fetch(joinUrl(baseUrl, `/sessions/${sessionId}/duplicate`), { method: 'POST' });
  return readJson<TripSession>(response);
}

export async function draftCreativeBrief(baseUrl: string, sessionId: string): Promise<TripSession> {
  const response = await fetch(joinUrl(baseUrl, `/sessions/${sessionId}/creative-brief`), { method: 'POST' });
  return readJson<TripSession>(response);
}

export async function updateCreativeBrief(baseUrl: string, sessionId: string, patch: CreativeBriefPatch): Promise<TripSession> {
  const response = await fetch(joinUrl(baseUrl, `/sessions/${sessionId}/creative-brief`), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
  return readJson<TripSession>(response);
}

export async function approveCreativeBrief(baseUrl: string, sessionId: string, patch: CreativeBriefPatch): Promise<TripSession> {
  const response = await fetch(joinUrl(baseUrl, `/sessions/${sessionId}/creative-brief/approve`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
  return readJson<TripSession>(response);
}

export async function deleteSession(baseUrl: string, sessionId: string): Promise<{ status: string }> {
  const response = await fetch(joinUrl(baseUrl, `/sessions/${sessionId}`), { method: 'DELETE' });
  return readJson<{ status: string }>(response);
}

export async function saveTripContext(
  baseUrl: string,
  sessionId: string,
  context: TripContext
): Promise<TripSession> {
  const response = await fetch(joinUrl(baseUrl, `/sessions/${sessionId}/context`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(context),
  });
  return readJson<TripSession>(response);
}

export async function uploadMedia(
  baseUrl: string,
  sessionId: string,
  assets: Array<{ uri: string; name?: string | null; mimeType?: string | null; file?: File | null }>
): Promise<TripSession> {
  const form = new FormData();
  for (const asset of assets) {
    if (asset.file) {
      form.append('files', asset.file, asset.name || asset.file.name || 'trip_clip.mp4');
    } else {
      form.append('files', {
        uri: asset.uri,
        name: asset.name || 'trip_clip.mp4',
        type: asset.mimeType || 'video/mp4',
      } as any);
    }
  }

  const response = await fetch(joinUrl(baseUrl, `/sessions/${sessionId}/media`), {
    method: 'POST',
    body: form,
    headers: { Accept: 'application/json' },
  });
  return readJson<TripSession>(response);
}

export async function generateStory(baseUrl: string, sessionId: string): Promise<TripSession> {
  const response = await fetch(joinUrl(baseUrl, `/sessions/${sessionId}/generate-story`), { method: 'POST' });
  return readJson<TripSession>(response);
}

export async function renderTripVideo(baseUrl: string, sessionId: string, options?: RenderOptions): Promise<TripSession> {
  const response = await fetch(joinUrl(baseUrl, `/sessions/${sessionId}/render`), {
    method: 'POST',
    headers: options ? { 'Content-Type': 'application/json' } : undefined,
    body: options ? JSON.stringify(options) : undefined,
  });
  return readJson<TripSession>(response);
}

export async function updateVoiceoverSegments(
  baseUrl: string,
  sessionId: string,
  segments: Array<{ segment_id: string; voiceover: string; caption?: string }>
): Promise<TripSession> {
  const response = await fetch(joinUrl(baseUrl, `/sessions/${sessionId}/voiceover-segments`), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ segments }),
  });
  return readJson<TripSession>(response);
}

export async function getJob(baseUrl: string, sessionId: string, jobId: string): Promise<JobSummary> {
  const response = await fetch(joinUrl(baseUrl, `/sessions/${sessionId}/jobs/${jobId}`));
  return readJson<JobSummary>(response);
}

export async function shareSession(baseUrl: string, sessionId: string): Promise<{ share_token: string; share_url: string; session: TripSession }> {
  const response = await fetch(joinUrl(baseUrl, `/sessions/${sessionId}/share`), { method: 'POST' });
  return readJson<{ share_token: string; share_url: string; session: TripSession }>(response);
}
