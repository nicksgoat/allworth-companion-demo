import { useMemo, useState } from 'react';
import AccountToolWidgets from './AccountToolWidgets';
import type { AccountWidgetKey } from './AccountToolWidgets';
import { assignableTools, type ToolDefinition } from '../config/toolManifest';
import { useJsonQuery } from '../hooks/useJsonQuery';
import './WorkspaceToolWidgets.css';

const CORE_WIDGET_IDS = assignableTools.filter((tool) => tool.widget?.kind === 'core').map((tool) => tool.id as AccountWidgetKey);

function readCount(payload: unknown, path?: string[]): number | null {
  let value: unknown = payload;
  for (const key of path ?? []) value = value && typeof value === 'object' ? (value as Record<string, unknown>)[key] : null;
  return Array.isArray(value) ? value.length : typeof value === 'number' ? value : null;
}

function LiveToolWidget({ definition }: { definition: ToolDefinition }) {
  const widget = definition.widget;
  const [query, setQuery] = useState('');
  const result = useJsonQuery<unknown>(widget?.endpoint ?? null);
  const count = readCount(result.data, widget?.count_path);
  const status = result.loading ? 'Loading…' : result.error ? 'Unavailable' : count == null ? (widget?.endpoint ? 'Connected' : 'Ready') : count === 0 ? `No ${widget?.count_label ?? 'items'}` : `${count} ${widget?.count_label}`;
  const href = definition.url ?? '#';
  const searchHref = `${href}${href.includes('?') ? '&' : '?'}q=${encodeURIComponent(query)}`;
  return <article className="workspace-live-widget">
    <header><div><span>{widget?.eyebrow ?? definition.kicker}</span><h3>{definition.name}</h3></div><b>{status}</b></header>
    <p>{definition.description}</p>
    {result.error && <div className="workspace-live-widget-error"><span>{result.error.message}</span><button type="button" onClick={result.retry}>Retry</button></div>}
    {widget?.action === 'search' && <form action={href}><input name="q" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={`Search ${definition.name.toLowerCase()}`} /><a href={searchHref}>Search</a></form>}
    <a className="workspace-live-widget-open" href={href}>Open tool <span>→</span></a>
  </article>;
}

export function WorkspaceToolWidgets({ toolIds, accountLabel }: { toolIds: string[]; accountLabel: string }) {
  const enabled = useMemo(() => Object.fromEntries(CORE_WIDGET_IDS.map((id) => [id, toolIds.includes(id)])) as Record<AccountWidgetKey, boolean>, [toolIds]);
  const utility = assignableTools.filter((definition) => definition.widget?.kind !== 'core' && toolIds.includes(definition.id));
  return <>
    <AccountToolWidgets enabled={enabled} accountLabel={accountLabel} />
    {!!utility.length && <section className="workspace-live-tools"><div className="workspace-live-tools-heading"><span>Connected tools</span><h2>Work queues and actions</h2></div><div className="workspace-live-tools-grid">
      {utility.map((definition) => <LiveToolWidget key={definition.id} definition={definition} />)}
    </div></section>}
  </>;
}
