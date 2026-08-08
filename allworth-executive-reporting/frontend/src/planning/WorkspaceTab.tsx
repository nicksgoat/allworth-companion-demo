import { useCallback, useEffect, useState } from 'react';
import {
  Alert, Box, Button, Card, CardContent, Checkbox, Chip, CircularProgress, List,
  ListItem, ListItemText, Stack, TextField, Typography,
} from '@mui/material';
import { planningApi, type FeedEvent, type PortalRecord } from '../services/planningApi';

const KIND_LABEL: Record<string, string> = {
  tasks: 'Task', alerts: 'Alert', organizer_change_requests: 'Organizer change',
};
const KIND_COLOR: Record<string, 'default' | 'primary' | 'warning'> = {
  tasks: 'primary', alerts: 'warning', organizer_change_requests: 'default',
};

const recordTitle = (record: PortalRecord) =>
  String(record.payload.title || record.payload.message || record.payload.summary || '(untitled)');

interface Props {
  householdId: string;
  householdName: string;
  onError: (message: string) => void;
}

export default function WorkspaceTab({ householdId, householdName, onError }: Props) {
  const [feed, setFeed] = useState<FeedEvent[]>([]);
  const [tasks, setTasks] = useState<PortalRecord[]>([]);
  const [alerts, setAlerts] = useState<PortalRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [newTask, setNewTask] = useState('');
  const [newAlert, setNewAlert] = useState('');
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [feedData, taskData, alertData] = await Promise.all([
        planningApi.advisorFeed(),
        planningApi.portalRecords(householdId, 'tasks'),
        planningApi.portalRecords(householdId, 'alerts'),
      ]);
      setFeed(feedData.events);
      setTasks(taskData.tasks || []);
      setAlerts(alertData.alerts || []);
    } catch (e) { onError(e instanceof Error ? e.message : 'Unable to load workspace'); }
    finally { setLoading(false); }
  }, [householdId, onError]);

  useEffect(() => { void load(); }, [load]);

  async function addRecord(kind: 'tasks' | 'alerts', title: string, reset: () => void) {
    if (!title.trim()) return;
    setSaving(true);
    try {
      await planningApi.createPortalRecord(householdId, kind, { title: title.trim(), status: 'open' });
      reset();
      await load();
    } catch (e) { onError(e instanceof Error ? e.message : 'Unable to save'); }
    finally { setSaving(false); }
  }

  async function toggleDone(record: PortalRecord) {
    const status = record.payload.status === 'done' ? 'open' : 'done';
    try {
      const updated = await planningApi.updatePortalRecord(householdId, 'tasks', record.id, { ...record.payload, status });
      setTasks(current => current.map(item => item.id === record.id ? updated : item));
    } catch (e) { onError(e instanceof Error ? e.message : 'Unable to update task'); }
  }

  if (loading) return <Box className="plan-loading"><CircularProgress /></Box>;

  return <Box className="plan-panel">
    <Box className="plan-decision" sx={{ gridTemplateColumns: { md: 'repeat(2, minmax(0,1fr))' } }}>
      <Card><CardContent>
        <Typography variant="h6">Tasks — {householdName}</Typography>
        <Typography color="text.secondary" sx={{ mb: 2 }}>Follow-ups for this household; check off when complete.</Typography>
        <Stack direction="row" sx={{ gap: 1.5, mb: 2 }}>
          <TextField size="small" fullWidth label="New task" value={newTask} onChange={e => setNewTask(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') void addRecord('tasks', newTask, () => setNewTask('')); }} />
          <Button variant="contained" onClick={() => void addRecord('tasks', newTask, () => setNewTask(''))} disabled={saving || !newTask.trim()}>Add</Button>
        </Stack>
        {tasks.length === 0 ? <Alert severity="info">No open tasks.</Alert>
          : <List dense>{tasks.map(record =>
            <ListItem key={record.id} disableGutters
              secondaryAction={<Checkbox edge="end" checked={record.payload.status === 'done'} onChange={() => void toggleDone(record)} />}>
              <ListItemText
                primary={<span style={{ textDecoration: record.payload.status === 'done' ? 'line-through' : 'none' }}>{recordTitle(record)}</span>}
                secondary={`${new Date(record.created_at).toLocaleDateString()} · ${record.created_by}`} />
            </ListItem>)}</List>}
      </CardContent></Card>
      <Card><CardContent>
        <Typography variant="h6">Alerts — {householdName}</Typography>
        <Typography color="text.secondary" sx={{ mb: 2 }}>Plan-level flags surfaced to the advisor feed.</Typography>
        <Stack direction="row" sx={{ gap: 1.5, mb: 2 }}>
          <TextField size="small" fullWidth label="New alert" value={newAlert} onChange={e => setNewAlert(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') void addRecord('alerts', newAlert, () => setNewAlert('')); }} />
          <Button variant="contained" onClick={() => void addRecord('alerts', newAlert, () => setNewAlert(''))} disabled={saving || !newAlert.trim()}>Add</Button>
        </Stack>
        {alerts.length === 0 ? <Alert severity="info">No active alerts.</Alert>
          : <List dense>{alerts.map(record =>
            <ListItem key={record.id} disableGutters>
              <ListItemText primary={recordTitle(record)}
                secondary={`${new Date(record.created_at).toLocaleDateString()} · ${record.created_by}`} />
            </ListItem>)}</List>}
      </CardContent></Card>
    </Box>
    <Card sx={{ mt: 2.5 }}><CardContent>
      <Typography variant="h6">Advisor feed</Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>Latest tasks, alerts, and organizer changes across every household you can access.</Typography>
      {feed.length === 0 ? <Alert severity="info">Nothing in the feed yet.</Alert>
        : <List dense>{feed.slice(0, 25).map(event =>
          <ListItem key={event.id} disableGutters>
            <Chip size="small" color={KIND_COLOR[event.kind] || 'default'} label={KIND_LABEL[event.kind] || event.kind} sx={{ mr: 1.5 }} />
            <ListItemText primary={recordTitle(event)}
              secondary={`${event.household_name} · ${new Date(event.updated_at).toLocaleString()} · ${event.created_by}`} />
          </ListItem>)}</List>}
    </CardContent></Card>
  </Box>;
}
