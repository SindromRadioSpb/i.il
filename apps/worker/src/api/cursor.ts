/**
 * Opaque pagination cursor: base64url-encoded JSON {last_update_at, story_id}.
 * Clients must treat cursors as black boxes (see API_CONTRACT.md §1.2).
 */

export interface CursorPayload {
  last_update_at: string;
  story_id: string;
}

export function encodeCursor(lastUpdateAt: string, storyId: string): string {
  const json = JSON.stringify({ last_update_at: lastUpdateAt, story_id: storyId });
  // base64url — no padding
  return btoa(json).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

export function decodeCursor(cursor: string): CursorPayload | null {
  if (!cursor || cursor.length > 500) return null;
  try {
    const padded = cursor.padEnd(
      cursor.length + (4 - (cursor.length % 4)) % 4,
      '=',
    );
    const b64 = padded.replace(/-/g, '+').replace(/_/g, '/');
    const parsed: unknown = JSON.parse(atob(b64));
    if (
      typeof parsed !== 'object' ||
      parsed === null ||
      typeof (parsed as Record<string, unknown>)['last_update_at'] !== 'string' ||
      typeof (parsed as Record<string, unknown>)['story_id'] !== 'string'
    ) {
      return null;
    }
    return parsed as CursorPayload;
  } catch {
    return null;
  }
}
