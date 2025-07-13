import React, { useState, useEffect } from 'react';
import { ThemeProvider } from '@mui/material/styles';
import { CssBaseline } from '@mui/material';
import Layout from './components/Layout';
import Dashboard from './components/Dashboard/Dashboard';
import Settings from './components/Settings/Settings';
import Trading from './components/Trading';
import { theme } from './utils/theme';
import { websocketService } from './services/websocket';
import { apiService } from './services/api';

function App() {
  const [currentPage, setCurrentPage] = useState('dashboard');
  const [systemStatus, setSystemStatus] = useState<'running' | 'stopped' | 'error'>('stopped');

  useEffect(() => {
    let isSubscribed = true;
    let statusInterval: NodeJS.Timeout;
    
    // WebSocket接続を開始（接続済みの場合はスキップされる）
    websocketService.connect();
    
    // システムステータスを定期的にチェック
    const checkStatus = async () => {
      if (isSubscribed) {
        await checkSystemStatus();
      }
    };
    
    checkStatus();
    statusInterval = setInterval(checkStatus, 10000);

    return () => {
      isSubscribed = false;
      clearInterval(statusInterval);
      // React.StrictModeでは2回呼ばれるため、disconnectは最後のクリーンアップでのみ実行
      // WebSocketサービス側で重複接続を防いでいるため、問題ない
    };
  }, []);

  const checkSystemStatus = async () => {
    try {
      const isHealthy = await apiService.healthCheck();
      setSystemStatus(isHealthy ? 'running' : 'error');
    } catch (error) {
      setSystemStatus('error');
    }
  };

  const renderPage = () => {
    switch (currentPage) {
      case 'dashboard':
        return <Dashboard />;
      case 'trading':
        return <Trading />;
      case 'analysis':
        return <div>分析画面（実装予定）</div>;
      case 'account':
        return <div>アカウント画面（実装予定）</div>;
      case 'settings':
        return <Settings />;
      default:
        return <Dashboard />;
    }
  };

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Layout 
        currentPage={currentPage} 
        onPageChange={setCurrentPage}
        systemStatus={systemStatus}
      >
        {renderPage()}
      </Layout>
    </ThemeProvider>
  );
}

export default App;
