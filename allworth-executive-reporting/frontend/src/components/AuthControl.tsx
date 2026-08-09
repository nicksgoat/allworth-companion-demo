import { useEffect, useMemo, useState } from 'react';
import { Avatar, Box, Button, CircularProgress, Tooltip, Typography } from '@mui/material';
import LoginIcon from '@mui/icons-material/Login';
import LogoutIcon from '@mui/icons-material/Logout';
import { resolveUserProfile, signIn, signOut } from '../services/auth';
import type { AuthUserProfile } from '../services/auth';

function initialsFor(profile: AuthUserProfile | null) {
  const label = profile?.name || profile?.email || '';
  const parts = label.split(/[\s.@_-]+/).filter(Boolean);
  return parts.slice(0, 2).map(part => part[0]?.toUpperCase()).join('') || 'AW';
}

export default function AuthControl() {
  const [profile, setProfile] = useState<AuthUserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    void resolveUserProfile()
      .then(data => {
        if (active) setProfile(data);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const label = useMemo(() => {
    if (!profile?.authenticated) return profile?.ssoConfigured ? 'Sign in' : 'Local access';
    return profile.email || profile.name || 'Signed in';
  }, [profile]);

  if (loading) {
    return (
      <Box className="aw-auth-control aw-auth-control--loading">
        <CircularProgress size={16} sx={{ color: 'rgba(255,255,255,0.72)' }} />
      </Box>
    );
  }

  if (!profile?.authenticated) {
    return (
      <Tooltip
        title={profile?.ssoConfigured && !profile.authAvailable ? 'App Service Authentication is not available on this host.' : ''}
        arrow
      >
        <span>
          <Button
            size="small"
            variant="outlined"
            startIcon={profile?.ssoConfigured ? <LoginIcon fontSize="small" /> : undefined}
            onClick={profile?.ssoConfigured ? signIn : undefined}
            disabled={!profile?.ssoConfigured}
            className="aw-auth-button"
          >
            {label}
          </Button>
        </span>
      </Tooltip>
    );
  }

  return (
    <Box className="aw-auth-control">
      <Avatar className="aw-auth-avatar">{initialsFor(profile)}</Avatar>
      <Box className="aw-auth-copy">
        <Typography className="aw-auth-label">Signed in</Typography>
        <Typography className="aw-auth-name">{label}</Typography>
      </Box>
      <Tooltip title="Sign out" arrow>
        <Button
          size="small"
          variant="text"
          onClick={signOut}
          className="aw-auth-logout"
          aria-label="Sign out"
        >
          <LogoutIcon fontSize="small" />
        </Button>
      </Tooltip>
    </Box>
  );
}
