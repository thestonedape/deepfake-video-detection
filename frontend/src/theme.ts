import { createTheme } from '@mui/material/styles';

const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: '#8b9cff' },
    secondary: { main: '#55d6b4' },
    error: { main: '#fb7185' },
    success: { main: '#34d399' },
    background: { default: '#0b1120', paper: '#111a2e' },
    text: { primary: '#f8fafc', secondary: '#9eabc2' },
  },
  shape: { borderRadius: 18 },
  typography: {
    fontFamily: ['Inter','ui-sans-serif','system-ui','-apple-system','BlinkMacSystemFont','Segoe UI','sans-serif'].join(','),
    h1: { fontSize: 'clamp(2.5rem, 6vw, 5rem)', fontWeight: 800, lineHeight: 0.98, letterSpacing: '-0.055em' },
    h2: { fontSize: '1.5rem', fontWeight: 750, letterSpacing: '-0.025em' },
    body1: { lineHeight: 1.7 },
    overline: { letterSpacing: '0.16em', fontWeight: 700 },
    button: { fontWeight: 700 },
  },
  components: {
    MuiCard: { styleOverrides: { root: { backgroundImage: 'none', backgroundColor: 'rgba(17,26,46,.86)', border: '1px solid rgba(148,163,184,.12)', boxShadow: '0 20px 70px rgba(0,0,0,.18)' } } },
    MuiButton: { styleOverrides: { root: { textTransform: 'none', borderRadius: 12, paddingInline: 20, paddingBlock: 10 } } },
    MuiLinearProgress: { styleOverrides: { root: { height: 10, borderRadius: 999, backgroundColor: 'rgba(148,163,184,.14)' }, bar: { borderRadius: 999 } } },
    MuiChip: { styleOverrides: { root: { fontWeight: 650 } } },
  },
});

export default theme;
