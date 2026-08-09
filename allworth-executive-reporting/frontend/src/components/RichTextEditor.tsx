import { useEffect, useRef } from 'react';
import { Box, Divider, IconButton, MenuItem, Select, Tooltip } from '@mui/material';
import type { SelectChangeEvent } from '@mui/material';
import FormatBoldIcon from '@mui/icons-material/FormatBold';
import FormatItalicIcon from '@mui/icons-material/FormatItalic';
import FormatUnderlinedIcon from '@mui/icons-material/FormatUnderlined';
import FormatListBulletedIcon from '@mui/icons-material/FormatListBulleted';
import FormatListNumberedIcon from '@mui/icons-material/FormatListNumbered';
import FormatColorFillIcon from '@mui/icons-material/FormatColorFill';
import FormatColorTextIcon from '@mui/icons-material/FormatColorText';
import FormatClearIcon from '@mui/icons-material/FormatClear';

const FONTS = ['Arial', 'Georgia', 'Times New Roman', 'Courier New', 'Verdana', 'Tahoma'];

interface Props {
  value: string;
  onChange: (html: string) => void;
}

/**
 * Lightweight rich-text editor built on a contentEditable region and
 * document.execCommand. Emits HTML; the backend sanitizes it to a safe
 * allowlist before it becomes the email body.
 */
export default function RichTextEditor({ value, onChange }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const inited = useRef(false);
  const savedRange = useRef<Range | null>(null);

  // Seed the editor's HTML once so React re-renders don't clobber the caret.
  useEffect(() => {
    if (ref.current && !inited.current) {
      ref.current.innerHTML = value || '';
      inited.current = true;
    }
  }, [value]);

  const emit = () => onChange(ref.current?.innerHTML ?? '');

  const saveSelection = () => {
    const sel = window.getSelection();
    if (sel && sel.rangeCount && ref.current && ref.current.contains(sel.anchorNode)) {
      savedRange.current = sel.getRangeAt(0).cloneRange();
    }
  };

  const restoreSelection = () => {
    const sel = window.getSelection();
    if (savedRange.current && sel) {
      sel.removeAllRanges();
      sel.addRange(savedRange.current);
    }
  };

  const exec = (command: string, arg?: string) => {
    ref.current?.focus();
    restoreSelection();
    try {
      document.execCommand('styleWithCSS', false, 'true');
    } catch {
      /* not supported everywhere; inline styles still apply */
    }
    document.execCommand(command, false, arg);
    emit();
    saveSelection();
  };

  const onFont = (e: SelectChangeEvent) => {
    const font = e.target.value;
    if (font) exec('fontName', font);
  };

  return (
    <Box
      sx={{
        border: '1px solid rgba(23,61,103,0.23)',
        borderRadius: 1,
        '&:focus-within': { borderColor: 'primary.main', boxShadow: '0 0 0 1px rgba(62,113,183,0.6)' },
      }}
    >
      {/* Toolbar */}
      <Box
        sx={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: 0.25,
          p: 0.5,
          borderBottom: '1px solid rgba(23,61,103,0.12)',
        }}
        onMouseDown={(e) => e.preventDefault()} // keep the editor selection
      >
        <Select
          value=""
          onChange={onFont}
          displayEmpty
          size="small"
          variant="standard"
          disableUnderline
          renderValue={() => 'Font'}
          sx={{ minWidth: 78, fontSize: 13, mx: 0.5 }}
          MenuProps={{ disableAutoFocusItem: true }}
        >
          {FONTS.map((f) => (
            <MenuItem key={f} value={f} sx={{ fontFamily: f, fontSize: 14 }}>
              {f}
            </MenuItem>
          ))}
        </Select>
        <Divider orientation="vertical" flexItem sx={{ mx: 0.25 }} />
        <Tooltip title="Bold">
          <IconButton size="small" onClick={() => exec('bold')}>
            <FormatBoldIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Tooltip title="Italic">
          <IconButton size="small" onClick={() => exec('italic')}>
            <FormatItalicIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Tooltip title="Underline">
          <IconButton size="small" onClick={() => exec('underline')}>
            <FormatUnderlinedIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Divider orientation="vertical" flexItem sx={{ mx: 0.25 }} />
        <Tooltip title="Bulleted list">
          <IconButton size="small" onClick={() => exec('insertUnorderedList')}>
            <FormatListBulletedIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Tooltip title="Numbered list">
          <IconButton size="small" onClick={() => exec('insertOrderedList')}>
            <FormatListNumberedIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Divider orientation="vertical" flexItem sx={{ mx: 0.25 }} />
        <Tooltip title="Text color">
          <IconButton size="small" component="label">
            <FormatColorTextIcon fontSize="small" />
            <input
              type="color"
              defaultValue="#173d67"
              hidden
              onChange={(e) => exec('foreColor', e.target.value)}
            />
          </IconButton>
        </Tooltip>
        <Tooltip title="Highlight">
          <IconButton size="small" component="label">
            <FormatColorFillIcon fontSize="small" />
            <input
              type="color"
              defaultValue="#ffff00"
              hidden
              onChange={(e) => exec('hiliteColor', e.target.value)}
            />
          </IconButton>
        </Tooltip>
        <Divider orientation="vertical" flexItem sx={{ mx: 0.25 }} />
        <Tooltip title="Clear formatting">
          <IconButton size="small" onClick={() => exec('removeFormat')}>
            <FormatClearIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>

      {/* Editable area */}
      <Box
        ref={ref}
        contentEditable
        suppressContentEditableWarning
        onInput={() => {
          emit();
          saveSelection();
        }}
        onKeyUp={saveSelection}
        onMouseUp={saveSelection}
        onBlur={saveSelection}
        sx={{
          minHeight: 140,
          p: 1.5,
          fontSize: 14,
          lineHeight: 1.5,
          outline: 'none',
          fontFamily: 'Arial, sans-serif',
          '& p': { m: '0 0 8px' },
          '& ul, & ol': { m: '0 0 8px', pl: 3 },
        }}
      />
    </Box>
  );
}
