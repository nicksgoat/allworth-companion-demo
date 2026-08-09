import { useEffect, useMemo, useState } from 'react';
import {
  Box, Card, CardContent, Alert, Typography, Button, MenuItem, TextField,
  Table, TableBody, TableCell, TableHead, TableRow, TableSortLabel,
  CircularProgress, Chip, Divider, FormControlLabel, Switch,
} from '@mui/material';
import PictureAsPdfIcon from '@mui/icons-material/PictureAsPdf';
import AutoGraphIcon from '@mui/icons-material/AutoGraph';
import { colors } from '../theme';
import {
  fetchSampleStrategies,
  generateSamplePortfolio,
  downloadSamplePortfolioPdf,
  downloadSamplePortfolioProposal,
} from '../services/bondApi';
import type { SampleStrategy, SamplePortfolioResult } from '../services/bondApi';

const money = (v: number | null, d = 0) =>
  v == null ? '—' : `$${v.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })}`;
const pct = (v: number | null, d = 3) => (v == null ? '—' : `${v.toFixed(d)}%`);

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <Box sx={{ display: 'flex', justifyContent: 'space-between', py: 0.5, borderBottom: `1px solid ${colors.hairline}` }}>
      <Typography variant="body2" sx={{ color: colors.inkSecondary }}>{label}</Typography>
      <Typography variant="body2" sx={{ fontWeight: 600, color: colors.allworthNavy }}>{value}</Typography>
    </Box>
  );
}

export default function SamplePortfolio() {
  const [strategies, setStrategies] = useState<SampleStrategy[]>([]);
  const [strategyKey, setStrategyKey] = useState('');
  const [targetValue, setTargetValue] = useState(1_000_000);
  const [taxRate, setTaxRate] = useState(37);
  const [excludeUnrated, setExcludeUnrated] = useState(false);
  const [lotSize, setLotSize] = useState(5000);
  const [state, setState] = useState('');
  const [clientName, setClientName] = useState('');
  const [preparedBy, setPreparedBy] = useState('');
  const [proposalTitle, setProposalTitle] = useState('');
  const [result, setResult] = useState<SamplePortfolioResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [proposalLoading, setProposalLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sortCol, setSortCol] = useState<string>('maturity_date');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');

  const handleSort = (col: string) => {
    if (col === sortCol) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortCol(col); setSortDir('asc'); }
  };

  const sortedBonds = useMemo(() => {
    if (!result) return [];
    return [...result.bonds].sort((a, b) => {
      const av = (a as unknown as Record<string, unknown>)[sortCol] ?? '';
      const bv = (b as unknown as Record<string, unknown>)[sortCol] ?? '';
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [result, sortCol, sortDir]);

  const col = (label: string, key: string, align: 'left' | 'right' = 'right') => (
    <TableCell align={align} sx={{ whiteSpace: 'nowrap' }}>
      <TableSortLabel
        active={sortCol === key}
        direction={sortCol === key ? sortDir : 'asc'}
        onClick={() => handleSort(key)}
      >{label}</TableSortLabel>
    </TableCell>
  );

  useEffect(() => {
    fetchSampleStrategies()
      .then((s) => {
        setStrategies(s);
        if (s.length) setStrategyKey(s[0].key);
      })
      .catch((e) => setError(e.message));
  }, []);

  const request = useMemo(
    () => ({
      strategy: strategyKey,
      target_value: targetValue,
      tax_rate: taxRate / 100,
      exclude_unrated: excludeUnrated,
      lot_size: lotSize,
      state: state.trim() || undefined,
    }),
    [strategyKey, targetValue, taxRate, excludeUnrated, lotSize, state],
  );

  const selectedStrategy = strategies.find(s => s.key === strategyKey);

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await generateSamplePortfolio(request));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handlePdf = async () => {
    setPdfLoading(true);
    setError(null);
    try {
      await downloadSamplePortfolioPdf(request);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPdfLoading(false);
    }
  };

  const handleProposal = async () => {
    setProposalLoading(true);
    setError(null);
    try {
      await downloadSamplePortfolioProposal({
        ...request,
        client_name: clientName.trim() || undefined,
        prepared_by: preparedBy.trim() || undefined,
        proposal_title: proposalTitle.trim() || undefined,
      });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setProposalLoading(false);
    }
  };

  const m = result?.metrics;

  return (
    <Box>
      <Typography variant="h6" sx={{ fontWeight: 700, color: colors.allworthNavy, mb: 0.5 }}>
        Sample Bond Portfolio
      </Typography>
      <Typography variant="body2" sx={{ color: colors.inkSecondary, mb: 2 }}>
        Generate an illustrative laddered portfolio that mirrors an Allworth strategy from the
        current bond-ladder universe, with fact-sheet analytics and a one-page PDF.
      </Typography>

      <Card sx={{ mb: 2 }}>
        <CardContent sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'center' }}>
          <TextField
            select label="Strategy" value={strategyKey} size="small" sx={{ minWidth: 260 }}
            onChange={(e) => setStrategyKey(e.target.value)}
          >
            {strategies.map((s) => (
              <MenuItem key={s.key} value={s.key}>{s.label}</MenuItem>
            ))}
          </TextField>
          <TextField
            label="Portfolio Value" type="number" size="small" value={targetValue}
            onChange={(e) => setTargetValue(Number(e.target.value))} sx={{ width: 180 }}
          />
          <TextField
            label="Federal Tax Rate %" type="number" size="small" value={taxRate}
            onChange={(e) => setTaxRate(Number(e.target.value))} sx={{ width: 160 }}
          />
          <TextField
            select label="Lot Size" value={lotSize} size="small" sx={{ width: 160 }}
            onChange={(e) => setLotSize(Number(e.target.value))}
          >
            {[1000, 5000, 10000, 25000, 50000, 100000].map(v => (
              <MenuItem key={v} value={v}>${(v / 1000).toFixed(0)}K</MenuItem>
            ))}
          </TextField>
          {selectedStrategy?.asset === 'municipal' && (
            <TextField
              label="State"
              size="small"
              value={state}
              onChange={(e) => setState(e.target.value.toUpperCase().slice(0, 2))}
              placeholder="CA"
              sx={{ width: 100 }}
            />
          )}
          <FormControlLabel
            control={<Switch checked={excludeUnrated} onChange={(e) => setExcludeUnrated(e.target.checked)} size="small" />}
            label="Require Fitch rating (exclude NR)"
            sx={{ ml: 0.5 }}
          />
          <Button
            variant="contained" startIcon={<AutoGraphIcon />} onClick={handleGenerate}
            disabled={loading || !strategyKey}
          >
            {loading ? 'Generating…' : 'Generate'}
          </Button>
          <Button
            variant="outlined" startIcon={pdfLoading ? <CircularProgress size={16} /> : <PictureAsPdfIcon />}
            onClick={handlePdf} disabled={pdfLoading || !strategyKey}
          >
            Download Fact Sheet
          </Button>
        </CardContent>
      </Card>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {loading && (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}><CircularProgress /></Box>
      )}

      {result && m && (
        <>
          {result.warnings.map((w, i) => (
            <Alert key={i} severity="warning" sx={{ mb: 2 }}>{w}</Alert>
          ))}

          <Card sx={{ mb: 2, borderTop: `3px solid ${colors.allworthAccent}` }}>
            <CardContent>
              <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 0.5, color: colors.allworthNavy }}>
                Build Proposal
              </Typography>
              <Typography variant="body2" sx={{ color: colors.inkSecondary, mb: 2 }}>
                Add client details and download a branded, multi-page proposal (cover, summary, credit
                quality, income schedule, and holdings) for this ladder.
              </Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'center' }}>
                <TextField
                  label="Client (Regarding)" size="small" value={clientName}
                  onChange={(e) => setClientName(e.target.value)} sx={{ minWidth: 200 }}
                />
                <TextField
                  label="Prepared By" size="small" value={preparedBy}
                  onChange={(e) => setPreparedBy(e.target.value)} sx={{ minWidth: 180 }}
                />
                <TextField
                  label="Proposal Title" size="small" value={proposalTitle}
                  onChange={(e) => setProposalTitle(e.target.value)}
                  placeholder={selectedStrategy?.label} sx={{ minWidth: 220 }}
                />
                <Button
                  variant="contained"
                  startIcon={proposalLoading ? <CircularProgress size={16} color="inherit" /> : <PictureAsPdfIcon />}
                  onClick={handleProposal} disabled={proposalLoading}
                >
                  {proposalLoading ? 'Building…' : 'Download Proposal'}
                </Button>
              </Box>
            </CardContent>
          </Card>

          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, mb: 2 }}>
            <Card sx={{ flex: '1 1 260px' }}>
              <CardContent>
                <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>Investment</Typography>
                <StatRow label="Portfolio Value" value={money(m.portfolio_value)} />
                <StatRow label="Cash Invested" value={money(m.cash_invested)} />
                <StatRow label="Total Face Value" value={money(m.total_face_value)} />
                <StatRow label="Number of Securities" value={`${m.number_of_securities}`} />
              </CardContent>
            </Card>
            <Card sx={{ flex: '1 1 260px' }}>
              <CardContent>
                <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>Statistics</Typography>
                <StatRow label="Avg Credit Quality" value={m.average_credit_quality ?? '—'} />
                <StatRow label="YTW / YTM" value={`${pct(m.yield_to_worst)} / ${pct(m.yield_to_maturity)}`} />
                <StatRow label="Tax-Equivalent YTW / YTM" value={`${pct(m.tax_equivalent_ytw)} / ${pct(m.tax_equivalent_ytm)}`} />
                <StatRow label="Investor Federal Tax Rate" value={pct(m.investor_federal_tax_rate, 1)} />
              </CardContent>
            </Card>
            <Card sx={{ flex: '1 1 260px' }}>
              <CardContent>
                <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>Income</Typography>
                <StatRow label="Annual Taxable Interest Income" value={money(m.annual_taxable_income)} />
                <StatRow label="Annual Tax-Exempt Interest Income" value={money(m.annual_tax_exempt_income)} />
                <Divider sx={{ my: 1 }} />
                <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>Credit Quality</Typography>
                {m.credit_quality_distribution.map((g) => (
                  <StatRow key={g.grade} label={g.grade} value={`${g.pct}%`} />
                ))}
              </CardContent>
            </Card>
          </Box>

          <Card>
            <CardContent>
              <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                Holdings <Chip size="small" label={`${result.bonds.length} bonds`} sx={{ ml: 1 }} />
              </Typography>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    {col('CUSIP', 'cusip', 'left')}
                    {col('Description', 'description', 'left')}
                    {col('State', 'state', 'left')}
                    {col('Coupon', 'coupon')}
                    {col('Maturity', 'maturity_date')}
                    {col('Face', 'quantity')}
                    {col('Price', 'price')}
                    {col('Market Value', 'market_value')}
                    {col('YTW', 'yield_to_worst')}
                    {col('Rating', 'rating')}
                    {col('Quality', 'corporate_quality_score')}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {sortedBonds.map((b, i) => (
                    <TableRow key={b.cusip ?? i}>
                      <TableCell>{b.cusip ?? ''}</TableCell>
                      <TableCell>{b.description?.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(' ')}</TableCell>
                      <TableCell>{b.state ?? '—'}</TableCell>
                      <TableCell align="right">{pct(b.coupon, 3)}</TableCell>
                      <TableCell align="right">{b.maturity_date ?? '—'}</TableCell>
                      <TableCell align="right">{money(b.quantity)}</TableCell>
                      <TableCell align="right">{b.price == null ? '—' : b.price.toFixed(2)}</TableCell>
                      <TableCell align="right">{money(b.market_value)}</TableCell>
                      <TableCell align="right">{pct(b.yield_to_worst, 3)}</TableCell>
                      <TableCell align="right">
                        {b.rating
                          ? <>{b.rating}{b.rating_agency && (
                              <Typography component="span" variant="caption" sx={{ color: 'text.secondary', ml: 0.5 }}>
                                ({b.rating_agency})
                              </Typography>
                            )}</>
                          : <Chip size="small" variant="outlined" label="Not rated" sx={{ color: colors.inkTertiary, borderColor: colors.hairline, height: 20, fontSize: 11 }} />}
                      </TableCell>
                      <TableCell align="right">
                        {b.corporate_quality_score == null ? '—' : b.corporate_quality_score.toFixed(1)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </Box>
  );
}
