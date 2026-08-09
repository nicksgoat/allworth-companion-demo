import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { IMPERSONATION_EVENT, readImpersonation } from '../services/access';
import { workspaceApi, type HouseholdContext, type WorkspaceMe } from '../services/workspace';

interface WorkspaceState {
  me: WorkspaceMe | null;
  household: HouseholdContext | null;
  loading: boolean;
  householdLoading: boolean;
}

const WorkspaceContext = createContext<WorkspaceState>({ me: null, household: null, loading: true, householdLoading: false });

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const [me, setMe] = useState<WorkspaceMe | null>(null);
  const [loading, setLoading] = useState(true);
  const [household, setHousehold] = useState<HouseholdContext | null>(null);
  const [householdLoading, setHouseholdLoading] = useState(false);

  useEffect(() => {
    let live = true;
    const load = async () => {
      setLoading(true);
      const imp = readImpersonation();
      if (imp?.assignment) {
        const effective = new Set(imp.tools);
        const configured = imp.assignment.home_tool_ids.filter((tool) => effective.has(tool));
        let advisor = imp.advisor ?? null;
        if (imp.assignment.type === 'advisor' && !advisor) {
          try { advisor = await workspaceApi.resolveAdvisor(imp.email); } catch { advisor = null; }
        }
        if (live) {
          setMe({ email: imp.email, assignment: imp.assignment, home_tool_ids: configured,
            all_access: false, effective_tools: imp.tools, advisor,
            advisor_status: imp.assignment.type === 'advisor' ? (advisor ? 'resolved' : 'unresolved') : 'not_applicable' });
          setLoading(false);
        }
        return;
      }
      try { const result = await workspaceApi.me(); if (live) setMe(result); }
      catch { if (live) setMe(null); }
      finally { if (live) setLoading(false); }
    };
    void load();
    const reload = () => void load();
    window.addEventListener(IMPERSONATION_EVENT, reload);
    return () => { live = false; window.removeEventListener(IMPERSONATION_EVENT, reload); };
  }, []);

  useEffect(() => {
    const search = new URLSearchParams(location.search);
    const planningId = search.get('household');
    const leadId = search.get('client');
    const hhid = search.get('hhid');
    const avhhid = search.get('avhhid');
    if (!planningId && !leadId && !hhid && !avhhid) { setHousehold(null); return; }
    let live = true;
    setHouseholdLoading(true);
    void workspaceApi.resolveHousehold({ planningId, leadId, hhid, avhhid })
      .then((value) => { if (live) setHousehold(value); })
      .catch(() => { if (live) setHousehold(null); })
      .finally(() => { if (live) setHouseholdLoading(false); });
    return () => { live = false; };
  }, [location.search]);

  const value = useMemo(() => ({ me, household, loading, householdLoading }), [me, household, loading, householdLoading]);
  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace() { return useContext(WorkspaceContext); }
