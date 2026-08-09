import { householdHref } from '../services/workspace';
import { useWorkspace } from './WorkspaceContext';
import './RelationshipSpine.css';

function money(value: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', notation: 'compact', maximumFractionDigits: 1 }).format(value);
}

export function RelationshipSpine() {
  const { household, householdLoading } = useWorkspace();
  if (householdLoading) return <div className="relationship-spine relationship-spine-loading">Restoring household context…</div>;
  if (!household) return null;
  const status = household.plan_status === 'published' ? 'Plan published' : household.plan_status === 'draft' ? 'Plan in progress' : 'Plan not started';
  return (
    <section className="relationship-spine" aria-label={`Active household: ${household.name}`}>
      <div className="relationship-identity">
        <span>Active household</span>
        <strong>{household.name}</strong>
        <small>{household.advisor_name || 'Advisor not assigned'}</small>
      </div>
      <div className="relationship-facts">
        <span><small>Relationship</small><strong>{money(household.aum)}</strong></span>
        <span><small>Planning</small><strong>{status}</strong></span>
        <span><small>Data status</small><strong>{household.data_quality_warnings ? `${household.data_quality_warnings} to review` : 'Current'}</strong></span>
      </div>
      <nav className="relationship-actions" aria-label="Household tools">
        <a href={householdHref('/crm', household)}>Relationship</a>
        <a href={householdHref('/planning', household)} className={!household.planning_household_id ? 'disabled' : ''}>Plan</a>
        <a href={householdHref('/pipeline-review', household)}>Pipeline</a>
        <a href={householdHref('/fee-calculator', household)}>Pricing</a>
      </nav>
    </section>
  );
}
