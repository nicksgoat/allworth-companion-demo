// src/AppUsage.tsx
// App Usage — an admin-only dashboard of page-view traffic per tool, backed by
// GET /api/analytics (aip.page_views in Synapse). Supports a "Last N days"
// window and a user-email include/exclude filter with a searchable dropdown.
// Mounts the shared <SideNav /> like the Admin console; page chrome reuses the
// .t2-* glass theme, with usage-specific UI scoped under .usage-console.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent, MouseEvent as ReactMouseEvent } from 'react';
import './Tamarac2.css';
import './AppUsage.css';
import SideNav from './components/SideNav';
import TimezonePicker from './components/TimezonePicker';
import { analyticsApi, type UsageResponse } from './services/analytics';
import { adminApi, type AdminGroup } from './services/admin';
import { getTzIana, useTimezone, type TzKey } from './services/timezone';

const DAY_PRESETS = [7, 30, 90, 365];

const numberFmt = (n: number) => n.toLocaleString('en-US');

// Tracked timestamps are stored in UTC but serialized naive (no offset), which
// JS would otherwise parse as browser-local. Append 'Z' so the instant is read
// as UTC before it's rendered in the viewer-selected zone.
const asUtcDate = (iso: string): Date => {
  const hasTz = /(?:Z|[+-]\d{2}:?\d{2})$/.test(iso);
  return new Date(hasTz ? iso : `${iso}Z`);
};

// Render a tracked-view timestamp as a compact date + time in the given zone.
const formatDateTime = (iso: string | null, tz: TzKey): string => {
  if (!iso) return '—';
  const d = asUtcDate(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZone: getTzIana(tz),
  });
};

// Short axis label for a daily bucket, e.g. "Jul 22". The date is a bare
// YYYY-MM-DD, so anchor it at local midnight to avoid an off-by-one shift.
const formatDayLabel = (date: string): string => {
  const d = new Date(`${date}T00:00:00`);
  if (Number.isNaN(d.getTime())) return date;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};

// Round a raw step up to a clean 1/2/5 × 10ⁿ value so y-axis ticks read nicely.
const niceStep = (raw: number): number => {
  if (raw <= 0) return 1;
  const pow = Math.pow(10, Math.floor(Math.log10(raw)));
  const n = raw / pow;
  const nice = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10;
  return nice * pow;
};

// Evenly spaced y-axis ticks from 0 up to at least `max`, using a nice step.
// Returns the tick values plus the top value used to scale the bars.
const buildYTicks = (max: number, targetCount = 4): { ticks: number[]; top: number } => {
  if (max <= 0) return { ticks: [0], top: 1 };
  const step = niceStep(max / targetCount);
  const ticks: number[] = [];
  for (let v = 0; v <= max + step / 2; v += step) ticks.push(v);
  const top = ticks[ticks.length - 1];
  return { ticks, top };
};

// Right-click context menu — either on a per-tool bar or a top-users bar.
type MenuState =
  | { kind: 'tool'; x: number; y: number; toolId: string; toolName: string }
  | { kind: 'user'; x: number; y: number; email: string };

export default function AppUsage() {
  const [days, setDays] = useState(7);
  // App Usage defaults to Central and keeps its own stored preference, separate
  // from the pipeline views (which default to Eastern).
  const [tz, setTz] = useTimezone({ defaultTz: 'central', storageKey: 'appusage.tz' });
  const [emails, setEmails] = useState<string[]>([]);
  const [groupIds, setGroupIds] = useState<string[]>([]);
  const [groups, setGroups] = useState<AdminGroup[]>([]);
  const [mode, setMode] = useState<'include' | 'exclude'>('include');
  const [tools, setTools] = useState<string[]>([]);
  const [toolMode, setToolMode] = useState<'include' | 'exclude'>('include');
  const [data, setData] = useState<UsageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [menu, setMenu] = useState<MenuState | null>(null);

  // Groups power the "filter by group" option — selecting one expands to its
  // member emails, which flow through the same include/exclude email filter.
  useEffect(() => {
    adminApi.getGroups().then(setGroups).catch(() => setGroups([]));
  }, []);

  const selectedGroups = useMemo(
    () => groups.filter((g) => groupIds.includes(g.id)),
    [groups, groupIds]
  );

  // Union of directly-picked user emails and every member of the picked groups.
  const effectiveEmails = useMemo(() => {
    const set = new Set(emails);
    for (const g of selectedGroups) for (const m of g.members) set.add(m);
    return [...set];
  }, [emails, selectedGroups]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await analyticsApi.fetchUsage({
        days,
        emails: effectiveEmails,
        mode,
        tools,
        toolMode,
      });
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [days, effectiveEmails, mode, tools, toolMode]);

  useEffect(() => {
    void load();
  }, [load]);

  const knownEmails = data?.emails ?? [];
  const byTool = data?.by_tool ?? [];
  const byUser = data?.by_user ?? [];
  const daily = data?.daily ?? [];
  const details = data?.details ?? [];
  const summary = data?.summary;

  const maxToolViews = useMemo(
    () => byTool.reduce((m, t) => Math.max(m, t.views), 0),
    [byTool]
  );
  const maxUserViews = useMemo(
    () => byUser.reduce((m, u) => Math.max(m, u.views), 0),
    [byUser]
  );
  const maxDaily = useMemo(
    () => daily.reduce((m, d) => Math.max(m, d.views), 0),
    [daily]
  );
  // Y-axis ticks + the top value the bars scale against (so bars line up with
  // the gridlines rather than a raw max).
  const { ticks: yTicks, top: yTop } = useMemo(() => buildYTicks(maxDaily), [maxDaily]);
  // Thin the x-axis labels so ~8 show at most, regardless of the window length.
  const xLabelStep = useMemo(() => Math.max(1, Math.ceil(daily.length / 8)), [daily.length]);

  const addEmail = (e: string) => {
    const clean = e.trim().toLowerCase();
    if (!clean) return;
    setEmails((prev) => (prev.includes(clean) ? prev : [...prev, clean]));
  };
  const removeEmail = (e: string) => setEmails((prev) => prev.filter((x) => x !== e));
  const addGroup = (id: string) =>
    setGroupIds((prev) => (prev.includes(id) ? prev : [...prev, id]));
  const removeGroup = (id: string) => setGroupIds((prev) => prev.filter((x) => x !== id));
  const clearUserGroup = () => {
    setEmails([]);
    setGroupIds([]);
  };

  // ── tool filter (right-click menu) ──────────────────────────────────────────
  const filterToTool = (toolId: string) => {
    setToolMode('include');
    setTools([toolId]);
    setMenu(null);
  };
  const excludeTool = (toolId: string) => {
    setToolMode((prevMode) => (prevMode === 'exclude' ? prevMode : 'exclude'));
    setTools((prev) => {
      // Switching into exclude mode starts a fresh exclusion list.
      const base = toolMode === 'exclude' ? prev : [];
      return base.includes(toolId) ? base : [...base, toolId];
    });
    setMenu(null);
  };
  const clearToolFilter = () => {
    setTools([]);
    setToolMode('include');
    setMenu(null);
  };
  const openMenu = (e: ReactMouseEvent, toolId: string, toolName: string) => {
    e.preventDefault();
    setMenu({ kind: 'tool', x: e.clientX, y: e.clientY, toolId, toolName });
  };

  // ── user filter (right-click menu on the Top Users tile) ────────────────────
  // Reuses the page-wide email include/exclude filter, so a pick here reshapes
  // every panel. Groups are cleared since the intent is to focus on / hide one
  // specific person.
  const filterToUser = (email: string) => {
    setMode('include');
    setGroupIds([]);
    setEmails([email]);
    setMenu(null);
  };
  const excludeUser = (email: string) => {
    // Switching into exclude mode starts a fresh exclusion list.
    setEmails((prev) => {
      const base = mode === 'exclude' ? prev : [];
      return base.includes(email) ? base : [...base, email];
    });
    setMode('exclude');
    setGroupIds([]);
    setMenu(null);
  };
  const clearUserFilter = () => {
    setEmails([]);
    setGroupIds([]);
    setMode('include');
    setMenu(null);
  };
  const openUserMenu = (e: ReactMouseEvent, email: string) => {
    e.preventDefault();
    setMenu({ kind: 'user', x: e.clientX, y: e.clientY, email });
  };

  // Close the context menu on Escape or any scroll.
  useEffect(() => {
    if (!menu) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setMenu(null);
    const onScroll = () => setMenu(null);
    window.addEventListener('keydown', onKey);
    window.addEventListener('scroll', onScroll, true);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('scroll', onScroll, true);
    };
  }, [menu]);

  const toolFilterActive = tools.length > 0;
  const userFilterActive = emails.length > 0 || groupIds.length > 0;

  return (
    <div className="t2-page has-sidenav">
      <SideNav />
      <div className="t2-bg" aria-hidden="true">
        <div className="t2-orb t2-orb-1" />
        <div className="t2-orb t2-orb-2" />
        <div className="t2-orb t2-orb-3" />
        <div className="t2-orb t2-orb-4" />
        <div className="t2-orb t2-orb-5" />
      </div>

      <div className="t2-shell usage-console">
        <header className="usage-hero">
          <div className="usage-hero-left">
            <div className="usage-kicker-row">
              <a className="usage-home" href="/">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6" /></svg>
                Back to hub
              </a>
              <span className="usage-kicker">Admin · Analytics</span>
            </div>
            <div className="usage-title"><h1>App Usage</h1></div>
            <p className="usage-tagline">
              Page-view traffic per tool. Filter by time window and by user or
              group to focus on (or exclude) specific people.
            </p>
          </div>
        </header>

        {/* ── filters ──────────────────────────────────────────────────── */}
        <section className="usage-filters">
          <div className="usage-filter">
            <span className="usage-filter-label">Time window</span>
            <div className="usage-daybtns" role="group" aria-label="Time window">
              {DAY_PRESETS.map((d) => (
                <button
                  key={d}
                  type="button"
                  className={'usage-daybtn' + (days === d ? ' active' : '')}
                  onClick={() => setDays(d)}
                >
                  Last {d} days
                </button>
              ))}
            </div>
          </div>

          <div className="usage-filter">
            <span className="usage-filter-label">Timezone</span>
            <TimezonePicker value={tz} onChange={setTz} ariaLabel="Display timezone" />
          </div>

          <div className="usage-filter usage-filter-grow">
            <span className="usage-filter-label">
              User or group
              <span className="usage-mode-toggle" role="group" aria-label="Include or exclude">
                <button
                  type="button"
                  className={'usage-mode' + (mode === 'include' ? ' active' : '')}
                  onClick={() => setMode('include')}
                >
                  Include
                </button>
                <button
                  type="button"
                  className={'usage-mode' + (mode === 'exclude' ? ' active' : '')}
                  onClick={() => setMode('exclude')}
                >
                  Exclude
                </button>
              </span>
            </span>
            <UserGroupFilter
              knownEmails={knownEmails}
              groups={groups}
              selectedEmails={emails}
              selectedGroupIds={groupIds}
              onAddEmail={addEmail}
              onRemoveEmail={removeEmail}
              onAddGroup={addGroup}
              onRemoveGroup={removeGroup}
              onClear={clearUserGroup}
            />
          </div>
        </section>

        {toolFilterActive && (
          <div className="usage-active-filters">
            <span className="usage-active-label">
              {toolMode === 'exclude' ? 'Excluding tools:' : 'Showing only:'}
            </span>
            {tools.map((tid) => {
              const name = byTool.find((t) => t.tool_id === tid)?.tool ?? tid;
              return (
                <span className="usage-active-chip" key={tid}>
                  {name}
                  <button
                    type="button"
                    className="usage-active-x"
                    onClick={() => setTools((prev) => prev.filter((x) => x !== tid))}
                    title="Remove"
                  >
                    ×
                  </button>
                </span>
              );
            })}
            <button type="button" className="usage-active-clear" onClick={clearToolFilter}>
              Clear
            </button>
          </div>
        )}

        {error && <div className="usage-error">{error}</div>}

        {loading && !data ? (
          <div className="usage-loading">Loading usage…</div>
        ) : (
          <>
            {/* ── summary tiles ──────────────────────────────────────── */}
            <section className="usage-stats">
              <StatTile label="Total views" value={summary?.total_views ?? 0} />
              <StatTile label="Unique visitors" value={summary?.unique_visitors ?? 0} />
              <StatTile label="Known users" value={summary?.unique_users ?? 0} />
              <StatTile label="Tools used" value={byTool.length} />
            </section>

            {/* ── traffic per tool + top users (split row) ───────────── */}
            <div className="usage-split">
              <section className="usage-panel">
                <div className="usage-panel-head">
                  <h2>Traffic per tool</h2>
                  <span className="usage-panel-sub">Page views in the last {days} days</span>
                </div>
                {byTool.length === 0 ? (
                  <div className="usage-empty">No traffic in this window.</div>
                ) : (
                  <div className="usage-bars">
                    {byTool.map((t) => (
                      <div
                        className="usage-bar-row"
                        key={t.tool_id}
                        onContextMenu={(e) => openMenu(e, t.tool_id, t.tool)}
                        title="Right-click to filter"
                      >
                        <div className="usage-bar-label">{t.tool}</div>
                        <div className="usage-bar-track">
                          <div
                            className="usage-bar-fill"
                            style={{ width: `${maxToolViews ? (t.views / maxToolViews) * 100 : 0}%` }}
                          />
                        </div>
                        <div className="usage-bar-value">{numberFmt(t.views)}</div>
                      </div>
                    ))}
                  </div>
                )}
              </section>

              <section className="usage-panel">
                <div className="usage-panel-head">
                  <h2>Top users</h2>
                  <span className="usage-panel-sub">Views by user in the last {days} days</span>
                </div>
                {byUser.length === 0 ? (
                  <div className="usage-empty">No traffic in this window.</div>
                ) : (
                  <div className="usage-bars">
                    {byUser.map((u) => (
                      <div
                        className={'usage-bar-row' + (u.user_email ? '' : ' usage-bar-row-static')}
                        key={u.user_email ?? '(anonymous)'}
                        onContextMenu={u.user_email ? (e) => openUserMenu(e, u.user_email as string) : undefined}
                        title={u.user_email ? 'Right-click to filter' : undefined}
                      >
                        <div className="usage-bar-label">
                          {u.user_email ?? <span className="usage-muted">anonymous</span>}
                        </div>
                        <div className="usage-bar-track">
                          <div
                            className="usage-bar-fill usage-bar-fill-user"
                            style={{ width: `${maxUserViews ? (u.views / maxUserViews) * 100 : 0}%` }}
                          />
                        </div>
                        <div className="usage-bar-value">{numberFmt(u.views)}</div>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            </div>

            {/* ── daily trend ────────────────────────────────────────── */}
            <section className="usage-panel">
              <div className="usage-panel-head">
                <h2>Daily views</h2>
                <span className="usage-panel-sub">{daily.length} day(s)</span>
              </div>
              {daily.length === 0 ? (
                <div className="usage-empty">No traffic in this window.</div>
              ) : (
                <div className="usage-chart">
                  {/* y-axis: view-count ticks aligned to the plot gridlines */}
                  <div className="usage-chart-y" aria-hidden="true">
                    {yTicks.map((v) => (
                      <span
                        key={v}
                        className="usage-chart-y-label"
                        style={{ bottom: `${(v / yTop) * 100}%` }}
                      >
                        {numberFmt(v)}
                      </span>
                    ))}
                  </div>
                  {/* plot: gridlines behind the daily bars */}
                  <div className="usage-chart-plot">
                    {yTicks.map((v) => (
                      <span
                        key={v}
                        className="usage-chart-grid"
                        style={{ bottom: `${(v / yTop) * 100}%` }}
                      />
                    ))}
                    <div className="usage-trend" role="img" aria-label="Daily views trend">
                      {daily.map((d) => (
                        <div key={d.date} className="usage-trend-col">
                          <div
                            className="usage-trend-bar"
                            style={{ height: `${yTop ? Math.max(2, (d.views / yTop) * 100) : 0}%` }}
                            title={`${formatDayLabel(d.date)}: ${numberFmt(d.views)} views`}
                          />
                        </div>
                      ))}
                    </div>
                  </div>
                  {/* x-axis: date labels, thinned to avoid crowding */}
                  <div className="usage-chart-x-spacer" aria-hidden="true" />
                  <div className="usage-chart-x">
                    {daily.map((d, i) => (
                      <div key={d.date} className="usage-chart-x-col">
                        <span className="usage-chart-x-label">
                          {i % xLabelStep === 0 ? formatDayLabel(d.date) : ''}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </section>

            {/* ── detailed views ─────────────────────────────────────── */}
            <section className="usage-panel">
              <div className="usage-panel-head">
                <h2>Detailed views</h2>
                <span className="usage-panel-sub">
                  {details.length === 0
                    ? 'No views match the current filters'
                    : `${numberFmt(details.length)} view${details.length === 1 ? '' : 's'} shown`}
                  {data?.details_truncated
                    ? ` (newest ${numberFmt(data.details_limit ?? details.length)} — narrow the filters to see more)`
                    : ''}
                </span>
              </div>
              {details.length === 0 ? (
                <div className="usage-empty">No matching views.</div>
              ) : (
                <div className="usage-table-wrap">
                  <table className="usage-table">
                    <thead>
                      <tr>
                        <th className="usage-th-date">Date &amp; time</th>
                        <th>User</th>
                        <th>Tool</th>
                      </tr>
                    </thead>
                    <tbody>
                      {details.map((r, i) => (
                        <tr key={`${r.timestamp}-${r.user_email ?? 'anon'}-${i}`}>
                          <td className="usage-td-date">{formatDateTime(r.timestamp, tz)}</td>
                          <td>{r.user_email ?? <span className="usage-muted">anonymous</span>}</td>
                          <td>{r.tool}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </>
        )}
      </div>

      {menu && (
        <>
          <div className="usage-menu-overlay" onClick={() => setMenu(null)} onContextMenu={(e) => { e.preventDefault(); setMenu(null); }} />
          <div className="usage-menu" style={{ top: menu.y, left: menu.x }} role="menu">
            {menu.kind === 'tool' ? (
              <>
                <div className="usage-menu-head">{menu.toolName}</div>
                <button type="button" className="usage-menu-item" onClick={() => filterToTool(menu.toolId)}>
                  Filter to this tool
                </button>
                <button type="button" className="usage-menu-item" onClick={() => excludeTool(menu.toolId)}>
                  Exclude this tool
                </button>
                {toolFilterActive && (
                  <>
                    <div className="usage-menu-sep" />
                    <button type="button" className="usage-menu-item" onClick={clearToolFilter}>
                      Clear tool filter
                    </button>
                  </>
                )}
              </>
            ) : (
              <>
                <div className="usage-menu-head">{menu.email}</div>
                <button type="button" className="usage-menu-item" onClick={() => filterToUser(menu.email)}>
                  Filter to this user
                </button>
                <button type="button" className="usage-menu-item" onClick={() => excludeUser(menu.email)}>
                  Exclude this user
                </button>
                {userFilterActive && (
                  <>
                    <div className="usage-menu-sep" />
                    <button type="button" className="usage-menu-item" onClick={clearUserFilter}>
                      Clear user filter
                    </button>
                  </>
                )}
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function StatTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="usage-stat">
      <div className="usage-stat-value">{numberFmt(value)}</div>
      <div className="usage-stat-label">{label}</div>
    </div>
  );
}

interface UserGroupFilterProps {
  knownEmails: string[];
  groups: AdminGroup[];
  selectedEmails: string[];
  selectedGroupIds: string[];
  onAddEmail: (email: string) => void;
  onRemoveEmail: (email: string) => void;
  onAddGroup: (id: string) => void;
  onRemoveGroup: (id: string) => void;
  onClear: () => void;
}

function UserGroupFilter({
  knownEmails,
  groups,
  selectedEmails,
  selectedGroupIds,
  onAddEmail,
  onRemoveEmail,
  onAddGroup,
  onRemoveGroup,
  onClear,
}: UserGroupFilterProps) {
  const [query, setQuery] = useState('');
  const [focused, setFocused] = useState(false);
  const blurTimer = useRef<number | undefined>(undefined);

  const q = query.trim().toLowerCase();
  const emailSet = useMemo(() => new Set(selectedEmails), [selectedEmails]);
  const groupSet = useMemo(() => new Set(selectedGroupIds), [selectedGroupIds]);

  const groupMatches = useMemo(
    () => groups.filter((g) => !groupSet.has(g.id) && g.name.toLowerCase().includes(q)).slice(0, 5),
    [groups, groupSet, q]
  );
  const emailMatches = useMemo(
    () => knownEmails.filter((e) => !emailSet.has(e) && e.toLowerCase().includes(q)).slice(0, 6),
    [knownEmails, emailSet, q]
  );
  const canAddCustom =
    q.includes('@') && !knownEmails.some((e) => e.toLowerCase() === q) && !emailSet.has(q);

  const pickEmail = (email: string) => {
    onAddEmail(email);
    setQuery('');
  };
  const pickGroup = (id: string) => {
    onAddGroup(id);
    setQuery('');
  };

  const onKeyDown = (e: ReactKeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'Enter') return;
    if (groupMatches.length > 0) pickGroup(groupMatches[0].id);
    else if (emailMatches.length > 0) pickEmail(emailMatches[0]);
    else if (canAddCustom) pickEmail(q);
  };

  const groupName = (id: string) => groups.find((g) => g.id === id)?.name ?? id;
  const hasSelection = selectedEmails.length > 0 || selectedGroupIds.length > 0;
  const showMenu =
    focused && (groupMatches.length > 0 || emailMatches.length > 0 || canAddCustom);

  return (
    <div className="usage-email">
      <div className="usage-email-box">
        {selectedGroupIds.map((id) => (
          <span className="usage-email-chip usage-email-chip-group" key={`g:${id}`}>
            <span className="usage-chip-kind">group</span>
            {groupName(id)}
            <button
              type="button"
              className="usage-email-x"
              onClick={() => onRemoveGroup(id)}
              title={`Remove ${groupName(id)}`}
            >
              ×
            </button>
          </span>
        ))}
        {selectedEmails.map((e) => (
          <span className="usage-email-chip" key={`u:${e}`}>
            {e}
            <button type="button" className="usage-email-x" onClick={() => onRemoveEmail(e)} title={`Remove ${e}`}>
              ×
            </button>
          </span>
        ))}
        <div className="usage-email-input">
          <input
            type="text"
            placeholder={hasSelection ? 'Add user or group…' : 'Search users or groups…'}
            value={query}
            onChange={(ev) => setQuery(ev.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => {
              blurTimer.current = window.setTimeout(() => setFocused(false), 120);
            }}
            onKeyDown={onKeyDown}
          />
          {showMenu && (
            <div className="usage-email-menu">
              {groupMatches.length > 0 && <div className="usage-email-group-head">Groups</div>}
              {groupMatches.map((g) => (
                <button
                  type="button"
                  key={g.id}
                  className="usage-email-item usage-email-item-row"
                  onMouseDown={() => pickGroup(g.id)}
                >
                  <span>{g.name}</span>
                  <span className="usage-chip-kind">
                    {g.all_members ? 'everyone' : `${g.members.length} member${g.members.length === 1 ? '' : 's'}`}
                  </span>
                </button>
              ))}
              {emailMatches.length > 0 && <div className="usage-email-group-head">Users</div>}
              {emailMatches.map((e) => (
                <button
                  type="button"
                  key={e}
                  className="usage-email-item"
                  onMouseDown={() => pickEmail(e)}
                >
                  {e}
                </button>
              ))}
              {canAddCustom && (
                <button
                  type="button"
                  className="usage-email-item usage-email-new"
                  onMouseDown={() => pickEmail(q)}
                >
                  Add: <strong>{q}</strong>
                </button>
              )}
            </div>
          )}
        </div>
        {hasSelection && (
          <button type="button" className="usage-email-clear" onClick={onClear}>
            Clear
          </button>
        )}
      </div>
    </div>
  );
}
