import React from 'react';
import { Box } from '@mui/material';

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
  /** Shared slug so the panel and its controlling tab reference each other. */
  idPrefix?: string;
}

export function TabPanel(props: TabPanelProps) {
  const { children, value, index, idPrefix = 'tab' } = props;
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`${idPrefix}-panel-${index}`}
      aria-labelledby={`${idPrefix}-${index}`}
      style={{ width: '100%' }}
    >
      {value === index && <Box sx={{ pt: 2 }}>{children}</Box>}
    </div>
  );
}
