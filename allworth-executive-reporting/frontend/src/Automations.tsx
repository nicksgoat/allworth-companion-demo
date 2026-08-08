// Automations — an admin-gated home for internal/dev tools that don't warrant
// their own top-level page. First resident: Email Automations (the mailer —
// email→pipeline trigger rules + send status). Add a new entry to TOOLS to slot
// another utility in as its own sub-tab. Page chrome (background, orbs, shell)
// reuses the .t2-* / .admin-console classes; automation-specific bits are scoped
// under .autom in Automations.css.
import { useCallback, useEffect, useState } from 'react';
import './Tamarac2.css';
import './Admin.css';
import './Automations.css';
import SideNav from './components/SideNav';

// --- mailer API (same-origin, gated by Easy Auth like every tool) ----------
interface Rule {
  id: string;
  mailbox: string;
  target_url: string;
  match: { from_contains?: string; subject_contains?: string };
  watermark?: string;
  active?: boolean;
}

async function mailer<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/mailer${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok || body.success === false) {
    throw new Error((body.error as string) || `${path} → ${res.status}`);
  }
  return body as T;
}

// --- registry of internal tools (extensible) -------------------------------
const TOOLS = [{ key: 'mailer', label: 'Email automations' }] as const;
type ToolKey = (typeof TOOLS)[number]['key'];

function EmailAutomations() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [fromConfigured, setFromConfigured] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  // create-form state
  const [targetUrl, setTargetUrl] = useState('');
  const [mailbox, setMailbox] = useState('');
  const [subjectContains, setSubjectContains] = useState('');
  const [fromContains, setFromContains] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [h, r] = await Promise.all([
        mailer<{ from_configured: boolean }>('/api/health'),
        mailer<{ rules: Rule[] }>('/api/rules'),
      ]);
      setFromConfigured(h.from_configured);
      setRules(r.rules ?? []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const flash = (m: string) => {
    setNote(m);
    setTimeout(() => setNote(null), 3000);
  };

  const createRule = async () => {
    if (!targetUrl.trim()) {
      setErr('A pipeline target URL is required.');
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await mailer('/api/rules', {
        method: 'POST',
        body: JSON.stringify({
          target_url: targetUrl.trim(),
          mailbox: mailbox.trim() || undefined,
          subject_contains: subjectContains.trim() || undefined,
          from_contains: fromContains.trim() || undefined,
        }),
      });
      setTargetUrl('');
      setMailbox('');
      setSubjectContains('');
      setFromContains('');
      flash('Trigger rule created.');
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to create rule');
    } finally {
      setBusy(false);
    }
  };

  const removeRule = async (id: string) => {
    try {
      await mailer(`/api/rules/${id}`, { method: 'DELETE' });
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to delete rule');
    }
  };

  const runPoll = async () => {
    setBusy(true);
    try {
      const r = await mailer<{ dispatched: number; rules: number }>('/api/poll', { method: 'POST' });
      flash(`Poll ran — ${r.dispatched} email(s) dispatched across ${r.rules} rule(s).`);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Poll failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="autom-panel">
      <p className="autom-lead">
        Trigger a pipeline when an email arrives. Each rule watches a mailbox and,
        on a match, POSTs the message to your pipeline's URL. A scheduled poll
        (or the button below) drives it — no inbox babysitting.
      </p>

      {fromConfigured === false ? (
        <div className="autom-warn">
          <strong>Heads up:</strong> no service mailbox is configured yet
          (<code>MAILER_FROM</code> app setting). App-only send/poll needs it, plus
          Application <code>Mail.Send</code>/<code>Mail.Read</code> admin consent.
          See <code>backend/mailer/SYNAPSE_INTEGRATION.md</code>.
        </div>
      ) : null}

      {err ? <div className="autom-error">{err}</div> : null}
      {note ? <div className="autom-note">{note}</div> : null}

      <div className="autom-card">
        <h3>New trigger rule</h3>
        <label>
          Pipeline target URL <span className="autom-req">required</span>
          <input
            value={targetUrl}
            onChange={(e) => setTargetUrl(e.target.value)}
            placeholder="https://…/your-pipeline-trigger"
          />
        </label>
        <div className="autom-row">
          <label>
            Mailbox <span className="autom-opt">defaults to MAILER_FROM</span>
            <input value={mailbox} onChange={(e) => setMailbox(e.target.value)} placeholder="automations@allworthfinancial.com" />
          </label>
        </div>
        <div className="autom-row">
          <label>
            Subject contains <span className="autom-opt">optional</span>
            <input value={subjectContains} onChange={(e) => setSubjectContains(e.target.value)} placeholder="sync complete" />
          </label>
          <label>
            From contains <span className="autom-opt">optional</span>
            <input value={fromContains} onChange={(e) => setFromContains(e.target.value)} placeholder="envestnet.com" />
          </label>
        </div>
        <button className="autom-btn autom-btn-primary" onClick={createRule} disabled={busy}>
          Create rule
        </button>
      </div>

      <div className="autom-card">
        <div className="autom-card-head">
          <h3>Active rules {loading ? '' : `(${rules.length})`}</h3>
          <button className="autom-btn" onClick={runPoll} disabled={busy || loading}>
            ↻ Run poll now
          </button>
        </div>
        {loading ? (
          <p className="autom-muted">Loading…</p>
        ) : rules.length === 0 ? (
          <p className="autom-muted">No rules yet. Create one above to start triggering a pipeline from email.</p>
        ) : (
          <ul className="autom-rules">
            {rules.map((r) => (
              <li key={r.id} className="autom-rule">
                <div className="autom-rule-main">
                  <div className="autom-rule-target">{r.target_url}</div>
                  <div className="autom-rule-meta">
                    <span>📥 {r.mailbox}</span>
                    {r.match?.subject_contains ? <span>subject ∋ “{r.match.subject_contains}”</span> : null}
                    {r.match?.from_contains ? <span>from ∋ “{r.match.from_contains}”</span> : null}
                    {!r.match?.subject_contains && !r.match?.from_contains ? <span>matches all mail</span> : null}
                  </div>
                </div>
                <button className="autom-btn autom-btn-danger" onClick={() => removeRule(r.id)}>
                  Delete
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export default function Automations() {
  const [tab, setTab] = useState<ToolKey>('mailer');
  return (
    <div className="t2-page has-sidenav">
      <SideNav />
      <div className="t2-shell admin-console">
        <header className="autom-hero">
          <div>
            <div className="autom-kicker">Admin · Automations</div>
            <h1>Automations</h1>
            <p className="autom-sub">Internal tools and automated workflows. More utilities can live here as tabs.</p>
          </div>
        </header>

        <nav className="autom-tabs" aria-label="Automation tools">
          {TOOLS.map((t) => (
            <button
              key={t.key}
              className={`autom-tab ${tab === t.key ? 'is-active' : ''}`}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </nav>

        {tab === 'mailer' ? <EmailAutomations /> : null}
      </div>
    </div>
  );
}
