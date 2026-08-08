// src/components/PipelineNav.tsx
// Shared nav strip for the pipeline-observability pages. Lives outside the
// Synapse/KPI data flow so it can safely appear on any page without extra deps.

import { Link, useLocation } from 'react-router-dom';
import './PipelineNav.css';

interface NavItem {
  to: string;
  label: string;
  matches: string[];
}

const NAV_ITEMS: NavItem[] = [
  { to: '/tamarac', label: 'Tamarac', matches: ['/tamarac'] },
  { to: '/refresh_log', label: 'Full Log', matches: ['/refresh_log', '/refresh-log'] },
];

const PipelineNav = () => {
  const location = useLocation();
  const current = location.pathname.replace(/\/+$/, '') || '/';

  return (
    <nav className="pipeline-nav">
      <div className="pipeline-nav-inner">
        <span className="pipeline-nav-brand">Pipeline Monitor</span>
        <div className="pipeline-nav-links">
          {NAV_ITEMS.map((item) => {
            const active = item.matches.includes(current);
            return (
              <Link
                key={item.to}
                to={item.to}
                className={active ? 'pipeline-nav-link active' : 'pipeline-nav-link'}
              >
                {item.label}
              </Link>
            );
          })}
        </div>
      </div>
    </nav>
  );
};

export default PipelineNav;
