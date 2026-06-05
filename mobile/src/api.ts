import type { JobSummary, ProjectSummary, RenderOptions, TimelineSegmentUpdate, TripContext, TripSession } from './types';

export type CreativeBriefPatch = {
  selected_direction_id?: string | null;
  answers?: Array<{ question_id: string; answer: string }>;
  notes?: string | null;
};

export type UploadAsset = {
  uri: string;
  name?: string | null;
  mimeType?: string | null;
  file?: File | null;
  size?: number | null;
};

export type UploadMediaProgress = {
  loadedBytes: number;
  totalBytes: number | null;
  percent: number | null;
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
    throw new Error(apiErrorMessage(data, response.status));
  }
  return data as T;
}

function apiErrorMessage(data: any, status: number): string {
  return typeof data?.detail === 'string'
    ? data.detail
    : Array.isArray(data?.detail)
      ? data.detail.map((item: { msg?: string; loc?: string[] }) => `${item.loc?.join('.') || 'request'}: ${item.msg || 'invalid'}`).join('; ')
      : `Request failed (${status})`;
}

function parseResponseJson(text: string): any {
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    throw new Error('Server returned an invalid JSON response');
  }
}

function estimatedUploadBytes(assets: UploadAsset[]): number | null {
  const total = assets.reduce((sum, asset) => {
    const size = typeof asset.file?.size === 'number' ? asset.file.size : asset.size;
    return typeof size === 'number' && Number.isFinite(size) ? sum + size : sum;
  }, 0);
  return total > 0 ? total : null;
}

function uploadForm<T>(
  url: string,
  form: FormData,
  estimatedTotalBytes: number | null,
  onProgress?: (progress: UploadMediaProgress) => void
): Promise<T> {
  if (typeof XMLHttpRequest === 'undefined') {
    return fetch(url, {
      method: 'POST',
      body: form,
      headers: { Accept: 'application/json' },
    }).then((response) => readJson<T>(response));
  }

  return new Promise<T>((resolve, reject) => {
    const request = new XMLHttpRequest();
    let latestLoaded = 0;
    let latestTotal = estimatedTotalBytes;

    const reportProgress = (loadedBytes: number, totalBytes: number | null) => {
      latestLoaded = loadedBytes;
      latestTotal = totalBytes;
      const percent = totalBytes ? Math.min(100, Math.round((loadedBytes / totalBytes) * 100)) : null;
      onProgress?.({ loadedBytes, totalBytes, percent });
    };

    request.open('POST', url);
    request.setRequestHeader('Accept', 'application/json');
    request.upload.onprogress = (event) => {
      const totalBytes = event.lengthComputable ? event.total : estimatedTotalBytes;
      reportProgress(event.loaded, totalBytes);
    };
    request.upload.onload = () => {
      reportProgress(latestTotal || latestLoaded, latestTotal);
    };
    request.onload = () => {
      let data: any;
      try {
        data = parseResponseJson(request.responseText || '');
      } catch (error) {
        reject(error);
        return;
      }
      if (request.status < 200 || request.status >= 300) {
        reject(new Error(apiErrorMessage(data, request.status)));
        return;
      }
      resolve(data as T);
    };
    request.onerror = () => reject(new Error('Upload failed because the network request could not be completed'));
    request.onabort = () => reject(new Error('Upload canceled'));
    request.ontimeout = () => reject(new Error('Upload timed out'));
    request.send(form);
  });
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
  assets: UploadAsset[],
  onProgress?: (progress: UploadMediaProgress) => void
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

  return uploadForm<TripSession>(joinUrl(baseUrl, `/sessions/${sessionId}/media`), form, estimatedUploadBytes(assets), onProgress);
}

export async function generateStory(baseUrl: string, sessionId: string, options?: RenderOptions): Promise<TripSession> {
  const response = await fetch(joinUrl(baseUrl, `/sessions/${sessionId}/generate-story`), {
    method: 'POST',
    headers: options ? { 'Content-Type': 'application/json' } : undefined,
    body: options ? JSON.stringify(options) : undefined,
  });
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

export async function updateTimelineSegments(
  baseUrl: string,
  sessionId: string,
  segments: TimelineSegmentUpdate[],
  segmentOrder: string[]
): Promise<TripSession> {
  const response = await fetch(joinUrl(baseUrl, `/sessions/${sessionId}/timeline`), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ segments, segment_order: segmentOrder }),
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
