import type { TrendSession } from './types';

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
    const detail = typeof data?.detail === 'string' ? data.detail : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return data as T;
}

export function mediaUrl(baseUrl: string, path?: string | null): string | null {
  if (!path) return null;
  if (path.startsWith('http://') || path.startsWith('https://')) return path;
  return joinUrl(baseUrl, path);
}

export async function createSession(baseUrl: string): Promise<TrendSession> {
  const response = await fetch(joinUrl(baseUrl, '/sessions'), { method: 'POST' });
  return readJson<TrendSession>(response);
}

export async function getSession(baseUrl: string, sessionId: string): Promise<TrendSession> {
  const response = await fetch(joinUrl(baseUrl, `/sessions/${sessionId}`));
  return readJson<TrendSession>(response);
}

export async function startAnalysis(baseUrl: string, sessionId: string, url: string): Promise<TrendSession> {
  const response = await fetch(joinUrl(baseUrl, `/sessions/${sessionId}/analyze`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  });
  return readJson<TrendSession>(response);
}

export async function sendPreflightFrame(
  baseUrl: string,
  sessionId: string,
  imageBase64: string
): Promise<TrendSession> {
  const response = await fetch(joinUrl(baseUrl, `/sessions/${sessionId}/preflight-frame`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image_base64: imageBase64 }),
  });
  return readJson<TrendSession>(response);
}

export async function uploadClip(
  baseUrl: string,
  sessionId: string,
  clipUri: string,
  options?: { fullTake?: boolean }
): Promise<TrendSession> {
  const form = new FormData();
  form.append('files', {
    uri: clipUri,
    name: options?.fullTake ? 'full_take.mp4' : 'shot.mp4',
    type: 'video/mp4',
  } as any);

  const fullTake = options?.fullTake ? 'true' : 'false';
  const response = await fetch(
    joinUrl(baseUrl, `/sessions/${sessionId}/clips?auto_render=true&full_take=${fullTake}`),
    {
      method: 'POST',
      body: form,
      headers: { Accept: 'application/json' },
    }
  );
  return readJson<TrendSession>(response);
}
