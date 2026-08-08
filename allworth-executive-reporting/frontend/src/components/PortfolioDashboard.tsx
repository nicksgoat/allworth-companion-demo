import React, { useEffect, useMemo, useState } from 'react';
import { Box, Card, CardContent, Typography, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, TableSortLabel, Tabs, Tab, Alert, Skeleton, TextField, Chip,
  ToggleButton, ToggleButtonGroup, Button, TablePagination } from '@mui/material';
import PrintIcon from '@mui/icons-material/Print';
import { fetchAppraisalHoldings, fetchTransactions } from '../services/bondApi';
import type { AppraisalHolding, TransactionRow } from '../services/bondApi';
import { BarChart, Bar, PieChart, Pie, Cell, LineChart, Line, ScatterChart, Scatter, ZAxis, XAxis, YAxis, ReferenceLine,
  CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { colors, chartPalette, sectionHeaderStyle } from '../theme';
import type { PortfolioSummary, Dashboard, AISummary, Bond } from '../services/bondApi';
import { TabPanel } from './TabPanel';
import { printReport } from '../utils/print';

interface Props {
  portfolio: PortfolioSummary;
  dashboard: Dashboard;
  summary: AISummary;
}

// ─── Formatters ───────────────────────────────────────────────────────────────

const formatCurrency = (value: number | string) => {
  const n = typeof value === 'string' ? parseFloat(value) : value;
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
};

const formatCurrencyFull = (value: number | null | undefined) =>
  value == null ? '—' : value.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 });

const formatNumberFull = (value: number | null | undefined, digits = 2) =>
  value == null ? '—' : value.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });

const formatDateShort = (value: string | null | undefined) =>
  value ? new Date(`${value}T00:00:00`).toLocaleDateString('en-US', { month: '2-digit', day: '2-digit', year: 'numeric' }) : '—';

const formatGainPct = (value: number | null | undefined) =>
  value == null ? '—' : `${formatNumberFull(value, 2)}%`;

const gainColor = (value: number | null | undefined) =>
  value == null ? 'inherit' : value >= 0 ? colors.gain : colors.loss;

const appraisalColumns = [
  { label: 'Symbol', key: 'symbol', align: 'left' },
  { label: 'Description', key: 'description', align: 'left' },
  { label: 'Redemption Date', key: 'redemption_date', align: 'center' },
  { label: 'Quantity', key: 'quantity', align: 'right' },
  { label: 'Price', key: 'price', align: 'right' },
  { label: 'Value', key: 'market_value', align: 'right' },
  { label: 'Weight', key: 'weight', align: 'right' },
  { label: 'Call Date', key: 'call_date', align: 'center' },
  { label: 'Unrealized Gain/Loss', key: 'unrealized_gain_loss', align: 'right' },
  { label: 'Percent Gain/Loss', key: 'percent_gain_loss', align: 'right' },
  { label: 'Annual Income', key: 'annual_income', align: 'right' },
  { label: 'Annual Income Rate', key: 'annual_income_rate', align: 'right' },
  { label: 'Open Date', key: 'open_date', align: 'center' },
] as { label: string; key: keyof AppraisalHolding; align: 'left' | 'right' | 'center' }[];

function groupLabel(row: AppraisalHolding) {
  return row.asset_class || row.security_type || 'Unassigned';
}

function subgroupLabel(row: AppraisalHolding) {
  return row.subsector || 'Unassigned';
}

function bondTypeLabel(bond: Bond) {
  return bond.sector || 'Unassigned';
}

function sumRows(rows: AppraisalHolding[]) {
  const marketValue = rows.reduce((sum, row) => sum + (row.market_value ?? 0), 0);
  const weight = rows.reduce((sum, row) => sum + (row.weight ?? 0), 0);
  const gainLoss = rows.reduce((sum, row) => sum + (row.unrealized_gain_loss ?? 0), 0);
  const annualIncome = rows.reduce((sum, row) => sum + (row.annual_income ?? 0), 0);
  const costBasis = marketValue - gainLoss;
  const percentGainLoss = costBasis !== 0 ? (gainLoss / costBasis) * 100 : null;
  return { marketValue, weight, gainLoss, percentGainLoss, annualIncome };
}

function groupSortValue(label: string) {
  const normalized = label.toLowerCase();
  if (normalized === 'cash') return 0;
  if (normalized === 'fixed income') return 1;
  if (normalized.includes('equity') || normalized.includes('stock')) return 2;
  if (normalized.includes('alternative')) return 3;
  return 4;
}

function bondKey(bond: Bond) {
  return (bond.cusip || bond.symbol || bond.description || '').trim().toUpperCase();
}

function holdingKey(row: AppraisalHolding) {
  return (row.cusip || row.symbol || row.description || '').trim().toUpperCase();
}

function matchesBondSearch(bond: Bond, query: string) {
  if (!query) return true;
  const haystack = [
    bond.symbol,
    bond.cusip,
    bond.description,
    bond.issuer,
    bond.sector,
    bond.maturity_date,
  ].join(' ').toLowerCase();
  return haystack.includes(query.toLowerCase());
}

function matchesHoldingSearch(row: AppraisalHolding, query: string) {
  if (!query) return true;
  const haystack = [
    row.symbol,
    row.cusip,
    row.description,
    row.asset_class,
    row.subsector,
    row.security_type,
    row.redemption_date,
  ].join(' ').toLowerCase();
  return haystack.includes(query.toLowerCase());
}

function BondHoldingsTable({
  bonds,
  selectedKey,
  onSelect,
  showAccount = false,
}: {
  bonds: Bond[];
  selectedKey?: string | null;
  onSelect?: (key: string) => void;
  showAccount?: boolean;
}) {
  type BondSortKey = keyof Bond | 'bond_type';
  const [sortKey, setSortKey] = useState<BondSortKey>('maturity_date');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [groupByType, setGroupByType] = useState(false);
  const handleSort = (key: BondSortKey) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else {
      setSortKey(key);
      setSortDir('asc');
    }
  };
  const sortValue = (bond: Bond, key: BondSortKey) => key === 'bond_type' ? bondTypeLabel(bond) : bond[key];
  const compare = (a: Bond, b: Bond) => {
    const av = sortValue(a, sortKey);
    const bv = sortValue(b, sortKey);
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    const cmp = av < bv ? -1 : av > bv ? 1 : 0;
    return sortDir === 'asc' ? cmp : -cmp;
  };
  const rows = [...bonds].sort(compare);

  // When grouping by bond type, cluster rows by type and sort within each group
  // by the active column (defaults to maturity), per advisor request.
  const groups = useMemo(() => {
    if (!groupByType) return null;
    const map = new Map<string, Bond[]>();
    rows.forEach(bond => {
      const label = bondTypeLabel(bond);
      if (!map.has(label)) map.set(label, []);
      map.get(label)!.push(bond);
    });
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [rows, groupByType]);

  const colSpan = showAccount ? 13 : 12;

  const header = (label: string, key: BondSortKey, align: 'left' | 'right' | 'center' = 'left') => (
    <TableCell align={align}>
      <TableSortLabel
        active={sortKey === key}
        direction={sortKey === key ? sortDir : 'asc'}
        onClick={() => handleSort(key)}
      >
        {label}
      </TableSortLabel>
    </TableCell>
  );

  const bodyRow = (bond: Bond, idx: number) => {
    const key = bondKey(bond);
    const selected = selectedKey === key;
    return (
      <TableRow
        key={`${bond.cusip}-${idx}`}
        hover
        onClick={() => onSelect?.(key)}
        sx={{
          cursor: onSelect ? 'pointer' : 'default',
          '& td': { fontSize: '0.8rem', py: 0.75 },
          backgroundColor: selected ? '#EAF3FA' : 'inherit',
        }}
      >
        {showAccount && (
          <TableCell sx={{ whiteSpace: 'nowrap', fontFamily: 'monospace', fontWeight: 700, color: colors.allworthNavy }}>
            {bond.account_number || '—'}
          </TableCell>
        )}
        <TableCell sx={{ whiteSpace: 'nowrap' }}>{bondTypeLabel(bond)}</TableCell>
        <TableCell sx={{ fontWeight: 700, color: colors.allworthNavy, fontFamily: 'monospace' }}>
          {bond.symbol || bond.cusip || '—'}
        </TableCell>
        <TableCell sx={{ maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {bond.description || bond.issuer || '—'}
        </TableCell>
        <TableCell align="center" sx={{ whiteSpace: 'nowrap' }}>{formatDateShort(bond.maturity_date)}</TableCell>
        <TableCell align="right">{formatNumberFull(bond.quantity)}</TableCell>
        <TableCell align="right">{formatNumberFull(bond.price)}</TableCell>
        <TableCell align="right" sx={{ fontWeight: 600 }}>{formatCurrencyFull(bond.market_value)}</TableCell>
        <TableCell align="right">{bond.weight == null ? '—' : `${formatNumberFull(bond.weight, 2)}%`}</TableCell>
        <TableCell align="right">{formatGainPct(bond.coupon)}</TableCell>
        <TableCell align="right">{formatGainPct(bond.yield_to_worst)}</TableCell>
        <TableCell align="right">{formatNumberFull(bond.effective_duration)}</TableCell>
        <TableCell align="center" sx={{ whiteSpace: 'nowrap' }}>{formatDateShort(bond.call_date)}</TableCell>
      </TableRow>
    );
  };

  const handlePrint = () => {
    const cols = [
      ...(showAccount ? [{ header: 'Account', value: (b: Bond) => b.account_number || '—' }] : []),
      { header: 'Type', value: (b: Bond) => bondTypeLabel(b) },
      { header: 'Symbol', value: (b: Bond) => b.symbol || b.cusip || '—' },
      { header: 'Description', value: (b: Bond) => b.description || b.issuer || '—' },
      { header: 'Maturity', value: (b: Bond) => formatDateShort(b.maturity_date), align: 'center' as const },
      { header: 'Quantity', value: (b: Bond) => formatNumberFull(b.quantity), align: 'right' as const },
      { header: 'Price', value: (b: Bond) => formatNumberFull(b.price), align: 'right' as const },
      { header: 'Value', value: (b: Bond) => formatCurrencyFull(b.market_value), align: 'right' as const },
      { header: 'Weight', value: (b: Bond) => (b.weight == null ? '—' : `${formatNumberFull(b.weight, 2)}%`), align: 'right' as const },
      { header: 'Coupon', value: (b: Bond) => formatGainPct(b.coupon), align: 'right' as const },
      { header: 'YTW', value: (b: Bond) => formatGainPct(b.yield_to_worst), align: 'right' as const },
      { header: 'Call Date', value: (b: Bond) => formatDateShort(b.call_date), align: 'center' as const },
    ];
    printReport({ title: 'Bond Holdings', columns: cols, rows });
  };

  return (
    <Card sx={{ overflow: 'hidden' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1, p: 1, borderBottom: `1px solid ${colors.hairline}` }}>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={groupByType ? 'type' : 'flat'}
          onChange={(_, v) => { if (v) setGroupByType(v === 'type'); }}
          sx={{ '& .MuiToggleButton-root': { textTransform: 'none', fontSize: 12, py: 0.25 } }}
        >
          <ToggleButton value="flat">Flat</ToggleButton>
          <ToggleButton value="type">Group by Type</ToggleButton>
        </ToggleButtonGroup>
        <Button size="small" startIcon={<PrintIcon fontSize="small" />} onClick={handlePrint} sx={{ textTransform: 'none', color: colors.allworthNavy }}>
          Print
        </Button>
      </Box>
      <TableContainer>
        <Table size="small">
          <TableHead>
            <TableRow sx={{ '& th': { backgroundColor: '#f5f7fa', py: 1 } }}>
              {showAccount && header('Account', 'account_number')}
              {header('Type', 'bond_type')}
              {header('Symbol', 'symbol')}
              {header('Description', 'description')}
              {header('Maturity', 'maturity_date', 'center')}
              {header('Quantity', 'quantity', 'right')}
              {header('Price', 'price', 'right')}
              {header('Value', 'market_value', 'right')}
              {header('Weight', 'weight', 'right')}
              {header('Coupon', 'coupon', 'right')}
              {header('YTW', 'yield_to_worst', 'right')}
              {header('Duration', 'effective_duration', 'right')}
              {header('Call Date', 'call_date', 'center')}
            </TableRow>
          </TableHead>
          <TableBody>
            {groups
              ? groups.map(([label, groupBonds]) => (
                  <React.Fragment key={label}>
                    <TableRow sx={{ '& td': { backgroundColor: '#f8f9fa', fontWeight: 800, py: 0.9 } }}>
                      <TableCell colSpan={colSpan}>{label} · {groupBonds.length} holding{groupBonds.length !== 1 ? 's' : ''}</TableCell>
                    </TableRow>
                    {groupBonds.map((bond, idx) => bodyRow(bond, idx))}
                  </React.Fragment>
                ))
              : rows.map((bond, idx) => bodyRow(bond, idx))}
          </TableBody>
        </Table>
      </TableContainer>
    </Card>
  );
}

function AccountCashTable({ rows }: { rows: AppraisalHolding[] }) {
  const cashRows = rows.filter(row => {
    const text = `${row.asset_class} ${row.security_type} ${row.subsector} ${row.description}`.toLowerCase();
    return text.includes('cash') || row.symbol.toLowerCase() === 'cash';
  });
  if (!cashRows.length) return null;
  const byAccount = new Map<string, { name: string; value: number; weight: number }>();
  cashRows.forEach(row => {
    const key = row.account_number || 'Unassigned';
    const current = byAccount.get(key) ?? { name: row.account_name || key, value: 0, weight: 0 };
    current.value += row.market_value ?? 0;
    current.weight += row.weight ?? 0;
    byAccount.set(key, current);
  });
  return (
    <Card sx={{ mb: 2 }}>
      <CardContent sx={{ p: '14px 16px !important' }}>
        <SectionHeader>Cash By Account</SectionHeader>
        <Table size="small">
          <TableHead>
            <TableRow sx={{ '& th': { backgroundColor: '#f5f7fa', py: 0.8 } }}>
              <TableCell>Account</TableCell>
              <TableCell>Name</TableCell>
              <TableCell align="right">Cash Value</TableCell>
              <TableCell align="right">Weight</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {Array.from(byAccount.entries()).map(([account, row]) => (
              <TableRow key={account}>
                <TableCell sx={{ fontFamily: 'monospace', fontWeight: 700 }}>{account}</TableCell>
                <TableCell>{row.name}</TableCell>
                <TableCell align="right" sx={{ fontWeight: 700 }}>{formatCurrencyFull(row.value)}</TableCell>
                <TableCell align="right">{formatNumberFull(row.weight, 2)}%</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function CompareMetric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Box sx={{ minWidth: 150, flex: 1, border: `1px solid ${colors.hairline}`, borderRadius: 1, p: 1.25 }}>
      <Typography variant="caption" sx={{ color: colors.inkTertiary, fontWeight: 700, textTransform: 'uppercase' }}>
        {label}
      </Typography>
      <Typography variant="subtitle1" sx={{ color: colors.allworthNavy, fontWeight: 800, lineHeight: 1.3 }}>
        {value}
      </Typography>
      {sub && <Typography variant="caption" sx={{ color: colors.inkSecondary }}>{sub}</Typography>}
    </Box>
  );
}

function CompareBondTable({
  bonds,
  selectedKey,
  onSelect,
}: {
  bonds: Bond[];
  selectedKey: string | null;
  onSelect: (key: string) => void;
}) {
  return (
    <TableContainer sx={{ maxHeight: 560 }}>
      <Table size="small" stickyHeader>
        <TableHead>
          <TableRow sx={{ '& th': { backgroundColor: '#f5f7fa', py: 0.9, fontSize: '0.72rem' } }}>
            <TableCell>Symbol</TableCell>
            <TableCell>Description</TableCell>
            <TableCell align="right">Value</TableCell>
            <TableCell align="center">Maturity</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {bonds.map((bond, idx) => {
            const key = bondKey(bond);
            return (
              <TableRow
                key={`${key}-${idx}`}
                hover
                onClick={() => onSelect(key)}
                sx={{
                  cursor: 'pointer',
                  backgroundColor: selectedKey === key ? '#EAF3FA' : 'inherit',
                  '& td': { fontSize: '0.8rem', py: 0.75 },
                }}
              >
                <TableCell sx={{ fontFamily: 'monospace', fontWeight: 800, color: colors.allworthNavy, whiteSpace: 'nowrap' }}>
                  {bond.symbol || bond.cusip || '—'}
                </TableCell>
                <TableCell sx={{ maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {bond.description || bond.issuer || '—'}
                </TableCell>
                <TableCell align="right" sx={{ fontWeight: 700 }}>{formatCurrencyFull(bond.market_value)}</TableCell>
                <TableCell align="center" sx={{ whiteSpace: 'nowrap' }}>{formatDateShort(bond.maturity_date)}</TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

function CompareAllHoldingsTable({
  rows,
  bondKeys,
  selectedKey,
  onSelect,
}: {
  rows: AppraisalHolding[];
  bondKeys: Set<string>;
  selectedKey: string | null;
  onSelect: (key: string) => void;
}) {
  return (
    <TableContainer sx={{ maxHeight: 560 }}>
      <Table size="small" stickyHeader>
        <TableHead>
          <TableRow sx={{ '& th': { backgroundColor: '#f5f7fa', py: 0.9, fontSize: '0.72rem' } }}>
            <TableCell>Symbol</TableCell>
            <TableCell>Description</TableCell>
            <TableCell>Class</TableCell>
            <TableCell align="right">Value</TableCell>
            <TableCell align="right">Weight</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row, idx) => {
            const key = holdingKey(row);
            const inBondView = bondKeys.has(key);
            return (
              <TableRow
                key={`${key}-${idx}`}
                hover
                onClick={() => onSelect(key)}
                sx={{
                  cursor: 'pointer',
                  backgroundColor: selectedKey === key ? '#EAF3FA' : inBondView ? 'inherit' : '#FFF8E6',
                  '& td': { fontSize: '0.8rem', py: 0.75 },
                }}
              >
                <TableCell sx={{ fontFamily: 'monospace', fontWeight: 800, color: colors.allworthNavy, whiteSpace: 'nowrap' }}>
                  {row.symbol || row.cusip || '—'}
                </TableCell>
                <TableCell sx={{ maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {row.description || '—'}
                </TableCell>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>
                  {inBondView ? (
                    <Chip label={row.asset_class || 'Bond'} size="small" sx={{ height: 20, fontSize: '0.68rem' }} />
                  ) : (
                    <Chip label="Only in All" size="small" sx={{ height: 20, fontSize: '0.68rem', backgroundColor: '#FFF0C2', color: colors.inkSecondary }} />
                  )}
                </TableCell>
                <TableCell align="right" sx={{ fontWeight: 700 }}>{formatCurrencyFull(row.market_value)}</TableCell>
                <TableCell align="right">{row.weight != null ? `${formatNumberFull(row.weight, 2)}%` : '—'}</TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

const yearTimestamp = (year: number) => new Date(year, 0, 1).getTime();

function timelineDomain(rows: { timestamp: number }[]): [number, number] | undefined {
  if (rows.length === 0) return undefined;
  const minYear = new Date(rows[0].timestamp).getFullYear();
  const maxYear = new Date(rows[rows.length - 1].timestamp).getFullYear();
  const startYear = Math.max(new Date().getFullYear(), minYear) - 1;
  const endYear = Math.max(startYear + 3, maxYear + 1);
  return [yearTimestamp(startYear), yearTimestamp(endYear)];
}

function timelineTicks(domain: [number, number] | undefined): number[] | undefined {
  if (!domain) return undefined;
  const startYear = new Date(domain[0]).getFullYear();
  const endYear = new Date(domain[1]).getFullYear();
  const span = Math.max(1, endYear - startYear);
  const step = span <= 6 ? 1 : span <= 14 ? 2 : span <= 24 ? 3 : 5;
  const ticks: number[] = [];
  for (let year = startYear; year <= endYear; year += step) {
    ticks.push(yearTimestamp(year));
  }
  return ticks;
}

function timelineYearMarkers(domain: [number, number] | undefined): number[] {
  if (!domain) return [];
  const startYear = new Date(domain[0]).getFullYear();
  const endYear = new Date(domain[1]).getFullYear();
  const markers: number[] = [];
  for (let year = startYear; year <= endYear; year += 1) {
    markers.push(yearTimestamp(year));
  }
  return markers;
}

// ─── Sub-components ───────────────────────────────────────────────────────────

/** Mirrors the HeroNumber component from the mobile app */
function KpiCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card sx={{ height: '100%' }}>
      <CardContent sx={{ p: '20px !important' }}>
        <p className="aw-kpi-card__label" style={{ margin: '0 0 8px' }}>{label}</p>
        <p className="aw-kpi-card__value" style={{ margin: '0 0 4px' }}>{value}</p>
        {sub && <Typography variant="caption" sx={{ color: colors.inkTertiary }}>{sub}</Typography>}
      </CardContent>
    </Card>
  );
}

/** Section header: 11px Lato Bold uppercase (mirrors sectionHeader from mobile theme) */
function SectionHeader({ children }: { children: React.ReactNode }) {
  return <p style={{ ...sectionHeaderStyle, margin: '0 0 16px' }}>{children}</p>;
}

/** Insight list card — maps to alert boxes with Allworth severity colors */
function InsightCard({
  title,
  items,
  severity,
}: {
  title: string;
  items: string[];
  severity: 'success' | 'warning' | 'info';
}) {
  if (items.length === 0) return null;
  return (
    <Alert severity={severity} sx={{ mb: 2 }}>
      <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 700 }}>
        {title}
      </Typography>
      <ul style={{ margin: '4px 0 0', paddingLeft: 20 }}>
        {items.map((item, i) => (
          <li key={i} style={{ marginBottom: 4 }}>{item}</li>
        ))}
      </ul>
    </Alert>
  );
}

function TimelineTooltip({
  active,
  payload,
  dateKey,
  dateLabel,
}: {
  active?: boolean;
  payload?: Array<{ payload?: Record<string, unknown> }>;
  dateKey: 'maturity_date' | 'call_date';
  dateLabel: string;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload ?? {};
  const issuer = String(row.issuer ?? 'Unknown issuer');
  const rawDate = row[dateKey];
  const date = rawDate ? new Date(String(rawDate)).toLocaleDateString() : 'N/A';
  const marketValue = Number(row.market_value ?? 0);

  return (
    <div
      style={{
        background: '#ffffff',
        border: `1px solid ${colors.hairline}`,
        borderRadius: 6,
        boxShadow: '0 8px 24px rgba(12,46,78,0.14)',
        color: colors.inkSecondary,
        fontFamily: 'Lato, sans-serif',
        fontSize: 12,
        minWidth: 210,
        padding: '10px 12px',
      }}
    >
      <div style={{ color: colors.allworthNavy, fontWeight: 800, marginBottom: 6 }}>
        {issuer}
      </div>
      <div>{dateLabel}: <strong>{date}</strong></div>
      <div>Market Value: <strong>{formatCurrency(marketValue)}</strong></div>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function PortfolioDashboard({ portfolio, dashboard, summary }: Props) {
  const [tab, setTab] = useState(0);

  // ── Appraisal holdings state (Holdings tab) ──────────────────────────
  type AppraisalSortKey = keyof AppraisalHolding;
  const [appraisalRows, setAppraisalRows] = useState<AppraisalHolding[] | null>(null);
  const [appraisalLoading, setAppraisalLoading] = useState(false);
  const [appraisalError, setAppraisalError] = useState<string | null>(null);
  const [appraisalSortKey, setAppraisalSortKey] = useState<AppraisalSortKey>('description');
  const [appraisalSortDir, setAppraisalSortDir] = useState<'asc' | 'desc'>('asc');
  const [compareSearch, setCompareSearch] = useState('');
  const [selectedCompareKey, setSelectedCompareKey] = useState<string | null>(null);

  // ── Transactions state (Transactions tab) ────────────────────────────
  const [txRows, setTxRows] = useState<TransactionRow[] | null>(null);
  const [txLoading, setTxLoading] = useState(false);
  const [txError, setTxError] = useState<string | null>(null);
  const [txSearch, setTxSearch] = useState('');

  // Fetch appraisal data lazily when the All Holdings or Compare tab is first opened
  useEffect(() => {
    if (![5, 6].includes(tab) || appraisalRows !== null || appraisalLoading) return;
    if (!portfolio.accounts.length) return;
    setAppraisalLoading(true);
    setAppraisalError(null);
    fetchAppraisalHoldings(portfolio.accounts)
      .then(r => setAppraisalRows(r.rows))
      .catch(e => setAppraisalError(e instanceof Error ? e.message : 'Failed to load holdings'))
      .finally(() => setAppraisalLoading(false));
  }, [tab, portfolio.accounts, appraisalRows, appraisalLoading]);

  // Fetch transactions lazily when the Transactions tab (index 8) is opened
  useEffect(() => {
    if (tab !== 8 || txRows !== null || txLoading) return;
    if (!portfolio.accounts.length) return;
    setTxLoading(true);
    setTxError(null);
    fetchTransactions(portfolio.accounts)
      .then(r => setTxRows(r.rows))
      .catch(e => setTxError(e instanceof Error ? e.message : 'Failed to load transactions'))
      .finally(() => setTxLoading(false));
  }, [tab, portfolio.accounts, txRows, txLoading]);

  const handleAppraisalSort = (key: AppraisalSortKey) => {
    if (appraisalSortKey === key) {
      setAppraisalSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setAppraisalSortKey(key);
      setAppraisalSortDir('asc');
    }
  };

  const sortedAppraisalRows = useMemo(() => {
    if (!appraisalRows) return [];
    return [...appraisalRows].sort((a, b) => {
      const av = a[appraisalSortKey];
      const bv = b[appraisalSortKey];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return appraisalSortDir === 'asc' ? cmp : -cmp;
    });
  }, [appraisalRows, appraisalSortKey, appraisalSortDir]);

  const groupedAppraisalRows = useMemo(() => {
    const groups = new Map<string, Map<string, AppraisalHolding[]>>();
    sortedAppraisalRows.forEach((row) => {
      const category = groupLabel(row);
      const subcategory = subgroupLabel(row);
      if (!groups.has(category)) groups.set(category, new Map());
      const subgroups = groups.get(category)!;
      if (!subgroups.has(subcategory)) subgroups.set(subcategory, []);
      subgroups.get(subcategory)!.push(row);
    });
    return Array.from(groups.entries()).map(([category, subgroups]) => ({
      category,
      subgroups: Array.from(subgroups.entries()).sort(([a], [b]) => a.localeCompare(b)).map(([subcategory, rows]) => ({
        subcategory,
        rows,
        totals: sumRows(rows),
      })),
      totals: sumRows(Array.from(subgroups.values()).flat()),
    })).sort((a, b) => groupSortValue(a.category) - groupSortValue(b.category) || a.category.localeCompare(b.category));
  }, [sortedAppraisalRows]);

  const sortedBonds = useMemo(() =>
    [...dashboard.bonds].sort((a, b) => {
      const aDate = a.maturity_date ? new Date(a.maturity_date).getTime() : Number.MAX_SAFE_INTEGER;
      const bDate = b.maturity_date ? new Date(b.maturity_date).getTime() : Number.MAX_SAFE_INTEGER;
      return aDate - bDate;
    }),
    [dashboard.bonds]);

  const bondKeySet = useMemo(() => new Set(dashboard.bonds.map(bondKey).filter(Boolean)), [dashboard.bonds]);

  const filteredCompareBonds = useMemo(() =>
    sortedBonds.filter(bond => matchesBondSearch(bond, compareSearch)),
    [sortedBonds, compareSearch]);

  const filteredCompareHoldings = useMemo(() =>
    (appraisalRows ?? [])
      .filter(row => matchesHoldingSearch(row, compareSearch))
      .sort((a, b) => groupSortValue(groupLabel(a)) - groupSortValue(groupLabel(b)) || groupLabel(a).localeCompare(groupLabel(b)) || (b.market_value ?? 0) - (a.market_value ?? 0)),
    [appraisalRows, compareSearch]);

  const compareTotals = useMemo(() => {
    const bondValue = dashboard.bonds.reduce((sum, bond) => sum + (bond.market_value ?? 0), 0);
    const allValue = (appraisalRows ?? []).reduce((sum, row) => sum + (row.market_value ?? 0), 0);
    const onlyAllRows = (appraisalRows ?? []).filter(row => !bondKeySet.has(holdingKey(row)));
    const onlyAllValue = onlyAllRows.reduce((sum, row) => sum + (row.market_value ?? 0), 0);
    return {
      bondValue,
      allValue,
      onlyAllRows,
      onlyAllValue,
      bondPct: allValue > 0 ? (bondValue / allValue) * 100 : null,
    };
  }, [dashboard.bonds, appraisalRows, bondKeySet]);

  const sectorData = useMemo(() =>
    Object.entries(dashboard.sector_allocation).map(([name, value]) => ({ name, value })),
    [dashboard.sector_allocation]);

  const stateData = useMemo(() =>
    Object.entries(dashboard.state_allocation).map(([name, value]) => ({ name, value })),
    [dashboard.state_allocation]);

  const maturityTimelineData = useMemo(() =>
    dashboard.bonds
      .map((bond) => ({
        timestamp: new Date(bond.maturity_date).getTime(),
        maturity_date: bond.maturity_date,
        market_value: bond.market_value,
        size: Math.max(28, Math.min(160, Math.sqrt(Math.max(bond.market_value, 0)) * 0.72)),
        issuer: bond.issuer || bond.description || bond.cusip,
        cusip: bond.cusip,
        sector: bond.sector,
      }))
      .filter(row => Number.isFinite(row.timestamp))
      .sort((a, b) => a.timestamp - b.timestamp),
    [dashboard.bonds]);

  const maturityData = useMemo(() => {
    const entries = Object.entries(dashboard.maturity_ladder)
      .map(([name, value]) => ({ year: Number(name), value }))
      .filter(e => Number.isFinite(e.year))
      .sort((a, b) => a.year - b.year);
    if (entries.length === 0) return [] as { name: string; value: number }[];
    // Fill every calendar year in the span so the ladder reads year-by-year
    // rather than collapsing sparse years next to each other.
    const minYear = entries[0].year;
    const maxYear = entries[entries.length - 1].year;
    const byYear = new Map(entries.map(e => [e.year, e.value]));
    const filled: { name: string; value: number }[] = [];
    for (let y = minYear; y <= maxYear; y += 1) {
      filled.push({ name: String(y), value: byYear.get(y) ?? 0 });
    }
    return filled;
  }, [dashboard.maturity_ladder]);

  const maturityTimelineDomain = useMemo(() => timelineDomain(maturityTimelineData), [maturityTimelineData]);
  const maturityTimelineTicks = useMemo(() => timelineTicks(maturityTimelineDomain), [maturityTimelineDomain]);
  const maturityTimelineMarkers = useMemo(() => timelineYearMarkers(maturityTimelineDomain), [maturityTimelineDomain]);

  const callData = useMemo(() =>
    Object.entries(dashboard.call_ladder).map(([name, value]) => ({ name, value })),
    [dashboard.call_ladder]);

  const callTimelineData = useMemo(() =>
    dashboard.bonds
      .filter((bond) => bond.call_date)
      .map((bond) => ({
        timestamp: new Date(bond.call_date as string).getTime(),
        call_date: bond.call_date as string,
        market_value: bond.market_value,
        size: Math.max(28, Math.min(160, Math.sqrt(Math.max(bond.market_value, 0)) * 0.72)),
        issuer: bond.issuer || bond.description || bond.cusip,
        cusip: bond.cusip,
        sector: bond.sector,
      }))
      .filter(row => Number.isFinite(row.timestamp))
      .sort((a, b) => a.timestamp - b.timestamp),
    [dashboard.bonds]);

  const callTimelineDomain = useMemo(() => timelineDomain(callTimelineData), [callTimelineData]);
  const callTimelineTicks = useMemo(() => timelineTicks(callTimelineDomain), [callTimelineDomain]);
  const callTimelineMarkers = useMemo(() => timelineYearMarkers(callTimelineDomain), [callTimelineDomain]);

  const creditData = useMemo(() =>
    Object.entries(dashboard.credit_distribution).map(([name, value]) => ({ name, value })),
    [dashboard.credit_distribution]);

  const cashFlowData = useMemo(() =>
    dashboard.cash_flow_projection.slice(0, 24),
    [dashboard.cash_flow_projection]);

  const healthColor = dashboard.kpis.health_score >= 80
    ? colors.gain
    : dashboard.kpis.health_score >= 60
      ? colors.attention
      : colors.loss;

  return (
    <Box>
      {/* ── Portfolio identity header ──────────────────────────────────── */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" sx={{ color: colors.allworthNavy, mb: 0.5 }}>
          {portfolio.name}
        </Typography>
        <Typography variant="body2" sx={{ color: colors.inkTertiary }}>
          {dashboard.bonds.length} holdings · {portfolio.accounts.length} account{portfolio.accounts.length !== 1 ? 's' : ''}
        </Typography>
      </Box>

      {/* ── Tab navigation ────────────────────────────────────────────── */}
      <Tabs
        value={tab}
        onChange={(_, v) => setTab(v)}
        sx={{ borderBottom: `1px solid ${colors.hairline}`, mb: 3 }}
      >
        {['Overview', 'Allocations', 'Ladders', 'Cash Flow', 'Bond Holdings', 'All Holdings', 'Compare', 'Insights', 'Transactions'].map((label) => (
          <Tab key={label} label={label} />
        ))}
      </Tabs>

      {/* ── Tab 0: Overview ───────────────────────────────────────────── */}
      <TabPanel value={tab} index={0}>
        {/* KPI cards row */}
        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 2, mb: 3 }}>
          <KpiCard label="Market Value" value={formatCurrency(dashboard.kpis.market_value)} />
          <KpiCard label="Annual Income" value={formatCurrency(dashboard.kpis.annual_income)} />
          <KpiCard label="Avg Duration" value={`${dashboard.kpis.avg_duration.toFixed(2)} yrs`} />
          <KpiCard
            label="Health Score"
            value={`${dashboard.kpis.health_score.toFixed(1)} / 100`}
          />
        </Box>

        {/* Detail cards */}
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' }, gap: 2 }}>
          <Card>
            <CardContent>
              <SectionHeader>Yield &amp; Coupon</SectionHeader>
              {[
                ['Avg Coupon', `${dashboard.kpis.avg_coupon.toFixed(3)}%`],
                ['Avg Yield to Worst', `${dashboard.kpis.avg_yield.toFixed(3)}%`],
                ['Avg Credit Rating', dashboard.kpis.avg_rating],
                ['Callable Bonds', `${dashboard.kpis.callable_pct.toFixed(1)}%`],
              ].map(([label, val]) => (
                <Box key={label} sx={{ display: 'flex', justifyContent: 'space-between', py: 1, borderBottom: `1px solid ${colors.hairline}` }}>
                  <Typography variant="body2" sx={{ color: colors.inkSecondary }}>{label}</Typography>
                  <Typography variant="body2" sx={{ fontWeight: 700 }}>{val}</Typography>
                </Box>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <SectionHeader>Portfolio Quality</SectionHeader>
              {[
                ['Total Holdings', String(dashboard.bonds.length)],
                ['Ladder Quality', `${dashboard.ladder_quality_score.toFixed(1)} / 100`],
                ['Portfolio Health', `${dashboard.portfolio_health_score.toFixed(1)} / 100`],
              ].map(([label, val]) => (
                <Box key={label} sx={{ display: 'flex', justifyContent: 'space-between', py: 1, borderBottom: `1px solid ${colors.hairline}` }}>
                  <Typography variant="body2" sx={{ color: colors.inkSecondary }}>{label}</Typography>
                  <Typography variant="body2" sx={{ fontWeight: 700, color: label === 'Portfolio Health' ? healthColor : 'inherit' }}>{val}</Typography>
                </Box>
              ))}
            </CardContent>
          </Card>
        </Box>
      </TabPanel>

      {/* ── Tab 1: Allocations ────────────────────────────────────────── */}
      <TabPanel value={tab} index={1}>
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
          <Card>
            <CardContent>
              <SectionHeader>Fixed Income Allocation</SectionHeader>
              <ResponsiveContainer width="100%" height={280}>
                <PieChart>
                  <Pie
                    data={sectorData}
                    cx="50%"
                    cy="50%"
                    outerRadius={90}
                    dataKey="value"
                    label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}
                    labelLine={false}
                  >
                    {sectorData.map((_, i) => (
                      <Cell key={i} fill={chartPalette[i % chartPalette.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v) => formatCurrency(Number(v))} />
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <SectionHeader>State Allocation</SectionHeader>
              {(() => {
                const labelWidth = Math.min(140, Math.max(70,
                  (stateData.reduce((max, d) => Math.max(max, d.name.length), 0)) * 7
                ));
                const chartHeight = Math.max(180, stateData.length * 32);
                return (
                  <ResponsiveContainer width="100%" height={chartHeight}>
                    <BarChart data={stateData} layout="vertical" margin={{ left: 4, right: 24, top: 4, bottom: 4 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke={colors.hairline} />
                      <XAxis type="number" tick={{ fontSize: 11, fill: colors.inkTertiary }}
                        tickFormatter={(v) => `$${(v / 1000).toFixed(0)}K`} />
                      <YAxis dataKey="name" type="category"
                        tick={{ fontSize: 11, fill: colors.inkSecondary }}
                        width={labelWidth} />
                      <Tooltip formatter={(v) => formatCurrency(Number(v))} />
                      <Bar dataKey="value" fill={colors.allworthAccent} radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                );
              })()}
            </CardContent>
          </Card>

          <Card sx={{ gridColumn: { md: '1 / -1' } }}>
            <CardContent>
              <SectionHeader>Credit Distribution</SectionHeader>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={creditData}>
                  <CartesianGrid strokeDasharray="3 3" stroke={colors.hairline} />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: colors.inkSecondary }} />
                  <YAxis tick={{ fontSize: 11, fill: colors.inkTertiary }} />
                  <Tooltip formatter={(v) => formatCurrency(Number(v))} />
                  <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                    {creditData.map((entry, i) => {
                      const isIG = ['AAA','AA','A','BBB','Aaa','Aa','Baa'].some(r => entry.name.startsWith(r));
                      return <Cell key={i} fill={isIG ? colors.chartEvergreen : colors.chartPumpkin} />;
                    })}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Box>
      </TabPanel>

      {/* ── Tab 2: Ladders ────────────────────────────────────────────── */}
      <TabPanel value={tab} index={2}>
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
          <Card>
            <CardContent>
              <SectionHeader>Maturity Ladder</SectionHeader>
              <Box sx={{ height: { xs: 260, md: 300 } }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={maturityData}>
                    <CartesianGrid strokeDasharray="3 3" stroke={colors.hairline} />
                    <XAxis dataKey="name" tick={{ fontSize: 11, fill: colors.inkSecondary }} />
                    <YAxis tick={{ fontSize: 11, fill: colors.inkTertiary }} tickFormatter={(v) => `$${(v/1000).toFixed(0)}K`} />
                    <Tooltip formatter={(v) => formatCurrency(Number(v))} />
                    <Bar dataKey="value" fill={colors.allworthNavy} radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </Box>
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <SectionHeader>Bond Maturity Timeline</SectionHeader>
              {maturityTimelineData.length > 0 ? (
                <Box sx={{ height: { xs: 280, md: 320 } }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <ScatterChart margin={{ left: 4, right: 18, top: 12, bottom: 12 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke={colors.hairline} />
                      <XAxis
                        type="number"
                        dataKey="timestamp"
                        scale="time"
                        domain={maturityTimelineDomain}
                        ticks={maturityTimelineTicks}
                        tick={{ fontSize: 11, fill: colors.inkSecondary }}
                        tickFormatter={(v) => new Date(Number(v)).getFullYear().toString()}
                      />
                      <YAxis
                        type="number"
                        dataKey="market_value"
                        tick={{ fontSize: 11, fill: colors.inkTertiary }}
                        tickFormatter={(v) => `$${(Number(v) / 1000).toFixed(0)}K`}
                      />
                      {maturityTimelineMarkers.map(marker => (
                        <ReferenceLine
                          key={marker}
                          x={marker}
                          stroke={colors.hairline}
                          strokeDasharray="3 3"
                          ifOverflow="extendDomain"
                        />
                      ))}
                      <ZAxis type="number" dataKey="size" range={[28, 160]} />
                      <Tooltip
                        cursor={{ stroke: colors.allworthNavy, strokeDasharray: '3 3' }}
                        content={<TimelineTooltip dateKey="maturity_date" dateLabel="Maturity" />}
                      />
                      <Scatter name="Maturity" data={maturityTimelineData} fill={colors.allworthNavy}>
                        {maturityTimelineData.map((row, i) => (
                          <Cell
                            key={`${row.cusip}-${row.maturity_date}-${i}`}
                            fill={row.sector === 'Municipal' ? colors.chartSky : colors.allworthNavy}
                            fillOpacity={0.78}
                            stroke="#ffffff"
                            strokeWidth={1}
                          />
                        ))}
                      </Scatter>
                    </ScatterChart>
                  </ResponsiveContainer>
                </Box>
              ) : (
                <Typography variant="body2" sx={{ color: colors.inkSecondary, py: 4, textAlign: 'center' }}>
                  No maturity dates available.
                </Typography>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <SectionHeader>Call Ladder</SectionHeader>
              <Box sx={{ height: { xs: 260, md: 300 } }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={callData}>
                    <CartesianGrid strokeDasharray="3 3" stroke={colors.hairline} />
                    <XAxis dataKey="name" tick={{ fontSize: 11, fill: colors.inkSecondary }} />
                    <YAxis tick={{ fontSize: 11, fill: colors.inkTertiary }} tickFormatter={(v) => `$${(v/1000).toFixed(0)}K`} />
                    <Tooltip formatter={(v) => formatCurrency(Number(v))} />
                    <Bar dataKey="value" fill={colors.chartGold} radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </Box>
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <SectionHeader>Bond Call Timeline</SectionHeader>
              {callTimelineData.length > 0 ? (
                <Box sx={{ height: { xs: 280, md: 320 } }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <ScatterChart margin={{ left: 4, right: 18, top: 12, bottom: 12 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke={colors.hairline} />
                      <XAxis
                        type="number"
                        dataKey="timestamp"
                        scale="time"
                        domain={callTimelineDomain}
                        ticks={callTimelineTicks}
                        tick={{ fontSize: 11, fill: colors.inkSecondary }}
                        tickFormatter={(v) => new Date(Number(v)).getFullYear().toString()}
                      />
                      <YAxis
                        type="number"
                        dataKey="market_value"
                        tick={{ fontSize: 11, fill: colors.inkTertiary }}
                        tickFormatter={(v) => `$${(Number(v) / 1000).toFixed(0)}K`}
                      />
                      {callTimelineMarkers.map(marker => (
                        <ReferenceLine
                          key={marker}
                          x={marker}
                          stroke={colors.hairline}
                          strokeDasharray="3 3"
                          ifOverflow="extendDomain"
                        />
                      ))}
                      <ZAxis type="number" dataKey="size" range={[28, 160]} />
                      <Tooltip
                        cursor={{ stroke: colors.allworthAccent, strokeDasharray: '3 3' }}
                        content={<TimelineTooltip dateKey="call_date" dateLabel="Call Date" />}
                      />
                      <Scatter name="Call Date" data={callTimelineData} fill={colors.allworthAccent}>
                        {callTimelineData.map((row, i) => (
                          <Cell
                            key={`${row.cusip}-${row.call_date}-${i}`}
                            fill={colors.allworthAccent}
                            fillOpacity={0.78}
                            stroke="#ffffff"
                            strokeWidth={1}
                          />
                        ))}
                      </Scatter>
                    </ScatterChart>
                  </ResponsiveContainer>
                </Box>
              ) : (
                <Typography variant="body2" sx={{ color: colors.inkSecondary, py: 4, textAlign: 'center' }}>
                  No call dates available.
                </Typography>
              )}
            </CardContent>
          </Card>
        </Box>
      </TabPanel>

      {/* ── Tab 3: Cash Flow ──────────────────────────────────────────── */}
      <TabPanel value={tab} index={3}>
        <Card>
          <CardContent>
            <SectionHeader>10-Year Cash Flow Projection</SectionHeader>
            <ResponsiveContainer width="100%" height={400}>
              <LineChart data={cashFlowData}>
                <CartesianGrid strokeDasharray="3 3" stroke={colors.hairline} />
                <XAxis dataKey="month" tick={{ fontSize: 11, fill: colors.inkSecondary }} />
                <YAxis tick={{ fontSize: 11, fill: colors.inkTertiary }} tickFormatter={(v) => `$${(v/1000).toFixed(0)}K`} />
                <Tooltip formatter={(v) => formatCurrency(Number(v))} />
                <Legend />
                <Line type="monotone" dataKey="principal" stroke={colors.allworthNavy} strokeWidth={2} dot={false} name="Principal" />
                <Line type="monotone" dataKey="income" stroke={colors.chartSky} strokeWidth={2} dot={false} name="Income" />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </TabPanel>

      {/* ── Tab 4: Bond Holdings ──────────────────────────────────────── */}
      <TabPanel value={tab} index={4}>
        <BondHoldingsTable bonds={dashboard.bonds} showAccount={portfolio.accounts.length > 1} />
      </TabPanel>

      {/* ── Tab 5: All Holdings ───────────────────────────────────────── */}
      <TabPanel value={tab} index={5}>
        {appraisalLoading && (
          <Box>
            <Skeleton variant="rectangular" height={40} sx={{ mb: 1, borderRadius: 1 }} />
            {[1,2,3,4,5,6,7].map(i => (
              <Skeleton key={i} variant="rectangular" height={44} sx={{ mb: 0.5, borderRadius: 1 }} />
            ))}
          </Box>
        )}
        {appraisalError && (
          <Alert severity="error" onClose={() => setAppraisalError(null)}>{appraisalError}</Alert>
        )}
        {!appraisalLoading && !appraisalError && appraisalRows !== null && (
          <>
          <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 1 }}>
            <Button
              size="small"
              startIcon={<PrintIcon fontSize="small" />}
              onClick={() => printReport({
                title: 'Holdings Appraisal',
                subtitle: portfolio.name,
                meta: [{ label: 'Holdings', value: sortedAppraisalRows.length.toLocaleString() }],
                columns: appraisalColumns.map(c => ({
                  header: c.label,
                  align: c.align,
                  value: (row: AppraisalHolding) => {
                    const v = row[c.key];
                    if (v == null) return '—';
                    if (c.key === 'redemption_date' || c.key === 'call_date' || c.key === 'open_date') return formatDateShort(v as string);
                    if (typeof v === 'number') {
                      if (c.key === 'market_value' || c.key === 'unrealized_gain_loss' || c.key === 'annual_income') return formatCurrencyFull(v);
                      if (c.key === 'weight' || c.key === 'percent_gain_loss') return `${formatNumberFull(v, 2)}%`;
                      return formatNumberFull(v);
                    }
                    return String(v);
                  },
                })),
                rows: sortedAppraisalRows,
              })}
              sx={{ textTransform: 'none', color: colors.allworthNavy }}
            >
              Print
            </Button>
          </Box>
          {portfolio.accounts.length > 1 && <AccountCashTable rows={appraisalRows} />}
          <Card sx={{ overflow: 'hidden' }}>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow sx={{ '& th': { backgroundColor: '#f5f7fa', py: 1 } }}>
                    {appraisalColumns.map(({ label, key, align }) => (
                      <TableCell key={key} align={align} sx={{ whiteSpace: 'nowrap', fontSize: '0.72rem', fontWeight: 600, color: colors.inkSecondary, userSelect: 'none' }}>
                        <TableSortLabel
                          active={appraisalSortKey === key}
                          direction={appraisalSortKey === key ? appraisalSortDir : 'asc'}
                          onClick={() => handleAppraisalSort(key)}
                          sx={{ '& .MuiTableSortLabel-icon': { opacity: appraisalSortKey === key ? 1 : 0.3 } }}
                        >
                          {label}
                        </TableSortLabel>
                      </TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {groupedAppraisalRows.map((group) => (
                    <React.Fragment key={group.category}>
                      <TableRow sx={{ '& td': { backgroundColor: '#f8f9fa', borderTop: `1px solid ${colors.hairline}`, fontWeight: 800, py: 1 } }}>
                        <TableCell colSpan={13}>{group.category}</TableCell>
                      </TableRow>
                      {group.subgroups.map((subgroup) => (
                        <React.Fragment key={`${group.category}-${subgroup.subcategory}`}>
                          <TableRow sx={{ '& td': { backgroundColor: '#ffffff', fontWeight: 800, py: 0.9 } }}>
                            <TableCell />
                            <TableCell colSpan={12}>{subgroup.subcategory}</TableCell>
                          </TableRow>
                          {subgroup.rows.map((row, idx) => (
                            <React.Fragment key={`${group.category}-${subgroup.subcategory}-${row.cusip}-${idx}`}>
                              <TableRow hover sx={{ '& td': { fontSize: '0.8rem', py: 0.75, verticalAlign: 'top', borderBottom: row.accrued_income ? 0 : undefined } }}>
                                <TableCell sx={{ fontWeight: 700, color: colors.allworthNavy, fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
                                  {row.symbol || row.cusip || '—'}
                                </TableCell>
                                <TableCell sx={{ maxWidth: 320 }}>
                                  <Typography variant="caption" sx={{ display: 'block', fontWeight: 600 }}>
                                    {row.description || '—'}
                                  </Typography>
                                </TableCell>
                                <TableCell align="center" sx={{ whiteSpace: 'nowrap' }}>{formatDateShort(row.redemption_date)}</TableCell>
                                <TableCell align="right">{formatNumberFull(row.quantity)}</TableCell>
                                <TableCell align="right">{formatNumberFull(row.price)}</TableCell>
                                <TableCell align="right" sx={{ fontWeight: 600 }}>{formatCurrencyFull(row.market_value)}</TableCell>
                                <TableCell align="right">{row.weight != null ? `${formatNumberFull(row.weight, 2)}%` : '—'}</TableCell>
                                <TableCell align="center" sx={{ whiteSpace: 'nowrap' }}>{formatDateShort(row.call_date)}</TableCell>
                                <TableCell align="right" sx={{ color: gainColor(row.unrealized_gain_loss) }}>{formatCurrencyFull(row.unrealized_gain_loss)}</TableCell>
                                <TableCell align="right" sx={{ color: gainColor(row.percent_gain_loss) }}>{formatGainPct(row.percent_gain_loss)}</TableCell>
                                <TableCell align="right">{formatCurrencyFull(row.annual_income)}</TableCell>
                                <TableCell align="right">{row.annual_income_rate == null ? '—' : formatNumberFull(row.annual_income_rate, 4)}</TableCell>
                                <TableCell align="center" sx={{ whiteSpace: 'nowrap' }}>{formatDateShort(row.open_date)}</TableCell>
                              </TableRow>
                              {row.accrued_income ? (
                                <TableRow sx={{ '& td': { fontSize: '0.8rem', py: 0.45 } }}>
                                  <TableCell />
                                  <TableCell>Accrued Income</TableCell>
                                  <TableCell />
                                  <TableCell />
                                  <TableCell />
                                  <TableCell align="right">{formatCurrencyFull(row.accrued_income)}</TableCell>
                                  <TableCell colSpan={7} />
                                </TableRow>
                              ) : null}
                            </React.Fragment>
                          ))}
                          <TableRow sx={{ '& td': { backgroundColor: '#f1f2f2', fontWeight: 800, py: 0.8 } }}>
                            <TableCell />
                            <TableCell>{subgroup.subcategory} Total</TableCell>
                            <TableCell />
                            <TableCell />
                            <TableCell />
                            <TableCell align="right">{formatCurrencyFull(subgroup.totals.marketValue)}</TableCell>
                            <TableCell align="right">{formatNumberFull(subgroup.totals.weight, 2)}%</TableCell>
                            <TableCell />
                            <TableCell align="right" sx={{ color: gainColor(subgroup.totals.gainLoss) }}>{formatCurrencyFull(subgroup.totals.gainLoss)}</TableCell>
                            <TableCell align="right" sx={{ color: gainColor(subgroup.totals.percentGainLoss) }}>{formatGainPct(subgroup.totals.percentGainLoss)}</TableCell>
                            <TableCell align="right">{formatCurrencyFull(subgroup.totals.annualIncome)}</TableCell>
                            <TableCell />
                            <TableCell />
                          </TableRow>
                        </React.Fragment>
                      ))}
                      <TableRow sx={{ '& td': { backgroundColor: '#ffffff', fontWeight: 800, py: 0.9 } }}>
                        <TableCell />
                        <TableCell>{group.category} Total</TableCell>
                        <TableCell />
                        <TableCell />
                        <TableCell />
                        <TableCell align="right">{formatCurrencyFull(group.totals.marketValue)}</TableCell>
                        <TableCell align="right">{formatNumberFull(group.totals.weight, 2)}%</TableCell>
                        <TableCell />
                        <TableCell align="right" sx={{ color: gainColor(group.totals.gainLoss) }}>{formatCurrencyFull(group.totals.gainLoss)}</TableCell>
                        <TableCell align="right" sx={{ color: gainColor(group.totals.percentGainLoss) }}>{formatGainPct(group.totals.percentGainLoss)}</TableCell>
                        <TableCell align="right">{formatCurrencyFull(group.totals.annualIncome)}</TableCell>
                        <TableCell />
                        <TableCell />
                      </TableRow>
                    </React.Fragment>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Card>
          </>
        )}
      </TabPanel>

      {/* ── Tab 6: Compare ────────────────────────────────────────────── */}
      <TabPanel value={tab} index={6}>
        {appraisalLoading && (
          <Box>
            <Skeleton variant="rectangular" height={96} sx={{ mb: 2, borderRadius: 1 }} />
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '1fr 1fr' }, gap: 2 }}>
              <Skeleton variant="rectangular" height={420} sx={{ borderRadius: 1 }} />
              <Skeleton variant="rectangular" height={420} sx={{ borderRadius: 1 }} />
            </Box>
          </Box>
        )}
        {appraisalError && (
          <Alert severity="error" onClose={() => setAppraisalError(null)}>{appraisalError}</Alert>
        )}
        {!appraisalLoading && !appraisalError && appraisalRows !== null && (
          <Box>
            <Card sx={{ mb: 2 }}>
              <CardContent sx={{ p: '16px !important' }}>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.25, mb: 2 }}>
                  <CompareMetric
                    label="Bond Value"
                    value={formatCurrencyFull(compareTotals.bondValue)}
                    sub={`${dashboard.bonds.length.toLocaleString()} bond holding${dashboard.bonds.length !== 1 ? 's' : ''}`}
                  />
                  <CompareMetric
                    label="All Value"
                    value={formatCurrencyFull(compareTotals.allValue)}
                    sub={`${appraisalRows.length.toLocaleString()} total holding${appraisalRows.length !== 1 ? 's' : ''}`}
                  />
                  <CompareMetric
                    label="Bond Share"
                    value={compareTotals.bondPct == null ? '—' : `${formatNumberFull(compareTotals.bondPct, 2)}%`}
                    sub="of all holdings value"
                  />
                  <CompareMetric
                    label="Only In All"
                    value={formatCurrencyFull(compareTotals.onlyAllValue)}
                    sub={`${compareTotals.onlyAllRows.length.toLocaleString()} non-bond/cash row${compareTotals.onlyAllRows.length !== 1 ? 's' : ''}`}
                  />
                </Box>
                <TextField
                  value={compareSearch}
                  onChange={(event) => setCompareSearch(event.target.value)}
                  placeholder="Search symbol, CUSIP, description, class, or date"
                  size="small"
                  fullWidth
                  sx={{ '& .MuiOutlinedInput-root': { backgroundColor: colors.surfaceCard } }}
                />
              </CardContent>
            </Card>

            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', xl: 'minmax(0, 1fr) minmax(0, 1fr)' }, gap: 2 }}>
              <Card sx={{ overflow: 'hidden' }}>
                <CardContent sx={{ p: '14px 16px 10px !important', borderBottom: `1px solid ${colors.hairline}` }}>
                  <Box sx={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 1 }}>
                    <Typography variant="subtitle2" sx={{ color: colors.allworthNavy, fontWeight: 800 }}>
                      Bond Holdings
                    </Typography>
                    <Typography variant="caption" sx={{ color: colors.inkTertiary }}>
                      {filteredCompareBonds.length.toLocaleString()} shown
                    </Typography>
                  </Box>
                </CardContent>
                <CompareBondTable
                  bonds={filteredCompareBonds}
                  selectedKey={selectedCompareKey}
                  onSelect={setSelectedCompareKey}
                />
              </Card>

              <Card sx={{ overflow: 'hidden' }}>
                <CardContent sx={{ p: '14px 16px 10px !important', borderBottom: `1px solid ${colors.hairline}` }}>
                  <Box sx={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 1 }}>
                    <Typography variant="subtitle2" sx={{ color: colors.allworthNavy, fontWeight: 800 }}>
                      All Holdings
                    </Typography>
                    <Typography variant="caption" sx={{ color: colors.inkTertiary }}>
                      {filteredCompareHoldings.length.toLocaleString()} shown
                    </Typography>
                  </Box>
                </CardContent>
                <CompareAllHoldingsTable
                  rows={filteredCompareHoldings}
                  bondKeys={bondKeySet}
                  selectedKey={selectedCompareKey}
                  onSelect={setSelectedCompareKey}
                />
              </Card>
            </Box>
          </Box>
        )}
      </TabPanel>

      {/* ── Tab 7: Insights ───────────────────────────────────────────── */}
      <TabPanel value={tab} index={7}>
        <InsightCard title="Strengths" items={summary.strengths} severity="success" />
        <InsightCard title="Risks" items={summary.risks} severity="warning" />
        <InsightCard title="Concentration Warnings" items={summary.concentration_warnings} severity="warning" />
        <InsightCard title="Recommendations" items={summary.recommendations} severity="info" />
      </TabPanel>

      {/* ── Tab 8: Transactions (Tamarac-style activity) ──────────────── */}
      <TabPanel value={tab} index={8}>
        <TransactionsTab
          rows={txRows}
          loading={txLoading}
          error={txError}
          search={txSearch}
          onSearch={setTxSearch}
          onClearError={() => setTxError(null)}
        />
      </TabPanel>
    </Box>
  );
}

function TransactionsTab({
  rows,
  loading,
  error,
  search,
  onSearch,
  onClearError,
}: {
  rows: TransactionRow[] | null;
  loading: boolean;
  error: string | null;
  search: string;
  onSearch: (value: string) => void;
  onClearError: () => void;
}) {
  type TxSortKey = keyof TransactionRow;
  const [sortKey, setSortKey] = useState<TxSortKey>('trade_date');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(100);

  const toggleSort = (key: TxSortKey) => {
    setPage(0);
    if (sortKey === key) setSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortDir('asc'); }
  };

  const filtered = useMemo(() => {
    if (!rows) return [];
    const q = search.trim().toLowerCase();
    const matched = q
      ? rows.filter(r =>
          [r.account_number, r.transaction_type, r.symbol, r.cusip, r.description, r.notes]
            .concat(r.amount == null ? [] : [String(r.amount)])
            .join(' ')
            .toLowerCase()
            .includes(q),
        )
      : rows;
    return [...matched].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [rows, search, sortKey, sortDir]);

  const visibleRows = useMemo(
    () => filtered.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage),
    [filtered, page, rowsPerPage],
  );

  useEffect(() => {
    const lastPage = Math.max(0, Math.ceil(filtered.length / rowsPerPage) - 1);
    if (page > lastPage) setPage(lastPage);
  }, [filtered.length, page, rowsPerPage]);

  const handlePrint = () => {
    printReport({
      title: 'Transactions',
      subtitle: 'Account activity history',
      meta: [{ label: 'Transactions', value: filtered.length.toLocaleString() }],
      columns: [
        { header: 'Account #', value: r => r.account_number },
        { header: 'Trade Date', value: r => formatDateShort(r.trade_date) },
        { header: 'Type', value: r => r.transaction_type || '—' },
        { header: 'Symbol / CUSIP', value: r => r.symbol || r.cusip || '—' },
        { header: 'Description', value: r => r.description || '—' },
        { header: 'Quantity', value: r => formatNumberFull(r.quantity), align: 'right' },
        { header: 'Price', value: r => formatNumberFull(r.price), align: 'right' },
        { header: 'Amount', value: r => formatCurrencyFull(r.amount), align: 'right' },
        { header: 'Notes', value: r => r.notes || '—' },
      ],
      rows: filtered,
    });
  };

  const sourceCounts = useMemo(() => {
    const counts = { staging: 0, over30: 0 };
    for (const row of rows ?? []) {
      if (row.source.endsWith('.transactions_staging')) counts.staging += 1;
      if (row.source.endsWith('.transactions_sells_over_30')) counts.over30 += 1;
    }
    return counts;
  }, [rows]);

  const th = (label: string, key: TxSortKey, align: 'left' | 'right' | 'center' = 'left') => (
    <TableCell align={align} sx={{ whiteSpace: 'nowrap', fontSize: '0.72rem', fontWeight: 600, color: colors.inkSecondary }}>
      <TableSortLabel active={sortKey === key} direction={sortKey === key ? sortDir : 'asc'} onClick={() => toggleSort(key)}>
        {label}
      </TableSortLabel>
    </TableCell>
  );

  if (loading) {
    return (
      <Box>
        <Skeleton variant="rectangular" height={40} sx={{ mb: 1, borderRadius: 1 }} />
        {[1, 2, 3, 4, 5, 6, 7].map(i => (
          <Skeleton key={i} variant="rectangular" height={40} sx={{ mb: 0.5, borderRadius: 1 }} />
        ))}
      </Box>
    );
  }
  if (error) {
    return <Alert severity="error" onClose={onClearError}>{error}</Alert>;
  }
  if (!rows) return null;

  return (
    <>
      <Box sx={{ display: 'flex', gap: 1.5, mb: 2, alignItems: 'center', flexWrap: 'wrap' }}>
        <TextField
          value={search}
          onChange={e => {
            setPage(0);
            onSearch(e.target.value);
          }}
          placeholder="Search type, symbol, CUSIP, description, notes"
          size="small"
          sx={{ flex: 1, minWidth: 260, '& .MuiOutlinedInput-root': { backgroundColor: colors.surfaceCard } }}
        />
        <Button size="small" startIcon={<PrintIcon fontSize="small" />} onClick={handlePrint} disabled={filtered.length === 0}
          sx={{ textTransform: 'none', color: colors.allworthNavy }}>
          Print
        </Button>
        <Chip size="small" label={`Staging: ${sourceCounts.staging.toLocaleString()}`} />
        <Chip size="small" label={`Over 30 days: ${sourceCounts.over30.toLocaleString()}`} />
      </Box>
      {filtered.length === 0 ? (
        <Typography variant="body2" sx={{ color: colors.inkSecondary, py: 4, textAlign: 'center' }}>
          No transactions found for {rows.length === 0 ? 'these accounts' : `"${search}"`}.
        </Typography>
      ) : (
        <Card sx={{ overflow: 'hidden' }}>
          <TableContainer sx={{ maxHeight: 620 }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow sx={{ '& th': { backgroundColor: '#f5f7fa', py: 1 } }}>
                  {th('Account #', 'account_number')}
                  {th('Trade Date', 'trade_date')}
                  {th('Type', 'transaction_type')}
                  {th('Symbol / CUSIP', 'symbol')}
                  {th('Description', 'description')}
                  {th('Quantity', 'quantity', 'right')}
                  {th('Price', 'price', 'right')}
                  {th('Amount', 'amount', 'right')}
                  {th('Notes', 'notes')}
                </TableRow>
              </TableHead>
              <TableBody>
                {visibleRows.map((r, idx) => (
                  <TableRow key={r.transaction_id || `${r.account_number}-${r.trade_date}-${r.amount}-${idx}`} hover sx={{ '& td': { fontSize: '0.8rem', py: 0.6 } }}>
                    <TableCell sx={{ fontFamily: 'monospace', fontWeight: 700, color: colors.allworthNavy, whiteSpace: 'nowrap' }}>
                      {r.account_number}
                    </TableCell>
                    <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDateShort(r.trade_date)}</TableCell>
                    <TableCell sx={{ whiteSpace: 'nowrap' }}>{r.transaction_type || '—'}</TableCell>
                    <TableCell sx={{ fontFamily: 'monospace', whiteSpace: 'nowrap' }}>{r.symbol || r.cusip || '—'}</TableCell>
                    <TableCell sx={{ maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {r.description || '—'}
                    </TableCell>
                    <TableCell align="right">{formatNumberFull(r.quantity)}</TableCell>
                    <TableCell align="right">{formatNumberFull(r.price)}</TableCell>
                    <TableCell align="right" sx={{ fontWeight: 600 }}>{formatCurrencyFull(r.amount)}</TableCell>
                    <TableCell sx={{ color: colors.inkSecondary, maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {r.notes || '—'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          <TablePagination
            component="div"
            count={filtered.length}
            page={page}
            onPageChange={(_, nextPage) => setPage(nextPage)}
            rowsPerPage={rowsPerPage}
            onRowsPerPageChange={event => {
              setRowsPerPage(Number(event.target.value));
              setPage(0);
            }}
            rowsPerPageOptions={[50, 100, 250]}
          />
        </Card>
      )}
    </>
  );
}
