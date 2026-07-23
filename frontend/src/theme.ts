import { createTheme } from '@mui/material/styles';

const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#7c8cf8',
    },
    secondary: {
      main: '#4dd0b1',
    },
    error: {
      main: '#f87171',
    },
    success: {
      main: '#34d399',
    },
    background: {
      default: '#0b1120',
      paper: '#121a2e',
    },
  },
  shape: {
    borderRadius: 14,
  },
  typography: {
    fontFamily: [
      '-apple-system',
      'BlinkMacSystemFont',
      '"Segoe UI"',
      'Roboto',
      '"Helvetica Neue"',
      'Arial',
      'sans-serif',
    ].join(','),
    h1: {
      fontSize: '2.4rem',
      fontWeight: 700,
      lineHeight: 1.2,
    },
    h2: {
      fontSize: '1.4rem',
      fontWeight: 600,
    },
    overline: {
      letterSpacing: '0.18em',
      fontWeight: 600,
    },
  },
  components: {
    MuiCard: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          border: '1px solid rgba(148, 163, 184, 0.12)',
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          fontWeight: 600,
          paddingInline: 24,
          paddingBlock: 10,
        },
      },
    },
    MuiLinearProgress: {
      styleOverrides: {
        root: {
          height: 10,
          borderRadius: 5,
          backgroundColor: 'rgba(148, 163, 184, 0.15)',
        },
        bar: {
          borderRadius: 5,
        },
      },
    },
  },
});

export default theme;
