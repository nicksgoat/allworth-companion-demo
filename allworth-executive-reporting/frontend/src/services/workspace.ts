import type { Assignment } from './admin';
import { requestJson } from './http';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000/api';
const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';

export interface WorkspaceAdvisor {
  advisor_id: string;
  name?: string;
  region?: string;
  title?: string;
  email?: string;
  resolution?: 'email' | 'override';
}

export interface WorkspaceMe {
  email: string;
  assignment: Assignment;
  home_tool_ids: string[];
  all_access: boolean;
  effective_tools: string[];
  advisor: WorkspaceAdvisor | null;
  advisor_status: 'resolved' | 'unresolved' | 'not_applicable';
}

export interface HouseholdContext {
  planning_household_id: string | null;
  crm_lead_id: string | null;
  salesforce_household_id: string | null;
  avhhid: string | null;
  name: string;
  advisor_id: string | null;
  advisor_name: string | null;
  aum: number;
  plan_status: 'published' | 'draft' | 'not_started';
  last_actuals_sync: string | null;
  freshness: 'available' | 'unknown';
  data_quality_warnings: number;
  data_quality_state: 'healthy' | 'warning';
}

export interface AdvisorHomeHousehold {
  household_id: string;
  name: string;
  total_assets: string;
  health_score: number;
  health_band: 'healthy' | 'watch' | 'at_risk';
  open_alerts: number;
  open_tasks: number;
  drift_flagged: boolean;
  publication_status: string;
  last_actuals_sync?: string | null;
  context: HouseholdContext;
}

export interface AdvisorHomeData {
  advisor: WorkspaceAdvisor;
  summary: { households: number; total_assets: string; at_risk: number; needs_attention: number; unpublished: number };
  households: AdvisorHomeHousehold[];
}

const demoMe: WorkspaceMe = {
  email: 'demo@allworth.com',
  assignment: { id: 'advisor-preview', name: 'Advisor', type: 'advisor', home_tool_ids: ['avantos', 'crm', 'financial_planning', 'pipeline_review', 'fee_calculator'] },
  home_tool_ids: ['avantos', 'crm', 'financial_planning', 'pipeline_review', 'fee_calculator'],
  all_access: true,
  effective_tools: [],
  advisor: { advisor_id: 'preview-advisor', name: 'Morgan Lee', title: 'Financial Advisor', region: 'Central' },
  advisor_status: 'resolved',
};

export const workspaceApi = {
  async me(): Promise<WorkspaceMe> {
    if (DEMO_MODE) return demoMe;
    return requestJson<WorkspaceMe>(`${API_BASE_URL}/workspace/me`);
  },
  async resolveHousehold(params: { planningId?: string | null; leadId?: string | null; hhid?: string | null; avhhid?: string | null }): Promise<HouseholdContext> {
    if (DEMO_MODE) {
      return {
        planning_household_id: params.planningId || 'preview-household', crm_lead_id: params.leadId || 'preview-client',
        salesforce_household_id: params.hhid || 'HH-1042', avhhid: params.avhhid || 'AV-1042', name: 'Evergreen Family',
        advisor_id: 'preview-advisor', advisor_name: 'Morgan Lee', aum: 5750000, plan_status: 'draft',
        last_actuals_sync: new Date(Date.now() - 86400000).toISOString(), freshness: 'available', data_quality_warnings: 1, data_quality_state: 'warning',
      };
    }
    const search = new URLSearchParams();
    if (params.planningId) search.set('planning_id', params.planningId);
    if (params.leadId) search.set('lead_id', params.leadId);
    if (params.hhid) search.set('hhid', params.hhid);
    if (params.avhhid) search.set('avhhid', params.avhhid);
    const data = await requestJson<{ household: HouseholdContext }>(`${API_BASE_URL}/workspace/households/resolve?${search}`);
    return data.household;
  },
  async resolveAdvisor(email: string, advisorId?: string | null): Promise<WorkspaceAdvisor> {
    if (DEMO_MODE) return demoMe.advisor!;
    const search = new URLSearchParams({ email });
    if (advisorId) search.set('advisor_id', advisorId);
    const data = await requestJson<{ advisor: WorkspaceAdvisor }>(`${API_BASE_URL}/workspace/advisors/resolve?${search}`);
    return data.advisor;
  },
  async advisorHome(advisorId?: string): Promise<AdvisorHomeData> {
    if (DEMO_MODE) return {
      advisor: demoMe.advisor!,
      summary: { households: 24, total_assets: '184500000', at_risk: 3, needs_attention: 8, unpublished: 5 },
      households: [
        { household_id: 'preview-household', name: 'Evergreen Family', total_assets: '5750000', health_score: 64, health_band: 'watch', open_alerts: 2, open_tasks: 1, drift_flagged: true, publication_status: 'unpublished', context: await this.resolveHousehold({ planningId: 'preview-household' }) },
        { household_id: 'northstar', name: 'Northstar Household', total_assets: '8400000', health_score: 48, health_band: 'at_risk', open_alerts: 1, open_tasks: 2, drift_flagged: false, publication_status: 'published', context: { ...(await this.resolveHousehold({ planningId: 'northstar', leadId: 'preview-102' })), name: 'Northstar Household', aum: 8400000 } },
        { household_id: 'stonebridge', name: 'Stonebridge Family', total_assets: '4200000', health_score: 91, health_band: 'healthy', open_alerts: 0, open_tasks: 1, drift_flagged: false, publication_status: 'published', context: { ...(await this.resolveHousehold({ planningId: 'stonebridge', leadId: 'preview-103' })), name: 'Stonebridge Family', aum: 4200000, plan_status: 'published' } },
      ],
    };
    const search = advisorId ? `?advisor_id=${encodeURIComponent(advisorId)}` : '';
    return requestJson<AdvisorHomeData>(`${API_BASE_URL}/workspace/advisor-home${search}`);
  },
};

export function householdHref(path: string, household: HouseholdContext | null): string {
  if (!household) return path;
  const params = new URLSearchParams();
  if (household.planning_household_id) params.set('household', household.planning_household_id);
  if (household.crm_lead_id) params.set('client', household.crm_lead_id);
  if (household.salesforce_household_id) params.set('hhid', household.salesforce_household_id);
  if (household.avhhid) params.set('avhhid', household.avhhid);
  return `${path}?${params}`;
}
