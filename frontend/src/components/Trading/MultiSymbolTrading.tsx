import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  Chip,
  FormGroup,
  FormControlLabel,
  Checkbox,
  Alert,
  LinearProgress,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  IconButton,
  Tooltip,
  Badge,
  Stack,
  Divider,
  CircularProgress,
} from '@mui/material';
import {
  PlayArrow as PlayArrowIcon,
  Stop as StopIcon,
  Refresh as RefreshIcon,
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  Timer as TimerIcon,
  ShowChart as ShowChartIcon,
  AttachMoney as AttachMoneyIcon,
  CheckCircle as CheckCircleIcon,
  Cancel as CancelIcon,
  Warning as WarningIcon,
} from '@mui/icons-material';
import { apiService } from '../../services/api';

interface Signal {
  action: 'BUY' | 'SELL' | 'WAIT';
  confidence: number;
  entry_type: string;
  entry_price: number;
  stop_loss: number;
  take_profit: number[];
  risk_reward_ratio: number;
  position_size_multiplier?: number;
  reasons?: Array<{ factor: string; score: number; description: string }>;
  invalidation_price?: number;
  metadata?: Record<string, any>;
}

interface PortfolioSummary {
  summary: {
    total_positions: number;
    active_symbols: number;
    total_unrealized_pnl: number;
    total_realized_pnl: number;
    total_pnl: number;
    risk_utilization: number;
  };
  allocation: Record<string, {
    position_count: number;
    total_value: number;
    total_risk: number;
    percentage_of_portfolio: number;
  }>;
}

const MultiSymbolTrading: React.FC = () => {
  const [selectedSymbols, setSelectedSymbols] = useState<Set<string>>(new Set(['BTCUSDT', 'ETHUSDT']));
  const [signals, setSignals] = useState<Record<string, Signal | null>>({});
  const [loading, setLoading] = useState(false);
  const [autoTrading, setAutoTrading] = useState(false);
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
  const [recommendedSymbols, setRecommendedSymbols] = useState<string[]>([]);
  const [alerts, setAlerts] = useState<Array<{ message: string; type: 'success' | 'error' | 'warning' }>>([]);

  const allSymbols = [
    'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'XRPUSDT', 'SOLUSDT',
    'ADAUSDT', 'DOGEUSDT', 'DOTUSDT', 'LINKUSDT', 'MATICUSDT',
    'AVAXUSDT', 'UNIUSDT', 'ATOMUSDT', 'LTCUSDT', 'NEARUSDT',
    'FTMUSDT', 'ALGOUSDT', 'VETUSDT', 'ICPUSDT', 'FILUSDT',
  ];

  useEffect(() => {
    fetchPortfolio();
    fetchRecommendedSymbols();
    const interval = setInterval(() => {
      if (autoTrading && selectedSymbols.size > 0) {
        fetchMultiSymbolSignals();
      }
      fetchPortfolio();
    }, 30000); // 30秒ごと
    return () => clearInterval(interval);
  }, [autoTrading, selectedSymbols]);

  const addAlert = (message: string, type: 'success' | 'error' | 'warning') => {
    setAlerts((prev) => [...prev, { message, type }]);
    setTimeout(() => {
      setAlerts((prev) => prev.slice(1));
    }, 5000);
  };

  const fetchPortfolio = async () => {
    try {
      const response = await apiService.get<PortfolioSummary>('/api/trading/portfolio/summary');
      setPortfolio(response.data);
    } catch (error) {
      console.error('Failed to fetch portfolio:', error);
    }
  };

  const fetchRecommendedSymbols = async () => {
    try {
      const response = await apiService.get<{ recommended_symbols: string[] }>('/api/trading/portfolio/recommended-symbols');
      setRecommendedSymbols(response.data.recommended_symbols);
    } catch (error) {
      console.error('Failed to fetch recommended symbols:', error);
    }
  };

  const fetchMultiSymbolSignals = async () => {
    setLoading(true);
    try {
      const response = await apiService.post<{ signals: Record<string, Signal | null> }>('/api/trading/multi-symbol-signals', {
        symbols: Array.from(selectedSymbols),
      });
      setSignals(response.data.signals);
      
      // シグナルがあるシンボルをチェック
      const buySignals = Object.entries(response.data.signals).filter(
        ([_, signal]) => signal && signal.action === 'BUY' && signal.confidence > 0.65
      );
      const sellSignals = Object.entries(response.data.signals).filter(
        ([_, signal]) => signal && signal.action === 'SELL' && signal.confidence > 0.65
      );
      
      if (buySignals.length > 0 || sellSignals.length > 0) {
        addAlert(
          `新しいシグナル: BUY ${buySignals.length}件, SELL ${sellSignals.length}件`,
          'success'
        );
        
        // 自動取引が有効な場合、高信頼度のシグナルを自動実行
        if (autoTrading) {
          const highConfidenceSignals = [...buySignals, ...sellSignals].filter(
            ([_, signal]) => signal && signal.confidence > 0.7
          );
          
          for (const [symbol, signal] of highConfidenceSignals) {
            if (signal) {
              addAlert(`🤖 自動エントリー: ${symbol} ${signal.action} (信頼度: ${(signal.confidence * 100).toFixed(0)}%)`, 'success');
              await executeEntry(symbol, signal);
            }
          }
        }
      }
    } catch (error) {
      console.error('Failed to fetch signals:', error);
      addAlert('シグナルの取得に失敗しました', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleSymbolToggle = (symbol: string) => {
    const newSelected = new Set(selectedSymbols);
    if (newSelected.has(symbol)) {
      newSelected.delete(symbol);
    } else {
      newSelected.add(symbol);
    }
    setSelectedSymbols(newSelected);
  };

  const executeEntry = async (symbol: string, signal: Signal) => {
    console.log('Executing entry for', symbol, signal); // デバッグ用
    try {
      const response = await apiService.post('/api/trading/execute-entry', {
        symbol,
        signal: {
          ...signal,
          position_size_multiplier: signal.position_size_multiplier || 1.0,
          reasons: signal.reasons || [],
          invalidation_price: signal.invalidation_price || signal.stop_loss,
          metadata: signal.metadata || { timestamp: new Date().toISOString() }
        },
      });
      
      const data = response.data as { result: { executed: boolean; error?: string } };
      if (data.result.executed) {
        addAlert(`${symbol} エントリーが実行されました`, 'success');
        fetchPortfolio();
      } else {
        addAlert(`${symbol} エントリー失敗: ${data.result.error}`, 'error');
      }
    } catch (error) {
      console.error('Failed to execute entry:', error);
      addAlert('エントリーの実行に失敗しました', 'error');
    }
  };

  const getActionColor = (action: string) => {
    switch (action) {
      case 'BUY':
        return 'success';
      case 'SELL':
        return 'error';
      default:
        return 'default';
    }
  };

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.8) return '#4caf50';
    if (confidence >= 0.65) return '#ff9800';
    return '#f44336';
  };

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        🌐 複数通貨同時取引
      </Typography>

      {/* アラート表示 */}
      <Stack spacing={1} sx={{ mb: 3 }}>
        {alerts.map((alert, index) => (
          <Alert key={index} severity={alert.type}>
            {alert.message}
          </Alert>
        ))}
      </Stack>

      {/* ポートフォリオサマリー */}
      {portfolio && (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              📊 ポートフォリオ状況
            </Typography>
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2, 1fr)', md: 'repeat(4, 1fr)' }, gap: 2 }}>
              <Box>
                <Typography variant="body2" color="textSecondary">
                  アクティブポジション
                </Typography>
                <Typography variant="h6">
                  {portfolio.summary.total_positions}
                </Typography>
              </Box>
              <Box>
                <Typography variant="body2" color="textSecondary">
                  未実現損益
                </Typography>
                <Typography 
                  variant="h6" 
                  color={portfolio.summary.total_unrealized_pnl >= 0 ? 'success.main' : 'error.main'}
                >
                  ${portfolio.summary.total_unrealized_pnl.toFixed(2)}
                </Typography>
              </Box>
              <Box>
                <Typography variant="body2" color="textSecondary">
                  実現損益
                </Typography>
                <Typography 
                  variant="h6"
                  color={portfolio.summary.total_realized_pnl >= 0 ? 'success.main' : 'error.main'}
                >
                  ${portfolio.summary.total_realized_pnl.toFixed(2)}
                </Typography>
              </Box>
              <Box>
                <Typography variant="body2" color="textSecondary">
                  リスク使用率
                </Typography>
                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                  <LinearProgress
                    variant="determinate"
                    value={portfolio.summary.risk_utilization}
                    sx={{ flexGrow: 1, mr: 1, height: 8, borderRadius: 4 }}
                    color={portfolio.summary.risk_utilization > 80 ? 'error' : 'primary'}
                  />
                  <Typography variant="body2">
                    {portfolio.summary.risk_utilization.toFixed(0)}%
                  </Typography>
                </Box>
              </Box>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* 通貨選択 */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
            <Typography variant="h6">
              取引通貨選択
            </Typography>
            <Box>
              {recommendedSymbols.length > 0 && (
                <Chip
                  label={`推奨: ${recommendedSymbols.join(', ')}`}
                  color="info"
                  size="small"
                  sx={{ mr: 2 }}
                />
              )}
              <Typography variant="body2" component="span">
                選択中: {selectedSymbols.size} / 10
              </Typography>
            </Box>
          </Box>
          
          <FormGroup row>
            {allSymbols.map((symbol) => (
              <FormControlLabel
                key={symbol}
                control={
                  <Checkbox
                    checked={selectedSymbols.has(symbol)}
                    onChange={() => handleSymbolToggle(symbol)}
                    disabled={!selectedSymbols.has(symbol) && selectedSymbols.size >= 10}
                  />
                }
                label={
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    {symbol}
                    {recommendedSymbols.includes(symbol) && (
                      <Chip label="推奨" size="small" color="info" />
                    )}
                    {portfolio?.allocation[symbol] && (
                      <Badge 
                        badgeContent={portfolio.allocation[symbol].position_count} 
                        color="primary"
                      />
                    )}
                  </Box>
                }
              />
            ))}
          </FormGroup>
        </CardContent>
      </Card>

      {/* コントロール */}
      <Box sx={{ mb: 3 }}>
        <Stack direction="row" spacing={2}>
          <Button
            variant="contained"
            startIcon={loading ? <CircularProgress size={20} /> : <RefreshIcon />}
            onClick={fetchMultiSymbolSignals}
            disabled={loading || selectedSymbols.size === 0}
          >
            一括シグナル分析
          </Button>
          <Button
            variant={autoTrading ? 'contained' : 'outlined'}
            color={autoTrading ? 'error' : 'primary'}
            startIcon={autoTrading ? <StopIcon /> : <PlayArrowIcon />}
            onClick={() => setAutoTrading(!autoTrading)}
            disabled={selectedSymbols.size === 0}
          >
            {autoTrading ? '自動取引停止' : '自動取引開始'}
          </Button>
        </Stack>
      </Box>

      {/* シグナル一覧 */}
      {Object.keys(signals).length > 0 && (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              📡 エントリーシグナル
            </Typography>
            
            <TableContainer component={Paper} variant="outlined">
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>通貨ペア</TableCell>
                    <TableCell>シグナル</TableCell>
                    <TableCell>信頼度</TableCell>
                    <TableCell>エントリー価格</TableCell>
                    <TableCell>リスクリワード</TableCell>
                    <TableCell>アクション</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {Array.from(selectedSymbols).map((symbol) => {
                    const signal = signals[symbol];
                    if (!signal) return null;
                    
                    return (
                      <TableRow key={symbol}>
                        <TableCell>{symbol}</TableCell>
                        <TableCell>
                          <Chip
                            label={signal.action}
                            color={getActionColor(signal.action)}
                            size="small"
                            icon={signal.action === 'BUY' ? <TrendingUpIcon /> : signal.action === 'SELL' ? <TrendingDownIcon /> : <TimerIcon />}
                          />
                        </TableCell>
                        <TableCell>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <LinearProgress
                              variant="determinate"
                              value={signal.confidence * 100}
                              sx={{
                                width: 60,
                                height: 6,
                                borderRadius: 3,
                                '& .MuiLinearProgress-bar': {
                                  backgroundColor: getConfidenceColor(signal.confidence),
                                },
                              }}
                            />
                            <Typography variant="body2">
                              {(signal.confidence * 100).toFixed(0)}%
                            </Typography>
                          </Box>
                        </TableCell>
                        <TableCell>${signal.entry_price.toFixed(2)}</TableCell>
                        <TableCell>1:{signal.risk_reward_ratio.toFixed(1)}</TableCell>
                        <TableCell>
                          {signal.action !== 'WAIT' && signal.confidence > 0.65 ? (
                            <Button
                              size="small"
                              variant="contained"
                              color={signal.action === 'BUY' ? 'success' : 'error'}
                              onClick={() => executeEntry(symbol, signal)}
                              startIcon={<AttachMoneyIcon />}
                            >
                              実行
                            </Button>
                          ) : (
                            <Typography variant="body2" color="textSecondary">
                              待機
                            </Typography>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      )}
    </Box>
  );
};

export default MultiSymbolTrading;