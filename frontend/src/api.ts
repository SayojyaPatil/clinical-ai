export interface Note {
  id: string;
  patient_id: string;
  diagnoses: string;
  medications: string;
  follow_ups: string;
  urgency: string;
  confidence: number;
  warning: string | null;
  created_at: string;
}

export interface AIExtractionSnapshot {
  diagnoses: string[];
  medications: string[];
  follow_ups: string[];
  urgency: string;
  confidence: number;
}

export interface DocumentSource {
  note_id: string;
  source_id: string | null;
  kind: 'text' | 'image' | 'unknown';
  availability: 'available' | 'unavailable';
  provenance: 'submitted' | 'legacy_inferred' | null;
  original_filename: string | null;
  mime_type: string | null;
  byte_size: number | null;
  sha256: string | null;
  stored_at: string | null;
  original_text: string | null;
  unavailable_reason: string | null;
  ai_result: AIExtractionSnapshot | null;
  model_name: string | null;
  prompt_version: string | null;
  extraction_schema_version: number | null;
  review_status: 'unreviewed' | 'draft' | 'approved' | null;
}

const base = import.meta.env.VITE_API_BASE_URL || '/api';

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); this.name = 'ApiError'; }
}

async function authorizedFetch(path: string, init: RequestInit = {}, token?: string): Promise<Response> {
  const headers = new Headers(init.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(`${base}${path}`, { ...init, headers });
  if (!response.ok) {
    const content = await response.json().catch(() => null);
    const detail = content?.detail;
    throw new ApiError(typeof detail === 'string' ? detail : response.status === 401 ? 'Your session expired. Please sign in again.' : 'Something went wrong. Please try again.', response.status);
  }
  return response;
}

async function request<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  return (await authorizedFetch(path, init, token)).json() as Promise<T>;
}

export const api = {
  note: (token: string, id: string, signal?: AbortSignal) => request<Note>(`/notes/${encodeURIComponent(id)}`, { signal, cache: 'no-store' }, token),
  source: (token: string, id: string, signal?: AbortSignal) => request<DocumentSource>(`/notes/${encodeURIComponent(id)}/source`, { signal, cache: 'no-store' }, token),
  sourceContent: async (token: string, id: string, signal?: AbortSignal): Promise<Blob> => {
    const response = await authorizedFetch(`/notes/${encodeURIComponent(id)}/source/content`, { signal, cache: 'no-store' }, token);
    return response.blob();
  },
  signup: (username: string, password: string) => request<{ message: string }>('/auth/signup', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password }),
  }),
  login: (username: string, password: string) => request<{ access_token: string; token_type: string }>('/auth/token', {
    method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ username, password }),
  }),
  notes: (token: string) => request<Note[]>('/notes', {}, token),
  analyzeText: (token: string, patient_id: string, note_text: string) => request<Note>('/notes/analyze-text', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ patient_id, note_text }),
  }, token),
  analyzeImage: (token: string, patient_id: string, file: File) => {
    const data = new FormData(); data.append('file', file);
    return request<Note>(`/notes/analyze-image?patient_id=${encodeURIComponent(patient_id)}`, { method: 'POST', body: data }, token);
  },
};
