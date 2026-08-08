import type { KpiDataset } from '../types/kpi';

// Metrics: NCNM, Clients, Appointments, Leads
// Channels: Total, Advisor Enabled, CRP, Paid Leads, Media
// Each metric has 5 rows (Total + 4 channels) = 20 tiles per period

// Helper to create entry with PY data
type EntryConfig = {
  metric: string;
  channel: string;
  period: string;
  actual: number;
  goal: number;
  pyActual: number;
  currency?: string;
  unit?: string;
};

const createEntry = (config: EntryConfig, index: number) => {
  const slugify = (v: string) => v.toLowerCase().replace(/[^a-z0-9]+/g, '-');
  // For Jan 2026 (current month), prorate PY and goal by ~42% (13 days / 31 days)
  const isCurrentMonth = config.period === 'Jan 2026';
  const prorateFactor = isCurrentMonth ? 13 / 31 : 1;
  
  return {
    id: `${slugify(config.metric)}-${slugify(config.channel)}-${slugify(config.period)}-${index}`,
    metric: config.metric,
    channel: config.channel,
    period: config.period,
    actual: config.actual,
    goal: config.goal,
    pyActual: config.pyActual,
    pyProrated: Math.round(config.pyActual * prorateFactor * 100) / 100,
    goalProrated: Math.round(config.goal * prorateFactor * 100) / 100,
    currency: config.currency,
    unit: config.unit,
  };
};

export const demoMetrics: KpiDataset = [
  // ===== JANUARY 2026 (This Month - prorated) =====
  
  // NCNM
  createEntry({ metric: 'NCNM', channel: 'Total', period: 'Jan 2026', actual: 52.4, goal: 145.0, pyActual: 138.5, currency: 'USD', unit: 'millions' }, 0),
  createEntry({ metric: 'NCNM', channel: 'Advisor Enabled', period: 'Jan 2026', actual: 24.8, goal: 70.0, pyActual: 65.2, currency: 'USD', unit: 'millions' }, 1),
  createEntry({ metric: 'NCNM', channel: 'CRP', period: 'Jan 2026', actual: 15.2, goal: 38.0, pyActual: 36.8, currency: 'USD', unit: 'millions' }, 2),
  createEntry({ metric: 'NCNM', channel: 'Paid Leads', period: 'Jan 2026', actual: 8.1, goal: 22.0, pyActual: 21.5, currency: 'USD', unit: 'millions' }, 3),
  createEntry({ metric: 'NCNM', channel: 'Media', period: 'Jan 2026', actual: 4.3, goal: 15.0, pyActual: 15.0, currency: 'USD', unit: 'millions' }, 4),
  
  // Clients
  createEntry({ metric: 'Clients', channel: 'Total', period: 'Jan 2026', actual: 38, goal: 95, pyActual: 89 }, 5),
  createEntry({ metric: 'Clients', channel: 'Advisor Enabled', period: 'Jan 2026', actual: 14, goal: 38, pyActual: 35 }, 6),
  createEntry({ metric: 'Clients', channel: 'CRP', period: 'Jan 2026', actual: 12, goal: 28, pyActual: 27 }, 7),
  createEntry({ metric: 'Clients', channel: 'Paid Leads', period: 'Jan 2026', actual: 7, goal: 17, pyActual: 15 }, 8),
  createEntry({ metric: 'Clients', channel: 'Media', period: 'Jan 2026', actual: 5, goal: 12, pyActual: 12 }, 9),
  
  // Appointments
  createEntry({ metric: 'Appointments', channel: 'Total', period: 'Jan 2026', actual: 156, goal: 380, pyActual: 365 }, 10),
  createEntry({ metric: 'Appointments', channel: 'Advisor Enabled', period: 'Jan 2026', actual: 52, goal: 125, pyActual: 118 }, 11),
  createEntry({ metric: 'Appointments', channel: 'CRP', period: 'Jan 2026', actual: 48, goal: 115, pyActual: 112 }, 12),
  createEntry({ metric: 'Appointments', channel: 'Paid Leads', period: 'Jan 2026', actual: 32, goal: 85, pyActual: 80 }, 13),
  createEntry({ metric: 'Appointments', channel: 'Media', period: 'Jan 2026', actual: 24, goal: 55, pyActual: 55 }, 14),
  
  // Leads
  createEntry({ metric: 'Leads', channel: 'Total', period: 'Jan 2026', actual: 892, goal: 2150, pyActual: 2050 }, 15),
  createEntry({ metric: 'Leads', channel: 'Advisor Enabled', period: 'Jan 2026', actual: 244, goal: 580, pyActual: 548 }, 16),
  createEntry({ metric: 'Leads', channel: 'CRP', period: 'Jan 2026', actual: 312, goal: 750, pyActual: 720 }, 17),
  createEntry({ metric: 'Leads', channel: 'Paid Leads', period: 'Jan 2026', actual: 198, goal: 520, pyActual: 490 }, 18),
  createEntry({ metric: 'Leads', channel: 'Media', period: 'Jan 2026', actual: 138, goal: 300, pyActual: 292 }, 19),

  // ===== DECEMBER 2025 (Last Month - full month) =====
  
  // NCNM
  createEntry({ metric: 'NCNM', channel: 'Total', period: 'Dec 2025', actual: 142.5, goal: 145.0, pyActual: 138.5, currency: 'USD', unit: 'millions' }, 20),
  createEntry({ metric: 'NCNM', channel: 'Advisor Enabled', period: 'Dec 2025', actual: 68.2, goal: 70.0, pyActual: 65.2, currency: 'USD', unit: 'millions' }, 21),
  createEntry({ metric: 'NCNM', channel: 'CRP', period: 'Dec 2025', actual: 37.5, goal: 38.0, pyActual: 36.8, currency: 'USD', unit: 'millions' }, 22),
  createEntry({ metric: 'NCNM', channel: 'Paid Leads', period: 'Dec 2025', actual: 22.8, goal: 22.0, pyActual: 21.5, currency: 'USD', unit: 'millions' }, 23),
  createEntry({ metric: 'NCNM', channel: 'Media', period: 'Dec 2025', actual: 14.0, goal: 15.0, pyActual: 15.0, currency: 'USD', unit: 'millions' }, 24),
  
  // Clients
  createEntry({ metric: 'Clients', channel: 'Total', period: 'Dec 2025', actual: 92, goal: 95, pyActual: 89 }, 25),
  createEntry({ metric: 'Clients', channel: 'Advisor Enabled', period: 'Dec 2025', actual: 36, goal: 38, pyActual: 35 }, 26),
  createEntry({ metric: 'Clients', channel: 'CRP', period: 'Dec 2025', actual: 27, goal: 28, pyActual: 27 }, 27),
  createEntry({ metric: 'Clients', channel: 'Paid Leads', period: 'Dec 2025', actual: 17, goal: 17, pyActual: 15 }, 28),
  createEntry({ metric: 'Clients', channel: 'Media', period: 'Dec 2025', actual: 12, goal: 12, pyActual: 12 }, 29),
  
  // Appointments
  createEntry({ metric: 'Appointments', channel: 'Total', period: 'Dec 2025', actual: 372, goal: 380, pyActual: 365 }, 30),
  createEntry({ metric: 'Appointments', channel: 'Advisor Enabled', period: 'Dec 2025', actual: 121, goal: 125, pyActual: 118 }, 31),
  createEntry({ metric: 'Appointments', channel: 'CRP', period: 'Dec 2025', actual: 112, goal: 115, pyActual: 112 }, 32),
  createEntry({ metric: 'Appointments', channel: 'Paid Leads', period: 'Dec 2025', actual: 84, goal: 85, pyActual: 80 }, 33),
  createEntry({ metric: 'Appointments', channel: 'Media', period: 'Dec 2025', actual: 55, goal: 55, pyActual: 55 }, 34),
  
  // Leads
  createEntry({ metric: 'Leads', channel: 'Total', period: 'Dec 2025', actual: 2105, goal: 2150, pyActual: 2050 }, 35),
  createEntry({ metric: 'Leads', channel: 'Advisor Enabled', period: 'Dec 2025', actual: 562, goal: 580, pyActual: 548 }, 36),
  createEntry({ metric: 'Leads', channel: 'CRP', period: 'Dec 2025', actual: 738, goal: 750, pyActual: 720 }, 37),
  createEntry({ metric: 'Leads', channel: 'Paid Leads', period: 'Dec 2025', actual: 505, goal: 520, pyActual: 490 }, 38),
  createEntry({ metric: 'Leads', channel: 'Media', period: 'Dec 2025', actual: 300, goal: 300, pyActual: 292 }, 39),

  // ===== NOVEMBER 2025 =====
  
  // NCNM
  createEntry({ metric: 'NCNM', channel: 'Total', period: 'Nov 2025', actual: 148.2, goal: 142.0, pyActual: 135.0, currency: 'USD', unit: 'millions' }, 40),
  createEntry({ metric: 'NCNM', channel: 'Advisor Enabled', period: 'Nov 2025', actual: 71.5, goal: 68.0, pyActual: 63.5, currency: 'USD', unit: 'millions' }, 41),
  createEntry({ metric: 'NCNM', channel: 'CRP', period: 'Nov 2025', actual: 39.8, goal: 37.0, pyActual: 35.5, currency: 'USD', unit: 'millions' }, 42),
  createEntry({ metric: 'NCNM', channel: 'Paid Leads', period: 'Nov 2025', actual: 23.4, goal: 22.0, pyActual: 21.0, currency: 'USD', unit: 'millions' }, 43),
  createEntry({ metric: 'NCNM', channel: 'Media', period: 'Nov 2025', actual: 13.5, goal: 15.0, pyActual: 15.0, currency: 'USD', unit: 'millions' }, 44),
  
  // Clients
  createEntry({ metric: 'Clients', channel: 'Total', period: 'Nov 2025', actual: 98, goal: 92, pyActual: 86 }, 45),
  createEntry({ metric: 'Clients', channel: 'Advisor Enabled', period: 'Nov 2025', actual: 39, goal: 37, pyActual: 34 }, 46),
  createEntry({ metric: 'Clients', channel: 'CRP', period: 'Nov 2025', actual: 29, goal: 27, pyActual: 26 }, 47),
  createEntry({ metric: 'Clients', channel: 'Paid Leads', period: 'Nov 2025', actual: 18, goal: 16, pyActual: 14 }, 48),
  createEntry({ metric: 'Clients', channel: 'Media', period: 'Nov 2025', actual: 12, goal: 12, pyActual: 12 }, 49),
  
  // Appointments
  createEntry({ metric: 'Appointments', channel: 'Total', period: 'Nov 2025', actual: 395, goal: 370, pyActual: 355 }, 50),
  createEntry({ metric: 'Appointments', channel: 'Advisor Enabled', period: 'Nov 2025', actual: 130, goal: 122, pyActual: 115 }, 51),
  createEntry({ metric: 'Appointments', channel: 'CRP', period: 'Nov 2025', actual: 118, goal: 112, pyActual: 108 }, 52),
  createEntry({ metric: 'Appointments', channel: 'Paid Leads', period: 'Nov 2025', actual: 90, goal: 82, pyActual: 78 }, 53),
  createEntry({ metric: 'Appointments', channel: 'Media', period: 'Nov 2025', actual: 57, goal: 54, pyActual: 54 }, 54),
  
  // Leads
  createEntry({ metric: 'Leads', channel: 'Total', period: 'Nov 2025', actual: 2280, goal: 2100, pyActual: 1980 }, 55),
  createEntry({ metric: 'Leads', channel: 'Advisor Enabled', period: 'Nov 2025', actual: 612, goal: 565, pyActual: 530 }, 56),
  createEntry({ metric: 'Leads', channel: 'CRP', period: 'Nov 2025', actual: 785, goal: 730, pyActual: 695 }, 57),
  createEntry({ metric: 'Leads', channel: 'Paid Leads', period: 'Nov 2025', actual: 545, goal: 505, pyActual: 470 }, 58),
  createEntry({ metric: 'Leads', channel: 'Media', period: 'Nov 2025', actual: 338, goal: 300, pyActual: 285 }, 59),
];
