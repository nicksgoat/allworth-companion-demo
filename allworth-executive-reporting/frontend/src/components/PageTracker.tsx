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
import { resolveUserEmail } from '../services/auth';

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
    void resolveUserEmail()
      .catch(() => null)
      .then((email) => {
        trackPageView({
          isEmbedded,
          // Only the initial load has a meaningful load time; omit it for
          // subsequent client-side navigations.
          loadTimeMs: first ? performance.now() - startRef.current : undefined,
          userEmail: email ?? null,
        });
      });
  }, [location.pathname]);

  return null;
}
