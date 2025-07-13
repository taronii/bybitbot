import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  Alert,
  Switch,
  FormControlLabel,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  CircularProgress,
  Chip,
  LinearProgress,
  Divider,
  Stack,
  Grid,
  Tooltip,
  IconButton,
} from '@mui/material';
import {
  FlashOn as FlashOnIcon,
  Speed as SpeedIcon,
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  Timer as TimerIcon,
  ShowChart as ShowChartIcon,
  Warning as WarningIcon,
  Settings as SettingsIcon,
  Refresh as RefreshIcon,
  PlayArrow as PlayArrowIcon,
  Stop as StopIcon,
} from '@mui/icons-material';
import { apiService } from '../../services/api';
import { wsClient } from '../../services/websocket';

interface ScalpingSignal {
  action: 'BUY' | 'SELL' | 'WAIT';
  confidence: number;
  entry_price: number;
  stop_loss: number;
  take_profit: number[];
  position_size_multiplier: number;
  speed_score: number;
  risk_reward_ratio: number;
  expected_duration_minutes: number;
  entry_reasons: Array<{
    factor: string;
    score: number;
    description: string;
  }>;
  invalidation_price: number;
  metadata: {
    pattern_type: string;
    timestamp: string;
    symbol: string;
  };
}

interface PerformanceSummary {
  overview: {
    total_trades: number;
    win_rate: number;
    total_profit_loss: number;
    net_profit: number;
    return_on_capital: number;
    current_capital: number;
  };
  risk_metrics: {
    max_drawdown: number;
    current_drawdown: number;
    sharpe_ratio: number;
    profit_factor: number;
  };
  trading_stats: {
    avg_profit_per_trade: number;
    avg_win: number;
    avg_loss: number;
    avg_holding_time_minutes: number;
    trades_per_hour: number;
  };
}

interface OptimizationSuggestion {
  category: string;
  priority: string;
  description: string;
  expected_improvement: number;
  confidence: number;
  difficulty: string;
}

const ScalpingMode: React.FC = () => {
  const [scalpingEnabled, setScalpingEnabled] = useState(false);
  const [autoTradeEnabled, setAutoTradeEnabled] = useState(false); // 自動取引フラグ
  const [loading, setLoading] = useState(false);
  const [signals, setSignals] = useState<Record<string, ScalpingSignal | null>>({});
  const [performance, setPerformance] = useState<PerformanceSummary | null>(null);
  const [suggestions, setSuggestions] = useState<OptimizationSuggestion[]>([]);
  const [selectedSymbols, setSelectedSymbols] = useState<Set<string>>(new Set(['BTCUSDT']));
  const [alerts, setAlerts] = useState<Array<{ message: string; type: 'success' | 'error' | 'warning' }>>([]);
  const [executedSignals, setExecutedSignals] = useState<Set<string>>(new Set()); // 実行済みシグナル追跡

  // スキャルピング対象シンボル（高流動性銘柄）
  const scalpingSymbols = [
    'BTCUSDT',
    'ETHUSDT', 
    'BNBUSDT',
    'XRPUSDT',
    'SOLUSDT',
    'ADAUSDT',
    'MATICUSDT',
    'DOTUSDT',
    'AVAXUSDT',
    'LINKUSDT'
  ];

  useEffect(() => {
    // WebSocket接続のセットアップ
    wsClient.connect();

    wsClient.on('scalping_signal', (data: any) => {
      if (selectedSymbols.has(data.symbol)) {
        setSignals(prev => ({ ...prev, [data.symbol]: data.signal }));
        if (data.signal.action !== 'WAIT' && data.signal.confidence > 0.75) {
          addAlert(`スキャルピングシグナル: ${data.signal.action} ${data.symbol} (信頼度: ${(data.signal.confidence * 100).toFixed(1)}%)`, 'success');
        }
      }
    });

    wsClient.on('scalping_performance', (data: any) => {
      setPerformance(data.performance);
    });

    return () => {
      wsClient.disconnect();
    };
  }, [selectedSymbols]);

  const addAlert = (message: string, type: 'success' | 'error' | 'warning') => {
    setAlerts((prev) => [...prev, { message, type }]);
    setTimeout(() => {
      setAlerts((prev) => prev.slice(1));
    }, 5000);
  };

  const toggleScalpingMode = async () => {
    try {
      const response = await apiService.post('/api/trading/scalping/toggle', {
        enabled: !scalpingEnabled
      });
      
      const data = response.data as { success: boolean };
      if (data.success) {
        setScalpingEnabled(!scalpingEnabled);
        addAlert(
          !scalpingEnabled ? 'スキャルピングモードが起動しました' : 'スキャルピングモードが停止しました',
          'success'
        );
      }
    } catch (error) {
      console.error('Failed to toggle scalping mode:', error);
      addAlert('スキャルピングモードの切り替えに失敗しました', 'error');
    }
  };

  const fetchScalpingSignals = async () => {
    setLoading(true);
    try {
      const promises = Array.from(selectedSymbols).map(async (symbol) => {
        const response = await apiService.get(`/api/trading/scalping/signal/${symbol}`);
        const data = response.data as { signal: ScalpingSignal };
        return { symbol, signal: data.signal };
      });
      
      const results = await Promise.all(promises);
      const newSignals: Record<string, ScalpingSignal> = {};
      
      results.forEach(({ symbol, signal }) => {
        newSignals[symbol] = signal;
      });
      
      setSignals(newSignals);
    } catch (error) {
      console.error('Failed to fetch scalping signals:', error);
      addAlert('スキャルピングシグナルの取得に失敗しました', 'error');
    } finally {
      setLoading(false);
    }
  };

  const fetchPerformance = async () => {
    try {
      const [perfResponse, suggestionsResponse] = await Promise.all([
        apiService.get('/api/trading/scalping/performance'),
        apiService.get('/api/trading/scalping/suggestions')
      ]);
      
      setPerformance(perfResponse.data as PerformanceSummary);
      setSuggestions(suggestionsResponse.data as OptimizationSuggestion[]);
    } catch (error) {
      console.error('Failed to fetch performance data:', error);
    }
  };

  const executeScalpingEntry = async (symbol: string, signal: ScalpingSignal) => {
    if (!signal || signal.action === 'WAIT') return;

    console.log('Executing scalping entry for', symbol, signal); // デバッグ用
    
    try {
      const response = await apiService.post('/api/trading/scalping/execute', {
        symbol: symbol,
        signal: signal  // シグナル全体を送信
      });
      
      console.log('Execute response:', response); // デバッグ用
      
      const data = response.data as { success: boolean; error?: string };
      if (data.success) {
        addAlert(`${symbol} スキャルピングエントリーが実行されました`, 'success');
        // 実行済みシグナルとして記録
        setExecutedSignals(prev => new Set(prev).add(`${symbol}-${signal.metadata.timestamp}`));
      } else {
        addAlert(`${symbol} エントリー失敗: ${data.error}`, 'error');
      }
    } catch (error) {
      console.error('Failed to execute scalping entry:', error);
      addAlert(`${symbol} スキャルピングエントリーの実行に失敗しました`, 'error');
    }
  };

  const getSpeedIcon = (speedScore: number) => {
    if (speedScore >= 0.9) return <FlashOnIcon color="error" />;
    if (speedScore >= 0.7) return <SpeedIcon color="warning" />;
    return <TimerIcon color="action" />;
  };

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.8) return '#4caf50';
    if (confidence >= 0.75) return '#ff9800';
    return '#f44336';
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'HIGH': return 'error';
      case 'MEDIUM': return 'warning';
      case 'LOW': return 'info';
      default: return 'default';
    }
  };

  useEffect(() => {
    fetchPerformance();
    const interval = setInterval(fetchPerformance, 30000); // 30秒ごと
    return () => clearInterval(interval);
  }, []);

  // 自動実行機能
  useEffect(() => {
    if (!autoTradeEnabled || !scalpingEnabled) return;

    const autoExecuteInterval = setInterval(() => {
      // 各シグナルをチェックして自動実行
      Object.entries(signals).forEach(([symbol, signal]) => {
        if (signal && signal.action !== 'WAIT' && signal.confidence >= 0.45) {
          const signalKey = `${symbol}-${signal.metadata.timestamp}`;
          // まだ実行されていないシグナルのみ実行
          if (!executedSignals.has(signalKey)) {
            console.log(`Auto-executing scalping for ${symbol}`, signal);
            executeScalpingEntry(symbol, signal);
          }
        }
      });
    }, 5000); // 5秒ごとにチェック

    return () => clearInterval(autoExecuteInterval);
  }, [autoTradeEnabled, scalpingEnabled, signals, executedSignals]);

  // シグナル自動取得
  useEffect(() => {
    if (!scalpingEnabled) return;

    // 初回取得
    fetchScalpingSignals();

    // 定期的に更新
    const signalInterval = setInterval(() => {
      fetchScalpingSignals();
    }, 10000); // 10秒ごとに短縮

    return () => clearInterval(signalInterval);
  }, [scalpingEnabled, selectedSymbols]);

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        ⚡ スキャルピングモード
      </Typography>

      {/* アラート表示 */}
      <Stack spacing={1} sx={{ mb: 3 }}>
        {alerts.map((alert, index) => (
          <Alert key={index} severity={alert.type}>
            {alert.message}
          </Alert>
        ))}
      </Stack>

      {/* モード制御 */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Box>
              <Typography variant="h6" gutterBottom>
                スキャルピングモード制御
              </Typography>
              <Typography variant="body2" color="textSecondary">
                高頻度取引（1日20-50回、勝率70%以上を目指す）
              </Typography>
            </Box>
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 1 }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={scalpingEnabled}
                    onChange={toggleScalpingMode}
                    color="primary"
                  />
                }
                label={scalpingEnabled ? '起動中' : '停止中'}
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={autoTradeEnabled}
                    onChange={(e) => setAutoTradeEnabled(e.target.checked)}
                    color="secondary"
                    disabled={!scalpingEnabled}
                  />
                }
                label={autoTradeEnabled ? '自動実行ON' : '自動実行OFF'}
              />
            </Box>
          </Box>
          {autoTradeEnabled && (
            <Alert severity="info" sx={{ mt: 2 }}>
              自動実行モード: 信頼度45%以上のシグナルを自動的に実行します
            </Alert>
          )}
        </CardContent>
      </Card>

      {/* シンボル選択 */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="subtitle1" gutterBottom>
          スキャルピング対象 - 選択中: {selectedSymbols.size}通貨 (最大5通貨)
        </Typography>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
          {scalpingSymbols.map((symbol) => (
            <Chip
              key={symbol}
              label={symbol}
              onClick={() => {
                const newSelected = new Set(selectedSymbols);
                if (newSelected.has(symbol)) {
                  newSelected.delete(symbol);
                } else if (newSelected.size < 5) {
                  newSelected.add(symbol);
                } else {
                  addAlert('最大5通貨まで選択可能です', 'warning');
                }
                setSelectedSymbols(newSelected);
              }}
              color={selectedSymbols.has(symbol) ? 'primary' : 'default'}
              variant={selectedSymbols.has(symbol) ? 'filled' : 'outlined'}
            />
          ))}
        </Box>
      </Box>

      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(2, 1fr)' }, gap: 3 }}>
        {/* スキャルピングシグナル */}
        <Card>
          <CardContent>
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
              <Typography variant="h6">
                高速エントリーシグナル
              </Typography>
              <Button
                variant="outlined"
                size="small"
                startIcon={loading ? <CircularProgress size={16} /> : <RefreshIcon />}
                onClick={fetchScalpingSignals}
                disabled={loading}
              >
                更新
              </Button>
            </Box>

            {Object.keys(signals).length > 0 ? (
              <TableContainer component={Paper} variant="outlined">
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>通貨ペア</TableCell>
                      <TableCell>シグナル</TableCell>
                      <TableCell>信頼度</TableCell>
                      <TableCell>スピード</TableCell>
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
                              color={signal.action === 'BUY' ? 'success' : signal.action === 'SELL' ? 'error' : 'default'}
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
                          <TableCell>
                            <Box sx={{ display: 'flex', alignItems: 'center' }}>
                              {getSpeedIcon(signal.speed_score)}
                              <Typography variant="body2" sx={{ ml: 1 }}>
                                {(signal.speed_score * 100).toFixed(0)}%
                              </Typography>
                            </Box>
                          </TableCell>
                          <TableCell>${signal.entry_price.toFixed(2)}</TableCell>
                          <TableCell>1:{signal.risk_reward_ratio.toFixed(1)}</TableCell>
                          <TableCell>
                            {signal.action !== 'WAIT' && signal.confidence >= 0.45 ? (
                              <Button
                                size="small"
                                variant="contained"
                                color={signal.action === 'BUY' ? 'success' : 'error'}
                                onClick={() => executeScalpingEntry(symbol, signal)}
                                disabled={!scalpingEnabled || autoTradeEnabled}
                                startIcon={<FlashOnIcon />}
                              >
                                {autoTradeEnabled ? '自動' : '実行'}
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
            ) : (
              <Typography color="textSecondary">
                シグナルを取得するには「更新」をクリックしてください
              </Typography>
            )}
          </CardContent>
        </Card>

        {/* パフォーマンス概要 */}
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              スキャルピング成績
            </Typography>

            {performance ? (
              <Box>
                <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2 }}>
                  <Box>
                    <Typography variant="body2" color="textSecondary">
                      総取引数
                    </Typography>
                    <Typography variant="h6">
                      {performance.overview.total_trades}
                    </Typography>
                  </Box>
                  <Box>
                    <Typography variant="body2" color="textSecondary">
                      勝率
                    </Typography>
                    <Typography variant="h6" color={performance.overview.win_rate >= 70 ? 'success.main' : 'warning.main'}>
                      {performance.overview.win_rate.toFixed(1)}%
                    </Typography>
                  </Box>
                  <Box>
                    <Typography variant="body2" color="textSecondary">
                      純利益
                    </Typography>
                    <Typography variant="h6" color={performance.overview.net_profit >= 0 ? 'success.main' : 'error.main'}>
                      ${performance.overview.net_profit.toFixed(2)}
                    </Typography>
                  </Box>
                  <Box>
                    <Typography variant="body2" color="textSecondary">
                      ROI
                    </Typography>
                    <Typography variant="h6" color={performance.overview.return_on_capital >= 0 ? 'success.main' : 'error.main'}>
                      {performance.overview.return_on_capital.toFixed(1)}%
                    </Typography>
                  </Box>
                </Box>

                  <Divider sx={{ my: 2 }} />

                  <Typography variant="subtitle2" gutterBottom>
                    リスク指標
                  </Typography>
                  <Box sx={{ mb: 1 }}>
                    <Typography variant="body2" color="textSecondary">
                      最大ドローダウン: {performance.risk_metrics.max_drawdown.toFixed(1)}%
                    </Typography>
                  </Box>
                  <Box sx={{ mb: 1 }}>
                    <Typography variant="body2" color="textSecondary">
                      プロフィットファクター: {performance.risk_metrics.profit_factor.toFixed(2)}
                    </Typography>
                  </Box>
                  <Box sx={{ mb: 1 }}>
                    <Typography variant="body2" color="textSecondary">
                      平均保有時間: {performance.trading_stats.avg_holding_time_minutes.toFixed(1)}分
                    </Typography>
                  </Box>
                  <Box>
                    <Typography variant="body2" color="textSecondary">
                      時間あたり取引数: {performance.trading_stats.trades_per_hour.toFixed(1)}回/時
                    </Typography>
                  </Box>
                </Box>
              ) : (
                <Typography color="textSecondary">
                  パフォーマンスデータを読み込み中...
                </Typography>
              )}
            </CardContent>
          </Card>
      </Box>

      {/* 最適化提案 */}
      {suggestions.length > 0 && (
        <Card sx={{ mt: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              🎯 最適化提案
            </Typography>
            
            <TableContainer component={Paper} variant="outlined">
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>優先度</TableCell>
                    <TableCell>カテゴリ</TableCell>
                    <TableCell>提案内容</TableCell>
                    <TableCell>期待改善</TableCell>
                    <TableCell>実装難易度</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {suggestions.map((suggestion, index) => (
                    <TableRow key={index}>
                      <TableCell>
                        <Chip
                          label={suggestion.priority}
                          color={getPriorityColor(suggestion.priority)}
                          size="small"
                        />
                      </TableCell>
                      <TableCell>{suggestion.category}</TableCell>
                      <TableCell>{suggestion.description}</TableCell>
                      <TableCell>
                        <Box sx={{ display: 'flex', alignItems: 'center' }}>
                          <TrendingUpIcon color="success" sx={{ mr: 0.5 }} />
                          {suggestion.expected_improvement.toFixed(1)}%
                        </Box>
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={suggestion.difficulty}
                          variant="outlined"
                          size="small"
                          color={suggestion.difficulty === 'EASY' ? 'success' : suggestion.difficulty === 'MEDIUM' ? 'warning' : 'error'}
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      )}
    </Box>
  );
};

export default ScalpingMode;