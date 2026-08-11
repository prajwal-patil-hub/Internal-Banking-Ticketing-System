import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// axios.post is what attemptRefresh calls directly (not through `api`), so the
// default export is stubbed while `api.create` still returns a real instance.
vi.mock('axios', async () => {
  const actual = await vi.importActual<typeof import('axios')>('axios');
  const post = vi.fn();
  return {
    ...actual,
    default: Object.assign(
      { ...actual.default, post },
      { create: actual.default.create.bind(actual.default) },
    ),
  };
});

import axios from 'axios';
import { refreshAccessToken, AI_TIMEOUT_MS } from './api';

const post = axios.post as unknown as ReturnType<typeof vi.fn>;

/** The shape zustand's persist middleware writes. */
function storeAuth(refreshToken: string | undefined) {
  localStorage.setItem(
    'success-auth',
    JSON.stringify({ state: { accessToken: 'old-access', refreshToken } }),
  );
  localStorage.setItem('access_token', 'old-access');
}

beforeEach(() => {
  localStorage.clear();
  post.mockReset();
});

afterEach(() => {
  localStorage.clear();
});

describe('refreshAccessToken', () => {
  it('stores the new pair and returns the access token', async () => {
    storeAuth('refresh-1');
    post.mockResolvedValue({
      data: { data: { access_token: 'new-access', refresh_token: 'refresh-2' } },
    });

    const token = await refreshAccessToken();

    expect(token).toBe('new-access');
    expect(localStorage.getItem('access_token')).toBe('new-access');
    // The rotated refresh token must be kept too: the server revokes the old
    // one, so keeping it would make the next refresh fail as a reuse attempt.
    const stored = JSON.parse(localStorage.getItem('success-auth')!);
    expect(stored.state.refreshToken).toBe('refresh-2');
  });

  it('coalesces concurrent callers into a single refresh request', async () => {
    storeAuth('refresh-1');
    let resolve!: (v: unknown) => void;
    post.mockReturnValue(new Promise((r) => { resolve = r; }));

    const all = Promise.all([
      refreshAccessToken(),
      refreshAccessToken(),
      refreshAccessToken(),
    ]);
    resolve({ data: { data: { access_token: 'new-access', refresh_token: 'r2' } } });
    const tokens = await all;

    // Three 401s arriving together must not fire three refreshes — the second
    // would present a token the first had just revoked, and the server treats
    // reuse as theft and kills the whole chain.
    expect(post).toHaveBeenCalledTimes(1);
    expect(tokens).toEqual(['new-access', 'new-access', 'new-access']);
  });

  it('refreshes again on a later call once the first has settled', async () => {
    storeAuth('refresh-1');
    post.mockResolvedValue({
      data: { data: { access_token: 'a', refresh_token: 'b' } },
    });

    await refreshAccessToken();
    await refreshAccessToken();

    // The single-flight latch must clear, or the session can never refresh
    // a second time.
    expect(post).toHaveBeenCalledTimes(2);
  });

  it('returns null and clears credentials when the refresh is rejected', async () => {
    storeAuth('expired');
    post.mockRejectedValue(new Error('401'));

    const token = await refreshAccessToken();

    expect(token).toBeNull();
    // Leaving a dead token behind means every later request retries a refresh
    // that cannot succeed.
    expect(localStorage.getItem('access_token')).toBeNull();
    expect(localStorage.getItem('success-auth')).toBeNull();
  });

  it('does not call the server when there is nothing stored', async () => {
    expect(await refreshAccessToken()).toBeNull();
    expect(post).not.toHaveBeenCalled();
  });

  it('does not call the server when the stored state has no refresh token', async () => {
    storeAuth(undefined);

    expect(await refreshAccessToken()).toBeNull();
    expect(post).not.toHaveBeenCalled();
  });

  it('survives corrupt stored auth rather than throwing', async () => {
    localStorage.setItem('success-auth', 'not json');

    await expect(refreshAccessToken()).resolves.toBeNull();
  });

  it('returns null when the response has no token payload', async () => {
    storeAuth('refresh-1');
    post.mockResolvedValue({ data: {} });

    expect(await refreshAccessToken()).toBeNull();
  });
});

describe('AI_TIMEOUT_MS', () => {
  it('sits above the backend AI budget of 180s', () => {
    // Below it, axios aborts a request the server is still serving and the
    // user sees a generic timeout instead of the server's actionable message.
    expect(AI_TIMEOUT_MS).toBeGreaterThan(180_000);
  });
});
