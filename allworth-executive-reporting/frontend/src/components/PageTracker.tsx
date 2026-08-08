// src/components/PageTracker.tsx
// Fires a page-view event on every route change — client-side (SPA) navigation
// included — so App Usage captures each page a user visits, not just the
// initial dashboard load. Mounted once inside each <BrowserRouter>.
//
// trackPageView() is fire-and-forget and reads window.location.pathname at call
// time; this effect runs after React Router has committed the navigation, so
// the path is already current. Identity is resolved as a fallback — the backend
// also reads the signed-in user from the SSO headers on the /api/track request.

import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { trackPageView } from '../services/api';
import { isAuthConfigured, resolveUserEmail } from '../services/auth';

const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';

const isEmbedded = (() => {
  try {
    return window.self !== window.top;
  } catch {
    return true;
  }
})();

export default function PageTracker() {
  const location = useLocation();
  const startRef = useRef(performance.now());
  const firstRef = useRef(true);

  useEffect(() => {
    if (DEMO_MODE) return; // no backend in the offline demo preview
    const first = firstRef.current;
    firstRef.current = false;

    let cancelled = false;

    const record = () => {
      void resolveUserEmail()
        .catch(() => null)
        .then((email) => {
          if (cancelled) return;
          // SSO builds enforce sign-in, so a missing identity means the caller
          // is unauthenticated (or an embed where identity can't be read).
          // Skip it rather than record an unattributable "anonymous" view.
          if (isAuthConfigured() && !email) return;
          trackPageView({
            isEmbedded,
            // Only the initial load has a meaningful load time; omit it for
            // subsequent client-side navigations.
            loadTimeMs: first ? performance.now() - startRef.current : undefined,
            userEmail: email ?? null,
          });
        });
    };

    // Don't record a view the user never saw: defer until the page is actually
    // visible so background/prerendered tabs are only counted if viewed.
    let onVisible: (() => void) | undefined;
    if (document.visibilityState === 'visible') {
      record();
    } else {
      onVisible = () => {
        if (document.visibilityState === 'visible') {
          document.removeEventListener('visibilitychange', onVisible!);
          onVisible = undefined;
          record();
        }
      };
      document.addEventListener('visibilitychange', onVisible);
    }

    return () => {
      cancelled = true;
      if (onVisible) document.removeEventListener('visibilitychange', onVisible);
    };
  }, [location.pathname]);

  return null;
}
