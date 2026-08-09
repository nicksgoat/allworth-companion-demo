import type { ReactNode } from 'react';

const paths: Record<string, ReactNode> = {
  performance: <><path d="M3 3v18h18" /><path d="M7 15l3-4 3 3 4-6" /></>,
  knowledge: <><path d="M5 4h12a2 2 0 0 1 2 2v14H7a2 2 0 0 1-2-2z" /><path d="M9 8h6M9 12h6M9 16h4" /></>,
  table: <><path d="M4 4h16v16H4zM4 9h16M4 14h16M9 4v16" /></>,
  admin: <><path d="M12 2 4 5v6c0 5 3.4 8.5 8 11 4.6-2.5 8-6 8-11V5z" /><circle cx="12" cy="10" r="2.4" /><path d="M8.5 16a3.7 3.7 0 0 1 7 0" /></>,
  calculator: <><rect x="4" y="2" width="16" height="20" rx="2" /><path d="M8 6h8M8 10h8M8 14h4M8 18h6" /></>,
  pipeline: <><path d="M3 3v18h18" /><path d="m7 14 4-4 3 3 5-6" /></>,
  report: <><path d="M3 3v18h18" /><rect x="7" y="11" width="3" height="6" /><rect x="12" y="7" width="3" height="10" /><rect x="17" y="4" width="3" height="13" /></>,
  relationships: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8" /></>,
  folder: <><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><path d="M12 11v5m-2.5-2.5L12 11l2.5 2.5" /></>,
  database: <><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" /></>,
  mail: <><path d="M3 6h18v12H3zM3 7l9 6 9-6" /></>,
  planning: <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="3.5" /><path d="M12 3v3M12 18v3M3 12h3M18 12h3" /></>,
  trend: <><path d="M3 17l6-6 4 4 8-8M14 7h7v7" /></>,
  balance: <><path d="M12 3v18M5 8l7-5 7 5M3 14a3 3 0 0 0 6 0L6 8zM15 14a3 3 0 0 0 6 0l-3-6z" /></>,
  refresh: <><path d="M21 12a9 9 0 1 1-3-6.7M21 3v6h-6" /></>,
  schema: <><path d="M4 6h16M4 12h16M4 18h10" /><circle cx="18" cy="18" r="2" /></>,
  reference: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 9h18M8 4v16" /></>,
  bonds: <><path d="M3 3v18h18M7 13h2v4H7zM11 9h2v8h-2zM15 5h2v12h-2z" /></>,
  grid: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
  document: <><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M8 13h8M8 17h6" /></>,
  compare: <><path d="M4 7h16M4 12h16M4 17h16M8 4v16" /></>,
};

export function ToolIcon({ name, className }: { name: string; className?: string }) {
  return <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {paths[name] ?? paths.document}
  </svg>;
}
