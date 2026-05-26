import type { TripContext, TripSession } from './types';

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

export async function createSession(baseUrl: string): Promise<TripSession> {
  const response = await fetch(joinUrl(baseUrl, '/sessions'), { method: 'POST' });
  return readJson<TripSession>(response);
}

export async function getSession(baseUrl: string, sessionId: string): Promise<TripSession> {
  const response = await fetch(joinUrl(baseUrl, `/sessions/${sessionId}`));
  return readJson<TripSession>(response);
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

export async function renderTripVideo(baseUrl: string, sessionId: string): Promise<TripSession> {
  const response = await fetch(joinUrl(baseUrl, `/sessions/${sessionId}/render`), { method: 'POST' });
  return readJson<TripSession>(response);
}
