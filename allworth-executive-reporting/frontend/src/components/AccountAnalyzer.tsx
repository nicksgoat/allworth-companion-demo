/**
 * AccountAnalyzer — DataWarehouse-backed bond analysis by account number.
 *
 * Renders:
 *  • Search form with account-number input
 *  • Loading skeleton while fetching
 *  • Friendly error states (not found, DB offline, generic)
 *  • Full PortfolioDashboard once results arrive
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  InputAdornment,
  Skeleton,
  TextField,
  Typography,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import AccountBalanceIcon from '@mui/icons-material/AccountBalance';
import { analyzeAccount, analyzeAccounts } from '../services/bondApi';
import type { AccountAnalysisResult } from '../services/bondApi';
import type { PortfolioSummary } from '../services/bondApi';
import { colors, sectionHeaderStyle } from '../theme';
import PortfolioDashboard from './PortfolioDashboard';

// ─── Helpers ───────────────────────────────────────────────────────────────────

function makeStubPortfolio(result: AccountAnalysisResult): PortfolioSummary {
  const accounts = result.account_numbers?.length ? result.account_numbers : [result.account_number];
  return {
    id: result.account_number,
    name: accounts.length > 1 ? `Combined Accounts (${accounts.length})` : result.account_name ?? result.account_number,
    source_filename: 'DataWarehouse',
    holdings: result.holdings_count,
    accounts,
    created_at: new Date().toISOString(),
  };
}

function parseAccountNumbers(value: string): string[] {
  return Array.from(
    new Set(
      value
        .split(/[\s,;]+/)
        .map(part => part.trim())
        .filter(Boolean)
    )
  );
}

// ─── Loading Skeleton ──────────────────────────────────────────────────────────

function DashboardSkeleton() {
  return (
    <Box>
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 2, mb: 3 }}>
        {[0, 1, 2, 3].map((i) => (
          <Card key={i}>
            <CardContent>
              <Skeleton variant="text" width="60%" height={14} sx={{ mb: 1 }} />
              <Skeleton variant="text" width="80%" height={28} />
            </CardContent>
          </Card>
        ))}
      </Box>
      <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2 }}>
        <Card>
          <CardContent>
            <Skeleton variant="text" width="40%" height={14} sx={{ mb: 2 }} />
            <Skeleton variant="rectangular" height={200} />
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <Skeleton variant="text" width="40%" height={14} sx={{ mb: 2 }} />
            <Skeleton variant="rectangular" height={200} />
          </CardContent>
        </Card>
      </Box>
    </Box>
  );
}

// ─── Empty / Welcome State ─────────────────────────────────────────────────────

function WelcomePrompt() {
  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        py: 8,
        gap: 2,
        color: colors.inkTertiary,
      }}
    >
      <AccountBalanceIcon sx={{ fontSize: 64, color: colors.inkFaint }} />
      <Typography variant="h6" sx={{ color: colors.inkSecondary }}>
        Account Analysis
      </Typography>
      <Typography variant="body2" align="center" sx={{ maxWidth: 400 }}>
        Enter one or more account numbers to pull live bond holdings from the DataWarehouse and run
        full fixed-income analytics.
      </Typography>
    </Box>
  );
}

// ─── Main Component ────────────────────────────────────────────────────────────

interface AccountAnalyzerProps {
  initialAccountNumber?: string;
  autoAnalyze?: boolean;
  hideSearch?: boolean;
}

export default function AccountAnalyzer({
  initialAccountNumber = '',
  autoAnalyze = false,
  hideSearch = false,
}: AccountAnalyzerProps) {
  const [input, setInput] = useState(initialAccountNumber);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AccountAnalysisResult | null>(null);

  const runAnalysis = useCallback(async (accountNumbers: string[]) => {
    if (accountNumbers.length === 0) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const data = accountNumbers.length === 1
        ? await analyzeAccount(accountNumbers[0])
        : await analyzeAccounts(accountNumbers);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An unexpected error occurred.');
    } finally {
      setLoading(false);
    }
  }, []);

  const handleAnalyze = () => runAnalysis(parseAccountNumbers(input));

  useEffect(() => {
    if (!autoAnalyze || !initialAccountNumber.trim()) return;
    setInput(initialAccountNumber);
    void runAnalysis([initialAccountNumber.trim()]);
  }, [autoAnalyze, initialAccountNumber, runAnalysis]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleAnalyze();
  };

  const handleClear = () => {
    setInput('');
    setError(null);
    setResult(null);
  };

  return (
    <Box>
      {/* ── Search bar ──────────────────────────────────────────────────── */}
      {!hideSearch && (
        <Box
          sx={{
            display: 'flex',
            gap: 1.5,
            alignItems: 'center',
            mb: 3,
            flexWrap: 'wrap',
          }}
        >
        <TextField
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Enter one or more account numbers…"
          size="small"
          disabled={loading}
          autoComplete="off"
          helperText="Separate multiple accounts with commas, spaces, or new lines."
          sx={{
            flex: 1,
            minWidth: 240,
            '& .MuiOutlinedInput-root': {
              backgroundColor: colors.surfaceCard,
            },
          }}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon fontSize="small" sx={{ color: colors.inkTertiary }} />
                </InputAdornment>
              ),
            },
          }}
        />
        <Button
          variant="contained"
          onClick={handleAnalyze}
          disabled={loading || parseAccountNumbers(input).length === 0}
          sx={{
            backgroundColor: colors.allworthNavy,
            '&:hover': { backgroundColor: '#0f2e53' },
            textTransform: 'none',
            fontWeight: 700,
            px: 3,
          }}
        >
          {loading ? <CircularProgress size={18} color="inherit" /> : 'Analyze'}
        </Button>
        {(result || error) && (
          <Button
            variant="text"
            onClick={handleClear}
            disabled={loading}
            sx={{ color: colors.inkSecondary, textTransform: 'none' }}
          >
            Clear
          </Button>
        )}
        </Box>
      )}

      {/* ── Result metadata strip ────────────────────────────────────────── */}
      {result && !loading && (
        <Box sx={{ mb: 2 }}>
          <p style={{ ...sectionHeaderStyle, margin: '0 0 4px' }}>
            {(result.account_numbers?.length ?? 1) > 1 ? 'Combined account analysis' : `Account ${result.account_number}`}
            {result.account_name ? ` · ${result.account_name}` : ''}
          </p>
          {(result.account_numbers?.length ?? 0) > 1 && (
            <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap', mb: 0.75 }}>
              {result.account_numbers.map(accountNumber => (
                <Chip
                  key={accountNumber}
                  label={accountNumber}
                  size="small"
                  sx={{ backgroundColor: colors.ice, color: colors.allworthNavy, fontWeight: 700 }}
                />
              ))}
            </Box>
          )}
          <Typography variant="caption" sx={{ color: colors.inkTertiary }}>
            {result.holdings_count} holding{result.holdings_count !== 1 ? 's' : ''} ·{' '}
            {result.enriched_count} enriched from security master
          </Typography>
          {result.enriched_count < result.holdings_count && (
            <Alert severity="info" sx={{ mt: 1, py: 0.5 }}>
              {result.holdings_count - result.enriched_count} holding(s) could not be matched to
              the security master — analytics may be partial.
            </Alert>
          )}
        </Box>
      )}

      {/* ── Error state ──────────────────────────────────────────────────── */}
      {error && (
        <Alert severity="error" onClose={() => setError(null)} sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {/* ── Loading skeleton ─────────────────────────────────────────────── */}
      {loading && <DashboardSkeleton />}

      {/* ── Results ──────────────────────────────────────────────────────── */}
      {!loading && result && (
        <PortfolioDashboard
          portfolio={makeStubPortfolio(result)}
          dashboard={result.dashboard}
          summary={result.summary}
        />
      )}

      {/* ── Empty / welcome state ─────────────────────────────────────────── */}
      {!loading && !result && !error && <WelcomePrompt />}
    </Box>
  );
}
