import { useCallback, useEffect, useState } from 'react';
import {
  Alert, Box, Button, Card, CardContent, Table, TableBody, TableCell, TableHead,
  TableRow, Typography,
} from '@mui/material';
import { planningApi, type PortalRecord } from '../services/planningApi';

interface Props {
  householdId: string;
  scenario: string;
  reports: Array<{ id: number; name: string }>;
  onError: (message: string) => void;
}

export default function ReportsTab({ householdId, scenario, reports, onError }: Props) {
  const [runs, setRuns] = useState<PortalRecord[]>([]);

  const load = useCallback(async () => {
    try { setRuns((await planningApi.reportHistory(householdId)).runs); }
    catch (e) { onError(e instanceof Error ? e.message : 'Unable to load report history'); }
  }, [householdId, onError]);

  useEffect(() => { void load(); }, [load]);

  function open(definitionId: number, scenarioId: string) {
    window.open(`/api/v1/scenarios/${scenarioId}/reports/${definitionId}`, '_blank', 'noopener,noreferrer');
    window.setTimeout(() => void load(), 1200); // refresh history after the render is logged
  }

  return <Box className="plan-panel">
    <Card><CardContent>
      <Typography variant="h6">Reports catalog</Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>Every report is derived from versioned facts and projection outputs.</Typography>
      <Box className="plan-report-grid">
        {reports.map(report =>
          <Button key={report.id} variant="outlined" onClick={() => open(report.id, scenario)}>{report.name}</Button>)}
      </Box>
    </CardContent></Card>
    <Card sx={{ mt: 2.5 }}><CardContent>
      <Typography variant="h6">Run history</Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>Audit trail of every report generated for this household.</Typography>
      {runs.length === 0 ? <Alert severity="info">No reports have been generated yet.</Alert>
        : <Table size="small">
          <TableHead><TableRow>
            <TableCell>Report</TableCell><TableCell>Scenario</TableCell>
            <TableCell>Generated</TableCell><TableCell>By</TableCell><TableCell align="right"></TableCell>
          </TableRow></TableHead>
          <TableBody>{runs.map(run =>
            <TableRow key={run.id}>
              <TableCell>{String(run.payload.definition_name)}</TableCell>
              <TableCell>{String(run.payload.scenario_name)}</TableCell>
              <TableCell>{new Date(run.created_at).toLocaleString()}</TableCell>
              <TableCell>{run.created_by}</TableCell>
              <TableCell align="right">
                <Button size="small" onClick={() => open(Number(run.payload.definition_id), String(run.payload.scenario_id))}>Re-run</Button>
              </TableCell>
            </TableRow>)}</TableBody>
        </Table>}
    </CardContent></Card>
  </Box>;
}
