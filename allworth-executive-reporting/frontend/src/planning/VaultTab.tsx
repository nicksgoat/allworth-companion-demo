import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert, Box, Button, Card, CardContent, Chip, CircularProgress, IconButton, Stack,
  Switch, Table, TableBody, TableCell, TableHead, TableRow, Typography,
} from '@mui/material';
import UploadFileOutlinedIcon from '@mui/icons-material/UploadFileOutlined';
import DeleteOutlinedIcon from '@mui/icons-material/DeleteOutlined';
import DownloadOutlinedIcon from '@mui/icons-material/DownloadOutlined';
import { planningApi, type VaultFile } from '../services/planningApi';

const formatSize = (bytes: number) => bytes >= 1048576
  ? `${(bytes / 1048576).toFixed(1)} MB`
  : `${Math.max(1, Math.round(bytes / 1024))} KB`;

export default function VaultTab({ householdId, onError }: { householdId: string; onError: (message: string) => void }) {
  const [files, setFiles] = useState<VaultFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try { setFiles((await planningApi.vaultFiles(householdId)).files); }
    catch (e) { onError(e instanceof Error ? e.message : 'Unable to load vault'); }
    finally { setLoading(false); }
  }, [householdId, onError]);

  useEffect(() => { void load(); }, [load]);

  async function upload(fileList: FileList | null) {
    const file = fileList?.[0];
    if (!file) return;
    setUploading(true);
    try { await planningApi.vaultUpload(householdId, file, 'Shared', false); await load(); }
    catch (e) { onError(e instanceof Error ? e.message : 'Upload failed'); }
    finally { setUploading(false); if (inputRef.current) inputRef.current.value = ''; }
  }

  async function toggleShare(file: VaultFile) {
    try {
      const updated = await planningApi.vaultShare(householdId, file.id, !file.shared_with_client);
      setFiles(current => current.map(item => item.id === file.id ? updated : item));
    } catch (e) { onError(e instanceof Error ? e.message : 'Share update failed'); }
  }

  async function remove(file: VaultFile) {
    if (!window.confirm(`Delete "${file.name}" from the vault?`)) return;
    try { await planningApi.vaultDelete(householdId, file.id); await load(); }
    catch (e) { onError(e instanceof Error ? e.message : 'Delete failed'); }
  }

  return <Box className="plan-panel">
    <Card><CardContent>
      <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 2, mb: 2 }}>
        <Box>
          <Typography variant="h6">Document vault</Typography>
          <Typography color="text.secondary">Plan documents with client-sharing controls; every access is audit-logged.</Typography>
        </Box>
        <Button variant="contained" startIcon={<UploadFileOutlinedIcon />} onClick={() => inputRef.current?.click()} disabled={uploading}>
          {uploading ? 'Uploading…' : 'Upload document'}
        </Button>
        <input ref={inputRef} type="file" hidden onChange={e => void upload(e.target.files)} />
      </Stack>
      {loading ? <Box className="plan-loading" sx={{ minHeight: '20vh' }}><CircularProgress /></Box>
        : files.length === 0 ? <Alert severity="info">No documents yet. Upload plan PDFs, statements, or estate documents.</Alert>
          : <Table size="small">
            <TableHead><TableRow>
              <TableCell>Name</TableCell><TableCell>Folder</TableCell><TableCell align="right">Size</TableCell>
              <TableCell>Uploaded</TableCell><TableCell align="center">Shared with client</TableCell><TableCell align="right">Actions</TableCell>
            </TableRow></TableHead>
            <TableBody>{files.map(file =>
              <TableRow key={file.id}>
                <TableCell>{file.name}</TableCell>
                <TableCell><Chip size="small" label={file.folder} /></TableCell>
                <TableCell align="right">{formatSize(file.size)}</TableCell>
                <TableCell>{new Date(file.uploaded_at).toLocaleDateString()} · {file.uploaded_by}</TableCell>
                <TableCell align="center"><Switch size="small" checked={file.shared_with_client} onChange={() => void toggleShare(file)} /></TableCell>
                <TableCell align="right">
                  <IconButton size="small" component="a" href={planningApi.vaultDownloadUrl(householdId, file.id)} download aria-label="Download"><DownloadOutlinedIcon fontSize="small" /></IconButton>
                  <IconButton size="small" onClick={() => void remove(file)} aria-label="Delete"><DeleteOutlinedIcon fontSize="small" /></IconButton>
                </TableCell>
              </TableRow>)}</TableBody>
          </Table>}
    </CardContent></Card>
  </Box>;
}
