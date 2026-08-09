import type { ReactNode } from 'react';
import SideNav from './SideNav';
import { RelationshipSpine } from './RelationshipSpine';
import './ToolPage.css';

export type ToolPageWidth = 'standard' | 'wide' | 'full';
export type ToolTone = 'neutral' | 'positive' | 'warning' | 'critical' | 'info';

interface ToolPageProps {
  eyebrow: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  context?: ReactNode;
  children: ReactNode;
  width?: ToolPageWidth;
  className?: string;
}

/**
 * Shared desktop chrome for every authenticated workspace tool.
 * Owns navigation, page width, title hierarchy, and action placement so tools
 * can focus on their workflow instead of recreating the application shell.
 */
export function ToolPage({
  eyebrow,
  title,
  description,
  actions,
  context,
  children,
  width = 'wide',
  className = '',
}: ToolPageProps) {
  return (
    <div className={`aw-tool-page ${className}`.trim()}>
      <SideNav />
      <main className={`aw-tool-page__main aw-tool-page__main--${width}`}>
        <RelationshipSpine />
        <header className="aw-tool-header">
          <div className="aw-tool-header__copy">
            <p className="aw-tool-header__eyebrow">{eyebrow}</p>
            <h1>{title}</h1>
            {description && <p className="aw-tool-header__description">{description}</p>}
          </div>
          {actions && <div className="aw-tool-header__actions">{actions}</div>}
        </header>
        {context && <div className="aw-tool-context">{context}</div>}
        <div className="aw-tool-page__content">{children}</div>
      </main>
    </div>
  );
}

interface ToolPanelProps {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  flush?: boolean;
}

/** Quiet, hairline-bounded work surface for a single workflow or dataset. */
export function ToolPanel({ title, description, actions, children, className = '', flush = false }: ToolPanelProps) {
  return (
    <section className={`aw-tool-panel${flush ? ' aw-tool-panel--flush' : ''} ${className}`.trim()}>
      {(title || description || actions) && (
        <header className="aw-tool-panel__header">
          <div>
            {title && <h2>{title}</h2>}
            {description && <p>{description}</p>}
          </div>
          {actions && <div className="aw-tool-panel__actions">{actions}</div>}
        </header>
      )}
      <div className="aw-tool-panel__body">{children}</div>
    </section>
  );
}

interface ToolMetricProps {
  label: ReactNode;
  value: ReactNode;
  detail?: ReactNode;
  tone?: ToolTone;
}

/** Standard decision metric used across advisor, planning, and ops tools. */
export function ToolMetric({ label, value, detail, tone = 'neutral' }: ToolMetricProps) {
  return (
    <div className={`aw-tool-metric aw-tool-metric--${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
    </div>
  );
}

export function ToolMetricGrid({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`aw-tool-metric-grid ${className}`.trim()}>{children}</div>;
}

export function ToolStatus({ children, tone = 'neutral' }: { children: ReactNode; tone?: ToolTone }) {
  return <span className={`aw-tool-status aw-tool-status--${tone}`}>{children}</span>;
}

interface ToolSurfaceProps {
  children: ReactNode;
  className?: string;
  tone?: 'default' | 'subtle' | 'warm';
}

/** Shared unheaded work surface for compact controls, summaries, and details. */
export function ToolSurface({ children, className = '', tone = 'default' }: ToolSurfaceProps) {
  return <section className={`aw-tool-surface aw-tool-surface--${tone} ${className}`.trim()}>{children}</section>;
}

export function ToolToolbar({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`aw-tool-toolbar ${className}`.trim()}>{children}</div>;
}

export function ToolTableFrame({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`aw-tool-table-frame ${className}`.trim()}>{children}</div>;
}

interface ToolChartProps {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}

/** Chart frame with one title, legend/action zone, and plot treatment. */
export function ToolChart({ title, description, actions, children, className = '' }: ToolChartProps) {
  return (
    <ToolPanel title={title} description={description} actions={actions} className={`aw-tool-chart ${className}`.trim()}>
      <div className="aw-tool-chart__plot">{children}</div>
    </ToolPanel>
  );
}

export function ToolEmptyState({ title, detail, action }: { title: ReactNode; detail?: ReactNode; action?: ReactNode }) {
  return (
    <div className="aw-tool-empty">
      <h3>{title}</h3>
      {detail && <p>{detail}</p>}
      {action && <div>{action}</div>}
    </div>
  );
}
