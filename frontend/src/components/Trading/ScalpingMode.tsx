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

interface PositionWithLevels {
  position_id: string;
  symbol: string;
  direction: string;
  entry_price: number;
  quantity: number;
  signal_confidence: number;
  expected_duration: number;
  profit_targets: Array<{
    price: number;
    percentage: number;
    type: string;
    priority: number;
    description: string;
  }>;
  stop_levels: Array<{
    price: number;
    name: string;
    trigger_conditions: string[];
    priority: number;
    description: string;
  }>;
}

const ScalpingMode: React.FC = () => {
  const [scalpingEnabled, setScalpingEnabled] = useState(false);
  const [autoTradeEnabled, setAutoTradeEnabled] = useState(false); // 自動取引フラグ
  const [loading, setLoading] = useState(false);
  const [signals, setSignals] = useState<Record<string, ScalpingSignal | null>>({});
  const [performance, setPerformance] = useState<PerformanceSummary | null>(null);
  const [suggestions, setSuggestions] = useState<OptimizationSuggestion[]>([]);
  const [selectedSymbols, setSelectedSymbols] = useState<Set<string>>(new Set([
    'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 
    'ADAUSDT', 'MATICUSDT', 'DOTUSDT', 'AVAXUSDT', 'LINKUSDT',
    'LTCUSDT', 'ATOMUSDT', 'UNIUSDT', 'NEARUSDT', 'FTMUSDT'
  ]));
  const [alerts, setAlerts] = useState<Array<{ message: string; type: 'success' | 'error' | 'warning' }>>([]);
  const [executedSignals, setExecutedSignals] = useState<Set<string>>(new Set()); // 実行済みシグナル追跡
  const [activePositions, setActivePositions] = useState<PositionWithLevels[]>([]); // アクティブポジション
  const [isInitialized, setIsInitialized] = useState(false); // 初期化フラグ

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
    'LINKUSDT',
    'LTCUSDT',     // ライトコイン
    'ATOMUSDT',    // コスモス
    'UNIUSDT',     // ユニスワップ
    'NEARUSDT',    // ニア
    'FTMUSDT',     // ファントム
    'ALGOUSDT',    // アルゴランド
    'VETUSDT',     // ヴィチェーン
    'ICPUSDT',     // インターネットコンピュータ
    'FILUSDT',     // ファイルコイン
    'DOGEUSDT'     // ドージコイン
  ];

  // 初期化時にサーバーの状態を取得
  useEffect(() => {
    const initializeScalpingMode = async () => {
      if (!isInitialized) {
        try {
          console.log('Initializing scalping mode...');
          const response = await apiService.get('/api/trading/scalping/status');
          const statusData = response.data as any;
          
          if (statusData.mode_status) {
            const isScalpingActive = statusData.mode_status.modes?.scalping?.enabled || false;
            console.log('Initial scalping mode status from server:', isScalpingActive);
            setScalpingEnabled(isScalpingActive);
            
            // 初期状態がtrueの場合、フラグを立てるだけ
            // 実際のデータ取得は別のuseEffectで行う
          }
          setIsInitialized(true);
        } catch (error) {
          console.error('Failed to initialize scalping mode:', error);
          setIsInitialized(true); // エラーでも初期化済みとする
        }
      }
    };
    
    initializeScalpingMode();
  }, [isInitialized]);

  useEffect(() => {
    // WebSocket接続のセットアップ
    try {
      console.log('Setting up WebSocket connection for scalping mode...');
      wsClient.connect();

      const signalHandler = (data: any) => {
        console.log('Received scalping signal:', data);
        if (selectedSymbols.has(data.symbol)) {
          setSignals(prev => ({ ...prev, [data.symbol]: data.signal }));
          if (data.signal.action !== 'WAIT' && data.signal.confidence > 0.75) {
            addAlert(`スキャルピングシグナル: ${data.signal.action} ${data.symbol} (信頼度: ${(data.signal.confidence * 100).toFixed(1)}%)`, 'success');
          }
        }
      };

      const performanceHandler = (data: any) => {
        console.log('Received scalping performance:', data);
        setPerformance(data.performance);
      };

      wsClient.on('scalping_signal', signalHandler);
      wsClient.on('scalping_performance', performanceHandler);

      return () => {
        console.log('Cleaning up WebSocket handlers...');
        wsClient.off('scalping_signal', signalHandler);
        wsClient.off('scalping_performance', performanceHandler);
        // WebSocket接続は維持（他のコンポーネントでも使用するため）
      };
    } catch (error) {
      console.error('WebSocket setup error:', error);
      addAlert('WebSocket接続の設定に失敗しました', 'error');
    }
  }, [selectedSymbols]);

  const addAlert = (message: string, type: 'success' | 'error' | 'warning') => {
    setAlerts((prev) => [...prev, { message, type }]);
    setTimeout(() => {
      setAlerts((prev) => prev.slice(1));
    }, 5000);
  };

  const toggleScalpingMode = async () => {
    console.log('=== toggleScalpingMode called ===');
    console.log('Current scalpingEnabled:', scalpingEnabled);
    console.log('Attempting to set to:', !scalpingEnabled);
    
    try {
      const response = await apiService.post('/api/trading/scalping/toggle', {
        enabled: !scalpingEnabled
      });
      
      console.log('Toggle API response:', response);
      const data = response.data as { success: boolean };
      
      if (data.success) {
        const newEnabled = !scalpingEnabled;
        console.log('Setting scalpingEnabled to:', newEnabled);
        setScalpingEnabled(newEnabled);
        
        addAlert(
          newEnabled ? 'スキャルピングモードが起動しました' : 'スキャルピングモードが停止しました',
          'success'
        );
        
        // スキャルピングモードが有効になったらシグナルを取得
        if (newEnabled) {
          // WebSocket接続を確立（既に接続済みの場合は何もしない）
          if (!wsClient.isConnected()) {
            console.log('WebSocket not connected, attempting to connect...');
            wsClient.connect();
          }
          
          console.log('Scheduling signal fetch in 1 second...');
          setTimeout(() => {
            console.log('Fetching signals and performance...');
            fetchScalpingSignals();
            fetchPerformance();
          }, 1000);
        }
      } else {
        console.error('Toggle API returned success: false', data);
      }
    } catch (error) {
      console.error('Failed to toggle scalping mode:', error);
      addAlert('スキャルピングモードの切り替えに失敗しました', 'error');
      // エラーが発生してもモードの状態は維持
    }
  };

  const fetchScalpingSignals = async () => {
    setLoading(true);
    try {
      const promises = Array.from(selectedSymbols).map(async (symbol) => {
        try {
          const response = await apiService.get(`/api/trading/scalping/signal/${symbol}`);
          const data = response.data as { signal: ScalpingSignal };
          console.log(`Signal for ${symbol}:`, data); // デバッグログ
          return { symbol, signal: data.signal };
        } catch (error) {
          console.error(`Failed to fetch signal for ${symbol}:`, error);
          return { symbol, signal: null };
        }
      });
      
      const results = await Promise.all(promises);
      const newSignals: Record<string, ScalpingSignal | null> = {};
      
      results.forEach(({ symbol, signal }) => {
        if (signal) {
          newSignals[symbol] = signal;
        }
      });
      
      console.log('All signals:', newSignals); // デバッグログ
      setSignals(newSignals);
    } catch (error) {
      console.error('Failed to fetch scalping signals:', error);
      addAlert('スキャルピングシグナルの取得に失敗しました', 'error');
    } finally {
      setLoading(false);
    }
  };

  const fetchPerformance = async () => {
    console.log('=== fetchPerformance called ===');
    console.log('Current scalpingEnabled state:', scalpingEnabled);
    
    try {
      const [perfResponse, suggestionsResponse, statusResponse] = await Promise.all([
        apiService.get('/api/trading/scalping/performance'),
        apiService.get('/api/trading/scalping/suggestions'),
        apiService.get('/api/trading/scalping/status')
      ]);
      
      console.log('Status response:', statusResponse.data);
      
      setPerformance(perfResponse.data as PerformanceSummary);
      setSuggestions(suggestionsResponse.data as OptimizationSuggestion[]);
      
      // アクティブポジションを更新
      const statusData = statusResponse.data as any;
      setActivePositions(statusData.active_positions || []);
      
      // モードの状態をチェックして同期
      // 注意: サーバー側の状態は参考程度に留め、フロントエンドの状態を優先する
      if (statusData.mode_status) {
        console.log('Full mode_status:', statusData.mode_status);
        const isScalpingActive = statusData.mode_status.active_modes?.includes('SCALPING') || 
                                 statusData.mode_status.active_modes?.includes('scalping') || false;
        console.log('Server scalping mode status:', isScalpingActive, 'Local status:', scalpingEnabled);
        
        // デバッグ: mode_statusの詳細を確認
        if (statusData.mode_status.modes) {
          console.log('Scalping mode details:', statusData.mode_status.modes.scalping);
        }
        
        // サーバーとローカルの状態が異なる場合は警告のみ
        if (isScalpingActive !== scalpingEnabled) {
          console.warn('Mode status mismatch - Server:', isScalpingActive, 'Local:', scalpingEnabled);
          console.warn('This should NOT change the local state');
          // 自動同期は行わない（ユーザーの操作を優先）
        }
      }
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
    // 初回のパフォーマンスデータ取得
    fetchPerformance();
    
    // スキャルピングモードが有効な場合のみ定期更新
    let interval: NodeJS.Timeout | null = null;
    if (scalpingEnabled) {
      interval = setInterval(fetchPerformance, 30000); // 30秒ごと
    }
    
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [scalpingEnabled]); // scalpingEnabledの変更を監視

  // スキャルピングモードが有効になったときの処理
  useEffect(() => {
    console.log('=== useEffect [scalpingEnabled] triggered ===');
    console.log('ScalpingMode enabled state changed to:', scalpingEnabled);
    
    if (scalpingEnabled) {
      console.log('Scalping mode is ENABLED, setting up timers...');
      // 少し遅延させてからシグナルを取得
      const timer = setTimeout(() => {
        console.log('Initial fetch timer fired');
        fetchScalpingSignals();
        fetchPerformance();
      }, 1000);
      
      // 定期的な更新を設定
      const signalInterval = setInterval(() => {
        console.log('Signal interval timer fired');
        fetchScalpingSignals();
      }, 10000); // 10秒ごと
      
      return () => {
        console.log('Cleaning up scalping mode timers');
        clearTimeout(timer);
        clearInterval(signalInterval);
      };
    } else {
      console.log('Scalping mode is DISABLED');
    }
  }, [scalpingEnabled]);

  // 自動実行機能
  useEffect(() => {
    if (!autoTradeEnabled || !scalpingEnabled) return;

    const autoExecuteInterval = setInterval(() => {
      // 各シグナルをチェックして自動実行
      Object.entries(signals).forEach(([symbol, signal]) => {
        if (signal && signal.action !== 'WAIT' && signal.confidence >= 0.35) { // 閾値を0.45から0.35に下げて、より多くのエントリー機会を確保
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

  // この重複したuseEffectを削除（既に上で同じ処理を行っている）
  // 削除理由: 上記のuseEffect（行383-410）と重複しており、
  // 複数回fetchPerformanceが呼ばれる原因となっている

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
                      <TableCell>利確/損切り</TableCell>
                      <TableCell>リスクリワード</TableCell>
                      <TableCell>アクション</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {Array.from(selectedSymbols).map((symbol) => {
                      const signal = signals[symbol];
                      if (!signal) {
                        // シグナルがない場合は待機状態を表示
                        return (
                          <TableRow key={symbol}>
                            <TableCell>{symbol}</TableCell>
                            <TableCell>
                              <Chip label="WAIT" color="default" size="small" icon={<TimerIcon />} />
                            </TableCell>
                            <TableCell>-</TableCell>
                            <TableCell>-</TableCell>
                            <TableCell>-</TableCell>
                            <TableCell>-</TableCell>
                            <TableCell>-</TableCell>
                            <TableCell>
                              <Typography variant="body2" color="textSecondary">
                                データ取得中...
                              </Typography>
                            </TableCell>
                          </TableRow>
                        );
                      }
                      
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
                                value={(signal.confidence || 0) * 100}
                                sx={{
                                  width: 60,
                                  height: 6,
                                  borderRadius: 3,
                                  '& .MuiLinearProgress-bar': {
                                    backgroundColor: getConfidenceColor(signal.confidence || 0),
                                  },
                                }}
                              />
                              <Typography variant="body2">
                                {((signal.confidence || 0) * 100).toFixed(0)}%
                              </Typography>
                            </Box>
                          </TableCell>
                          <TableCell>
                            <Box sx={{ display: 'flex', alignItems: 'center' }}>
                              {getSpeedIcon(signal.speed_score || 0)}
                              <Typography variant="body2" sx={{ ml: 1 }}>
                                {((signal.speed_score || 0) * 100).toFixed(0)}%
                              </Typography>
                            </Box>
                          </TableCell>
                          <TableCell>${signal.entry_price ? signal.entry_price.toFixed(2) : '0.00'}</TableCell>
                          <TableCell>
                            <Box sx={{ fontSize: '0.75rem' }}>
                              <Typography variant="caption" sx={{ color: 'success.main', display: 'block' }}>
                                利確: ${signal.take_profit && signal.take_profit.length > 0 && signal.take_profit[0] ? signal.take_profit[0].toFixed(2) : '---'}
                              </Typography>
                              <Typography variant="caption" sx={{ color: 'error.main', display: 'block' }}>
                                損切: ${signal.stop_loss ? signal.stop_loss.toFixed(2) : '---'}
                              </Typography>
                            </Box>
                          </TableCell>
                          <TableCell>1:{signal.risk_reward_ratio ? signal.risk_reward_ratio.toFixed(1) : '0.0'}</TableCell>
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

        {/* アクティブポジション */}
        {activePositions.length > 0 && (
          <Card>
            <CardContent>
              <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                <Typography variant="h6">
                  アクティブポジション
                </Typography>
                <Box>
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={async () => {
                      try {
                        const response = await fetch(`${process.env.REACT_APP_API_URL || 'https://bybitbot-backend-elvv4omjba-an.a.run.app'}/api/trading/scalping/sync-positions`, {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' }
                        });
                        if (response.ok) {
                          await fetchPerformance();
                          alert('ポジション情報を同期しました');
                        }
                      } catch (error) {
                        console.error('Sync failed:', error);
                      }
                    }}
                    sx={{ mr: 1 }}
                  >
                    同期
                  </Button>
                  <Button
                    size="small"
                    variant="outlined"
                    color="error"
                    onClick={async () => {
                      if (window.confirm('すべてのポジション情報をクリアしますか？')) {
                        try {
                          const response = await fetch(`${process.env.REACT_APP_API_URL || 'https://bybitbot-backend-elvv4omjba-an.a.run.app'}/api/trading/scalping/clear-positions`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' }
                          });
                          if (response.ok) {
                            await fetchPerformance();
                            alert('ポジション情報をクリアしました');
                          }
                        } catch (error) {
                          console.error('Clear failed:', error);
                        }
                      }
                    }}
                  >
                    クリア
                  </Button>
                </Box>
              </Box>
              
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>シンボル</TableCell>
                      <TableCell>方向</TableCell>
                      <TableCell>エントリー価格</TableCell>
                      <TableCell>数量</TableCell>
                      <TableCell>利確レベル</TableCell>
                      <TableCell>損切りレベル</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {activePositions.map((position) => (
                      <TableRow key={position.position_id}>
                        <TableCell>{position.symbol}</TableCell>
                        <TableCell>
                          <Chip
                            label={position.direction}
                            color={position.direction === 'BUY' ? 'success' : 'error'}
                            size="small"
                          />
                        </TableCell>
                        <TableCell>${position.entry_price ? position.entry_price.toFixed(2) : '0.00'}</TableCell>
                        <TableCell>{position.quantity ? position.quantity.toFixed(4) : '0.0000'}</TableCell>
                        <TableCell>
                          <Box>
                            {position.profit_targets && position.profit_targets.map((target, idx) => (
                              <Typography key={idx} variant="caption" display="block" sx={{ color: 'success.main' }}>
                                {target.description || '---'}
                              </Typography>
                            ))}
                          </Box>
                        </TableCell>
                        <TableCell>
                          <Box>
                            {position.stop_levels && position.stop_levels.map((stop, idx) => (
                              <Typography key={idx} variant="caption" display="block" sx={{ color: 'error.main' }}>
                                {stop.description || '---'}
                              </Typography>
                            ))}
                          </Box>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        )}

        {/* パフォーマンス概要 */}
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              スキャルピング成績
            </Typography>

            {performance && performance.overview ? (
              <Box>
                <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2 }}>
                  <Box>
                    <Typography variant="body2" color="textSecondary">
                      総取引数
                    </Typography>
                    <Typography variant="h6">
                      {performance.overview.total_trades || 0}
                    </Typography>
                  </Box>
                  <Box>
                    <Typography variant="body2" color="textSecondary">
                      勝率
                    </Typography>
                    <Typography variant="h6" color={(performance.overview.win_rate || 0) >= 70 ? 'success.main' : 'warning.main'}>
                      {(performance.overview.win_rate || 0).toFixed(1)}%
                    </Typography>
                  </Box>
                  <Box>
                    <Typography variant="body2" color="textSecondary">
                      純利益
                    </Typography>
                    <Typography variant="h6" color={(performance.overview.net_profit || 0) >= 0 ? 'success.main' : 'error.main'}>
                      ${(performance.overview.net_profit || 0).toFixed(2)}
                    </Typography>
                  </Box>
                  <Box>
                    <Typography variant="body2" color="textSecondary">
                      ROI
                    </Typography>
                    <Typography variant="h6" color={(performance.overview.return_on_capital || 0) >= 0 ? 'success.main' : 'error.main'}>
                      {(performance.overview.return_on_capital || 0).toFixed(1)}%
                    </Typography>
                  </Box>
                </Box>

                  <Divider sx={{ my: 2 }} />

                  <Typography variant="subtitle2" gutterBottom>
                    リスク指標
                  </Typography>
                  <Box sx={{ mb: 1 }}>
                    <Typography variant="body2" color="textSecondary">
                      最大ドローダウン: {(performance.risk_metrics?.max_drawdown || 0).toFixed(1)}%
                    </Typography>
                  </Box>
                  <Box sx={{ mb: 1 }}>
                    <Typography variant="body2" color="textSecondary">
                      プロフィットファクター: {(performance.risk_metrics?.profit_factor || 0).toFixed(2)}
                    </Typography>
                  </Box>
                  <Box sx={{ mb: 1 }}>
                    <Typography variant="body2" color="textSecondary">
                      平均保有時間: {(performance.trading_stats?.avg_holding_time_minutes || 0).toFixed(1)}分
                    </Typography>
                  </Box>
                  <Box>
                    <Typography variant="body2" color="textSecondary">
                      時間あたり取引数: {(performance.trading_stats?.trades_per_hour || 0).toFixed(1)}回/時
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