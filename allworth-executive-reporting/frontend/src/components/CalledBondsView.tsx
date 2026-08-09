import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  IconButton,
  InputAdornment,
  MenuItem,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TableSortLabel,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import AutorenewIcon from '@mui/icons-material/Autorenew';
import SearchIcon from '@mui/icons-material/Search';
import { colors, sectionHeaderStyle } from '../theme';
import { fetchBondLadderCalled } from '../services/bondApi';
import type { CalledBondRow, CalledReport } from '../services/bondApi';

const money = (value: number | null | undefined) =>
  value == null
    ? '—'
    : value.toLocaleString(undefined, {
        style: 'currency',
        currency: 'USD',
        maximumFractionDigits: 0,
      });

const number = (value: number | null | undefined) =>
  value == null ? '—' : Math.abs(value).toLocaleString();

type ReviewFilter = 'all' | 'cash' | 'yellow' | 'unresolved';
type SortColumn =
  | 'account'
  | 'called_date'
  | 'called_bond'
  | 'quantity'
  | 'redeemed'
  | 'cash'
  | 'cash_percent'
  | 'matching_buy'
  | 'review_result';

const localDateString = (date: Date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const defaultEndDate = () => localDateString(new Date());
const defaultStartDate = () => {
  const date = new Date();
  date.setDate(date.getDate() - 30);
  return localDateString(date);
};

const sortValue = (row: CalledBondRow, column: SortColumn): string | number => {
  switch (column) {
    case 'account': return row.account_number;
    case 'called_date': return row.trade_date ?? '';
    case 'called_bond': return row.cusip || row.symbol || row.description || '';
    case 'quantity': return Math.abs(row.quantity ?? 0);
    case 'redeemed': return Math.abs(row.amount ?? 0);
    case 'cash': return row.cash_value;
    case 'cash_percent': return row.cash_percent;
    case 'matching_buy':
      return row.matching_buy?.cusip || row.matching_buy?.symbol || row.matching_buy?.description || '';
    case 'review_result':
      return row.highlight === 'cash' ? 2 : row.highlight === 'yellow' ? 1 : 0;
  }
};

function SummaryCard({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <Card sx={{ flex: 1, minWidth: 150 }}>
      <CardContent sx={{ px: 2, py: 1.5, '&:last-child': { pb: 1.5 } }}>
        <Typography variant="caption" sx={{ textTransform: 'uppercase', letterSpacing: 0.5 }}>
          {label}
        </Typography>
        <Typography variant="h6" sx={{ color: color ?? colors.allworthNavy, mt: 0.25 }}>
          {value.toLocaleString()}
        </Typography>
      </CardContent>
    </Card>
  );
}

export default function CalledBondsView() {
  const [report, setReport] = useState<CalledReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>('all');
  const [accounts, setAccounts] = useState<string[]>([]);
  const [startDate, setStartDate] = useState(defaultStartDate);
  const [endDate, setEndDate] = useState(defaultEndDate);
  const [appliedDates, setAppliedDates] = useState({
    startDate: defaultStartDate(),
    endDate: defaultEndDate(),
  });
  const [sortColumn, setSortColumn] = useState<SortColumn>('called_date');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');

  const load = useCallback(async (forceRefresh = false) => {
    setLoading(true);
    setError(null);
    try {
      setReport(await fetchBondLadderCalled({
        startDate: appliedDates.startDate,
        endDate: appliedDates.endDate,
        forceRefresh,
      }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to load called bonds.');
    } finally {
      setLoading(false);
    }
  }, [appliedDates]);

  useEffect(() => {
    load();
  }, [load]);

  const accountOptions = useMemo(
    () => Array.from(new Set(report?.rows.map(row => row.account_number) ?? [])).sort(),
    [report],
  );

  const rows = useMemo(() => {
    if (!report) return [];
    const query = search.trim().toLowerCase();
    const selectedAccounts = new Set(accounts);
    const filtered = report.rows.filter(row => {
      if (selectedAccounts.size && !selectedAccounts.has(row.account_number)) return false;
      if (reviewFilter === 'cash' && row.highlight !== 'cash') return false;
      if (reviewFilter === 'yellow' && row.highlight !== 'yellow') return false;
      if (reviewFilter === 'unresolved' && row.highlight !== null) return false;
      if (!query) return true;
      return [
        row.account_number,
        row.account_name,
        row.cusip,
        row.symbol,
        row.description,
        row.notes,
        row.matching_buy?.cusip,
        row.matching_buy?.description,
      ].some(value => (value ?? '').toLowerCase().includes(query));
    });
    return [...filtered].sort((left, right) => {
      const leftValue = sortValue(left, sortColumn);
      const rightValue = sortValue(right, sortColumn);
      const result =
        typeof leftValue === 'number' && typeof rightValue === 'number'
          ? leftValue - rightValue
          : String(leftValue).localeCompare(String(rightValue), undefined, {
              numeric: true,
              sensitivity: 'base',
            });
      if (result !== 0) return sortDirection === 'asc' ? result : -result;
      return left.account_number.localeCompare(right.account_number, undefined, { numeric: true });
    });
  }, [accounts, report, reviewFilter, search, sortColumn, sortDirection]);

  const dateError =
    !startDate || !endDate
      ? 'Choose both dates.'
      : startDate > endDate
        ? 'From date must be on or before To date.'
        : '';

  const applyDates = () => {
    if (dateError) return;
    setAccounts([]);
    setAppliedDates({ startDate, endDate });
  };

  const handleSort = (column: SortColumn) => {
    if (sortColumn === column) {
      setSortDirection(direction => direction === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(column);
      setSortDirection(column === 'called_date' ? 'desc' : 'asc');
    }
  };

  const SortCell = ({
    column,
    label,
    align = 'left',
  }: {
    column: SortColumn;
    label: string;
    align?: 'left' | 'right';
  }) => (
    <TableCell align={align}>
      <TableSortLabel
        active={sortColumn === column}
        direction={sortColumn === column ? sortDirection : 'asc'}
        onClick={() => handleSort(column)}
      >
        {label}
      </TableSortLabel>
    </TableCell>
  );

  return (
    <Box sx={{ p: { xs: 1, sm: 2 } }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2 }}>
        <AutorenewIcon sx={{ color: colors.allworthNavy, fontSize: 28 }} />
        <Box sx={{ flex: 1 }}>
          <Typography variant="h5" sx={{ ...sectionHeaderStyle, mb: 0 }}>
            Recently Called Bonds
          </Typography>
          <Typography variant="caption" sx={{ color: colors.inkSecondary }}>
            REDEMP sells, excluding maturities · {appliedDates.startDate} through {appliedDates.endDate}
          </Typography>
        </Box>
        <Tooltip title="Refresh from the warehouse">
          <span>
            <IconButton
              size="small"
              disabled={loading}
              onClick={() => load(true)}
              sx={{
                color: colors.allworthNavy,
                animation: loading ? 'spin 1s linear infinite' : undefined,
                '@keyframes spin': {
                  '0%': { transform: 'rotate(0deg)' },
                  '100%': { transform: 'rotate(360deg)' },
                },
              }}
            >
              <AutorenewIcon fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>
      </Box>

      {report && (
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, mb: 2 }}>
          <SummaryCard label="Called" value={report.count} />
          <SummaryCard label="Cash Available" value={report.cash_flagged_count} color={colors.gain} />
          <SummaryCard label="Bond Purchased" value={report.reinvested_count} color="#8A6D00" />
          <SummaryCard label="Unresolved" value={report.unresolved_count} color={colors.loss} />
        </Box>
      )}

      <Alert severity="info" sx={{ mb: 2 }}>
        Green rows have cash above 3% and enough cash to cover the redemption.
        Yellow rows did not pass that test but have a corresponding bond BUY
        with the same quantity, or the same transaction amount when the source
        does not publish quantity.
        Unresolved rows are intentionally left unhighlighted.
      </Alert>

      <Card sx={{ mb: 2, border: `1px solid ${colors.hairline}`, boxShadow: 'none' }}>
        <CardContent
          sx={{
            p: 1.5,
            display: 'grid',
            gridTemplateColumns: {
              xs: '1fr',
              sm: 'repeat(2, minmax(180px, 1fr))',
              lg: 'minmax(240px, 1.2fr) 210px minmax(220px, 1fr) 170px 170px auto',
            },
            gap: 1.25,
            '&:last-child': { pb: 1.5 },
          }}
        >
          <TextField
            size="small"
            placeholder="Search account, CUSIP, security…"
            value={search}
            onChange={event => setSearch(event.target.value)}
            slotProps={{
              input: {
                startAdornment: (
                  <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment>
                ),
              },
            }}
          />
          <TextField
            select
            size="small"
            label="Review result"
            value={reviewFilter}
            onChange={event => setReviewFilter(event.target.value as ReviewFilter)}
          >
            <MenuItem value="all">All results</MenuItem>
            <MenuItem value="cash">Cash available</MenuItem>
            <MenuItem value="yellow">Bond purchased</MenuItem>
            <MenuItem value="unresolved">Unresolved</MenuItem>
          </TextField>
          <Autocomplete
            multiple
            size="small"
            options={accountOptions}
            value={accounts}
            onChange={(_, value) => setAccounts(value)}
            limitTags={2}
            renderInput={params => <TextField {...params} label="Accounts" placeholder="All accounts" />}
          />
          <TextField
            type="date"
            size="small"
            label="From"
            value={startDate}
            onChange={event => setStartDate(event.target.value)}
            error={Boolean(dateError)}
            slotProps={{ inputLabel: { shrink: true } }}
          />
          <TextField
            type="date"
            size="small"
            label="To"
            value={endDate}
            onChange={event => setEndDate(event.target.value)}
            error={Boolean(dateError)}
            helperText={dateError || undefined}
            slotProps={{ inputLabel: { shrink: true } }}
          />
          <Button
            variant="contained"
            onClick={applyDates}
            disabled={
              loading
              || Boolean(dateError)
              || (
                startDate === appliedDates.startDate
                && endDate === appliedDates.endDate
              )
            }
            sx={{ minWidth: 92 }}
          >
            Apply
          </Button>
        </CardContent>
      </Card>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {loading && !report && <Skeleton variant="rounded" height={320} />}

      {report && (
        <Card sx={{ overflow: 'hidden' }}>
          <Box sx={{ overflowX: 'auto', maxHeight: 'max(360px, calc(100vh - 430px))' }}>
            <Table size="small" stickyHeader sx={{ minWidth: 1160 }}>
              <TableHead>
                <TableRow sx={{ '& th': { fontSize: '0.72rem', fontWeight: 700, whiteSpace: 'nowrap' } }}>
                  <SortCell column="account" label="Account" />
                  <SortCell column="called_date" label="Called Date" />
                  <SortCell column="called_bond" label="Called Bond" />
                  <SortCell column="quantity" label="Quantity" align="right" />
                  <SortCell column="redeemed" label="Redeemed" align="right" />
                  <SortCell column="cash" label="Cash" align="right" />
                  <SortCell column="cash_percent" label="Cash %" align="right" />
                  <SortCell column="matching_buy" label="Matching Bond BUY" />
                  <SortCell column="review_result" label="Review Result" />
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((row, index) => {
                  const backgroundColor =
                    row.highlight === 'cash'
                      ? '#E8F3E5'
                      : row.highlight === 'yellow'
                        ? '#FFF4B8'
                        : undefined;
                  return (
                    <TableRow
                      key={`${row.account_number}-${row.trade_date}-${row.cusip}-${index}`}
                      sx={{ backgroundColor, '& td': { fontSize: '0.72rem', py: 0.65 } }}
                    >
                      <TableCell>
                        <Typography variant="caption" sx={{ display: 'block', color: colors.allworthNavy, fontWeight: 700 }}>
                          {row.account_number}
                        </Typography>
                        <Typography variant="caption">{row.account_name || '—'}</Typography>
                      </TableCell>
                      <TableCell>{row.trade_date ? new Date(row.trade_date).toLocaleDateString() : '—'}</TableCell>
                      <TableCell>
                        <Typography variant="caption" sx={{ display: 'block', fontFamily: 'monospace' }}>
                          {row.cusip || row.symbol || '—'}
                        </Typography>
                        <Typography variant="caption">{row.description || row.notes || '—'}</Typography>
                      </TableCell>
                      <TableCell align="right">{number(row.quantity)}</TableCell>
                      <TableCell align="right">{money(Math.abs(row.amount ?? 0))}</TableCell>
                      <TableCell align="right">{money(row.cash_value)}</TableCell>
                      <TableCell align="right">{row.cash_percent.toFixed(2)}%</TableCell>
                      <TableCell>
                        {row.matching_buy ? (
                          <>
                            <Typography variant="caption" sx={{ display: 'block', fontFamily: 'monospace' }}>
                              {row.matching_buy.cusip || row.matching_buy.symbol || '—'}
                            </Typography>
                            <Typography variant="caption">
                              {row.matching_buy.trade_date
                                ? new Date(row.matching_buy.trade_date).toLocaleDateString()
                                : '—'} · {row.match_basis === 'quantity'
                                  ? number(row.matching_buy.quantity)
                                  : money(Math.abs(row.matching_buy.amount ?? 0))}
                            </Typography>
                          </>
                        ) : '—'}
                      </TableCell>
                      <TableCell>
                        {row.highlight === 'cash' ? (
                          <Chip size="small" color="success" label="Cash covers redemption" />
                        ) : row.highlight === 'yellow' ? (
                          <Chip
                            size="small"
                            label="Bond purchased"
                            sx={{ backgroundColor: '#F4D35E', color: '#4B3B00', fontWeight: 700 }}
                          />
                        ) : null}
                      </TableCell>
                    </TableRow>
                  );
                })}
                {rows.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={9} align="center" sx={{ py: 5, color: colors.inkSecondary }}>
                      No called bonds match the selected filters.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Box>
          <Box sx={{ px: 2, py: 1, borderTop: `1px solid ${colors.ice}` }}>
            <Typography variant="caption">
              {rows.length.toLocaleString()} of {report.count.toLocaleString()} redemption
              {report.count === 1 ? '' : 's'} · {report.start_date} through {report.end_date}
              {' · '}Sorted by {sortColumn.replaceAll('_', ' ')} ({sortDirection})
            </Typography>
          </Box>
        </Card>
      )}
    </Box>
  );
}
