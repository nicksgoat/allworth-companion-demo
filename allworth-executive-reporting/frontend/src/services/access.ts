// src/services/access.ts
// Shared, impersonation-aware access resolution used by the global navigation
// (SideNav), the Home hub card grid, and any surface that needs to hide or show
// UI based on the current user's effective tool access.
//
// An active "view as" impersonation overlay (written by the Admin page into
// sessionStorage) always takes precedence over the real signed-in user's
// access so an admin sees the site EXACTLY as the impersonated user would.
// Resolution fails closed when the backend lookup errors so a transient
// service issue can never become an implicit all-tools grant.

import { useEffect, useState } from 'react';
import { adminApi } from './admin';
import type { Assignment } from './admin';
import type { WorkspaceAdvisor } from './workspace';

export const IMPERSONATION_KEY = 'allworth-impersonation';
export const IMPERSONATION_EVENT = 'allworth-impersonation-change';

export interface Impersonation {
  email: string;
  tools: string[];
  /** tool ids the impersonated user may share (optional; older overlays omit). */
  shareTools?: string[];
  /** whether the impersonated user can share every tool. */
  shareAll?: boolean;
  assignment?: Assignment;
  advisor?: WorkspaceAdvisor | null;
}

export interface EffectiveAccess {
  /** Email for the signed-in user, or the active "view as" account. */
  email: string | null;
  /** True while an administrator is viewing the workspace as another user. */
  impersonating: boolean;
  /** true when the user can open every tool (all-access or enforcement off). */
  all: boolean;
  /** effective tool ids the user can open (ignored when `all` is true). */
  tools: Set<string>;
  /** true when the user can share every tool (all-access admin). */
  shareAll: boolean;
  /** tool ids the user is allowed to share with others. */
  shareTools: Set<string>;
}

/** Read the active "view as" overlay, or null when not impersonating. */
export function readImpersonation(): Impersonation | null {
  try {
    const raw = sessionStorage.getItem(IMPERSONATION_KEY);
    return raw ? (JSON.parse(raw) as Impersonation) : null;
  } catch {
    return null;
  }
}

// The real user's access is fetched once and cached for the page lifetime.
let meCache: EffectiveAccess | null = null;
let mePromise: Promise<EffectiveAccess> | null = null;

function loadMe(): Promise<EffectiveAccess> {
  if (!mePromise) {
    mePromise = adminApi
      .getMe()
      .then((m) => {
        meCache = {
          email: m.email,
          impersonating: false,
          all: m.all_access,
          tools: new Set(m.effective_tools),
          shareAll: !!m.can_share_all,
          shareTools: new Set(m.share_tools ?? []),
        };
        return meCache;
      })
      .catch(() => {
        // Fail closed for both viewing and sharing.
        meCache = {
          email: null,
          impersonating: false,
          all: false,
          tools: new Set(),
          shareAll: false,
          shareTools: new Set(),
        };
        return meCache;
      });
  }
  return mePromise;
}

/**
 * Resolve the current effective access, honoring an active impersonation
 * overlay. Returns null until the initial real-user lookup resolves so callers
 * can wait before filtering (avoids a flash of tools the user can't reach).
 * Re-renders when impersonation starts/stops.
 */
export function useEffectiveAccess(): EffectiveAccess | null {
  const [imp, setImp] = useState(readImpersonation());
  const [me, setMe] = useState<EffectiveAccess | null>(meCache);

  useEffect(() => {
    const sync = () => setImp(readImpersonation());
    window.addEventListener(IMPERSONATION_EVENT, sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener(IMPERSONATION_EVENT, sync);
      window.removeEventListener('storage', sync);
    };
  }, []);

  useEffect(() => {
    if (meCache) setMe(meCache);
    else void loadMe().then(setMe);
  }, []);

  // Impersonation ("view as") takes precedence over the real user's access,
  // including the impersonated user's SHARE access so an admin can verify the
  // share affordance exactly as that user would experience it.
  if (imp)
    return {
      email: imp.email,
      impersonating: true,
      all: false,
      tools: new Set(imp.tools),
      shareAll: !!imp.shareAll,
      shareTools: new Set(imp.shareTools ?? []),
    };
  return me;
}

/**
 * Whether the given tool id is reachable under the resolved access. Ungated
 * items (no toolId) are always visible; while access is still loading (null)
 * gated items are hidden.
 */
export function canAccessTool(access: EffectiveAccess | null, toolId?: string): boolean {
  if (!toolId) return true;
  if (!access) return false;
  return access.all || access.tools.has(toolId);
}

/**
 * Whether the current user may share the given tool with others. Requires the
 * resolved access to be loaded; unknown/loading resolves to false so a share
 * affordance never flashes before rights are confirmed.
 */
export function canShareTool(access: EffectiveAccess | null, toolId?: string): boolean {
  if (!toolId || !access) return false;
  return access.shareAll || access.shareTools.has(toolId);
}
