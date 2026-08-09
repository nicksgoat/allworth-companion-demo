import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Divider,
  FormControlLabel,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import SendIcon from '@mui/icons-material/Send';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import AuthControl from './components/AuthControl';
import EmailBatchReview from './components/EmailBatchReview';
import RichTextEditor from './components/RichTextEditor';
import ShareTool from './components/ShareTool';
import { ToolPage, ToolPanel } from './components/ToolPage';
import { ThemeProvider } from '@mui/material/styles';
import { colors, muiTheme } from './theme';
import { previewEmailBatch, sendEmailBatch, getMailerStatus } from './services/emailBatchApi';
import type { PreviewResponse, EmailBatchGroup, SendResponse, MailerStatus } from './services/emailBatchApi';
import { resolveUserProfile } from './services/auth';
import './BondAnalyzer.css';

const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';

const DEFAULT_MESSAGE = `<p>Hello,</p><p>We are raising cash for fees or MoDist. Please review and let us know if it is ok to trade. No need to respond if you do not want us to trade it.</p><p>Thank you</p><p>Best,</p>`;

function EmailPreview({ group }: { group: EmailBatchGroup }) {
  const [open, setOpen] = useState(false);
  return (
    <Box sx={{ mt: 1 }}>
      <Button
        size="small"
        startIcon={open ? <ExpandLessIcon /> : <ExpandMoreIcon />}
        onClick={() => setOpen((v) => !v)}
        sx={{ textTransform: 'none' }}
      >
        {open ? 'Hide email preview' : 'Show example email'}
      </Button>
      {open && (
        <Box
          sx={{
            mt: 1,
            border: '1px solid rgba(23,61,103,0.12)',
            borderRadius: 2,
            overflow: 'hidden',
          }}
        >
          <iframe
            title={`Email preview for ${group.advisors.join(', ') || group.email || 'advisor'}`}
            srcDoc={group.html}
            sandbox=""
            style={{ width: '100%', height: 360, border: 'none', background: '#fff' }}
          />
        </Box>
      )}
    </Box>
  );
}

function parseEmailList(raw: string): string[] {
  if (!raw.trim()) return [];
  const out: string[] = [];
  for (const part of raw.split(/[;,\n]+/)) {
    const v = part.trim();
    if (!v) continue;
    if (!out.some((item) => item.toLowerCase() === v.toLowerCase())) out.push(v);
  }
  return out;
}

export default function EmailBatchApp() {
  const [status, setStatus] = useState<MailerStatus | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState(DEFAULT_MESSAGE);
  const [subject, setSubject] = useState('');
  const [subjectEdited, setSubjectEdited] = useState(false);
  const [replyTo, setReplyTo] = useState('');
  const [replyToEdited, setReplyToEdited] = useState(false);
  const [groupCc, setGroupCc] = useState<Record<number, string>>({});
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [tab, setTab] = useState(0);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SendResponse | null>(null);

  // Pre-fill Reply-To with the signed-in user's email so advisor replies route
  // back to them. Skip if they've already typed something.

  useEffect(() => {
    if (DEMO_MODE) {
      setStatus({ graph_token_available: true, mailbox_fallback: false, ready: true, user: { email: 'demo@allworth.com', name: 'Demo user' } });
      return;
    }
    void getMailerStatus().then(setStatus);
  }, []);
  useEffect(() => {
    let cancelled = false;
    void resolveUserProfile().then((profile) => {
      if (cancelled || replyToEdited) return;
      if (profile.email) setReplyTo((prev) => prev || profile.email!);
    });
    return () => {
      cancelled = true;
    };
  }, [replyToEdited]);

  const sendableGroups = useMemo(
    () => (preview ? preview.groups.filter((g) => g.sendable) : []),
    [preview],
  );
  const selectedCount = useMemo(
    () => sendableGroups.filter((g) => selected.has(g.id)).length,
    [sendableGroups, selected],
  );
  const parsedReplyTo = useMemo(() => parseEmailList(replyTo), [replyTo]);
  const effectiveReplyTo = useMemo(
    () => (parsedReplyTo.length ? parsedReplyTo : (preview?.sender_email ? [preview.sender_email] : [])),
    [parsedReplyTo, preview?.sender_email],
  );

  function resetPreview() {
    setPreview(null);
    setSelected(new Set());
    setGroupCc({});
    setResult(null);
    setSubjectEdited(false);
  }

  async function handlePreview() {
    if (!file) return;
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const data = await previewEmailBatch(file, message);
      setPreview(data);
      if (!subjectEdited) setSubject(data.subject);
      setSelected(new Set(data.groups.filter((g) => g.sendable).map((g) => g.id)));
      setTab(0);
    } catch (err) {
      setPreview(null);
      setError(err instanceof Error ? err.message : 'Failed to build preview.');
    } finally {
      setLoading(false);
    }
  }

  function toggleGroup(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleSend() {
    if (!preview) return;
    setConfirmOpen(false);
    setError(null);
    setSending(true);
    try {
      const ids = sendableGroups.filter((g) => selected.has(g.id)).map((g) => g.id);
      const groupCcMap: Record<string, string[]> = {};
      for (const id of ids) {
        const list = (groupCc[id] ?? '')
          .split(/[,;\n]+/)
          .map((e) => e.trim())
          .filter(Boolean);
        if (list.length) groupCcMap[String(id)] = list;
      }
      const data = await sendEmailBatch(preview.batch_id, ids, groupCcMap, replyTo.trim() || undefined, subject.trim() || undefined);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send emails.');
    } finally {
      setSending(false);
    }
  }

  return (
    <ThemeProvider theme={muiTheme}>
      <ToolPage
        eyebrow="Communications"
        title="Advisor Mailer"
        description="Build, verify, and send account notices to advisors from a controlled workbook batch."
        width="wide"
        actions={
          <>
          <ShareTool toolId="advisor_mailer" toolName="Advisor Mailer" />
          <AuthControl />
          </>
        }
      >

      {/* ── Sign-in gate (mirrors Executive Brief) ───────────────────────── */}
      {status !== null && !status.ready && (
        <Box sx={{ minHeight: '70vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', px: 3, textAlign: 'center' }}>
          <Typography variant="h6" sx={{ fontWeight: 700, mb: 1 }}>Sign in to use Advisor Mailer</Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', mb: 3 }}>
            Sign in with your Allworth Microsoft account so emails are sent on your behalf and advisor replies reach your inbox.
          </Typography>
          <Button
            variant="contained"
            size="large"
            onClick={() => { window.location.href = '/.auth/login/aad?post_login_redirect_uri=/advisor-mailer'; }}
            sx={{ textTransform: 'none', fontWeight: 700, borderRadius: 6, px: 4 }}
          >
            Sign in with Microsoft
          </Button>
        </Box>
      )}

      {/* ── Main content (only when ready) ──────────────────────────────── */}
      {(status === null || status.ready) && (
      <>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        {/* Step 1 — upload */}
        <ToolPanel
          title="1 — Upload the accounts workbook"
          description="Use an Excel workbook with an advisor column such as Primary Advisor."
        >
          <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
            Message
          </Typography>
          <RichTextEditor
            value={message}
            onChange={(html) => {
              setMessage(html);
              resetPreview();
            }}
          />
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5, mb: 2 }}>
            This message is used for every advisor's email; the accounts table is added below it.
          </Typography>
          <TextField
            label="Subject line"
            size="small"
            fullWidth
            value={subject}
            onChange={(e) => {
              setSubjectEdited(true);
              setSubject(e.target.value);
            }}
            placeholder="Subject defaults to the uploaded file name"
            helperText="Defaults to the file name. Edit to override the subject for all emails in this batch."
            sx={{ mb: 2 }}
          />
          <TextField
            label="Reply-To email(s)"
            size="small"
            fullWidth
            type="text"
            value={replyTo}
            onChange={(e) => {
              setReplyToEdited(true);
              setReplyTo(e.target.value);
            }}
            placeholder="you@allworthfinancial.com; backup@allworthfinancial.com"
            helperText="Separate multiple emails with ; (example: you@allworthfinancial.com; team@allworthfinancial.com). If left blank, Reply-To defaults to your signed-in email."
            sx={{ mb: 2 }}
          />
          <Box sx={{ display: 'flex', flexDirection: { xs: 'column', sm: 'row' }, gap: 2, alignItems: { sm: 'center' } }}>
            <Button
              component="label"
              variant="outlined"
              startIcon={<UploadFileIcon />}
              sx={{ textTransform: 'none' }}
            >
              {file ? 'Change file' : 'Choose Excel file'}
              <input
                type="file"
                accept=".xlsx,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                hidden
                onChange={(e) => {
                  setFile(e.target.files?.[0] ?? null);
                  resetPreview();
                }}
              />
            </Button>
            {file && (
              <Typography variant="body2" sx={{ flex: 1, minWidth: 0 }}>
                {file.name}
              </Typography>
            )}
            <Button
              variant="contained"
              onClick={handlePreview}
              disabled={!file || loading}
              startIcon={loading ? <CircularProgress size={16} color="inherit" /> : undefined}
              sx={{ textTransform: 'none', fontWeight: 700 }}
            >
              {loading ? 'Building preview…' : 'Preview emails'}
            </Button>
          </Box>
        </ToolPanel>

        {/* Step 2 — preview + send */}
        {preview && (
          <ToolPanel
            title="2 — Verify, then send"
            description="Confirm recipients, account groups, reply routing, and the rendered message before delivery."
          >
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 1.5 }}>
              <Chip size="small" label={`Subject: ${subject || preview.subject}`} />
              <Chip size="small" label={`Advisor column: ${preview.advisor_column}`} />
              <Chip size="small" label={`${preview.total_rows} rows`} />
              <Chip
                size="small"
                variant="outlined"
                color={effectiveReplyTo.length > 0 ? 'default' : 'warning'}
                label={`CC & Reply-To: ${effectiveReplyTo.length ? effectiveReplyTo.join(', ') : 'not signed in'}`}
              />
              <Chip
                size="small"
                color="success"
                label={`${sendableGroups.length} sendable`}
                variant="outlined"
              />
            </Box>

            {preview.warnings.map((w, i) => (
              <Alert key={i} severity="warning" sx={{ mb: 1 }}>
                {w}
              </Alert>
            ))}

            {result && (
              <Alert
                severity={result.failed_count > 0 ? 'warning' : 'success'}
                sx={{ mb: 2 }}
                onClose={() => setResult(null)}
              >
                Sent {result.sent_count} email(s)
                {result.failed_count > 0 ? `, ${result.failed_count} failed` : ''}
                {result.skipped_count > 0 ? `, ${result.skipped_count} skipped` : ''}.
              </Alert>
            )}

            <Tabs
              value={tab}
              onChange={(_, v) => setTab(v)}
              sx={{ mb: 2, borderBottom: `1px solid ${colors.hairline}` }}
            >
              <Tab label="Review & verify" sx={{ textTransform: 'none', fontWeight: 700 }} />
              <Tab label="Email previews" sx={{ textTransform: 'none', fontWeight: 700 }} />
            </Tabs>

            {tab === 0 && (
              <Box>
                <EmailBatchReview preview={preview} />
                <Box sx={{ mt: 2, display: 'flex', justifyContent: 'flex-end' }}>
                  <Button
                    variant="contained"
                    onClick={() => setTab(1)}
                    sx={{ textTransform: 'none', fontWeight: 700 }}
                  >
                    Continue to email previews
                  </Button>
                </Box>
              </Box>
            )}

            {tab === 1 && (
            <>
            <Stack spacing={1.5} divider={<Divider flexItem />}>
              {preview.groups.map((group) => {
                const sentResult = result?.results.find((r) => r.group_id === group.id);
                return (
                  <Box key={group.id} sx={{ opacity: group.sendable ? 1 : 0.7 }}>
                    <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
                      <Checkbox
                        checked={group.sendable && selected.has(group.id)}
                        disabled={!group.sendable || sending}
                        onChange={() => toggleGroup(group.id)}
                        sx={{ mt: -0.5 }}
                      />
                      <Box sx={{ flex: 1, minWidth: 0 }}>
                        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
                          <Typography sx={{ fontWeight: 700 }}>
                            {group.advisors.join(', ') || '(no advisor name)'}
                          </Typography>
                          {group.sendable ? (
                            <Chip size="small" color="primary" variant="outlined" label={group.email} />
                          ) : (
                            <Chip size="small" color="warning" label="No email — will be skipped" />
                          )}
                          <Chip size="small" label={`${group.row_count} account(s)`} variant="outlined" />
                          {sentResult && (
                            <Chip
                              size="small"
                              color={sentResult.sent ? 'success' : 'error'}
                              label={sentResult.sent ? 'Sent' : sentResult.error || 'Failed'}
                            />
                          )}
                        </Box>
                        {group.cc.length > 0 && (
                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                            {(() => {
                              const sender = preview.sender_email?.toLowerCase();
                              const groupCcWithoutSender = group.cc.filter((c) => c.toLowerCase() !== sender);
                              const shownCc = effectiveReplyTo.length
                                ? [...effectiveReplyTo, ...groupCcWithoutSender]
                                : group.cc;
                              const deduped: string[] = [];
                              for (const item of shownCc) {
                                if (!deduped.some((d) => d.toLowerCase() === item.toLowerCase())) deduped.push(item);
                              }
                              return `CC: ${deduped.join(', ')}`;
                            })()}
                          </Typography>
                        )}
                        {group.sendable && (
                          <Box sx={{ mt: 1 }}>
                            <TextField
                              label="Additional CC for this email"
                              placeholder="cc1@example.com, cc2@example.com"
                              value={groupCc[group.id] ?? ''}
                              onChange={(e) =>
                                setGroupCc((prev) => ({ ...prev, [group.id]: e.target.value }))
                              }
                              disabled={sending}
                              size="small"
                              sx={{ width: '100%', maxWidth: 480 }}
                            />
                          </Box>
                        )}
                        <EmailPreview group={group} />
                      </Box>
                    </Box>
                  </Box>
                );
              })}
            </Stack>

            <Box sx={{ mt: 3, display: 'flex', justifyContent: 'flex-end', gap: 2 }}>
              <FormControlLabel
                sx={{ mr: 'auto' }}
                control={
                  <Checkbox
                    checked={selectedCount === sendableGroups.length && sendableGroups.length > 0}
                    indeterminate={selectedCount > 0 && selectedCount < sendableGroups.length}
                    disabled={sendableGroups.length === 0 || sending}
                    onChange={(e) =>
                      setSelected(
                        e.target.checked ? new Set(sendableGroups.map((g) => g.id)) : new Set(),
                      )
                    }
                  />
                }
                label="Select all"
              />
              <Button
                variant="contained"
                color="primary"
                startIcon={sending ? <CircularProgress size={16} color="inherit" /> : <SendIcon />}
                disabled={selectedCount === 0 || sending}
                onClick={() => setConfirmOpen(true)}
                sx={{ textTransform: 'none', fontWeight: 700, px: 3 }}
              >
                {sending ? 'Sending…' : `Send ${selectedCount} email${selectedCount === 1 ? '' : 's'}`}
              </Button>
            </Box>
            </>
            )}
          </ToolPanel>
        )}

      <Dialog open={confirmOpen} onClose={() => setConfirmOpen(false)}>
        <DialogTitle>Send advisor emails?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            This will send {selectedCount} email{selectedCount === 1 ? '' : 's'} to the selected
            advisors{effectiveReplyTo.length ? `, CC and Reply-To ${effectiveReplyTo.join(', ')}` : ''}, plus
            any per-email CC you added. This action cannot be undone.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmOpen(false)} sx={{ textTransform: 'none' }}>
            Cancel
          </Button>
          <Button onClick={handleSend} variant="contained" sx={{ textTransform: 'none', fontWeight: 700 }}>
            Send now
          </Button>
        </DialogActions>
      </Dialog>
      </>
      )}
      </ToolPage>
    </ThemeProvider>
  );
}
