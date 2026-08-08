// src/FeeCalculator.tsx
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import './FeeCalculator.css';

interface TierBreakdown {
  from: number;
  to: number | null;
  rate: number;
  assets_in_tier: number;
  fee: number;
}

interface FeeResult {
  schedule_name: string;
  aum: number;
  breakdown: TierBreakdown[];
  annual_fee: number;
  quarterly_fee: number;
  effective_rate_pct: number;
  effective_rate_bps: number;
  min_fee_applied: boolean;
  min_quarterly_fee: number;
}

interface HouseholdSearchResult {
  avhhid: number;
  advisor_name: string;
  region: string | null;
  aum: number;
}

interface FilterOptions {
  advisors: { id: string; name: string }[];
  regions: string[];
  channels: string[];
}

interface ProposedFee {
  annual_fee: number;
  quarterly_fee: number;
  effective_rate_pct: number;
  delta: number;
  delta_pct: number;
  min_fee_applied: boolean;
}

interface BillingHousehold {
  avhhid: number;
  household_name?: string;
  advisor?: string;
  billing_def?: string;
  channel?: string;
  campaign_name?: string;
  total_billable: number;
  non_waived_billable: number;
  waived_billable: number;
  waived_accounts: number;
  has_waived: boolean;
  current_aum: number;
  accounts: number;
  current_annual_fee: number;
  current_quarterly_fee: number;
  current_rate_pct: number;
  closest_schedule: string;
  auto_schedule: string;
  auto_schedule_name: string;
  auto_proposed_annual: number;
  auto_proposed_quarterly: number;
  auto_proposed_rate_pct: number;
  auto_delta: number;
  auto_delta_pct: number;
  // Include-waived variants
  auto_proposed_annual_incl: number;
  auto_proposed_rate_pct_incl: number;
  auto_delta_incl: number;
  proposed: Record<string, ProposedFee>;
  proposed_incl: Record<string, ProposedFee>;
}

interface ScheduleSummary {
  name: string;
  total_annual_proposed: number;
  total_delta: number;
  delta_pct: number;
  total_annual_proposed_incl: number;
  total_delta_incl: number;
  delta_pct_incl: number;
}

interface BillingData {
  summary: {
    total_households: number;
    total_accounts: number;
    total_billable_value: number;
    total_non_waived_billable: number;
    total_waived_billable: number;
    total_waived_accounts: number;
    total_annual_billed: number;
  };
  schedule_summary: Record<string, ScheduleSummary>;
  households: BillingHousehold[];
  total_returned: number;
  total_households: number;
}

const SCHEDULE_OPTIONS: { key: string; label: string }[] = [
  { key: 'gm_schedule_new', label: 'GM Schedule New (Min Fee)' },
  { key: 'airline', label: 'New Airline Clients' },
  { key: 'repricing_silver', label: 'Repricing - Silver (1)' },
  { key: 'repricing_gold', label: 'Repricing - Gold (2)' },
  { key: 'repricing_platinum', label: 'Repricing - Platinum (3)' },
  { key: 'repricing_diamond', label: 'Repricing - Diamond (4)' },
  { key: 'repricing_elite', label: 'Repricing - Elite (5)' },
  { key: 'fixed_150', label: '1.50% Fixed' },
  { key: 'fixed_145', label: '1.45% Fixed' },
  { key: 'fixed_140', label: '1.40% Fixed' },
  { key: 'fixed_135', label: '1.35% Fixed' },
  { key: 'fixed_130', label: '1.30% Fixed' },
  { key: 'fixed_125', label: '1.25% Fixed' },
  { key: 'fixed_120', label: '1.20% Fixed' },
  { key: 'fixed_115', label: '1.15% Fixed' },
  { key: 'fixed_110', label: '1.10% Fixed' },
  { key: 'fixed_105', label: '1.05% Fixed' },
  { key: 'fixed_100', label: '1.00% Fixed' },
  { key: 'fixed_095', label: '0.95% Fixed' },
  { key: 'fixed_090', label: '0.90% Fixed' },
  { key: 'fixed_085', label: '0.85% Fixed' },
  { key: 'fixed_080', label: '0.80% Fixed' },
  { key: 'fixed_075', label: '0.75% Fixed' },
  { key: 'fixed_070', label: '0.70% Fixed' },
];

const formatCurrency = (value: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(value);

const formatCurrencyDetailed = (value: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);

const formatTierRange = (from: number, to: number | null) => {
  if (to === null) return `${formatCurrency(from)}+`;
  return `${formatCurrency(from)} – ${formatCurrency(to)}`;
};

const FeeCalculator = () => {
  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [, setSearchResults] = useState<HouseholdSearchResult[]>([]);
  const [, setSearchLoading] = useState(false);
  const searchTimer = useRef<number | null>(null);

  // Filter state
  const [filters, setFilters] = useState<FilterOptions>({ advisors: [], regions: [], channels: [] });
  const [selectedAdvisor, setSelectedAdvisor] = useState('');
  const [selectedRegion, setSelectedRegion] = useState('');
  const [selectedChannel, setSelectedChannel] = useState('');
  const [filtersLoading, setFiltersLoading] = useState(true);

  // Household state
  const [selectedAvhhid, setSelectedAvhhid] = useState<number | null>(null);

  // Calculator state
  const [manualAum, setManualAum] = useState('');
  const [selectedSchedule, setSelectedSchedule] = useState('gm_schedule_new');
  const [feeResult, setFeeResult] = useState<FeeResult | null>(null);
  const [allResults, setAllResults] = useState<Record<string, FeeResult> | null>(null);
  const [compareMode, setCompareMode] = useState(false);
  const [calcLoading, setCalcLoading] = useState(false);

  // Billing upload state
  const [billingData, setBillingData] = useState<BillingData | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [billingSchedule, setBillingSchedule] = useState('');
  const [includeWaived, setIncludeWaived] = useState(false);
  const [statusFilter, setStatusFilter] = useState<'' | 'above' | 'below' | 'on-track'>('');
  const [deltaMinPct, setDeltaMinPct] = useState('');
  const [deltaMaxPct, setDeltaMaxPct] = useState('');
  const [minBillableAum, setMinBillableAum] = useState('');
  const [visibleRows, setVisibleRows] = useState(100);
  const [debouncedDeltaMin, setDebouncedDeltaMin] = useState('');
  const [debouncedDeltaMax, setDebouncedDeltaMax] = useState('');
  const [debouncedMinAum, setDebouncedMinAum] = useState('');
  const [userScheduleOverrides, setUserScheduleOverrides] = useState<Record<string, string>>({});
  const [userModifiedKeys, setUserModifiedKeys] = useState<Set<string>>(new Set());
  const [awfFilter, setAwfFilter] = useState<'' | 'modified' | 'unfilled' | 'auto'>('');
  const [repricingFilter, setRepricingFilter] = useState('');
  // Column sort state
  const [sortColumn, setSortColumn] = useState<string>('');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  // Column filter state
  const [columnFilters, setColumnFilters] = useState<Record<string, string>>({});
  const fileInputRef = useRef<HTMLInputElement>(null);
  const tableWrapRef = useRef<HTMLDivElement>(null);
  const [highlightedAvhhid, setHighlightedAvhhid] = useState<number | null>(null);
  // Range slider filters for scatter chart + table
  const [aumRange, setAumRange] = useState<[number, number]>([0, 0]);
  const [rateRange, setRateRange] = useState<[number, number]>([0, 3]);
  const [debouncedAumRange, setDebouncedAumRange] = useState<[number, number]>([0, 0]);
  const [debouncedRateRange, setDebouncedRateRange] = useState<[number, number]>([0, 3]);
  const [aumMax, setAumMax] = useState(20_000_000);
  const [slidersInitialized, setSlidersInitialized] = useState(false);
  // Lasso (free-draw) selection state
  const [lassoActive, setLassoActive] = useState(false);
  const [lassoDrawing, setLassoDrawing] = useState(false);
  const [lassoPath, setLassoPath] = useState<{ x: number; y: number }[]>([]);
  const [lassoSelectedIds, setLassoSelectedIds] = useState<Set<number>>(new Set());
  const chartContainerRef = useRef<HTMLDivElement>(null);
  // Refs for uncontrolled range number inputs
  const aumMinRef = useRef<HTMLInputElement>(null);
  const aumMaxRef = useRef<HTMLInputElement>(null);
  const rateMinRef = useRef<HTMLInputElement>(null);
  const rateMaxRef = useRef<HTMLInputElement>(null);

  const fmtDollar = (v: number) => '$' + v.toLocaleString();
  const fmtPct = (v: number) => v + '%';
  const parseDollar = (s: string) => parseFloat(s.replace(/[$,\s]/g, ''));
  const parsePct = (s: string) => parseFloat(s.replace(/%/g, ''));

  // Load filter options + cached billing data on mount
  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try {
        const res = await fetch('/fee-calculator/api/filters', { signal: controller.signal });
        const json = await res.json();
        if (json.success) setFilters(json.data);
      } catch { /* ignore — filters just stay as "All" */ }
      finally { setFiltersLoading(false); }
    })();
    // Try to restore last billing upload from server cache
    (async () => {
      try {
        const res = await fetch('/fee-calculator/api/billing-data', { signal: controller.signal });
        const json = await res.json();
        if (json.success) setBillingData(json.data);
      } catch { /* no cached data — user will upload */ }
    })();
    // If the fetch takes >8s (auth popup blocking), unlock the filters anyway
    const timeout = window.setTimeout(() => setFiltersLoading(false), 8000);
    return () => { controller.abort(); clearTimeout(timeout); };
  }, []);

  // Debounce delta % range + min AUM inputs (avoids re-filtering on every keystroke)
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedDeltaMin(deltaMinPct);
      setDebouncedDeltaMax(deltaMaxPct);
      setDebouncedMinAum(minBillableAum);
    }, 400);
    return () => clearTimeout(timer);
  }, [deltaMinPct, deltaMaxPct, minBillableAum]);

  // Initialize range sliders when billing data loads
  useEffect(() => {
    if (!billingData || slidersInitialized) return;
    const maxAum = Math.max(...billingData.households.map((h) => h.current_aum), 1);
    const roundedMax = Math.ceil(maxAum / 1_000_000) * 1_000_000;
    setAumMax(roundedMax);
    setAumRange([0, roundedMax]);
    setDebouncedAumRange([0, roundedMax]);
    setRateRange([0, 3]);
    setDebouncedRateRange([0, 3]);
    setSlidersInitialized(true);
  }, [billingData, slidersInitialized]);

  // Debounce range sliders (300ms) to avoid re-filtering on every drag tick
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedAumRange(aumRange);
      setDebouncedRateRange(rateRange);
    }, 300);
    return () => clearTimeout(timer);
  }, [aumRange, rateRange]);

  // Sync uncontrolled inputs when slider values change
  useEffect(() => {
    if (aumMinRef.current && document.activeElement !== aumMinRef.current) aumMinRef.current.value = fmtDollar(aumRange[0]);
    if (aumMaxRef.current && document.activeElement !== aumMaxRef.current) aumMaxRef.current.value = fmtDollar(aumRange[1]);
  }, [aumRange]);
  useEffect(() => {
    if (rateMinRef.current && document.activeElement !== rateMinRef.current) rateMinRef.current.value = fmtPct(rateRange[0]);
    if (rateMaxRef.current && document.activeElement !== rateMaxRef.current) rateMaxRef.current.value = fmtPct(rateRange[1]);
  }, [rateRange]);

  // Reset visible rows when filters change + scroll table into view
  useEffect(() => {
    setVisibleRows(100);
    if (tableWrapRef.current) {
      tableWrapRef.current.scrollTop = 0;
    }
  }, [searchQuery, selectedAdvisor, selectedChannel, statusFilter, debouncedDeltaMin, debouncedDeltaMax, debouncedMinAum, billingSchedule, includeWaived, awfFilter]);

  // Clear lasso + click-highlight when external filters change
  useEffect(() => {
    if (lassoSelectedIds.size > 0) {
      setLassoSelectedIds(new Set());
      setLassoPath([]);
    }
    if (highlightedAvhhid) setHighlightedAvhhid(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedAdvisor, selectedChannel, statusFilter, awfFilter, repricingFilter]);

  // Auto-populate AWF Recommended based on AUM bands (Jacob's rules):
  // <$300K → Silver, $300K–$1M → Gold, $1M–$2M → Platinum, >$2M → manual
  // If schedule results in lower fee → No Change. Waived → No Change.
  useEffect(() => {
    if (!billingData) return;
    const pKey = includeWaived ? 'proposed_incl' : 'proposed';

    setUserScheduleOverrides((prev) => {
      const overrides: Record<string, string> = {};

      for (const hh of billingData.households) {
        const rowKey = `${hh.avhhid}-${hh.billing_def || ''}`;

        // Preserve user-modified entries
        if (userModifiedKeys.has(rowKey)) {
          overrides[rowKey] = prev[rowKey] || '';
          continue;
        }

        const aum = hh.current_aum;

        // Waived → No Change
        if (hh.has_waived || hh.current_annual_fee <= 0) {
          overrides[rowKey] = 'no_change';
          continue;
        }

        // Determine schedule by AUM band
        let schedKey: string | null = null;
        if (aum < 300000) {
          schedKey = 'repricing_silver';
        } else if (aum < 1000000) {
          schedKey = 'repricing_gold';
        } else if (aum < 2000000) {
          schedKey = 'repricing_platinum';
        } else {
          // >$2M — leave blank for manual selection
          continue;
        }

        // Check if the schedule would lower the fee
        const proposed = (hh as any)[pKey] || hh.proposed;
        const schedFee = proposed[schedKey]?.annual_fee ?? 0;
        if (schedFee <= hh.current_annual_fee) {
          overrides[rowKey] = 'no_change';
        } else {
          overrides[rowKey] = schedKey;
        }
      }

      return overrides;
    });
  }, [billingData, includeWaived, userModifiedKeys]);

  // Debounced search (includes active filters)
  const doSearch = useCallback(async (query: string, advisor: string, region: string, channel: string) => {
    if (query.length < 2 && !advisor && !region && !channel) {
      setSearchResults([]);
      return;
    }
    setSearchLoading(true);
    try {
      const params = new URLSearchParams();
      if (query.length >= 2) params.set('q', query);
      if (advisor) params.set('advisor', advisor);
      if (region) params.set('region', region);
      if (channel) params.set('channel', channel);
      const res = await fetch(`/fee-calculator/api/search?${params.toString()}`);
      const json = await res.json();
      if (json.success) setSearchResults(json.results);
    } catch {
      /* ignore */
    } finally {
      setSearchLoading(false);
    }
  }, []);

  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = window.setTimeout(() => doSearch(searchQuery, selectedAdvisor, selectedRegion, selectedChannel), 300);
    return () => { if (searchTimer.current) clearTimeout(searchTimer.current); };
  }, [searchQuery, selectedAdvisor, selectedRegion, selectedChannel, doSearch]);

  const calculateFee = async () => {
    const aum = parseFloat(manualAum.replace(/[,$\s]/g, ''));
    if (isNaN(aum) || aum <= 0) return;
    setCalcLoading(true);
    try {
      if (compareMode) {
        const res = await fetch('/fee-calculator/api/calculate-all', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ aum }),
        });
        const json = await res.json();
        if (json.success) {
          setAllResults(json.data);
          setFeeResult(json.data[selectedSchedule] || null);
        }
      } else {
        const res = await fetch('/fee-calculator/api/calculate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ aum, schedule: selectedSchedule }),
        });
        const json = await res.json();
        if (json.success) {
          setFeeResult(json.data);
          setAllResults(null);
        }
      }
    } catch {
      /* ignore */
    } finally {
      setCalcLoading(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadError(null);
    setUploadLoading(true);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch('/fee-calculator/api/upload-billing', {
        method: 'POST',
        body: formData,
      });
      if (res.status === 413) {
        setUploadError('File too large to upload. Please split the export or contact support.');
      } else if (res.status === 504 || res.status === 502) {
        setUploadError('Upload timed out while processing. The file may be too large — try a smaller export or retry.');
      } else {
        const text = await res.text();
        let json: any = null;
        try { json = JSON.parse(text); } catch { /* non-JSON error page */ }
        if (json && json.success) {
          setBillingData(json.data);
        } else if (json && json.error) {
          setUploadError(json.error);
        } else {
          setUploadError(`Upload failed (HTTP ${res.status}).`);
        }
      }
    } catch (err) {
      setUploadError('Upload failed — network or server error. Please retry.');
    } finally {
      setUploadLoading(false);
    }
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const activeAum = parseFloat(manualAum.replace(/[,$\s]/g, ''));

  // Filter billing households by search query + active filters + selected household
  const filteredBillingHouseholds = useMemo(() => {
    if (!billingData) return [];
    let list = billingData.households;
    // If a specific household was selected from search, filter to just that one
    if (selectedAvhhid) {
      list = list.filter((hh) => hh.avhhid === selectedAvhhid);
      return list;
    }
    const q = searchQuery.trim().toLowerCase();
    if (q.length >= 2) {
      list = list.filter((hh) =>
        String(hh.avhhid).includes(q) ||
        (hh.household_name || '').toLowerCase().includes(q) ||
        (hh.advisor || '').toLowerCase().includes(q)
      );
    }
    if (selectedAdvisor) {
      const advName = filters.advisors.find((a) => a.id === selectedAdvisor)?.name?.toLowerCase() || '';
      list = list.filter((hh) => (hh.advisor || '').toLowerCase() === advName);
    }
    if (selectedChannel) {
      list = list.filter((hh) => (hh.channel || '').toLowerCase() === selectedChannel.toLowerCase());
    }
    // Min billable AUM filter
    if (debouncedMinAum) {
      const minAum = parseFloat(debouncedMinAum);
      if (!isNaN(minAum)) {
        list = list.filter((hh) => hh.total_billable >= minAum);
      }
    }
    // Status filter & delta % range
    if (statusFilter || debouncedDeltaMin || debouncedDeltaMax) {
      const useAuto = !billingSchedule;
      const pKey = includeWaived ? 'proposed_incl' : 'proposed';
      const minPct = debouncedDeltaMin !== '' ? parseFloat(debouncedDeltaMin) : null;
      const maxPct = debouncedDeltaMax !== '' ? parseFloat(debouncedDeltaMax) : null;

      list = list.filter((hh) => {
        const proposed = (hh as any)[pKey] || hh.proposed;
        const delta: number = useAuto
          ? (includeWaived ? hh.auto_delta_incl : hh.auto_delta)
          : (proposed[billingSchedule]?.delta ?? 0);
        const currentAnnual = hh.current_annual_fee;
        const deltaPct = currentAnnual > 0 ? (delta / currentAnnual) * 100 : 0;

        // Status filter
        if (statusFilter === 'above' && !(delta < -10)) return false;
        if (statusFilter === 'below' && !(delta > 10)) return false;
        if (statusFilter === 'on-track' && (delta < -10 || delta > 10)) return false;

        // Delta % range
        if (minPct !== null && deltaPct < minPct) return false;
        if (maxPct !== null && deltaPct > maxPct) return false;

        return true;
      });
    }
    // AWF assignment filter
    if (awfFilter) {
      list = list.filter((hh) => {
        const rowKey = `${hh.avhhid}-${hh.billing_def || ''}`;
        const userSched = userScheduleOverrides[rowKey] || '';
        const isModified = userModifiedKeys.has(rowKey);
        if (awfFilter === 'modified') return isModified;
        if (awfFilter === 'unfilled') return !userSched;
        if (awfFilter === 'auto') return !!userSched && !isModified;
        return true;
      });
    }
    // Repricing campaign filter
    if (repricingFilter) {
      list = list.filter((hh) => {
        if (repricingFilter === 'in_campaign') return !!(hh.campaign_name);
        if (repricingFilter === 'not_in_campaign') return !(hh.campaign_name);
        // Specific campaign name match (campaign_name may contain multiple comma-separated)
        return (hh.campaign_name || '').toLowerCase().includes(repricingFilter.toLowerCase());
      });
    }
    // Range slider filters (AUM + Fee Rate)
    if (slidersInitialized) {
      list = list.filter((hh) =>
        hh.current_aum >= debouncedAumRange[0] && hh.current_aum <= debouncedAumRange[1]
        && hh.current_rate_pct >= debouncedRateRange[0] && hh.current_rate_pct <= debouncedRateRange[1]
      );
    }
    // Lasso selection filter
    if (lassoSelectedIds.size > 0) {
      list = list.filter((hh) => lassoSelectedIds.has(hh.avhhid));
    }
    return list;
  }, [billingData, searchQuery, selectedAdvisor, selectedChannel, selectedAvhhid, filters.advisors, statusFilter, debouncedDeltaMin, debouncedDeltaMax, debouncedMinAum, billingSchedule, includeWaived, awfFilter, repricingFilter, userScheduleOverrides, userModifiedKeys, debouncedAumRange, debouncedRateRange, slidersInitialized, lassoSelectedIds]);

  // Slider bounds: based on external filters only (NOT range sliders themselves)
  const sliderBounds = useMemo(() => {
    if (!billingData) return { maxAum: 1, maxRate: 3 };
    let list = billingData.households;
    if (selectedAdvisor) {
      const advName = filters.advisors.find((a) => a.id === selectedAdvisor)?.name?.toLowerCase() || '';
      list = list.filter((hh) => (hh.advisor || '').toLowerCase() === advName);
    }
    if (selectedChannel) {
      list = list.filter((hh) => (hh.channel || '').toLowerCase() === selectedChannel.toLowerCase());
    }
    if (debouncedMinAum) {
      const minAum = parseFloat(debouncedMinAum);
      if (!isNaN(minAum)) list = list.filter((hh) => hh.total_billable >= minAum);
    }
    if (awfFilter) {
      list = list.filter((hh) => {
        const rowKey = `${hh.avhhid}-${hh.billing_def || ''}`;
        const userSched = userScheduleOverrides[rowKey] || '';
        const isModified = userModifiedKeys.has(rowKey);
        if (awfFilter === 'modified') return isModified;
        if (awfFilter === 'unfilled') return !userSched;
        if (awfFilter === 'auto') return !!userSched && !isModified;
        return true;
      });
    }
    if (repricingFilter) {
      list = list.filter((hh) => {
        if (repricingFilter === 'in_campaign') return !!(hh.campaign_name);
        if (repricingFilter === 'not_in_campaign') return !(hh.campaign_name);
        return (hh.campaign_name || '').toLowerCase().includes(repricingFilter.toLowerCase());
      });
    }
    let maxAum = 1, maxRate = 0.5;
    for (const hh of list) {
      if (hh.current_aum > maxAum) maxAum = hh.current_aum;
      if (hh.current_rate_pct > 0 && hh.current_rate_pct <= 3 && hh.current_rate_pct > maxRate) maxRate = hh.current_rate_pct;
    }
    return { maxAum, maxRate: Math.ceil(maxRate * 20) / 20 };
  }, [billingData, selectedAdvisor, selectedChannel, debouncedMinAum, awfFilter, repricingFilter, filters.advisors, userScheduleOverrides, userModifiedKeys]);

  // Reset range sliders to full extent when external filters change
  useEffect(() => {
    if (!slidersInitialized) return;
    setAumRange([0, sliderBounds.maxAum]);
    setRateRange([0, sliderBounds.maxRate]);
  }, [sliderBounds.maxAum, sliderBounds.maxRate, slidersInitialized]);

  // Memoize campaign filter options (avoid re-computing flatMap in JSX)
  const campaignOptions = useMemo(() => {
    if (!billingData) return [];
    return [...new Set(
      billingData.households.flatMap((hh) => (hh.campaign_name || '').split(', ').filter(Boolean))
    )].sort();
  }, [billingData]);

  // Active filter count for badge
  const activeFilterCount = useMemo(() => {
    let count = 0;
    if (selectedAdvisor) count++;
    if (selectedRegion) count++;
    if (selectedChannel) count++;
    if (statusFilter) count++;
    if (deltaMinPct || deltaMaxPct) count++;
    if (minBillableAum) count++;
    if (awfFilter) count++;
    if (repricingFilter) count++;
    if (searchQuery.trim().length >= 2) count++;
    if (lassoSelectedIds.size > 0) count++;
    return count;
  }, [selectedAdvisor, selectedRegion, selectedChannel, statusFilter, deltaMinPct, deltaMaxPct, minBillableAum, awfFilter, repricingFilter, searchQuery, lassoSelectedIds]);

  // Helper to get a sortable/filterable value from a household row by column key
  const getColumnValue = useCallback((hh: BillingHousehold, col: string): string | number => {
    const useAuto = !billingSchedule;
    const proposed = includeWaived ? hh.proposed_incl : hh.proposed;
    const pKey = includeWaived ? 'proposed_incl' : 'proposed';
    const rowKey = `${hh.avhhid}-${hh.billing_def || ''}`;
    const userSched = userScheduleOverrides[rowKey] || '';
    switch (col) {
      case 'avhhid': return hh.avhhid;
      case 'household_name': return hh.household_name || '';
      case 'advisor': return hh.advisor || '';
      case 'billing_def': return hh.billing_def || '';
      case 'campaign_name': return hh.campaign_name || '';
      case 'total_billable': return hh.total_billable;
      case 'current_aum': return hh.current_aum;
      case 'quarterly_fee': return hh.current_quarterly_fee;
      case 'annual_fee': return hh.current_annual_fee;
      case 'current_rate': return hh.current_rate_pct;
      case 'proposed_schedule': return useAuto ? hh.auto_schedule_name : (SCHEDULE_OPTIONS.find(s => s.key === billingSchedule)?.label || '');
      case 'proposed_annual': return useAuto ? (includeWaived ? hh.auto_proposed_annual_incl : hh.auto_proposed_annual) : (proposed[billingSchedule]?.annual_fee ?? 0);
      case 'proposed_rate': return useAuto ? (includeWaived ? hh.auto_proposed_rate_pct_incl : hh.auto_proposed_rate_pct) : (proposed[billingSchedule]?.effective_rate_pct ?? 0);
      case 'delta': return useAuto ? (includeWaived ? hh.auto_delta_incl : hh.auto_delta) : (proposed[billingSchedule]?.delta ?? 0);
      case 'status': {
        const d = useAuto ? (includeWaived ? hh.auto_delta_incl : hh.auto_delta) : (((hh as any)[pKey] || hh.proposed)[billingSchedule]?.delta ?? 0);
        return d < -10 ? 'Above' : d > 10 ? 'Below' : 'On Track';
      }
      case 'awf_schedule': {
        if (!userSched) return '';
        return userSched === 'no_change' ? 'No Change' : (SCHEDULE_OPTIONS.find(s => s.key === userSched)?.label || '');
      }
      case 'awf_annual': {
        if (!userSched) return '';
        if (userSched === 'no_change') return hh.current_annual_fee;
        return proposed[userSched]?.annual_fee ?? 0;
      }
      case 'awf_delta': {
        if (!userSched) return '';
        if (userSched === 'no_change') return 0;
        const fee = proposed[userSched]?.annual_fee ?? 0;
        return fee - hh.current_annual_fee;
      }
      default: return '';
    }
  }, [billingSchedule, includeWaived, userScheduleOverrides]);

  // Apply column filters + sort on top of existing filtered list
  const sortedBillingHouseholds = useMemo(() => {
    let list = [...filteredBillingHouseholds];

    // Column dropdown filters
    const activeFilters = Object.entries(columnFilters).filter(([, v]) => v.trim() !== '');
    if (activeFilters.length > 0) {
      list = list.filter((hh) =>
        activeFilters.every(([col, filterVal]) => {
          const val = getColumnValue(hh, col);
          if (filterVal === '__empty__') return String(val) === '';
          const strVal = String(val).toLowerCase();
          // Campaign column: use includes since values may be comma-separated
          if (col === 'campaign_name') return strVal.includes(filterVal.trim().toLowerCase());
          return strVal === filterVal.trim().toLowerCase();
        })
      );
    }

    // Sort
    if (sortColumn) {
      list.sort((a, b) => {
        const aVal = getColumnValue(a, sortColumn);
        const bVal = getColumnValue(b, sortColumn);
        let cmp = 0;
        if (typeof aVal === 'number' && typeof bVal === 'number') {
          cmp = aVal - bVal;
        } else {
          cmp = String(aVal).localeCompare(String(bVal), undefined, { numeric: true, sensitivity: 'base' });
        }
        return sortDirection === 'desc' ? -cmp : cmp;
      });
    }

    return list;
  }, [filteredBillingHouseholds, columnFilters, sortColumn, sortDirection, getColumnValue]);

  const handleColumnSort = (col: string) => {
    if (sortColumn === col) {
      setSortDirection((d) => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(col);
      setSortDirection('asc');
    }
  };

  const handleColumnFilter = (col: string, value: string) => {
    setColumnFilters((prev) => ({ ...prev, [col]: value }));
  };

  const handleScatterClick = (point: any) => {
    if (lassoActive) return; // Don't handle clicks while lasso mode is on
    setHighlightedAvhhid(point.avhhid);
    // Scroll table into view without filtering (use search to find the row)
    setSearchQuery(String(point.avhhid));
    setTimeout(() => {
      tableWrapRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
  };

  // Recompute summary + schedule impact from filtered households
  // Uses AWF Recommended overrides — unfilled households assumed "no change" for totals
  const filteredSummary = useMemo(() => {
    const hhs = sortedBillingHouseholds;
    const pKey = includeWaived ? 'proposed_incl' : 'proposed';

    const totalAccounts = hhs.reduce((s, h) => s + h.accounts, 0);
    const totalAum = hhs.reduce((s, h) => s + h.current_aum, 0);
    const totalAnnualCurrent = hhs.reduce((s, h) => s + h.current_annual_fee, 0);
    const currentRate = totalAum > 0 ? (totalAnnualCurrent / totalAum) * 100 : 0;

    // After fee changes — filled use their assigned schedule, unfilled use current (no change)
    let totalAnnualProposed = 0;
    for (const hh of hhs) {
      const rowKey = `${hh.avhhid}-${hh.billing_def || ''}`;
      const userSched = userScheduleOverrides[rowKey] || '';
      if (!userSched || userSched === 'no_change') {
        totalAnnualProposed += hh.current_annual_fee;
      } else {
        const proposed = (hh as any)[pKey] || hh.proposed;
        totalAnnualProposed += proposed[userSched]?.annual_fee ?? hh.current_annual_fee;
      }
    }
    const proposedRate = totalAum > 0 ? (totalAnnualProposed / totalAum) * 100 : 0;
    const feeChange = totalAnnualProposed - totalAnnualCurrent;

    return {
      total_households: hhs.length,
      total_accounts: totalAccounts,
      total_aum: totalAum,
      current_rate: currentRate,
      current_annual: totalAnnualCurrent,
      proposed_rate: proposedRate,
      proposed_annual: totalAnnualProposed,
      fee_change: feeChange,
    };
  }, [sortedBillingHouseholds, includeWaived, userScheduleOverrides]);

  // Book segments breakdown by AUM tier — uses AWF Recommended overrides
  const bookSegments = useMemo(() => {
    const hhs = sortedBillingHouseholds;
    if (!hhs.length) return null;
    const pKey = includeWaived ? 'proposed_incl' : 'proposed';

    const tiers = [
      { label: '<$300K', min: 0, max: 300000 },
      { label: '$300K–$1M', min: 300000, max: 1000000 },
      { label: '$1M–$2M', min: 1000000, max: 2000000 },
      { label: '$2M–$5M', min: 2000000, max: 5000000 },
      { label: '>$5M', min: 5000000, max: Infinity },
    ];

    const segments = tiers.map(({ label, min, max }) => {
      const tierHhs = hhs.filter(h => h.current_aum >= min && h.current_aum < max);
      const clients = tierHhs.length;
      const aum = tierHhs.reduce((s, h) => s + h.current_aum, 0);
      const currentAnnual = tierHhs.reduce((s, h) => s + h.current_annual_fee, 0);

      let proposedAnnual = 0;
      let withIncrease = 0;
      let filledClients = 0;
      for (const hh of tierHhs) {
        const rowKey = `${hh.avhhid}-${hh.billing_def || ''}`;
        const userSched = userScheduleOverrides[rowKey] || '';

        let pa: number;
        if (!userSched || userSched === 'no_change') {
          pa = hh.current_annual_fee; // Unfilled or No Change → current fee
        } else {
          filledClients++;
          const proposed = (hh as any)[pKey] || hh.proposed;
          pa = proposed[userSched]?.annual_fee ?? hh.current_annual_fee;
        }
        proposedAnnual += pa;
        if (pa > hh.current_annual_fee + 1) withIncrease++;
      }

      // needsAttention = clients with no AWF assignment at all
      const unfilledCount = tierHhs.filter(h => !userScheduleOverrides[`${h.avhhid}-${h.billing_def || ''}`]).length;
      const newRate = aum > 0 ? (proposedAnnual / aum) * 100 : 0;
      const feeChange = proposedAnnual - currentAnnual;
      const feeChangePct = currentAnnual > 0 ? (feeChange / currentAnnual) * 100 : 0;

      return { label, clients, needsAttention: unfilledCount, withIncrease, aum, newRate, proposedAnnual, feeChange, feeChangePct };
    });

    // Totals row
    const totals = {
      label: 'Totals',
      clients: segments.reduce((s, seg) => s + seg.clients, 0),
      needsAttention: segments.reduce((s, seg) => s + seg.needsAttention, 0),
      withIncrease: segments.reduce((s, seg) => s + seg.withIncrease, 0),
      aum: segments.reduce((s, seg) => s + seg.aum, 0),
      newRate: 0,
      proposedAnnual: segments.reduce((s, seg) => s + seg.proposedAnnual, 0),
      feeChange: segments.reduce((s, seg) => s + seg.feeChange, 0),
      feeChangePct: 0,
    };
    totals.newRate = totals.aum > 0 ? (totals.proposedAnnual / totals.aum) * 100 : 0;
    const totalCurrentAnnual = hhs.reduce((s, h) => s + h.current_annual_fee, 0);
    totals.feeChangePct = totalCurrentAnnual > 0 ? (totals.feeChange / totalCurrentAnnual) * 100 : 0;

    return { segments, totals };
  }, [sortedBillingHouseholds, includeWaived, userScheduleOverrides]);

  // Scatter plot data: AUM vs Fee Rate (%), colored by fee status — pre-grouped
  // Scatter chart uses billingData directly (not table-filtered list) so table filters don't collapse the chart
  const scatterGroups = useMemo(() => {
    const groups = { onTrack: [] as any[], below: [] as any[], above: [] as any[] };
    if (!filteredBillingHouseholds || filteredBillingHouseholds.length === 0) return groups;
    for (const hh of filteredBillingHouseholds) {
      if (hh.current_rate_pct <= 0 || hh.current_rate_pct > 3 || hh.current_aum <= 0) continue;

      const rowKey = `${hh.avhhid}-${hh.billing_def || ''}`;
      const userSched = userScheduleOverrides[rowKey] || '';
      const pKey = includeWaived ? 'proposed_incl' : 'proposed';
      const proposed = (hh as any)[pKey] || hh.proposed;

      let delta = 0;
      if (userSched === 'no_change') {
        delta = 0;
      } else if (userSched) {
        delta = proposed[userSched]?.delta ?? 0;
      } else {
        delta = includeWaived ? hh.auto_delta_incl : hh.auto_delta;
      }
      const deltaPct = hh.current_annual_fee > 0 ? (delta / hh.current_annual_fee) * 100 : 0;

      const point = {
        avhhid: hh.avhhid,
        name: hh.household_name || `HH ${hh.avhhid}`,
        aum: hh.current_aum,
        ratePct: hh.current_rate_pct,
        advisor: hh.advisor || '',
        annualFee: hh.current_annual_fee,
        delta,
      };

      if (deltaPct < -10) groups.above.push(point);
      else if (deltaPct > 10) groups.below.push(point);
      else groups.onTrack.push(point);
    }
    return groups;
  }, [filteredBillingHouseholds, userScheduleOverrides, includeWaived]);

  // Axis domain bounds (safe reduce — no stack overflow from spread)
  const scatterBounds = useMemo(() => {
    let maxAum = 1, maxRate = 0.5;
    for (const arr of [scatterGroups.onTrack, scatterGroups.below, scatterGroups.above]) {
      for (const d of arr) {
        if (d.aum > maxAum) maxAum = d.aum;
        if (d.ratePct > maxRate) maxRate = d.ratePct;
      }
    }
    return { maxAum, maxRate: Math.ceil(maxRate * 20) / 20, count: scatterGroups.onTrack.length + scatterGroups.below.length + scatterGroups.above.length };
  }, [scatterGroups]);

  // Lasso: point-in-polygon (ray casting)
  const pointInPolygon = useCallback((px: number, py: number, polygon: { x: number; y: number }[]) => {
    let inside = false;
    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
      const xi = polygon[i].x, yi = polygon[i].y;
      const xj = polygon[j].x, yj = polygon[j].y;
      if ((yi > py) !== (yj > py) && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) {
        inside = !inside;
      }
    }
    return inside;
  }, []);

  // Convert data point to pixel position within chart area
  const dataToPixel = useCallback((aum: number, ratePct: number) => {
    const container = chartContainerRef.current;
    if (!container) return null;
    const rect = container.getBoundingClientRect();
    const plotLeft = 60;
    const plotTop = 10;
    const plotWidth = rect.width - 60 - 30;
    const plotHeight = 360 - 10 - 30;
    const x = plotLeft + (aum / scatterBounds.maxAum) * plotWidth;
    const y = plotTop + (1 - ratePct / scatterBounds.maxRate) * plotHeight;
    return { x, y };
  }, [scatterBounds.maxAum, scatterBounds.maxRate]);

  const handleLassoMouseDown = useCallback((e: React.MouseEvent) => {
    if (!lassoActive) return;
    const container = chartContainerRef.current;
    if (!container) return;
    const rect = container.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    setLassoDrawing(true);
    setLassoPath([{ x, y }]);
    setLassoSelectedIds(new Set());
  }, [lassoActive]);

  const handleLassoMouseMove = useCallback((e: React.MouseEvent) => {
    if (!lassoDrawing) return;
    const container = chartContainerRef.current;
    if (!container) return;
    const rect = container.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    setLassoPath((prev) => [...prev, { x, y }]);
  }, [lassoDrawing]);

  const handleLassoMouseUp = useCallback(() => {
    if (!lassoDrawing) return;
    setLassoDrawing(false);
    if (lassoPath.length < 3) return;
    const allPoints = [...scatterGroups.onTrack, ...scatterGroups.below, ...scatterGroups.above];
    const selected = new Set<number>();
    for (const pt of allPoints) {
      const pixel = dataToPixel(pt.aum, pt.ratePct);
      if (pixel && pointInPolygon(pixel.x, pixel.y, lassoPath)) {
        selected.add(pt.avhhid);
      }
    }
    setLassoSelectedIds(selected);
    if (selected.size > 0) {
      setTimeout(() => {
        tableWrapRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 100);
    }
  }, [lassoDrawing, lassoPath, scatterGroups, dataToPixel, pointInPolygon]);

  const clearLassoSelection = useCallback(() => {
    setLassoSelectedIds(new Set());
    setLassoPath([]);
  }, []);

  // Auto-recalculate when compareMode or selectedSchedule changes
  useEffect(() => {
    if (!isNaN(activeAum) && activeAum > 0 && (feeResult || allResults)) {
      calculateFee();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [compareMode, selectedSchedule]);

  // CSV export of billing comparison
  const exportBillingCsv = () => {
    if (!sortedBillingHouseholds.length) return;
    const useAuto = !billingSchedule;
    const hasHH = sortedBillingHouseholds[0]?.household_name !== undefined;
    const hasAdv = sortedBillingHouseholds[0]?.advisor !== undefined;
    const hasDef = sortedBillingHouseholds[0]?.billing_def !== undefined;
    const pKey = includeWaived ? 'proposed_incl' : 'proposed';

    const headers = [
      'AVHHID',
      ...(hasHH ? ['Household'] : []),
      ...(hasAdv ? ['Advisor'] : []),
      ...(hasDef ? ['Billing Definition'] : []),
      'CSV Billable', 'Non-Waived Billable', 'Waived Billable', 'Current AUM',
      'Current Quarterly', 'Current Annual', 'Current Rate',
      'Proposed Schedule', 'Proposed Annual', 'Proposed Rate', 'Delta', 'Status', 'Has Waived',
      'AWF Recommended', 'AWF Annual', 'AWF Delta',
      'Repricing Campaign',
    ];

    const rows = sortedBillingHouseholds.map((hh) => {
      const proposed = (hh as any)[pKey] || hh.proposed;
      const proposedAnnual = useAuto
        ? (includeWaived ? hh.auto_proposed_annual_incl : hh.auto_proposed_annual)
        : (proposed[billingSchedule]?.annual_fee ?? 0);
      const proposedRate = useAuto
        ? (includeWaived ? hh.auto_proposed_rate_pct_incl : hh.auto_proposed_rate_pct)
        : (proposed[billingSchedule]?.effective_rate_pct ?? 0);
      const delta = useAuto
        ? (includeWaived ? hh.auto_delta_incl : hh.auto_delta)
        : (proposed[billingSchedule]?.delta ?? 0);
      const schedName = useAuto ? hh.auto_schedule_name : SCHEDULE_OPTIONS.find(s => s.key === billingSchedule)?.label || '';
      const status = delta < -10 ? 'Above' : delta > 10 ? 'Below' : 'On Track';
      const rowKey = `${hh.avhhid}-${hh.billing_def || ''}`;
      const userSched = userScheduleOverrides[rowKey] || '';
      const userProposed = (userSched && userSched !== 'no_change') ? (proposed[userSched] ?? null) : null;
      const userAnnual = userSched === 'no_change' ? hh.current_annual_fee : (userProposed?.annual_fee ?? null);
      const userDelta = userSched === 'no_change' ? 0 : (userAnnual !== null ? userAnnual - hh.current_annual_fee : null);
      const userSchedName = userSched === 'no_change' ? 'No Change' : (userSched ? (SCHEDULE_OPTIONS.find(s => s.key === userSched)?.label || '') : '');
      return [
        hh.avhhid,
        ...(hasHH ? [hh.household_name || ''] : []),
        ...(hasAdv ? [hh.advisor || ''] : []),
        ...(hasDef ? [hh.billing_def || ''] : []),
        hh.total_billable.toFixed(2), hh.non_waived_billable.toFixed(2), hh.waived_billable.toFixed(2),
        hh.current_aum.toFixed(2),
        hh.current_quarterly_fee.toFixed(2), hh.current_annual_fee.toFixed(2),
        hh.current_rate_pct.toFixed(4) + '%',
        schedName, proposedAnnual.toFixed(2), proposedRate.toFixed(4) + '%',
        delta.toFixed(2), status, hh.has_waived ? 'Yes' : 'No',
        userSchedName, userAnnual !== null ? userAnnual.toFixed(2) : '', userDelta !== null ? userDelta.toFixed(2) : '',
        hh.campaign_name || '',
      ];
    });

    const csvContent = [headers, ...rows].map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `billing_comparison_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Excel export with dropdowns and formulas
  const exportExcel = async () => {
    if (!sortedBillingHouseholds.length) return;
    const households = sortedBillingHouseholds.map((hh) => ({
      avhhid: hh.avhhid,
      household_name: hh.household_name || '',
      advisor: hh.advisor || '',
      billing_def: hh.billing_def || '',
      current_aum: hh.current_aum,
      current_annual_fee: hh.current_annual_fee,
      current_rate_pct: hh.current_rate_pct,
      campaign_name: hh.campaign_name || '',
    }));
    try {
      const res = await fetch('/fee-calculator/api/export-excel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ households, overrides: userScheduleOverrides }),
      });
      if (!res.ok) throw new Error('Export failed');
      const blob = await res.blob();
      // Extract filename from Content-Disposition header if available
      const disposition = res.headers.get('Content-Disposition') || '';
      const filenameMatch = disposition.match(/filename=(.+?)(?:;|$)/);
      const filename = filenameMatch ? filenameMatch[1].replace(/"/g, '') : `Fee_Repricing-${new Date().toISOString().slice(0, 10)}.xlsx`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('Excel export error:', e);
      alert('Failed to export Excel file. Please try again.');
    }
  };

  return (
    <div className="fee-calc-page">
      <div className="fee-calc-bg" aria-hidden="true">
        <div className="fee-calc-orb fee-calc-orb-1" />
        <div className="fee-calc-orb fee-calc-orb-2" />
        <div className="fee-calc-orb fee-calc-orb-3" />
      </div>
      <div className="fee-calc-container">
      <a className="fee-calc-back" href="/">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6"/></svg>
        Back to hub
      </a>
      <header className="fee-calc-header">
        <h1>Fee Calculator</h1>
        <p className="fee-calc-subtitle">Tiered fee computation for new client pricing</p>
      </header>

      {/* Fee Schedule Reference Tile */}
      <section className="fee-calc-section fee-schedule-ref">
        <h2>New Fee Schedules</h2>
        <p className="fee-schedule-ref-desc">
          Clients are assigned a tier (Silver–Elite) based on total household AUM. Fees are calculated using a <strong>marginal/tiered</strong> structure — each AUM band is charged at its own rate, not a single flat rate on the entire balance.
        </p>
        <div className="fee-schedule-table-wrap">
          <table className="fee-schedule-table">
            <thead>
              <tr>
                <th>AUM From</th>
                <th>AUM To</th>
                <th>Explanation</th>
                <th className="aum-header">&lt;$300K<br/><span>Silver (1)</span></th>
                <th className="aum-header">$300K–$1M<br/><span>Gold (2)</span></th>
                <th className="aum-header">$1M–$2M<br/><span>Platinum (3)</span></th>
                <th className="aum-header">$2M–$5M<br/><span>Diamond (4)</span></th>
                <th className="aum-header">&gt;$5M<br/><span>Elite (5)</span></th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>$0</td><td>$100,000</td><td className="expl">First 100,000</td>
                <td>2.00%</td><td>1.40%</td><td>1.30%</td><td>1.20%</td><td>0.95%</td>
              </tr>
              <tr>
                <td>$100,001</td><td>$200,000</td><td className="expl">Next 100,000</td>
                <td>1.50%</td><td>1.40%</td><td>1.30%</td><td>1.20%</td><td>0.95%</td>
              </tr>
              <tr>
                <td>$200,001</td><td>$1,000,000</td><td className="expl">Next 800,000</td>
                <td>1.30%</td><td>1.20%</td><td>1.10%</td><td>1.00%</td><td>0.95%</td>
              </tr>
              <tr>
                <td>$1,000,001</td><td>$2,500,000</td><td className="expl">Next 1,500,000</td>
                <td>1.00%</td><td>1.00%</td><td>1.00%</td><td>0.95%</td><td>0.95%</td>
              </tr>
              <tr>
                <td>$2,500,001</td><td>$5,000,000</td><td className="expl">Next 2,500,000</td>
                <td>0.80%</td><td>0.80%</td><td>0.80%</td><td>0.85%</td><td>0.85%</td>
              </tr>
              <tr>
                <td>$5,000,001</td><td>∞</td><td className="expl">Above 5,000,000</td>
                <td>0.70%</td><td>0.70%</td><td>0.70%</td><td>0.75%</td><td>0.75%</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* Billing Comparison (top) — includes filters, search, HH card */}
      <section className="fee-calc-section">
        <h2>Billing Comparison</h2>
        <div className="fee-calc-panel">

        {/* Filters + Search + HH Card — merged into billing tile */}
        <div className="fee-calc-filters">
          <div className="fee-calc-filter">
            <label>Advisor</label>
            <div className="filter-select-wrap">
              <select
                value={selectedAdvisor}
                onChange={(e) => setSelectedAdvisor(e.target.value)}
                disabled={filtersLoading}
              >
                <option value="">All Advisors</option>
                {filters.advisors.map((a) => (
                  <option key={a.id} value={a.id}>{a.name}</option>
                ))}
              </select>
              {selectedAdvisor && <button className="filter-clear-x" onClick={() => setSelectedAdvisor('')} title="Clear">×</button>}
            </div>
          </div>
          <div className="fee-calc-filter">
            <label>Region</label>
            <div className="filter-select-wrap">
              <select
                value={selectedRegion}
                onChange={(e) => setSelectedRegion(e.target.value)}
                disabled={filtersLoading}
              >
                <option value="">All Regions</option>
                {filters.regions.map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
              {selectedRegion && <button className="filter-clear-x" onClick={() => setSelectedRegion('')} title="Clear">×</button>}
            </div>
          </div>
          <div className="fee-calc-filter">
            <label>Channel</label>
            <div className="filter-select-wrap">
              <select
                value={selectedChannel}
                onChange={(e) => setSelectedChannel(e.target.value)}
                disabled={filtersLoading}
              >
                <option value="">All Channels</option>
                {filters.channels.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
              {selectedChannel && <button className="filter-clear-x" onClick={() => setSelectedChannel('')} title="Clear">×</button>}
            </div>
          </div>
          <div className="fee-calc-filter">
            <label>Status</label>
            <div className="filter-select-wrap">
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as any)}
              >
                <option value="">All Statuses</option>
                <option value="above">Above</option>
                <option value="on-track">On Track</option>
                <option value="below">Below</option>
              </select>
              {statusFilter && <button className="filter-clear-x" onClick={() => setStatusFilter('')} title="Clear">×</button>}
            </div>
          </div>
          <div className="fee-calc-filter">
            <label>Delta % Range</label>
            <div className="fee-calc-delta-range">
              <input
                type="number"
                placeholder="Min"
                value={deltaMinPct}
                onChange={(e) => setDeltaMinPct(e.target.value)}
                className="delta-range-input"
              />
              <span className="delta-range-sep">to</span>
              <input
                type="number"
                placeholder="Max"
                value={deltaMaxPct}
                onChange={(e) => setDeltaMaxPct(e.target.value)}
                className="delta-range-input"
              />
            </div>
          </div>
          <div className="fee-calc-filter">
            <label>Min Billable AUM</label>
            <input
              type="number"
              placeholder="e.g. 500000"
              value={minBillableAum}
              onChange={(e) => setMinBillableAum(e.target.value)}
              className="delta-range-input min-aum-input"
            />
          </div>
          <div className="fee-calc-filter">
            <label>AWF Assignment</label>
            <div className="filter-select-wrap">
              <select
                value={awfFilter}
                onChange={(e) => setAwfFilter(e.target.value as any)}
              >
                <option value="">All</option>
                <option value="modified">User Modified</option>
                <option value="unfilled">Unfilled</option>
                <option value="auto">Auto-Filled</option>
              </select>
              {awfFilter && <button className="filter-clear-x" onClick={() => setAwfFilter('')} title="Clear">×</button>}
            </div>
          </div>
          <div className="fee-calc-filter">
            <label>Repricing Campaign</label>
            <div className="filter-select-wrap">
              <select
                value={repricingFilter}
                onChange={(e) => setRepricingFilter(e.target.value)}
              >
                <option value="">All</option>
                <option value="in_campaign">In Any Campaign</option>
                <option value="not_in_campaign">Not In Campaign</option>
                {campaignOptions.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
              {repricingFilter && <button className="filter-clear-x" onClick={() => setRepricingFilter('')} title="Clear">×</button>}
            </div>
          </div>
          {activeFilterCount > 0 && (
            <button
              className="fee-calc-btn-clear"
              onClick={() => {
                setSelectedAdvisor('');
                setSelectedRegion('');
                setSelectedChannel('');
                setSelectedAvhhid(null);
                setStatusFilter('');
                setDeltaMinPct('');
                setDeltaMaxPct('');
                setMinBillableAum('');
                setAwfFilter('');
                setRepricingFilter('');
                setSearchQuery('');
                setHighlightedAvhhid(null);
                setLassoSelectedIds(new Set());
                setLassoPath([]);
                setLassoActive(false);
                setColumnFilters({});
                setSortColumn('');
                setSortDirection('asc');
                if (slidersInitialized) {
                  setAumRange([0, aumMax]);
                  setRateRange([0, 3]);
                }
              }}
            >
              Clear Filters <span className="filter-badge">{activeFilterCount}</span>
            </button>
          )}
        </div>

        <div className="fee-calc-search-wrap">
          <input
            type="text"
            className="fee-calc-search"
            placeholder="Search by advisor name or AVHHID..."
            value={searchQuery}
            onChange={(e) => { setSearchQuery(e.target.value); setSelectedAvhhid(null); }}
          />
          {searchQuery && (
            <button className="search-clear-btn" onClick={() => { setSearchQuery(''); setHighlightedAvhhid(null); }} title="Clear search">×</button>
          )}
        </div>

        {/* Upload */}
        <p className="fee-calc-hint">Upload a Billable Data export (CSV or Excel) to compare current billing against proposed fee schedules.</p>
        <div className="billing-upload-row">
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.xlsx,.xls"
            onChange={handleFileUpload}
            className="fee-calc-file-input"
            disabled={uploadLoading}
          />
          {uploadLoading && <span className="billing-loading">Analyzing...</span>}
        </div>
        {uploadError && <div className="fee-calc-error">{uploadError}</div>}

        {billingData && (
          <div className="billing-analysis">
            <div className="book-row">
            {/* Client Book Summary */}
            <div className="book-col book-col-left">
            <h3>Client Book</h3>
            <div className="client-book-table-wrap">
              <table className="client-book-table">
                <thead>
                  <tr>
                    <th></th>
                    <th>AUM</th>
                    <th>Fee Rate</th>
                    <th>Annual Fee $</th>
                    <th>Fee $ Change</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="row-label">Historical</td>
                    <td>{formatCurrency(filteredSummary.total_aum)}</td>
                    <td>{filteredSummary.current_rate.toFixed(2)}%</td>
                    <td>{formatCurrency(filteredSummary.current_annual)}</td>
                    <td></td>
                  </tr>
                  <tr className="after-row">
                    <td className="row-label">After Fee Changes</td>
                    <td>{formatCurrency(filteredSummary.total_aum)}</td>
                    <td>{filteredSummary.proposed_rate.toFixed(2)}%</td>
                    <td>{formatCurrency(filteredSummary.proposed_annual)}</td>
                    <td className={filteredSummary.fee_change > 0 ? 'delta-up' : filteredSummary.fee_change < 0 ? 'delta-down' : ''}>
                      {filteredSummary.fee_change > 0 ? '+' : ''}{formatCurrency(filteredSummary.fee_change)}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            </div>

            {/* Book Segments Breakdown */}
            {bookSegments && (
              <div className="book-col book-col-right">
                <h3>Book Segments</h3>
                <div className="client-book-table-wrap">
                  <table className="client-book-table segments-table">
                    <thead>
                      <tr>
                        <th>Book Segments</th>
                        <th># of Clients</th>
                        <th>Needs Attention</th>
                        <th># w/Fee Increase</th>
                        <th>AUM</th>
                        <th>New Rate</th>
                        <th>New Annual Fee $</th>
                        <th>Fee $ Change</th>
                        <th>Fee % Change</th>
                      </tr>
                    </thead>
                    <tbody>
                      {bookSegments.segments.map((seg) => (
                        <tr key={seg.label}>
                          <td className="row-label">{seg.label}</td>
                          <td>{seg.clients.toLocaleString()}</td>
                          <td className={seg.needsAttention > 0 ? 'needs-attention' : ''}>{seg.needsAttention > 0 ? seg.needsAttention.toLocaleString() : '—'}</td>
                          <td>{seg.withIncrease.toLocaleString()}</td>
                          <td>{formatCurrency(seg.aum)}</td>
                          <td>{seg.clients > 0 ? seg.newRate.toFixed(2) + '%' : 'n/a'}</td>
                          <td>{formatCurrency(seg.proposedAnnual)}</td>
                          <td className={seg.feeChange > 0 ? 'delta-up' : seg.feeChange < 0 ? 'delta-down' : ''}>
                            {seg.feeChange > 0 ? '+' : ''}{formatCurrency(seg.feeChange)}
                          </td>
                          <td>{seg.clients > 0 ? seg.feeChangePct.toFixed(2) + '%' : 'n/m'}</td>
                        </tr>
                      ))}
                      <tr className="totals-row">
                        <td className="row-label">Totals</td>
                        <td>{bookSegments.totals.clients.toLocaleString()}</td>
                        <td className={bookSegments.totals.needsAttention > 0 ? 'needs-attention' : ''}>{bookSegments.totals.needsAttention > 0 ? bookSegments.totals.needsAttention.toLocaleString() : '—'}</td>
                        <td>{bookSegments.totals.withIncrease.toLocaleString()}</td>
                        <td>{formatCurrency(bookSegments.totals.aum)}</td>
                        <td>{bookSegments.totals.newRate.toFixed(2)}%</td>
                        <td>{formatCurrency(bookSegments.totals.proposedAnnual)}</td>
                        <td className={bookSegments.totals.feeChange > 0 ? 'delta-up' : bookSegments.totals.feeChange < 0 ? 'delta-down' : ''}>
                          {bookSegments.totals.feeChange > 0 ? '+' : ''}{formatCurrency(bookSegments.totals.feeChange)}
                        </td>
                        <td>{bookSegments.totals.feeChangePct.toFixed(2)}%</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            )}
            </div>

            {/* AUM vs Fee Rate Scatter Plot */}
            {(() => {
              const hasActiveFilter = !!(selectedAdvisor || selectedRegion || selectedChannel || searchQuery || statusFilter || awfFilter || repricingFilter || debouncedMinAum || debouncedDeltaMin || debouncedDeltaMax);
              if (!hasActiveFilter) {
                return (
                  <div className="scatter-chart-section scatter-chart-placeholder">
                    <h3>Client Overview — AUM vs Fee Rate</h3>
                    <p className="scatter-placeholder-msg">Apply a filter (advisor, region, channel, status, or search) to load the chart.</p>
                  </div>
                );
              }
              if (scatterBounds.count === 0) return null;
              return (
              <div className="scatter-chart-section">
                <h3>Client Overview — AUM vs Fee Rate</h3>
                <div className="scatter-toolbar">
                  <div className="scatter-legend">
                    <span className="legend-dot legend-on-track"></span> On Track
                    <span className="legend-dot legend-below"></span> Below Target (underpriced)
                  </div>
                  <button
                    className={`fee-calc-btn lasso-toggle-btn${lassoActive ? ' lasso-active' : ''}`}
                    onClick={() => { setLassoActive(!lassoActive); if (lassoActive) { clearLassoSelection(); } }}
                    title="Free-draw selection tool"
                  >
                    ✏️ {lassoActive ? 'Exit Lasso' : 'Lasso Select'}
                  </button>
                  {lassoSelectedIds.size > 0 && (
                    <button className="fee-calc-btn scatter-clear-btn" onClick={clearLassoSelection}>
                      Clear Lasso ({lassoSelectedIds.size})
                    </button>
                  )}
                </div>
                <div
                  className={`scatter-chart-wrapper${lassoActive ? ' lasso-mode' : ''}`}
                  ref={chartContainerRef}
                  onMouseDown={handleLassoMouseDown}
                  onMouseMove={handleLassoMouseMove}
                  onMouseUp={handleLassoMouseUp}
                  onMouseLeave={handleLassoMouseUp}
                >
                <ResponsiveContainer width="100%" height={360}>
                  <ScatterChart margin={{ top: 10, right: 30, bottom: 30, left: 60 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                    <XAxis
                      type="number"
                      dataKey="aum"
                      name="AUM"
                      domain={[0, scatterBounds.maxAum]}
                      tickFormatter={(v: number) => v >= 1_000_000 ? `$${(v / 1_000_000).toFixed(1)}M` : `$${(v / 1_000).toFixed(0)}K`}
                      label={{ value: 'AUM', position: 'bottom', offset: 10 }}
                    />
                    <YAxis
                      type="number"
                      dataKey="ratePct"
                      name="Fee Rate (%)"
                      domain={[0, scatterBounds.maxRate]}
                      tickFormatter={(v: number) => `${v.toFixed(1)}%`}
                      label={{ value: 'Fee Rate (%)', angle: -90, position: 'insideLeft', offset: -10 }}
                    />
                    <Tooltip
                      content={({ payload }) => {
                        if (!payload || !payload.length) return null;
                        const d = payload[0].payload;
                        return (
                          <div className="scatter-tooltip">
                            <strong>{d.name}</strong>
                            <div>AVHHID: {d.avhhid}</div>
                            <div>Advisor: {d.advisor}</div>
                            <div>AUM: ${d.aum.toLocaleString()}</div>
                            <div>Fee Rate: {d.ratePct.toFixed(2)}%</div>
                            <div>Annual Fee: ${d.annualFee.toLocaleString()}</div>
                            {d.delta !== 0 && <div>Proposed Δ: {d.delta > 0 ? '+' : ''}${d.delta.toLocaleString()}</div>}
                          </div>
                        );
                      }}
                    />
                    <Scatter
                      name="On Track"
                      data={scatterGroups.onTrack}
                      fill="#27ae60"
                      opacity={0.7}
                      onClick={handleScatterClick}
                      cursor="pointer"
                      isAnimationActive={false}
                    />
                    <Scatter
                      name="Below Target"
                      data={scatterGroups.below}
                      fill="#f39c12"
                      opacity={0.7}
                      onClick={handleScatterClick}
                      cursor="pointer"
                      isAnimationActive={false}
                    />
                    <Scatter
                      name="Above Target"
                      data={scatterGroups.above}
                      fill="#e74c3c"
                      opacity={0.7}
                      onClick={handleScatterClick}
                      cursor="pointer"
                      isAnimationActive={false}
                    />
                  </ScatterChart>
                </ResponsiveContainer>
                {/* Lasso SVG overlay */}
                {lassoActive && lassoPath.length > 1 && (
                  <svg className="lasso-overlay">
                    <polyline
                      points={lassoPath.map((p) => `${p.x},${p.y}`).join(' ')}
                      fill="rgba(52, 152, 219, 0.1)"
                      stroke="#3498db"
                      strokeWidth={2}
                      strokeDasharray="5,3"
                    />
                  </svg>
                )}
                </div>
                {highlightedAvhhid && (
                  <button className="fee-calc-btn scatter-clear-btn" onClick={() => { setHighlightedAvhhid(null); setSearchQuery(''); }}>
                    Clear selection
                  </button>
                )}
                {/* Range sliders */}
                <div className="scatter-range-sliders">
                  <div className="range-slider-row">
                    <label>Fee Rate</label>
                    <input
                      type="range"
                      min={0}
                      max={sliderBounds.maxRate}
                      step={0.05}
                      value={rateRange[0]}
                      onChange={(e) => setRateRange([parseFloat(e.target.value), rateRange[1]])}
                    />
                    <input
                      type="range"
                      min={0}
                      max={sliderBounds.maxRate}
                      step={0.05}
                      value={rateRange[1]}
                      onChange={(e) => setRateRange([rateRange[0], parseFloat(e.target.value)])}
                    />
                    <div className="range-inputs">
                      <span>Min</span>
                      <input type="text" ref={rateMinRef} defaultValue={fmtPct(rateRange[0])}
                        onFocus={(e) => { e.target.value = String(rateRange[0]); e.target.select(); }}
                        onBlur={(e) => { const v = parsePct(e.target.value); if (!isNaN(v)) { setRateRange([v, rateRange[1]]); e.target.value = fmtPct(v); } else e.target.value = fmtPct(rateRange[0]); }}
                        onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                      />
                      <span>Max</span>
                      <input type="text" ref={rateMaxRef} defaultValue={fmtPct(rateRange[1])}
                        onFocus={(e) => { e.target.value = String(rateRange[1]); e.target.select(); }}
                        onBlur={(e) => { const v = parsePct(e.target.value); if (!isNaN(v)) { setRateRange([rateRange[0], v]); e.target.value = fmtPct(v); } else e.target.value = fmtPct(rateRange[1]); }}
                        onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                      />
                    </div>
                  </div>
                  <div className="range-slider-row">
                    <label>AuM</label>
                    <input
                      type="range"
                      min={0}
                      max={sliderBounds.maxAum}
                      step={50000}
                      value={aumRange[0]}
                      onChange={(e) => setAumRange([parseFloat(e.target.value), aumRange[1]])}
                    />
                    <input
                      type="range"
                      min={0}
                      max={sliderBounds.maxAum}
                      step={50000}
                      value={aumRange[1]}
                      onChange={(e) => setAumRange([aumRange[0], parseFloat(e.target.value)])}
                    />
                    <div className="range-inputs">
                      <span>Min</span>
                      <input type="text" ref={aumMinRef} defaultValue={fmtDollar(aumRange[0])}
                        onFocus={(e) => { e.target.value = String(aumRange[0]); e.target.select(); }}
                        onBlur={(e) => { const v = parseDollar(e.target.value); if (!isNaN(v)) { setAumRange([v, aumRange[1]]); e.target.value = fmtDollar(v); } else e.target.value = fmtDollar(aumRange[0]); }}
                        onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                      />
                      <span>Max</span>
                      <input type="text" ref={aumMaxRef} defaultValue={fmtDollar(aumRange[1])}
                        onFocus={(e) => { e.target.value = String(aumRange[1]); e.target.select(); }}
                        onBlur={(e) => { const v = parseDollar(e.target.value); if (!isNaN(v)) { setAumRange([aumRange[0], v]); e.target.value = fmtDollar(v); } else e.target.value = fmtDollar(aumRange[1]); }}
                        onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                      />
                    </div>
                  </div>
                </div>
              </div>
              );
            })()}

            {/* Household-Level Comparison */}
            <div className="billing-hh-header" ref={tableWrapRef}>
              <div className="hh-header-row">
                <h3>Household Detail</h3>
                <button className="scroll-to-filters-btn" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
                  ↑ Back to Filters
                </button>
              </div>
              <div className="billing-hh-controls">
                <div className="billing-hh-schedule-pick">
                  <label>Override schedule:</label>
                  <select value={billingSchedule} onChange={(e) => setBillingSchedule(e.target.value)}>
                    <option value="">Auto-Detect</option>
                    {SCHEDULE_OPTIONS.map((opt) => (
                      <option key={opt.key} value={opt.key}>{opt.label}</option>
                    ))}
                  </select>
                </div>
                <label className="billing-waived-toggle">
                  <input
                    type="checkbox"
                    checked={includeWaived}
                    onChange={(e) => setIncludeWaived(e.target.checked)}
                  />
                  Include waived in proposed
                </label>
                <button className="fee-calc-btn fee-calc-btn-export" onClick={exportBillingCsv}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                  Export CSV
                </button>
                <button className="fee-calc-btn fee-calc-btn-export fee-calc-btn-excel" onClick={exportExcel}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                  Export Excel
                </button>
              </div>
            </div>
            <div className="billing-table-wrap">
              <table className="billing-hh-table">
                <thead>
                  <tr>
                    <th className="sortable-th" onClick={() => handleColumnSort('avhhid')}>AVHHID {sortColumn === 'avhhid' && <span className="sort-arrow">{sortDirection === 'asc' ? '▲' : '▼'}</span>}</th>
                    {billingData.households[0]?.household_name !== undefined && <th className="sortable-th" onClick={() => handleColumnSort('household_name')}>Household {sortColumn === 'household_name' && <span className="sort-arrow">{sortDirection === 'asc' ? '▲' : '▼'}</span>}</th>}
                    {billingData.households[0]?.advisor !== undefined && <th className="sortable-th" onClick={() => handleColumnSort('advisor')}>Advisor {sortColumn === 'advisor' && <span className="sort-arrow">{sortDirection === 'asc' ? '▲' : '▼'}</span>}</th>}
                    {billingData.households[0]?.billing_def !== undefined && <th className="sortable-th" onClick={() => handleColumnSort('billing_def')}>Billing Definition {sortColumn === 'billing_def' && <span className="sort-arrow">{sortDirection === 'asc' ? '▲' : '▼'}</span>}</th>}
                    <th className="sortable-th" onClick={() => handleColumnSort('total_billable')}>CSV Billable {sortColumn === 'total_billable' && <span className="sort-arrow">{sortDirection === 'asc' ? '▲' : '▼'}</span>}</th>
                    <th className="sortable-th" onClick={() => handleColumnSort('current_aum')}>Current AUM {sortColumn === 'current_aum' && <span className="sort-arrow">{sortDirection === 'asc' ? '▲' : '▼'}</span>}</th>
                    <th className="sortable-th" onClick={() => handleColumnSort('quarterly_fee')}>Quarterly Billed {sortColumn === 'quarterly_fee' && <span className="sort-arrow">{sortDirection === 'asc' ? '▲' : '▼'}</span>}</th>
                    <th className="sortable-th" onClick={() => handleColumnSort('annual_fee')}>Annual (est.) {sortColumn === 'annual_fee' && <span className="sort-arrow">{sortDirection === 'asc' ? '▲' : '▼'}</span>}</th>
                    <th className="sortable-th" onClick={() => handleColumnSort('current_rate')}>Current Rate {sortColumn === 'current_rate' && <span className="sort-arrow">{sortDirection === 'asc' ? '▲' : '▼'}</span>}</th>
                    <th className="sortable-th" onClick={() => handleColumnSort('proposed_schedule')}>Proposed Schedule {sortColumn === 'proposed_schedule' && <span className="sort-arrow">{sortDirection === 'asc' ? '▲' : '▼'}</span>}</th>
                    <th className="sortable-th" onClick={() => handleColumnSort('proposed_annual')}>Proposed Annual {sortColumn === 'proposed_annual' && <span className="sort-arrow">{sortDirection === 'asc' ? '▲' : '▼'}</span>}</th>
                    <th className="sortable-th" onClick={() => handleColumnSort('proposed_rate')}>Proposed Rate {sortColumn === 'proposed_rate' && <span className="sort-arrow">{sortDirection === 'asc' ? '▲' : '▼'}</span>}</th>
                    <th className="sortable-th" onClick={() => handleColumnSort('delta')}>Delta {sortColumn === 'delta' && <span className="sort-arrow">{sortDirection === 'asc' ? '▲' : '▼'}</span>}</th>
                    <th className="sortable-th" onClick={() => handleColumnSort('status')}>Status {sortColumn === 'status' && <span className="sort-arrow">{sortDirection === 'asc' ? '▲' : '▼'}</span>}</th>
                    <th className="sortable-th" onClick={() => handleColumnSort('awf_schedule')}>AWF Recommended {sortColumn === 'awf_schedule' && <span className="sort-arrow">{sortDirection === 'asc' ? '▲' : '▼'}</span>}</th>
                    <th className="sortable-th" onClick={() => handleColumnSort('awf_annual')}>AWF Annual {sortColumn === 'awf_annual' && <span className="sort-arrow">{sortDirection === 'asc' ? '▲' : '▼'}</span>}</th>
                    <th className="sortable-th" onClick={() => handleColumnSort('awf_delta')}>AWF Delta {sortColumn === 'awf_delta' && <span className="sort-arrow">{sortDirection === 'asc' ? '▲' : '▼'}</span>}</th>
                    <th className="sortable-th" onClick={() => handleColumnSort('campaign_name')}>Repricing Campaign {sortColumn === 'campaign_name' && <span className="sort-arrow">{sortDirection === 'asc' ? '▲' : '▼'}</span>}</th>
                  </tr>
                  <tr className="filter-row">
                    <th></th>
                    {billingData.households[0]?.household_name !== undefined && <th></th>}
                    {billingData.households[0]?.advisor !== undefined && <th></th>}
                    {billingData.households[0]?.billing_def !== undefined && <th></th>}
                    <th></th>
                    <th></th>
                    <th></th>
                    <th></th>
                    <th></th>
                    <th>
                      <select value={columnFilters['proposed_schedule'] || ''} onChange={(e) => handleColumnFilter('proposed_schedule', e.target.value)}>
                        <option value="">All</option>
                        {[...new Set(filteredBillingHouseholds.map((hh) => String(getColumnValue(hh, 'proposed_schedule'))))].sort().map((v) => (
                          <option key={v} value={v}>{v}</option>
                        ))}
                      </select>
                    </th>
                    <th></th>
                    <th></th>
                    <th></th>
                    <th>
                      <select value={columnFilters['status'] || ''} onChange={(e) => handleColumnFilter('status', e.target.value)}>
                        <option value="">All</option>
                        <option value="Above">Above</option>
                        <option value="On Track">On Track</option>
                        <option value="Below">Below</option>
                      </select>
                    </th>
                    <th>
                      <select value={columnFilters['awf_schedule'] || ''} onChange={(e) => handleColumnFilter('awf_schedule', e.target.value)}>
                        <option value="">All</option>
                        <option value="__empty__">Unfilled</option>
                        {[...new Set(filteredBillingHouseholds.map((hh) => String(getColumnValue(hh, 'awf_schedule'))).filter(Boolean))].sort().map((v) => (
                          <option key={v} value={v}>{v}</option>
                        ))}
                      </select>
                    </th>
                    <th></th>
                    <th></th>
                    <th>
                      <select value={columnFilters['campaign_name'] || ''} onChange={(e) => handleColumnFilter('campaign_name', e.target.value)}>
                        <option value="">All</option>
                        <option value="__empty__">None</option>
                        {[...new Set(filteredBillingHouseholds.flatMap((hh) => (hh.campaign_name || '').split(', ').filter(Boolean)))].sort().map((v) => (
                          <option key={v} value={v}>{v}</option>
                        ))}
                      </select>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sortedBillingHouseholds.slice(0, visibleRows).map((hh) => {
                    // Use auto-detected schedule or manual override
                    const useAuto = !billingSchedule;
                    const proposed = includeWaived ? hh.proposed_incl : hh.proposed;
                    const proposedAnnual = useAuto
                      ? (includeWaived ? hh.auto_proposed_annual_incl : hh.auto_proposed_annual)
                      : (proposed[billingSchedule]?.annual_fee ?? 0);
                    const proposedRate = useAuto
                      ? (includeWaived ? hh.auto_proposed_rate_pct_incl : hh.auto_proposed_rate_pct)
                      : (proposed[billingSchedule]?.effective_rate_pct ?? 0);
                    const delta = useAuto
                      ? (includeWaived ? hh.auto_delta_incl : hh.auto_delta)
                      : (proposed[billingSchedule]?.delta ?? 0);
                    const schedName = useAuto ? hh.auto_schedule_name : SCHEDULE_OPTIONS.find(s => s.key === billingSchedule)?.label || '';
                    const isHigh = delta < -10;
                    const isLow = delta > 10;
                    const rowKey = `${hh.avhhid}-${hh.billing_def || ''}`;
                    const userSched = userScheduleOverrides[rowKey] || '';
                    const userProposed = (userSched && userSched !== 'no_change') ? (proposed[userSched] ?? null) : null;
                    const userAnnual = userSched === 'no_change' ? hh.current_annual_fee : (userProposed?.annual_fee ?? null);
                    const userDelta = userSched === 'no_change' ? 0 : (userAnnual !== null ? userAnnual - hh.current_annual_fee : null);
                    return (
                      <tr key={rowKey} className={`${isHigh ? 'row-above' : isLow ? 'row-below' : ''} ${hh.has_waived ? 'row-has-waived' : ''}`}>
                        <td>{hh.avhhid}</td>
                        {hh.household_name !== undefined && <td>{hh.household_name}</td>}
                        {hh.advisor !== undefined && <td>{hh.advisor}</td>}
                        {hh.billing_def !== undefined && <td className="billing-def-cell">{hh.billing_def}</td>}
                        <td>
                          {formatCurrency(hh.total_billable)}
                          {hh.has_waived && <span className="waived-indicator" title={`Waived — ${hh.waived_accounts} acct(s), ${formatCurrency(hh.waived_billable)}`}> W</span>}
                        </td>
                        <td>{formatCurrency(hh.current_aum)}</td>
                        <td>{formatCurrencyDetailed(hh.current_quarterly_fee)}</td>
                        <td>{formatCurrencyDetailed(hh.current_annual_fee)}</td>
                        <td>{hh.current_rate_pct.toFixed(2)}%</td>
                        <td className="sched-name-cell">{schedName}</td>
                        <td>{formatCurrencyDetailed(proposedAnnual)}</td>
                        <td>{proposedRate.toFixed(2)}%</td>
                        <td className={delta > 0 ? 'delta-up' : delta < 0 ? 'delta-down' : ''}>
                          {delta > 0 ? '+' : ''}{formatCurrency(delta)}
                        </td>
                        <td>
                          {isHigh && <span className="badge-above">Above</span>}
                          {isLow && <span className="badge-below">Below</span>}
                          {!isHigh && !isLow && <span className="badge-on-track">On Track</span>}
                        </td>
                        <td className="user-sched-cell">
                          <select
                            value={userSched}
                            onChange={(e) => {
                              const newVal = e.target.value;
                              setUserScheduleOverrides((prev) => ({ ...prev, [rowKey]: newVal }));
                              setUserModifiedKeys((prev) => { const next = new Set(prev); next.add(rowKey); return next; });
                            }}
                          >
                            <option value="">—</option>
                            {SCHEDULE_OPTIONS.map((opt) => (
                              <option key={opt.key} value={opt.key}>{opt.label}</option>
                            ))}
                            <option value="no_change">No Change</option>
                          </select>
                        </td>
                        <td>{userAnnual !== null ? formatCurrencyDetailed(userAnnual) : '—'}</td>
                        <td className={userDelta !== null ? (userDelta > 0 ? 'delta-up' : userDelta < 0 ? 'delta-down' : '') : ''}>
                          {userDelta !== null ? `${userDelta > 0 ? '+' : ''}${formatCurrency(userDelta)}` : '—'}
                        </td>
                        <td className="campaign-cell">{hh.campaign_name || ''}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {sortedBillingHouseholds.length > visibleRows && (
              <div className="billing-show-more">
                <button className="fee-calc-btn" onClick={() => setVisibleRows((v) => v + 100)}>
                  Show more ({sortedBillingHouseholds.length - visibleRows} remaining)
                </button>
              </div>
            )}
            {sortedBillingHouseholds.length > 0 && (
              <p className="billing-truncated">Showing {Math.min(visibleRows, sortedBillingHouseholds.length)} of {sortedBillingHouseholds.length} households{(searchQuery.trim().length >= 2 || selectedAdvisor || selectedChannel || statusFilter || debouncedDeltaMin || debouncedDeltaMax) ? ' (filtered)' : ''}</p>
            )}
            {sortedBillingHouseholds.length === 0 && (searchQuery.trim().length >= 2 || selectedAdvisor || selectedChannel || statusFilter || debouncedDeltaMin || debouncedDeltaMax) && (
              <p className="billing-truncated">No households match current filters</p>
            )}
          </div>
        )}
        </div>
      </section>

      {/* Fee Calculation (bottom) */}
      <section className="fee-calc-section">
        <h2>Calculate Fee</h2>
        <div className="fee-calc-panel">
        <div className="fee-calc-inputs">
          <div className="fee-calc-field">
            <label>AUM ($)</label>
            <input
              type="text"
              value={manualAum}
              onChange={(e) => setManualAum(e.target.value)}
              placeholder="e.g. 2,000,000"
            />
          </div>
          <div className="fee-calc-field">
            <label>Fee Schedule</label>
            <select value={selectedSchedule} onChange={(e) => setSelectedSchedule(e.target.value)}>
              {SCHEDULE_OPTIONS.map((opt) => (
                <option key={opt.key} value={opt.key}>{opt.label}</option>
              ))}
            </select>
          </div>
          <div className="fee-calc-field fee-calc-toggle">
            <label>
              <input
                type="checkbox"
                checked={compareMode}
                onChange={(e) => setCompareMode(e.target.checked)}
              />
              Compare all schedules
            </label>
          </div>
          <button
            className="fee-calc-btn"
            onClick={calculateFee}
            disabled={calcLoading || isNaN(activeAum) || activeAum <= 0}
          >
            {calcLoading ? 'Calculating...' : 'Calculate'}
          </button>
        </div>

        {/* Single Schedule Result */}
        {feeResult && !compareMode && (
          <div className="fee-calc-result">
            <h3>{feeResult.schedule_name}</h3>
            <div className="fee-summary-grid">
              <div className="fee-summary-item">
                <span className="fee-label">Annual Fee</span>
                <span className="fee-value">{formatCurrencyDetailed(feeResult.annual_fee)}</span>
              </div>
              <div className="fee-summary-item">
                <span className="fee-label">Quarterly Fee</span>
                <span className="fee-value">{formatCurrencyDetailed(feeResult.quarterly_fee)}</span>
              </div>
              <div className="fee-summary-item">
                <span className="fee-label">Effective Rate</span>
                <span className="fee-value">{feeResult.effective_rate_pct.toFixed(4)}%</span>
              </div>
              <div className="fee-summary-item">
                <span className="fee-label">Effective BPS</span>
                <span className="fee-value">{feeResult.effective_rate_bps.toFixed(1)} bps</span>
              </div>
            </div>
            {feeResult.min_fee_applied && (
              <div className="fee-min-notice">
                Minimum quarterly fee of {formatCurrencyDetailed(feeResult.min_quarterly_fee)} applied
              </div>
            )}
            <table className="fee-tier-table">
              <thead>
                <tr>
                  <th>Tier Range</th>
                  <th>Rate</th>
                  <th>Assets in Tier</th>
                  <th>Fee</th>
                </tr>
              </thead>
              <tbody>
                {feeResult.breakdown.map((tier, i) => (
                  <tr key={i} className={tier.assets_in_tier > 0 ? 'active-tier' : ''}>
                    <td>{formatTierRange(tier.from, tier.to)}</td>
                    <td>{(tier.rate * 100).toFixed(2)}%</td>
                    <td>{formatCurrency(tier.assets_in_tier)}</td>
                    <td>{formatCurrencyDetailed(tier.fee)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Compare All Schedules */}
        {allResults && compareMode && (
          <div className="fee-calc-comparison">
            <h3>Schedule Comparison — {formatCurrency(activeAum)}</h3>
            <table className="fee-compare-table">
              <thead>
                <tr>
                  <th>Schedule</th>
                  <th>Annual Fee</th>
                  <th>Quarterly Fee</th>
                  <th>Effective Rate</th>
                  <th>Min Applied</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(allResults).map(([key, result]) => (
                  <tr key={key} className={key === selectedSchedule ? 'selected-row' : ''}>
                    <td>{result.schedule_name}</td>
                    <td>{formatCurrencyDetailed(result.annual_fee)}</td>
                    <td>{formatCurrencyDetailed(result.quarterly_fee)}</td>
                    <td>{result.effective_rate_pct.toFixed(4)}%</td>
                    <td>{result.min_fee_applied ? 'Yes' : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        </div>
      </section>
    </div>
    {/* Floating back-to-top button */}
    <button className="back-to-top-btn" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })} title="Back to top">↑</button>
    </div>
  );
};

export default FeeCalculator;
