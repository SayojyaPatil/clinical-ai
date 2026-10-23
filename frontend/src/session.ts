const SESSION_KEY = 'clinical-ai.session';

export interface Session { token: string; username: string }

// Decoding only checks expiry; GET /notes remains the server-side validation.
export function isUnexpiredToken(token: string, now = Date.now()): boolean {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return false;
    const payload = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const { exp } = JSON.parse(atob(payload.padEnd(Math.ceil(payload.length / 4) * 4, '=')));
    return typeof exp === 'number' && Number.isFinite(exp) && exp * 1000 > now;
  } catch { return false; }
}

export function clearSession(): void {
  try { sessionStorage.removeItem(SESSION_KEY); } catch { /* Storage may be disabled. */ }
}

export function saveSession(session: Session): void {
  try { sessionStorage.setItem(SESSION_KEY, JSON.stringify(session)); } catch { /* Keep in-memory login usable. */ }
}

export function readSession(): Session | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw);
    if (typeof session?.token === 'string' && typeof session?.username === 'string' && isUnexpiredToken(session.token)) return session;
  } catch { /* Malformed or unavailable storage cannot restore a session. */ }
  clearSession();
  return null;
}
