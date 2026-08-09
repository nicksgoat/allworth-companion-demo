import { useMemo, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import type { AdminGroup, AdminUser, Tool } from '../../services/admin';

const CATEGORY_META: { key: string; label: string; blurb: string }[] = [
  { key: 'live', label: 'Live tools', blurb: 'Shipped and in production today.' },
  { key: 'analytics', label: 'Analytics & reports', blurb: 'Reporting, visual analytics and exports.' },
  { key: 'utilities', label: 'Utilities', blurb: 'Internal apps and lookup tools.' },
];

const STATUS_LABEL: Record<string, string> = { live: 'Live', new: 'New', soon: 'Soon' };

interface ToolsPanelProps {
  tools: Tool[];
  users: AdminUser[];
  groups: AdminGroup[];
  onShareUser: (toolId: string, email: string, grant: boolean) => void;
  onShareGroup: (toolId: string, group: AdminGroup, grant: boolean) => void;
}

export function ToolsPanel({ tools, users, groups, onShareUser, onShareGroup }: ToolsPanelProps) {
  const categories = useMemo(() => {
    const byCategory = new Map<string, Tool[]>();
    for (const tool of tools) {
      const categoryTools = byCategory.get(tool.category) ?? [];
      categoryTools.push(tool);
      byCategory.set(tool.category, categoryTools);
    }

    const ordered = CATEGORY_META.flatMap((meta) => {
      const items = byCategory.get(meta.key);
      return items?.length ? [{ ...meta, items }] : [];
    });

    for (const [key, items] of byCategory) {
      if (!CATEGORY_META.some((meta) => meta.key === key)) {
        ordered.push({ key, label: key, blurb: '', items });
      }
    }
    return ordered;
  }, [tools]);

  if (tools.length === 0) {
    return <section className="admin-panel"><div className="admin-empty">No tools registered.</div></section>;
  }

  return (
    <section className="admin-panel">
      <p className="admin-tools-intro">
        Browse tools by section, drill into a tool, then share it with a user or group.
        Group shares cascade to every member.
      </p>
      <div className="admin-list">
        {categories.map((category) => (
          <ToolCategoryCard
            key={category.key}
            label={category.label}
            blurb={category.blurb}
            items={category.items}
            users={users}
            groups={groups}
            onShareUser={onShareUser}
            onShareGroup={onShareGroup}
          />
        ))}
      </div>
    </section>
  );
}

interface ToolCategoryCardProps extends Pick<ToolsPanelProps, 'users' | 'groups' | 'onShareUser' | 'onShareGroup'> {
  label: string;
  blurb: string;
  items: Tool[];
}

function ToolCategoryCard({ label, blurb, items, users, groups, onShareUser, onShareGroup }: ToolCategoryCardProps) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`admin-card${open ? ' open' : ''}`}>
      <div className="admin-card-head">
        <button type="button" className="admin-card-toggle" onClick={() => setOpen((current) => !current)}>
          <span className="admin-chevron" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m9 6 6 6-6 6" /></svg>
          </span>
          <span className="admin-card-titlewrap">
            <span className="admin-card-title">{label}</span>
            <span className="admin-card-count">{items.length} {items.length === 1 ? 'tool' : 'tools'}</span>
          </span>
        </button>
      </div>
      {open && (
        <div className="admin-card-body">
          {blurb && <div className="admin-card-sub">{blurb}</div>}
          <div className="admin-list admin-tool-sublist">
            {items.map((tool) => (
              <ToolShareRow
                key={tool.id}
                tool={tool}
                users={users}
                groups={groups}
                onShareUser={onShareUser}
                onShareGroup={onShareGroup}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

interface ToolShareRowProps extends Pick<ToolsPanelProps, 'users' | 'groups' | 'onShareUser' | 'onShareGroup'> {
  tool: Tool;
}

function ToolShareRow({ tool, users, groups, onShareUser, onShareGroup }: ToolShareRowProps) {
  const [open, setOpen] = useState(false);
  const grantingGroups = useMemo(
    () => groups.filter((group) => group.all_tools || group.tools.includes(tool.id)),
    [groups, tool.id],
  );
  const directUsers = useMemo(
    () => users.filter((user) => user.direct_tools.includes(tool.id)),
    [users, tool.id],
  );
  const shareCount = grantingGroups.length + directUsers.length;

  return (
    <div className={`admin-card admin-tool-card${open ? ' open' : ''}`}>
      <div className="admin-card-head">
        <button type="button" className="admin-card-toggle" onClick={() => setOpen((current) => !current)}>
          <span className="admin-chevron" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m9 6 6 6-6 6" /></svg>
          </span>
          <span className="admin-card-titlewrap">
            <span className="admin-card-title">
              {tool.name}
              {STATUS_LABEL[tool.status] && (
                <span className={`admin-status-badge admin-status-${tool.status}`}>{STATUS_LABEL[tool.status]}</span>
              )}
            </span>
            <span className="admin-card-count">
              {shareCount === 0 ? 'Not shared' : `Shared with ${shareCount} ${shareCount === 1 ? 'recipient' : 'recipients'}`}
            </span>
          </span>
        </button>
      </div>
      {open && (
        <div className="admin-card-body">
          <div className="admin-section-label">Share with a user or group</div>
          <ToolShareControl
            tool={tool}
            users={users}
            groups={groups}
            onShareUser={onShareUser}
            onShareGroup={onShareGroup}
          />
          <div className="admin-section-label">Groups <span className="admin-tab-count">{grantingGroups.length}</span></div>
          {grantingGroups.length === 0 ? (
            <div className="admin-muted admin-members-empty">No groups have this tool.</div>
          ) : (
            <div className="admin-members">
              {grantingGroups.map((group) => (
                <span className="admin-member" key={group.id}>
                  {group.name}
                  {group.all_tools ? (
                    <span className="admin-alltools-badge">All tools</span>
                  ) : (
                    <button
                      type="button"
                      className="admin-member-x"
                      onClick={() => onShareGroup(tool.id, group, false)}
                      title={`Remove ${tool.name} from ${group.name}`}
                    >×</button>
                  )}
                </span>
              ))}
            </div>
          )}
          <div className="admin-section-label">Users (direct) <span className="admin-tab-count">{directUsers.length}</span></div>
          {directUsers.length === 0 ? (
            <div className="admin-muted admin-members-empty">No users have this tool granted directly.</div>
          ) : (
            <div className="admin-members">
              {directUsers.map((user) => (
                <span className="admin-member" key={user.email}>
                  {user.email}
                  <button
                    type="button"
                    className="admin-member-x"
                    onClick={() => onShareUser(tool.id, user.email, false)}
                    title={`Remove ${tool.name} from ${user.email}`}
                  >×</button>
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ToolShareControl({ tool, users, groups, onShareUser, onShareGroup }: ToolShareRowProps) {
  const [query, setQuery] = useState('');
  const [focused, setFocused] = useState(false);
  const normalizedQuery = query.trim().toLowerCase();
  const groupMatches = useMemo(
    () => groups
      .filter((group) => !group.all_tools && !group.tools.includes(tool.id) && group.name.toLowerCase().includes(normalizedQuery))
      .slice(0, 5),
    [groups, normalizedQuery, tool.id],
  );
  const userMatches = useMemo(
    () => users
      .filter((user) => !user.direct_tools.includes(tool.id) && user.email.includes(normalizedQuery))
      .slice(0, 6),
    [users, normalizedQuery, tool.id],
  );
  const showMenu = focused && (groupMatches.length > 0 || userMatches.length > 0);

  const pickGroup = (group: AdminGroup) => {
    onShareGroup(tool.id, group, true);
    setQuery('');
    setFocused(false);
  };
  const pickUser = (email: string) => {
    onShareUser(tool.id, email, true);
    setQuery('');
    setFocused(false);
  };
  const onKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (event.key !== 'Enter') return;
    if (groupMatches.length > 0) pickGroup(groupMatches[0]);
    else if (userMatches.length > 0) pickUser(userMatches[0].email);
  };

  return (
    <div className="admin-search">
      <input
        type="text"
        placeholder="Search users or groups to share with…"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setTimeout(() => setFocused(false), 120)}
        onKeyDown={onKeyDown}
      />
      {showMenu && (
        <div className="admin-search-menu">
          {groupMatches.length > 0 && <div className="admin-search-group">Groups</div>}
          {groupMatches.map((group) => (
            <button type="button" key={group.id} className="admin-search-item" onMouseDown={() => pickGroup(group)}>
              <span>{group.name}</span><span className="admin-search-kind">group</span>
            </button>
          ))}
          {userMatches.length > 0 && <div className="admin-search-group">Users</div>}
          {userMatches.map((user) => (
            <button type="button" key={user.email} className="admin-search-item" onMouseDown={() => pickUser(user.email)}>
              <span>{user.email}</span><span className="admin-search-kind">user</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
