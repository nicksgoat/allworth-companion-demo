import { useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Chip,
  InputAdornment,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import type { PreviewResponse, EmailBatchRow, RowStatus } from '../services/emailBatchApi';

const STATUS_META: Record<RowStatus, { label: string; color: 'success' | 'warning' | 'error' }> = {
  ready: { label: 'Ready', color: 'success' },
  missing_email: { label: 'No email', color: 'warning' },
  missing_advisor: { label: 'No advisor', color: 'error' },
};

interface AdvisorRollup {
  advisor: string;
  emails: string[];
  accounts: number;
  missing: number;
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : value.toLocaleString(undefined, { maximumFractionDigits: 4 });
  }
  return String(value);
}

export default function EmailBatchReview({ preview }: { preview: PreviewResponse }) {
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<'all' | 'issues'>('all');

  const rows = preview.rows;

  const advisorRollup = useMemo<AdvisorRollup[]>(() => {
    const map = new Map<string, { advisor: string; emails: Set<string>; accounts: number; missing: number }>();
    for (const r of rows) {
      const key = r.__advisor ?? '(no advisor)';
      const entry = map.get(key) ?? { advisor: key, emails: new Set<string>(), accounts: 0, missing: 0 };
      entry.accounts += 1;
      if (r.__email) entry.emails.add(r.__email);
      else entry.missing += 1;
      map.set(key, entry);
    }
    return [...map.values()]
      .map((e) => ({ advisor: e.advisor, emails: [...e.emails], accounts: e.accounts, missing: e.missing }))
      .sort((a, b) => a.advisor.localeCompare(b.advisor));
  }, [rows]);

  const issues = useMemo(() => {
    const missingEmail = rows.filter((r) => r.__status === 'missing_email').length;
    const missingAdvisor = rows.filter((r) => r.__status === 'missing_advisor').length;
    const multiEmail = advisorRollup.filter((a) => a.emails.length > 1);
    return { missingEmail, missingAdvisor, multiEmail };
  }, [rows, advisorRollup]);

  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((r) => {
      if (filter === 'issues' && r.__status === 'ready') return false;
      if (!q) return true;
      const haystack = [r.__advisor, r.__email, ...preview.columns.map((c) => r[c])]
        .map((v) => (v == null ? '' : String(v)))
        .join(' ')
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [rows, search, filter, preview.columns]);

  const hasIssues = issues.missingEmail > 0 || issues.missingAdvisor > 0 || issues.multiEmail.length > 0;

  function rollupStatus(a: AdvisorRollup): { label: string; color: 'success' | 'warning' | 'error' } {
    if (a.emails.length > 1) return { label: 'Multiple emails', color: 'error' };
    if (a.emails.length === 0) return { label: 'No email', color: 'warning' };
    if (a.missing > 0) return { label: 'Partial', color: 'warning' };
    return { label: 'Ready', color: 'success' };
  }

  return (
    <Box>
      {/* Validation summary */}
      {hasIssues ? (
        <Alert severity="warning" sx={{ mb: 2 }}>
          <Typography sx={{ fontWeight: 700, mb: 0.5 }}>Review these before sending:</Typography>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {issues.missingEmail > 0 && <li>{issues.missingEmail} row(s) have an advisor but no resolved email — they will be skipped.</li>}
            {issues.missingAdvisor > 0 && <li>{issues.missingAdvisor} row(s) have no advisor value.</li>}
            {issues.multiEmail.length > 0 && (
              <li>
                {issues.multiEmail.length} advisor(s) map to more than one email:{' '}
                {issues.multiEmail.map((a) => a.advisor).join(', ')}
              </li>
            )}
          </ul>
        </Alert>
      ) : (
        <Alert severity="success" sx={{ mb: 2 }}>
          Every row has a resolved advisor and email. Nothing looks off.
        </Alert>
      )}

      {/* Summary chips */}
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 2 }}>
        <Chip size="small" label={`${preview.total_rows} rows`} />
        <Chip size="small" color="success" variant="outlined" label={`${preview.sendable_rows} sendable rows`} />
        <Chip size="small" label={`${advisorRollup.length} advisors`} />
        {Object.entries(preview.numeric_totals).map(([col, total]) => (
          <Chip
            key={col}
            size="small"
            variant="outlined"
            label={`Σ ${col}: ${total.toLocaleString(undefined, { maximumFractionDigits: 2 })}`}
          />
        ))}
      </Box>

      {/* Advisor rollup */}
      <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
        Advisors ({advisorRollup.length})
      </Typography>
      <TableContainer sx={{ mb: 3, border: '1px solid rgba(23,61,103,0.08)', borderRadius: 2, maxHeight: 280 }}>
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 700 }}>Advisor</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>Email(s)</TableCell>
              <TableCell sx={{ fontWeight: 700 }} align="right">Accounts</TableCell>
              <TableCell sx={{ fontWeight: 700 }}>Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {advisorRollup.map((a) => {
              const s = rollupStatus(a);
              return (
                <TableRow key={a.advisor} hover>
                  <TableCell>{a.advisor}</TableCell>
                  <TableCell sx={{ color: a.emails.length ? 'inherit' : 'text.disabled' }}>
                    {a.emails.length ? a.emails.join(', ') : '—'}
                  </TableCell>
                  <TableCell align="right">{a.accounts}</TableCell>
                  <TableCell>
                    <Chip size="small" color={s.color} variant="outlined" label={s.label} />
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>

      {/* Full data table */}
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'center', mb: 1 }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 700, mr: 'auto' }}>
          All rows ({filteredRows.length} of {rows.length})
        </Typography>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={filter}
          onChange={(_, v) => v && setFilter(v)}
        >
          <ToggleButton value="all" sx={{ textTransform: 'none' }}>All</ToggleButton>
          <ToggleButton value="issues" sx={{ textTransform: 'none' }}>Issues only</ToggleButton>
        </ToggleButtonGroup>
        <TextField
          size="small"
          placeholder="Search…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon fontSize="small" />
                </InputAdornment>
              ),
            },
          }}
        />
      </Box>
      <TableContainer sx={{ border: '1px solid rgba(23,61,103,0.08)', borderRadius: 2, maxHeight: 520 }}>
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 700, whiteSpace: 'nowrap' }}>Status</TableCell>
              <TableCell sx={{ fontWeight: 700, whiteSpace: 'nowrap' }}>Email (resolved)</TableCell>
              {preview.columns.map((c) => (
                <TableCell key={c} sx={{ fontWeight: 700, whiteSpace: 'nowrap' }}>
                  {c}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {filteredRows.map((r: EmailBatchRow, i) => {
              const meta = STATUS_META[r.__status];
              return (
                <TableRow
                  key={i}
                  hover
                  sx={{ backgroundColor: r.__status === 'ready' ? 'inherit' : 'rgba(255,167,38,0.08)' }}
                >
                  <TableCell>
                    <Chip size="small" color={meta.color} variant="outlined" label={meta.label} />
                  </TableCell>
                  <TableCell sx={{ whiteSpace: 'nowrap', color: r.__email ? 'inherit' : 'text.disabled' }}>
                    {r.__email ?? '—'}
                  </TableCell>
                  {preview.columns.map((c) => (
                    <TableCell key={c} sx={{ whiteSpace: 'nowrap' }}>
                      {formatCell(r[c])}
                    </TableCell>
                  ))}
                </TableRow>
              );
            })}
            {filteredRows.length === 0 && (
              <TableRow>
                <TableCell colSpan={preview.columns.length + 2} align="center" sx={{ color: 'text.secondary', py: 3 }}>
                  No rows match the current filter.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}
