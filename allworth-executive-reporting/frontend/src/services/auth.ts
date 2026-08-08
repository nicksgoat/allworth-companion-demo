// src/services/auth.ts
// SSO via Azure App Service Authentication ("Easy Auth").
//
// The Web App is fronted by App Service Authentication configured against the
// Entra app whose AAD callback (/.auth/login/aad/callback) is the REGISTERED
// redirect URI.  We therefore do NOT run a second OAuth flow in the browser:
// the previous MSAL `loginRedirect` sent the bare SPA origin
// (https://<host>) as the redirect_uri, which is not a registered redirect URI
// and fails with AADSTS50011.
//
// Identity and tokens are read from the platform endpoint `/.auth/me`, and an
// unauthenticated user is sent to `/.auth/login/aad` (which uses the
// registered callback).  The Easy Auth ID token is forwarded to the Flask
// backend as a Bearer token; the backend additionally accepts the Easy Auth
// principal header injected by the platform.

interface EasyAuthClaim {
  typ: string;
  val: string;
}

interface EasyAuthMe {
  id_token?: string;
  access_token?: string;
  user_id?: string;
  user_claims?: EasyAuthClaim[];
  provider_name?: string;
}

// Paths served by the Flask backend that require an authenticated identity.
// Anything else (static assets) is served by nginx and is not gated here.
const BACKEND_PATH_PREFIXES = ['/api/', '/jarvis/', '/home/'];

// App Service Authentication platform endpoints (same-origin).
const AUTH_ME_ENDPOINT = '/.auth/me';
const AUTH_LOGIN_ENDPOINT = '/.auth/login/aad';

// Build-time SSO switch.  The deploy workflows pass VITE_ENTRA_CLIENT_ID only
// where SSO should be enforced (production).  The dev workflow leaves it empty,
// so the dev slot runs UNAUTHENTICATED — its Easy Auth callback URL is not
// registered on the App Registration, so attempting login would 50011.
const SSO_ENABLED = Boolean(import.meta.env.VITE_ENTRA_CLIENT_ID);

// The original fetch, captured before installAuthFetch() wraps window.fetch,
// so our own `/.auth/me` bootstrap call is never gated or token-decorated.
const rawFetch = window.fetch.bind(window);

let currentMe: EasyAuthMe | null = null;
let fetched = false;
let inFlight: Promise<EasyAuthMe | null> | null = null;
// Whether App Service Authentication ("Easy Auth") is actually enabled on this
// host.  When it is NOT enabled, the platform does not intercept `/.auth/*`, so
// those requests fall through to nginx and return the SPA's index.html (HTML,
// not JSON).  In that case we must run UNAUTHENTICATED rather than redirect to
// `/.auth/login/aad` (which would loop).  Detected at runtime from `/.auth/me`.
let authAvailable = false;

/**
 * True when SSO is enabled for this build (production).  When false, the app
 * runs unauthenticated and never contacts the Easy Auth endpoints.
 */
export function isAuthConfigured(): boolean {
  return SSO_ENABLED;
}

/** Load (and cache) the current identity from the Easy Auth `/.auth/me` endpoint. */
async function loadMe(): Promise<EasyAuthMe | null> {
  if (!SSO_ENABLED) {
    fetched = true;
    return null;
  }
  if (fetched) return currentMe;
  if (inFlight) return inFlight;
  inFlight = (async () => {
    try {
      const resp = await rawFetch(AUTH_ME_ENDPOINT, {
        headers: { Accept: 'application/json' },
        credentials: 'include',
      });
      // 401 => Easy Auth is enabled but the caller is anonymous.
      if (resp.status === 401 || resp.status === 403) {
        authAvailable = true;
        currentMe = null;
      } else if (resp.ok) {
        // Easy Auth replies with JSON.  If we instead got HTML (the SPA
        // index.html), the `/.auth/*` route fell through to nginx => Easy Auth
        // is NOT enabled on this host, so do not gate.
        const ctype = resp.headers.get('content-type') ?? '';
        if (!ctype.includes('application/json')) {
          authAvailable = false;
          currentMe = null;
        } else {
          const data = (await resp.json()) as EasyAuthMe[] | EasyAuthMe;
          const me = Array.isArray(data) ? data[0] ?? null : data ?? null;
          // 200 with an identity => signed in.  200 with an empty array =>
          // Easy Auth enabled but anonymous (should log in).
          authAvailable = true;
          currentMe = me;
        }
      } else {
        // 404 / 5xx => `/.auth/me` not served => Easy Auth not enabled.
        authAvailable = false;
        currentMe = null;
      }
    } catch {
      authAvailable = false;
      currentMe = null;
    } finally {
      fetched = true;
      inFlight = null;
    }
    return currentMe;
  })();
  return inFlight;
}

/**
 * Redirect the browser to the App Service Authentication AAD login.  This uses
 * the REGISTERED /.auth/login/aad/callback redirect URI, so it never triggers
 * AADSTS50011.  The Promise never resolves – the page navigates away.
 */
function redirectToLogin(): Promise<never> {
  const target =
    window.location.pathname + window.location.search + window.location.hash;
  const url = `${AUTH_LOGIN_ENDPOINT}?post_login_redirect_uri=${encodeURIComponent(
    target,
  )}`;
  window.location.assign(url);
  return new Promise<never>(() => {});
}

/** Initialize auth state.  Safe to call multiple times. */
export async function initAuth(): Promise<void> {
  await loadMe();
}

/**
 * Ensure the user is signed in.  When App Service Authentication is enabled and
 * the user is already authenticated, `/.auth/me` returns their identity.  When
 * it is enabled but the user is anonymous, redirect to `/.auth/login/aad`
 * (registered callback).  When Easy Auth is NOT enabled on this host, run
 * unauthenticated (return null) rather than looping on a non-existent login
 * endpoint.
 */
export async function ensureAuthenticated(): Promise<EasyAuthMe | null> {
  if (!SSO_ENABLED) return null;
  const account = await loadMe();
  if (account) return account;
  if (authAvailable) return redirectToLogin();
  // Easy Auth not enabled – do not gate.
  console.warn(
    '⚠️  App Service Authentication not detected at /.auth/me – running ' +
      'unauthenticated (SSO disabled for this host)',
  );
  return null;
}

/** Extract the user's email/UPN from the Easy Auth claim set. */
function emailFromMe(account: EasyAuthMe | null): string | null {
  if (!account) return null;
  const claims = account.user_claims ?? [];
  const byType = (t: string): string | undefined =>
    claims.find((c) => c.typ === t || c.typ.endsWith('/' + t))?.val;
  return (
    byType('preferred_username') ||
    byType('upn') ||
    byType('email') ||
    byType('emailaddress') ||
    account.user_id ||
    null
  );
}

/**
 * Return the Easy Auth ID token for the active account (used as the Bearer
 * token to the Flask backend), or null if unavailable.
 */
export async function getIdToken(): Promise<string | null> {
  const account = await loadMe();
  return account?.id_token ?? null;
}

/**
 * Resolve the signed-in user's email/UPN from the Easy Auth identity.  Returns
 * null if no identity is available.
 */
export async function resolveUserEmail(): Promise<string | null> {
  const account = await loadMe();
  return emailFromMe(account);
}

/**
 * Install a global fetch() wrapper that automatically attaches a Bearer token
 * to same-origin requests targeting the Flask backend (paths under /api/,
 * /jarvis/, /home/).  Cross-origin requests and frontend asset requests are
 * passed through untouched.
 *
 * Idempotent: calling more than once is a no-op.
 */
let fetchInstalled = false;
export function installAuthFetch(): void {
  if (fetchInstalled || !isAuthConfigured()) return;
  fetchInstalled = true;
  const originalFetch = window.fetch.bind(window);

  window.fetch = (async (
    input: RequestInfo | URL,
    init?: RequestInit,
  ): Promise<Response> => {
    let url: string;
    if (typeof input === 'string') {
      url = input;
    } else if (input instanceof URL) {
      url = input.toString();
    } else {
      url = input.url;
    }

    let pathname: string;
    try {
      pathname = new URL(url, window.location.origin).pathname;
    } catch {
      return originalFetch(input as RequestInfo, init);
    }

    const needsAuth = BACKEND_PATH_PREFIXES.some((p) => pathname.startsWith(p));
    if (!needsAuth) {
      return originalFetch(input as RequestInfo, init);
    }

    const token = await getIdToken();
    const headers = new Headers(init?.headers ?? {});
    if (input instanceof Request) {
      // Preserve headers from the Request object
      input.headers.forEach((v, k) => {
        if (!headers.has(k)) headers.set(k, v);
      });
    }
    if (token && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`);
    }
    return originalFetch(input as RequestInfo, { ...init, headers });
  }) as typeof window.fetch;
}
