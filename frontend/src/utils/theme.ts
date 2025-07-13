import { createTheme } from '@mui/material/styles';

// カスタムテーマの設定
export const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#00D4AA', // Bybitのブランドカラー
      light: '#33DDB8',
      dark: '#00A076',
    },
    secondary: {
      main: '#FF6B35', // オレンジ系
      light: '#FF8A5B',
      dark: '#CC4A1A',
    },
    success: {
      main: '#00C851', // 利益の緑
      light: '#33D373',
      dark: '#00A041',
    },
    error: {
      main: '#FF4444', // 損失の赤
      light: '#FF6666',
      dark: '#CC2222',
    },
    warning: {
      main: '#FFB700', // 警告の黄色
      light: '#FFC733',
      dark: '#CC9200',
    },
    background: {
      default: '#0A0E1A', // ダークな背景
      paper: '#1A1F2E', // カードの背景
    },
    text: {
      primary: '#FFFFFF',
      secondary: '#B0BEC5',
    },
  },
  typography: {
    fontFamily: [
      'Noto Sans JP',
      'Roboto',
      '-apple-system',
      'BlinkMacSystemFont',
      'Arial',
      'sans-serif',
    ].join(','),
    h1: {
      fontSize: '2.5rem',
      fontWeight: 700,
    },
    h2: {
      fontSize: '2rem',
      fontWeight: 600,
    },
    h3: {
      fontSize: '1.5rem',
      fontWeight: 600,
    },
    h4: {
      fontSize: '1.25rem',
      fontWeight: 500,
    },
    h5: {
      fontSize: '1.125rem',
      fontWeight: 500,
    },
    h6: {
      fontSize: '1rem',
      fontWeight: 500,
    },
    body1: {
      fontSize: '0.875rem',
    },
    body2: {
      fontSize: '0.75rem',
    },
  },
  components: {
    MuiCard: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          borderRadius: '12px',
          border: '1px solid rgba(255, 255, 255, 0.1)',
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: '8px',
          textTransform: 'none',
          fontWeight: 500,
        },
      },
    },
    MuiTextField: {
      styleOverrides: {
        root: {
          '& .MuiOutlinedInput-root': {
            borderRadius: '8px',
          },
        },
      },
    },
  },
});