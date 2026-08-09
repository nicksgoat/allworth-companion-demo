import { lazy, Suspense, useState, useMemo, useCallback, useEffect, useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import {
  Box, Button, Card, CardContent, Chip, Alert, Typography,
  Dialog, DialogContent, DialogTitle, LinearProgress,
  Table, TableBody, TableCell, TableHead, TableRow,
  TableSortLabel, ToggleButton, ToggleButtonGroup, TextField, InputAdornment,
  Skeleton, Tooltip, IconButton, Autocomplete,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import AccountBalanceIcon from '@mui/icons-material/AccountBalance';
import RefreshIcon from '@mui/icons-material/Refresh';
import PrintIcon from '@mui/icons-material/Print';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import CloseIcon from '@mui/icons-material/Close';
import { colors, sectionHeaderStyle } from '../theme';
import { fetchBondLadder, refreshBondLadder } from '../services/bondApi';
import type { BondLadderResult } from '../services/bondApi';
import { printReport } from '../utils/print';

const AccountAnalyzer = lazy(() => import('./AccountAnalyzer'));

// ─── Fitch rating colour coding ───────────────────────────────────────────────
const FITCH_COLORS: Record<string, string> = {
  AAA: '#1B5E20', 'AA+': '#2E7D32', AA: '#2E7D32', 'AA-': '#388E3C',
  'A+': '#43A047', A: '#43A047', 'A-': '#66BB6A',
  'BBB+': '#F57F17', BBB: '#F57F17', 'BBB-': '#F9A825',
  'BB+': '#E65100', BB: '#E65100', 'BB-': '#EF6C00',
  'B+': '#B71C1C', B: '#B71C1C', 'B-': '#C62828',
  NR: '#828282', 'N/R': '#828282',
};
const ratingColor = (r: string | null) => FITCH_COLORS[r ?? ''] ?? '#9E9E9E';

// ─── Strategy abbreviation label ─────────────────────────────────────────────
const stratLabel = (s: string) =>
  s.replace('AWF - Bond Ladder ', '').replace(' year', 'yr');

const formatCurrency = (v: number) =>
  v >= 1_000_000
    ? `$${(v / 1_000_000).toFixed(2)}M`
    : v >= 1_000
    ? `$${(v / 1_000).toFixed(0)}K`
    : `$${v.toFixed(0)}`;

// ─── Strategy palette ─────────────────────────────────────────────────────────
const STRAT_COLORS: Record<string, string> = {
  Municipal: '#1565C0',
  Corporate: '#6A1B9A',
  Treasury:  '#00695C',
};
const stratColor = (s: string) => {
  for (const k of Object.keys(STRAT_COLORS)) {
    if (s.includes(k)) return STRAT_COLORS[k];
  }
  return colors.allworthNavy;
};

// ─── Summary stat card ────────────────────────────────────────────────────────
function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <Card sx={{ flex: { xs: '0 0 calc(50% - 8px)', sm: 1 }, minWidth: { xs: 0, sm: 140 } }}>
      <CardContent sx={{ py: 1.5, px: 2, '&:last-child': { pb: 1.5 } }}>
        <Typography variant="caption" sx={{ color: colors.inkSecondary, textTransform: 'uppercase', letterSpacing: 0.5 }}>
          {label}
        </Typography>
        <Typography variant="h6" sx={{ fontWeight: 700, color: colors.allworthNavy, mt: 0.25 }}>
          {value}
        </Typography>
      </CardContent>
    </Card>
  );
}

// ─── Skeleton while loading ───────────────────────────────────────────────────
function LoadingSkeleton() {
  return (
    <Box>
      <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
        {[1, 2, 3, 4].map(i => <Skeleton key={i} variant="rectangular" height={72} sx={{ flex: 1, borderRadius: 1 }} />)}
      </Box>
      <Skeleton variant="rectangular" height={40} sx={{ mb: 1, borderRadius: 1 }} />
      {[1,2,3,4,5,6,7,8].map(i => <Skeleton key={i} variant="rectangular" height={44} sx={{ mb: 0.5, borderRadius: 1 }} />)}
    </Box>
  );
}

// ─── Sort types ───────────────────────────────────────────────────────────────
type SortCol =
  | 'account_number' | 'account_name' | 'strategy'
  | 'issuer' | 'state' | 'quantity' | 'market_value'
  | 'coupon' | 'yield_to_worst' | 'maturity_date' | 'call_date' | 'fitch_rating';

export default function BondLadderView() {
  const [sortBy, setSortBy] = useState<'maturity' | 'call_date'>('maturity');
  const [strategy, setStrategy] = useState<string>('ALL');
  const [search, setSearch] = useState('');
  const [colSort, setColSort] = useState<SortCol>('maturity_date');
  const [colDir, setColDir] = useState<'asc' | 'desc'>('asc');
  // Secondary sort: when primary col ties, sort by account_number
  const secondarySort: SortCol = 'account_number';
  const [accountFilter, setAccountFilter] = useState<{ num: string; label: string }[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<{ number: string; name: string } | null>(null);
  // Alert filters (can be combined)
  const [alertFilters, setAlertFilters] = useState<Set<'downgraded30' | 'matures60'>>(new Set());

  const toggleAlert = (key: 'downgraded30' | 'matures60') => {
    setAlertFilters(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const [data, setData] = useState<BondLadderResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async (forceRefresh = false) => {
    if (forceRefresh) setRefreshing(true); else setLoading(true);
    setError(null);
    try {
      if (forceRefresh) await refreshBondLadder();
      const result = await fetchBondLadder(
        strategy === 'ALL' ? undefined : strategy,
        sortBy,
        forceRefresh,
      );
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [strategy, sortBy]);

  useEffect(() => { load(); }, [load]);

  // Alert counts over the full unfiltered bond list
  const alertCounts = useMemo(() => {
    if (!data) return { downgraded30: 0, matures60: 0 };
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const d60 = new Date(today); d60.setDate(d60.getDate() + 60);
    let downgraded30 = 0, matures60 = 0;
    for (const b of data.bonds) {
      if (b.is_downgraded) {
        // Use effective date if available, otherwise count all downgrades
        const effDate = b.fitch_rating_effective_date ? new Date(b.fitch_rating_effective_date) : null;
        const cutoff = new Date(today.getTime() - 30 * 86_400_000);
        if (!effDate || effDate >= cutoff) downgraded30++;
      }
      if (b.maturity_date) { const md = new Date(b.maturity_date); if (md >= today && md <= d60) matures60++; }
    }
    return { downgraded30, matures60 };
  }, [data]);

  // Sorted unique accounts for the account filter dropdown
  const accountOptions = useMemo(() => {
    if (!data) return [];
    const seen = new Map<string, string>();
    for (const b of data.bonds) {
      if (!seen.has(b.account_number))
        seen.set(b.account_number, `${b.account_number} — ${b.account_name}`);
    }
    return Array.from(seen.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([num, label]) => ({ num, label }));
  }, [data]);

  const strategyOptions = useMemo(() => ['ALL', ...(data?.strategies ?? [])], [data]);

  // Client-side column sort + search on top of server-sorted data
  const rows = useMemo(() => {
    if (!data) return [];
    let filtered = data.bonds;

    if (search.trim()) {
      const q = search.trim().toLowerCase();
      filtered = filtered.filter(b =>
        b.account_number.toLowerCase().includes(q) ||
        b.account_name.toLowerCase().includes(q) ||
        b.issuer.toLowerCase().includes(q) ||
        b.cusip.toLowerCase().includes(q) ||
        (b.fitch_rating ?? '').toLowerCase().includes(q) ||
        b.strategy.toLowerCase().includes(q)
      );
    }

    if (accountFilter.length > 0) {
      const nums = new Set(accountFilter.map(a => a.num));
      filtered = filtered.filter(b => nums.has(b.account_number));
    }

    if (alertFilters.size > 0) {
      const today = new Date(); today.setHours(0, 0, 0, 0);
      const d60 = new Date(today); d60.setDate(d60.getDate() + 60);
      filtered = filtered.filter(b => {
        if (alertFilters.has('downgraded30') && b.is_downgraded) {
          const effDate = b.fitch_rating_effective_date ? new Date(b.fitch_rating_effective_date) : null;
          const cutoff = new Date(today.getTime() - 30 * 86_400_000);
          if (!effDate || (effDate >= cutoff)) return true;
        }
        if (alertFilters.has('matures60') && b.maturity_date) {
          const md = new Date(b.maturity_date);
          if (md >= today && md <= d60) return true;
        }
        return false;
      });
    }

    return [...filtered].sort((a, b) => {
      const rec = (x: typeof a) => x as unknown as Record<string, unknown>;
      const av = rec(a)[colSort] ?? '';
      const bv = rec(b)[colSort] ?? '';
      if (av < bv) return colDir === 'asc' ? -1 : 1;
      if (av > bv) return colDir === 'asc' ? 1 : -1;
      // Tie-break: secondary sort by account_number asc
      const as2 = rec(a)[secondarySort] ?? '';
      const bs2 = rec(b)[secondarySort] ?? '';
      if (as2 < bs2) return -1;
      if (as2 > bs2) return 1;
      return 0;
    });
  }, [data, search, accountFilter, alertFilters, colSort, colDir, secondarySort]);

  const handleColSort = (col: SortCol) => {
    if (colSort === col) {
      setColDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setColSort(col);
      setColDir('asc');
    }
  };

  const handlePrint = () => {
    const fmtDate = (d: string | null) => (d ? new Date(d).toLocaleDateString() : '—');
    const activeAlerts = Array.from(alertFilters).map(k =>
      k === 'downgraded30' ? 'Downgraded' : 'Matures ≤60d',
    );
    printReport({
      title: 'Bond Ladder Monitor',
      subtitle: 'AWF Bond Ladder strategies · Individual Bonds · Reinvest accounts only',
      meta: [
        { label: 'Strategy', value: strategy === 'ALL' ? 'All Strategies' : strategy },
        { label: 'Holdings', value: rows.length.toLocaleString() },
        { label: 'Total Market Value', value: formatCurrency(rows.reduce((s, b) => s + b.market_value, 0)) },
        ...(search ? [{ label: 'Search', value: search }] : []),
        ...(activeAlerts.length ? [{ label: 'Alerts', value: activeAlerts.join(', ') }] : []),
      ],
      columns: [
        { header: 'Account #', value: b => b.account_number },
        { header: 'Account Name', value: b => b.account_name },
        { header: 'Strategy', value: b => stratLabel(b.strategy) },
        { header: 'Issuer', value: b => b.issuer || b.description },
        { header: 'Fitch', value: b => b.fitch_rating ?? '—' },
        { header: 'State', value: b => b.state || '—' },
        { header: 'Qty', value: b => b.quantity.toLocaleString(), align: 'right' },
        { header: 'Market Value', value: b => formatCurrency(b.market_value), align: 'right' },
        { header: 'Coupon', value: b => `${b.coupon.toFixed(3)}%`, align: 'right' },
        { header: 'YTW', value: b => `${b.yield_to_worst.toFixed(3)}%`, align: 'right' },
        { header: 'Maturity', value: b => fmtDate(b.maturity_date), align: 'right' },
        { header: 'Call Date', value: b => fmtDate(b.call_date), align: 'right' },
      ],
      rows,
    });
  };

  // ── Virtualizer setup ──────────────────────────────────────────────────────
  const ROW_HEIGHT = 33; // px — compact row for smaller font
  // Fills remaining viewport: subtract hero (~88px) + tabs (~49px) + card padding (~48px)
  // + page header (~60px) + stat cards (~90px) + two filter rows (~88px) + footer (~40px)
  const TABLE_VIEWPORT_HEIGHT = 'max(300px, calc(100vh - 480px))';
  const tableBodyRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => tableBodyRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 10, // render 10 extra rows above/below for smooth scrolling
  });

  const virtualItems = virtualizer.getVirtualItems();
  // Padding rows so the scrollbar thumb is accurate
  const paddingTop = virtualItems.length > 0 ? virtualItems[0].start : 0;
  const paddingBottom = virtualItems.length > 0
    ? virtualizer.getTotalSize() - virtualItems[virtualItems.length - 1].end
    : 0;

  const SortCell = ({ col, label, align = 'left' }: { col: SortCol; label: string; align?: 'left' | 'right' }) => (
    <TableCell align={align} sx={{ whiteSpace: 'nowrap', userSelect: 'none', fontWeight: 600, fontSize: '0.7rem', py: 0.75, px: 1 }}>
      <TableSortLabel
        active={colSort === col}
        direction={colSort === col ? colDir : 'asc'}
        onClick={() => handleColSort(col)}
        sx={{ '& .MuiTableSortLabel-icon': { opacity: colSort === col ? 1 : 0.3 } }}
      >
        {label}
      </TableSortLabel>
    </TableCell>
  );

  return (
    <Box sx={{ p: { xs: 1, sm: 2 } }}>
      {/* ── Page header ───────────────────────────────────────────────── */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2 }}>
        <AccountBalanceIcon sx={{ color: colors.allworthNavy, fontSize: 28 }} />
        <Box sx={{ flex: 1 }}>
          <Typography variant="h5" sx={{ ...sectionHeaderStyle, mb: 0 }}>
            Bond Ladder Monitor
          </Typography>
          <Typography variant="caption" sx={{ color: colors.inkSecondary }}>
            All accounts enrolled in AWF Bond Ladder strategies · Individual Bonds only
          </Typography>
        </Box>
        {/* Last refreshed + manual refresh */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          {data?.fetched_at && (
            <Typography variant="caption" sx={{ color: colors.inkSecondary, display: { xs: 'none', sm: 'block' } }}>
              Updated {new Date(data.fetched_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </Typography>
          )}
          <Tooltip title="Refresh from database" placement="left">
            <span>
              <IconButton
                size="small"
                onClick={() => load(true)}
                disabled={loading || refreshing}
                sx={{
                  color: colors.allworthNavy,
                  animation: refreshing ? 'spin 1s linear infinite' : undefined,
                  '@keyframes spin': { '0%': { transform: 'rotate(0deg)' }, '100%': { transform: 'rotate(360deg)' } },
                }}
              >
                <RefreshIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
          <Tooltip title="Print report" placement="left">
            <span>
              <IconButton
                size="small"
                onClick={handlePrint}
                disabled={loading || !data || rows.length === 0}
                sx={{ color: colors.allworthNavy }}
              >
                <PrintIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
        </Box>
      </Box>

      {/* ── Summary stats ─────────────────────────────────────────────── */}
      {data && !loading && (
        <Box sx={{ display: 'flex', gap: 2, mb: 2, flexWrap: 'wrap' }}>
          <StatCard label="Strategies" value={String(data.strategies.length)} />
          <StatCard label="Accounts" value={String(data.total_accounts)} />
          <StatCard label="Holdings" value={String(data.total_bonds)} />
          <StatCard label="Total Market Value" value={formatCurrency(data.total_market_value)} />
        </Box>
      )}
      {loading && (
        <Box sx={{ display: 'flex', gap: 2, mb: 2, flexWrap: 'wrap' }}>
          {[1,2,3,4].map(i => <Skeleton key={i} variant="rectangular" height={72} sx={{ flex: { xs: '0 0 calc(50% - 8px)', sm: 1 }, borderRadius: 1 }} />)}
        </Box>
      )}

      {/* ── Filter controls ───────────────────────────────────────────── */}
      <Card sx={{ mb: 2, border: `1px solid ${colors.hairline}`, boxShadow: 'none' }}>
        <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: {
                xs: '1fr',
                sm: 'minmax(220px, 1fr) minmax(210px, 1fr)',
                lg: '240px 210px minmax(240px, 1fr) minmax(260px, 1.2fr)',
              },
              gap: 1.25,
              alignItems: 'center',
            }}
          >
            <Autocomplete
              size="small"
              options={strategyOptions}
              value={strategy}
              getOptionLabel={option => option === 'ALL' ? 'All Strategies' : stratLabel(option)}
              onChange={(_, value) => setStrategy(value ?? 'ALL')}
              renderInput={params => <TextField {...params} label="Strategy" />}
              clearOnEscape
              disableClearable
            />

          <ToggleButtonGroup
            value={sortBy}
            exclusive
            size="small"
            onChange={(_, v) => { if (v) { setSortBy(v); setColSort(v === 'call_date' ? 'call_date' : 'maturity_date'); } }}
            sx={{
              width: '100%',
              '& .MuiToggleButton-root': {
                flex: 1,
                whiteSpace: 'nowrap',
                textTransform: 'none',
                fontSize: 12,
              },
            }}
          >
            <ToggleButton value="maturity">
              Sort: Maturity
            </ToggleButton>
            <ToggleButton value="call_date">
              Sort: Call Date
            </ToggleButton>
          </ToggleButtonGroup>

          <TextField
            size="small"
            placeholder="Search issuer, CUSIP…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            slotProps={{ input: { startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> } }}
            sx={{ width: '100%' }}
          />

          <Tooltip
            title={accountFilter.length > 0 ? accountFilter.map(a => a.label).join('\n') : ''}
            placement="top"
            arrow
            slotProps={{ tooltip: { sx: { whiteSpace: 'pre-line', maxWidth: 400 } } }}
          >
            <Autocomplete
              multiple
              size="small"
              options={accountOptions}
              getOptionLabel={o => o.num}
              renderOption={(props, o) => (
                <li {...props} key={o.num}>
                  <Typography variant="body2" noWrap>{o.label}</Typography>
                </li>
              )}
              value={accountFilter}
              onChange={(_, val) => setAccountFilter(val)}
              isOptionEqualToValue={(o, v) => o.num === v.num}
              disableCloseOnSelect
              limitTags={2}
              renderInput={params => (
                <TextField
                  {...params}
                  placeholder={accountFilter.length === 0 ? 'All accounts' : undefined}
                />
              )}
              sx={{ width: '100%' }}
              clearOnEscape
            />
          </Tooltip>
          </Box>

          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center', mt: 1.25 }}>
            <Typography variant="caption" sx={{ color: colors.inkSecondary, fontWeight: 600, mr: 0.5, textTransform: 'uppercase', letterSpacing: 0.5 }}>
              Alerts
            </Typography>
            {[
              { key: 'downgraded30' as const, label: `Downgraded (30d)`,    count: alertCounts.downgraded30, color: '#E65100' },
              { key: 'matures60'    as const, label: `Matures ≤60d`,        count: alertCounts.matures60,    color: '#1565C0' },
            ].map(({ key, label, count, color }) => (
              <Chip
                key={key}
                label={`${label}${count > 0 ? ` (${count})` : ''}`}
                onClick={() => toggleAlert(key)}
                variant={alertFilters.has(key) ? 'filled' : 'outlined'}
                size="small"
                sx={{
                  backgroundColor: alertFilters.has(key) ? color : undefined,
                  color: alertFilters.has(key) ? '#fff' : count > 0 ? color : undefined,
                  borderColor: count > 0 ? color : undefined,
                  fontWeight: count > 0 ? 700 : 500,
                  opacity: count === 0 ? 0.45 : 1,
                }}
              />
            ))}
          </Box>
        </CardContent>
      </Card>

      {/* ── Error state ───────────────────────────────────────────────── */}
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {/* ── Loading skeleton ──────────────────────────────────────────── */}
      {loading && !data && <LoadingSkeleton />}

      {/* ── Holdings table ────────────────────────────────────────────── */}
      {!loading && data && (
        <Card sx={{ overflow: 'hidden' }}>
          {/* Outer div: horizontal scroll on narrow screens */}
          <Box sx={{ overflowX: 'auto' }}>
            {/* Inner div: fixed-height vertical scroll container for the virtualizer */}
            <Box
              ref={tableBodyRef}
              sx={{ height: TABLE_VIEWPORT_HEIGHT, overflowY: 'auto', overflowX: 'visible' }}
            >
              <Table size="small" stickyHeader sx={{ tableLayout: 'fixed', minWidth: 960, fontSize: '0.72rem' }}>
                <colgroup>
                  <col style={{ width: 88 }}  />{/* Account # */}
                  <col style={{ width: 130 }} />{/* Account Name */}
                  <col style={{ width: 120 }} />{/* Strategy */}
                  <col style={{ width: 150 }} />{/* Issuer */}
                  <col style={{ width: 62 }}  />{/* Fitch */}
                  <col style={{ width: 46 }}  />{/* State */}
                  <col style={{ width: 68 }}  />{/* Qty */}
                  <col style={{ width: 104 }} />{/* Market Value */}
                  <col style={{ width: 62 }}  />{/* Coupon */}
                  <col style={{ width: 54 }}  />{/* YTW */}
                  <col style={{ width: 78 }}  />{/* Maturity */}
                  <col style={{ width: 78 }}  />{/* Call Date */}
                </colgroup>
                <TableHead>
                  <TableRow>
                    <SortCell col="account_number" label="Account #" />
                    <SortCell col="account_name"   label="Account Name" />
                    <SortCell col="strategy"       label="Strategy" />
                    <SortCell col="issuer"         label="Issuer" />
                    <SortCell col="fitch_rating"   label="Fitch" />
                    <SortCell col="state"          label="State" />
                    <SortCell col="quantity"       label="Qty"          align="right" />
                    <SortCell col="market_value"   label="Market Value" align="right" />
                    <SortCell col="coupon"         label="Coupon"       align="right" />
                    <SortCell col="yield_to_worst" label="YTW"          align="right" />
                    <SortCell col="maturity_date"  label="Maturity"     align="right" />
                    <SortCell col="call_date"      label="Call Date"    align="right" />
                  </TableRow>
                </TableHead>
                <TableBody>
                  {rows.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={12} align="center" sx={{ py: 4, color: colors.inkSecondary }}>
                        No holdings match the current filters.
                      </TableCell>
                    </TableRow>
                  )}
                  {/* Top spacer keeps the scrollbar thumb accurate */}
                  {paddingTop > 0 && (
                    <TableRow><TableCell colSpan={12} sx={{ p: 0, border: 0, height: paddingTop }} /></TableRow>
                  )}
                  {virtualItems.map(vRow => {
                    const bond = rows[vRow.index];
                    return (
                      <TableRow
                        key={`${bond.cusip}-${bond.account_number}-${vRow.index}`}
                        hover
                        sx={{ height: ROW_HEIGHT, '& .MuiTableCell-root': { fontSize: '0.72rem', py: 0.4, px: 1 } }}
                      >
                        <TableCell sx={{ overflow: 'hidden', whiteSpace: 'nowrap' }}>
                          <Tooltip title={`Open account ${bond.account_number}`} arrow>
                            <Button
                              size="small"
                              variant="text"
                              endIcon={<OpenInNewIcon sx={{ fontSize: '12px !important' }} />}
                              onClick={() => setSelectedAccount({
                                number: bond.account_number,
                                name: bond.account_name,
                              })}
                              sx={{
                                minWidth: 0,
                                p: 0,
                                fontSize: '0.72rem',
                                fontWeight: 700,
                                color: colors.allworthNavy,
                                textTransform: 'none',
                              }}
                            >
                              {bond.account_number}
                            </Button>
                          </Tooltip>
                        </TableCell>
                        <TableCell sx={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          <Tooltip title={bond.account_name} placement="top" arrow>
                            <span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{bond.account_name}</span>
                          </Tooltip>
                        </TableCell>
                        <TableCell sx={{ overflow: 'hidden', py: '2px !important' }}>
                          <Tooltip title={bond.strategy} placement="top" arrow>
                            <Chip
                              label={stratLabel(bond.strategy)}
                              size="small"
                              sx={{
                                fontSize: 10,
                                backgroundColor: stratColor(bond.strategy) + '1A',
                                color: stratColor(bond.strategy),
                                borderColor: stratColor(bond.strategy),
                                border: '1px solid',
                                fontWeight: 600,
                                maxWidth: '100%',
                              }}
                            />
                          </Tooltip>
                        </TableCell>
                        <TableCell sx={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          <Tooltip title={bond.issuer || bond.description} placement="top" arrow>
                            <span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{bond.issuer || bond.description}</span>
                          </Tooltip>
                        </TableCell>
                        <TableCell>
                          {bond.fitch_rating ? (
                            <Chip
                              label={bond.fitch_rating}
                              size="small"
                              sx={{ fontSize: 10, backgroundColor: ratingColor(bond.fitch_rating) + '22', color: ratingColor(bond.fitch_rating), border: `1px solid ${ratingColor(bond.fitch_rating)}`, fontWeight: 700 }}
                            />
                          ) : <Typography variant="caption" sx={{ color: colors.inkSecondary }}>—</Typography>}
                        </TableCell>
                        <TableCell>{bond.state || '—'}</TableCell>
                        <TableCell align="right">{bond.quantity.toLocaleString()}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>{formatCurrency(bond.market_value)}</TableCell>
                        <TableCell align="right">{bond.coupon.toFixed(3)}%</TableCell>
                        <TableCell align="right">{bond.yield_to_worst.toFixed(3)}%</TableCell>
                        <TableCell align="right" sx={{ color: sortBy === 'maturity' ? colors.allworthNavy : 'inherit', fontWeight: sortBy === 'maturity' ? 700 : 400 }}>
                          {bond.maturity_date ? new Date(bond.maturity_date).toLocaleDateString() : '—'}
                        </TableCell>
                        <TableCell align="right" sx={{ color: sortBy === 'call_date' ? colors.allworthAccent : 'inherit', fontWeight: sortBy === 'call_date' ? 700 : 400 }}>
                          {bond.call_date ? new Date(bond.call_date).toLocaleDateString() : '—'}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                  {/* Bottom spacer */}
                  {paddingBottom > 0 && (
                    <TableRow><TableCell colSpan={12} sx={{ p: 0, border: 0, height: paddingBottom }} /></TableRow>
                  )}
                </TableBody>
              </Table>
            </Box>
          </Box>
          <Box sx={{ px: 2, py: 1, borderTop: `1px solid ${colors.ice}` }}>
            <Typography variant="caption" sx={{ color: colors.inkSecondary }}>
              {rows.length.toLocaleString()} holding{rows.length !== 1 ? 's' : ''}
              {search ? ` matching "${search}"` : ''}
              {strategy !== 'ALL' ? ` · ${stratLabel(strategy)}` : ''}
            </Typography>
          </Box>
        </Card>
      )}

      <Dialog
        open={selectedAccount !== null}
        onClose={() => setSelectedAccount(null)}
        fullWidth
        maxWidth="xl"
        slotProps={{ paper: { sx: { height: '92vh', maxHeight: '92vh' } } }}
      >
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Box sx={{ flex: 1 }}>
            <Typography variant="h6" sx={{ color: colors.allworthNavy }}>
              Account {selectedAccount?.number}
            </Typography>
            {selectedAccount?.name && (
              <Typography variant="caption">{selectedAccount.name}</Typography>
            )}
          </Box>
          <IconButton
            aria-label="Close account details"
            onClick={() => setSelectedAccount(null)}
            size="small"
          >
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent dividers sx={{ p: { xs: 1.5, md: 3 } }}>
          {selectedAccount && (
            <Suspense fallback={<LinearProgress sx={{ mt: 2 }} />}>
              <AccountAnalyzer
                initialAccountNumber={selectedAccount.number}
                autoAnalyze
                hideSearch
              />
            </Suspense>
          )}
        </DialogContent>
      </Dialog>
    </Box>
  );
}
