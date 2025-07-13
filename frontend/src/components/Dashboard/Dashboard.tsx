import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  useTheme,
  Skeleton,
  Alert,
  Button,
} from '@mui/material';
import {
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  AccountBalance as BalanceIcon,
  Analytics as AnalyticsIcon,
} from '@mui/icons-material';
import { DashboardData, Position, Trade } from '../../types';
import { apiService } from '../../services/api';
import AccountBalanceCard from './AccountBalanceCard';
import PnLCard from './PnLCard';
import PositionsTable from './PositionsTable';
import RecentTradesTable from './RecentTradesTable';

const Dashboard: React.FC = () => {
  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const theme = useTheme();

  useEffect(() => {
    fetchDashboardData();
    const interval = setInterval(fetchDashboardData, 5000);
    return () => clearInterval(interval);
  }, []);

  const fetchDashboardData = async () => {
    try {
      // 実際のAPIからデータを取得
      const response = await apiService.get<DashboardData>('/api/dashboard');
      setDashboardData(response.data);
      setError(null);
    } catch (err) {
      // エラーの場合は設定画面への案内を表示
      if (err instanceof Error && err.message.includes('400')) {
        setError('API設定が見つかりません。設定画面でAPIキーを設定してください。');
      } else {
        setError('データの取得に失敗しました。設定画面でAPI接続を確認してください。');
      }
      console.error('Failed to fetch dashboard data:', err);
      
      // エラー時はダミーデータを表示
      const dummyData: DashboardData = {
        accountBalance: 0,
        totalPnL: 0,
        todayPnL: 0,
        openPositions: [],
        recentTrades: [],
        systemStatus: 'error',
      };
      setDashboardData(dummyData);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <Box>
        <Box
          display="grid"
          gridTemplateColumns="repeat(auto-fit, minmax(250px, 1fr))"
          gap={3}
        >
          {[1, 2, 3, 4].map((item) => (
            <Card key={`skeleton-card-${item}`}>
              <CardContent>
                <Skeleton variant="rectangular" height={120} />
              </CardContent>
            </Card>
          ))}
        </Box>
      </Box>
    );
  }

  if (error) {
    return (
      <Box py={4}>
        <Alert 
          severity="error" 
          action={
            <Button 
              color="inherit" 
              size="small"
              onClick={() => window.location.href = '#settings'}
            >
              設定画面へ
            </Button>
          }
        >
          {error}
        </Alert>
      </Box>
    );
  }

  if (!dashboardData) {
    return null;
  }

  return (
    <Box>
      <Box
        display="grid"
        gridTemplateColumns={{
          xs: '1fr',
          sm: 'repeat(2, 1fr)',
          md: 'repeat(4, 1fr)',
        }}
        gap={3}
        mb={3}
      >
        <AccountBalanceCard balance={dashboardData.accountBalance} />
        <PnLCard
          title="総損益"
          value={dashboardData.totalPnL}
          icon={dashboardData.totalPnL >= 0 ? <TrendingUpIcon /> : <TrendingDownIcon />}
          isPositive={dashboardData.totalPnL >= 0}
        />
        <PnLCard
          title="本日の損益"
          value={dashboardData.todayPnL}
          icon={dashboardData.todayPnL >= 0 ? <TrendingUpIcon /> : <TrendingDownIcon />}
          isPositive={dashboardData.todayPnL >= 0}
        />
        <Card>
          <CardContent>
            <Box display="flex" alignItems="center" mb={1}>
              <AnalyticsIcon sx={{ mr: 1, color: theme.palette.primary.main }} />
              <Typography variant="h6" component="div">
                ポジション数
              </Typography>
            </Box>
            <Typography variant="h4" component="div" fontWeight="bold">
              {dashboardData.openPositions.length}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              アクティブなポジション
            </Typography>
          </CardContent>
        </Card>
      </Box>

      <Box mb={3}>
        <PositionsTable positions={dashboardData.openPositions} />
      </Box>

      <Box>
        <RecentTradesTable trades={dashboardData.recentTrades} />
      </Box>
    </Box>
  );
};

export default Dashboard;