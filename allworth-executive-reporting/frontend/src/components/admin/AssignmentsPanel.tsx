import { useState } from 'react';
import { adminApi, type AdminUser, type Assignment, type AssignmentType, type Tool } from '../../services/admin';

const ASSIGNMENT_LABELS: Record<AssignmentType, string> = {
  advisor: 'Advisor', executive: 'Executive', operations: 'Operations',
  platform_admin: 'Platform Admin', general: 'General',
};

interface AssignmentsPanelProps {
  assignments: Assignment[];
  tools: Tool[];
  users: AdminUser[];
  onChanged: () => Promise<void>;
  onToast: (kind: 'ok' | 'err', message: string) => void;
}

export function AssignmentsPanel({ assignments, tools, users, onChanged, onToast }: AssignmentsPanelProps) {
  const [name, setName] = useState('');
  const [type, setType] = useState<AssignmentType>('general');
  const [homeTools, setHomeTools] = useState<string[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
  const assignable = tools.filter((tool) => tool.status !== 'soon');

  const reset = () => { setName(''); setType('general'); setHomeTools([]); setEditing(null); };
  const start = (assignment: Assignment) => {
    setEditing(assignment.id); setName(assignment.name); setType(assignment.type); setHomeTools(assignment.home_tool_ids);
  };
  const toggle = (toolId: string) => setHomeTools((current) => current.includes(toolId) ? current.filter((id) => id !== toolId) : [...current, toolId]);
  const save = async () => {
    if (!name.trim()) return;
    try {
      if (editing) await adminApi.updateAssignment(editing, name.trim(), type, homeTools);
      else await adminApi.addAssignment(name.trim(), type, homeTools);
      onToast('ok', editing ? `Updated ${name.trim()}` : `Created ${name.trim()}`);
      reset();
      await onChanged();
    } catch (error) {
      onToast('err', error instanceof Error ? error.message : String(error));
    }
  };
  const remove = async (assignment: Assignment) => {
    try {
      await adminApi.removeAssignment(assignment.id);
      onToast('ok', `Deleted ${assignment.name}`);
      await onChanged();
    } catch (error) {
      onToast('err', error instanceof Error ? error.message : String(error));
    }
  };

  return <section className="admin-panel admin-assignments-panel">
    <div className="admin-assignment-editor">
      <div><p className="admin-section-label">{editing ? 'Edit assignment' : 'New assignment'}</p><h2>{editing ? name : 'Create a governed workspace'}</h2></div>
      <label><span>Name</span><input value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Central region advisors" /></label>
      <label><span>Home type</span><select value={type} onChange={(event) => setType(event.target.value as AssignmentType)}>{Object.entries(ASSIGNMENT_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <div className="admin-assignment-tools"><span>Home tools</span><div>{assignable.map((tool) => <label key={tool.id} className={homeTools.includes(tool.id) ? 'selected' : ''}><input type="checkbox" checked={homeTools.includes(tool.id)} onChange={() => toggle(tool.id)} />{tool.name}</label>)}</div></div>
      <div className="admin-assignment-actions"><button className="admin-primary" onClick={save} disabled={!name.trim()}>{editing ? 'Save changes' : 'Create assignment'}</button>{editing && <button className="admin-secondary" onClick={reset}>Cancel</button>}</div>
    </div>
    <div className="admin-assignment-list">{assignments.map((assignment) => {
      const count = users.filter((user) => (user.assignment_id || 'general') === assignment.id).length;
      return <article key={assignment.id} className="admin-assignment-card">
        <header><div><span>{ASSIGNMENT_LABELS[assignment.type]}</span><h3>{assignment.name}</h3></div><b>{count} {count === 1 ? 'user' : 'users'}</b></header>
        <p>{assignment.home_tool_ids.length ? assignment.home_tool_ids.map((id) => tools.find((tool) => tool.id === id)?.name || id).join(' · ') : 'Uses the permission-filtered general hub'}</p>
        {!assignment.built_in && <footer><button className="admin-secondary" onClick={() => start(assignment)}>Edit</button><button className="admin-danger" onClick={() => void remove(assignment)}>Delete</button></footer>}
      </article>;
    })}</div>
  </section>;
}
