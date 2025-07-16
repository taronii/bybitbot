import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  Alert,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  CircularProgress,
  IconButton,
  Tooltip,
  LinearProgress,
  Divider,
  Stack,
  Tabs,
  Tab,
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
  Warning as WarningIcon,
} from '@mui/icons-material';
import { apiService } from '../../services/api';
import { wsClient } from '../../services/websocket';
import ScalpingMode from './ScalpingMode';
import MultiSymbolTrading from './MultiSymbolTrading';
import ConservativeMode from './ConservativeMode';

interface EntrySignal {
  action: 'BUY' | 'SELL' | 'WAIT';
  confidence: number;
  entry_type: string;
  entry_price: number;
  position_size_multiplier: number;
  reasons: Array<{
    factor: string;
    score: number;
    description: string;
  }>;
  invalidation_price: number;
  stop_loss: number;
  take_profit: number[];
  metadata: {
    regime: string;
    volatility: string;
    liquidity: number;
    timestamp: string;
    scores: Record<string, number>;
  };
}

interface MarketAnalysis {
  regime_analysis: {
    regime: string;
    trend_direction: number;
    trend_strength: number;
    volatility_level: string;
    liquidity_score: number;
    confidence: number;
  };
  mtf_analysis: any;
  smart_money_analysis: {
    direction: string;
    order_flow_imbalance: number;
    confidence: number;
    large_orders_count: number;
  };
  pattern_analysis: {
    detected_patterns: Array<{
      name: string;
      type: string;
      confidence: number;
      expected_move: number;
    }>;
    ml_prediction: {
      direction: string;
      confidence: number;
      expected_return: number;
    };
    trading_bias: string;
  };
}

const Trading: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [signals, setSignals] = useState<Record<string, EntrySignal | null>>({});
  const [analysis, setAnalysis] = useState<MarketAnalysis | null>(null);
  const [selectedSymbols, setSelectedSymbols] = useState<Set<string>>(new Set(['BTCUSDT']));
  const [autoTrading, setAutoTrading] = useState(false);
  const [alerts, setAlerts] = useState<Array<{ id: string; message: string; type: 'success' | 'error' | 'warning' }>>([]);
  const [currentTab, setCurrentTab] = useState(0);

  // 人気のトレーディングペア（拡張版）
  const symbols = [
    // メジャー通貨
    'BTCUSDT',
    'ETHUSDT',
    // 主要アルトコイン
    'BNBUSDT',
    'XRPUSDT',
    'SOLUSDT',
    'ADAUSDT',
    'DOGEUSDT',
    'DOTUSDT',
    'LINKUSDT',
    'MATICUSDT',
    // 追加通貨（流動性の高い人気銘柄）
    'AVAXUSDT',
    'UNIUSDT',
    'ATOMUSDT',
    'LTCUSDT',
    'NEARUSDT',
    'FTMUSDT',
    'ALGOUSDT',
    'VETUSDT',
    'ICPUSDT',
    'FILUSDT',
  ];

  // 関数定義を先に行う
  const addAlert = useCallback((message: string, type: 'success' | 'error' | 'warning') => {
    const id = `${Date.now()}-${Math.random()}`;
    setAlerts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setAlerts((prev) => prev.filter(alert => alert.id !== id));
    }, 5000);
  }, []);

  const executeEntry = useCallback(async (symbol: string, signal: EntrySignal) => {
    if (!signal || signal.action === 'WAIT') return;

    console.log('Executing entry for', symbol, signal); // デバッグ用
    
    // シグナルの形式を確認
    const signalData = {
      action: signal.action,
      confidence: signal.confidence,
      entry_type: signal.entry_type,
      entry_price: signal.entry_price,
      position_size_multiplier: signal.position_size_multiplier,
      reasons: signal.reasons,
      invalidation_price: signal.invalidation_price,
      stop_loss: signal.stop_loss,
      take_profit: signal.take_profit,
      metadata: signal.metadata
    };
    
    console.log('Sending signal data:', signalData); // デバッグ用
    
    try {
      const response = await apiService.post('/api/trading/execute-entry', {
        symbol: symbol,
        signal: signalData,
      });
      
      console.log('Execute response:', response); // デバッグ用
      
      const data = response.data as { result: { executed: boolean; error?: string } };
      if (data.result.executed) {
        addAlert(`${symbol} エントリーが正常に実行されました`, 'success');
      } else {
        addAlert(`${symbol} エントリー失敗: ${data.result.error}`, 'error');
      }
    } catch (error) {
      console.error('Failed to execute entry:', error);
      if (error instanceof Error) {
        addAlert(`${symbol} エントリーの実行に失敗しました: ${error.message}`, 'error');
      } else {
        addAlert(`${symbol} エントリーの実行に失敗しました`, 'error');
      }
    }
  }, [addAlert]);

  const fetchSignals = useCallback(async (isAutoCheck = false) => {
    if (!isAutoCheck) {
      setLoading(true);
    }
    
    try {
      const promises = Array.from(selectedSymbols).map(async (symbol) => {
        const response = await apiService.get<{ signal: EntrySignal }>(`/api/trading/entry-signal/${symbol}`);
        return { symbol, signal: response.data.signal };
      });
      
      const results = await Promise.all(promises);
      const newSignals: Record<string, EntrySignal> = {};
      
      results.forEach(({ symbol, signal }) => {
        newSignals[symbol] = signal;
        
        // 自動売買モードで、強いシグナルの場合は自動実行
        if (autoTrading && signal.action !== 'WAIT' && signal.confidence > 0.7) {
          addAlert(`🤖 自動エントリー: ${symbol} ${signal.action} (信頼度: ${(signal.confidence * 100).toFixed(0)}%)`, 'success');
          executeEntry(symbol, signal);
        }
      });
      
      setSignals(newSignals);
    } catch (error) {
      console.error('Failed to fetch signals:', error);
      if (!isAutoCheck) {
        addAlert('シグナルの取得に失敗しました', 'error');
      }
    } finally {
      if (!isAutoCheck) {
        setLoading(false);
      }
    }
  }, [selectedSymbols, autoTrading, executeEntry, addAlert]);

  const fetchAnalysis = async () => {
    try {
      // 最初に選択された通貨の分析を取得
      const firstSymbol = Array.from(selectedSymbols)[0];
      if (!firstSymbol) return;
      const response = await apiService.get(`/api/trading/market-analysis/${firstSymbol}`);
      setAnalysis(response.data as MarketAnalysis);
    } catch (error) {
      console.error('Failed to fetch analysis:', error);
    }
  };

  // WebSocket接続のセットアップ
  useEffect(() => {
    // 一度だけ接続
    if (!wsClient.isConnected()) {
      wsClient.connect();
    }

    wsClient.on('entry_signal', (data: any) => {
      if (selectedSymbols.has(data.symbol)) {
        setSignals(prev => ({ ...prev, [data.symbol]: data.signal }));
        if (data.signal.action !== 'WAIT' && data.signal.confidence > 0.65) {
          addAlert(`新しいエントリーシグナル: ${data.signal.action} ${data.symbol}`, 'success');
          
          // 自動売買が有効な場合、自動でエントリー
          if (autoTrading && data.signal.confidence > 0.7) {
            executeEntry(data.symbol, data.signal);
          }
        }
      }
    });

    wsClient.on('alert', (data: any) => {
      if (selectedSymbols.has(data.symbol)) {
        addAlert(`アラート: ${data.symbol} - ${data.signal.action}`, 'warning');
      }
    });

    return () => {
      wsClient.disconnect();
    };
  }, [selectedSymbols, autoTrading, addAlert, executeEntry]);

  // 自動売買の定期チェック
  useEffect(() => {
    if (autoTrading) {
      // 初回チェック
      fetchSignals(true);
      
      // 30秒ごとに自動チェック
      const interval = setInterval(() => {
        fetchSignals(true);
      }, 30000);
      
      return () => {
        clearInterval(interval);
      };
    }
  }, [autoTrading, fetchSignals]);

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

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setCurrentTab(newValue);
  };

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        🎯 トレーディングシステム
      </Typography>

      {/* タブナビゲーション */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={currentTab} onChange={handleTabChange}>
          <Tab label="慎重モード" />
          <Tab label="スキャルピングモード" />
          <Tab label="複数通貨取引" />
        </Tabs>
      </Box>

      {/* タブコンテンツ */}
      {currentTab === 0 && (
        <ConservativeMode />
      )}

      {currentTab === 0 && false && (
        <>
          <Stack spacing={1} sx={{ mb: 3 }}>
            {alerts.map((alert) => (
              <Alert key={alert.id} severity={alert.type}>
                {alert.message}
              </Alert>
            ))}
          </Stack>

          {/* シンボル選択 */}
          <Box sx={{ mb: 3 }}>
            <Typography variant="subtitle1" gutterBottom>
              🐢 慎重モード（1日3-10回の厳選取引） - 選択中: {selectedSymbols.size}通貨（最大10通貨）
            </Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
              {symbols.map((symbol) => (
                <Chip
                  key={symbol}
                  label={symbol}
                  onClick={() => {
                    const newSelected = new Set(selectedSymbols);
                    if (newSelected.has(symbol)) {
                      newSelected.delete(symbol);
                    } else if (newSelected.size < 10) { // 最大10通貨まで
                      newSelected.add(symbol);
                    } else {
                      addAlert('最大10通貨まで選択可能です', 'warning');
                    }
                    setSelectedSymbols(newSelected);
                  }}
                  color={selectedSymbols.has(symbol) ? 'primary' : 'default'}
                  variant={selectedSymbols.has(symbol) ? 'filled' : 'outlined'}
                />
              ))}
            </Box>
          </Box>

          {/* コントロールボタン */}
          <Box sx={{ mb: 3 }}>
            <Stack direction="row" spacing={2}>
              <Button
                variant="contained"
                startIcon={loading ? <CircularProgress size={20} /> : <RefreshIcon />}
                onClick={() => {
                  fetchSignals();
                  // fetchAnalysis(); // 分析は最初に選択した通貨のみ
                }}
                disabled={loading}
              >
                シグナル分析
              </Button>
              <Button
                variant={autoTrading ? 'contained' : 'outlined'}
                color={autoTrading ? 'error' : 'primary'}
                startIcon={autoTrading ? <StopIcon /> : <PlayArrowIcon />}
                onClick={() => {
                  setAutoTrading(!autoTrading);
                  if (!autoTrading) {
                    addAlert('🤖 自動売買を開始しました。信頼度70%以上のシグナルで自動エントリーします。', 'success');
                  } else {
                    addAlert('🛑 自動売買を停止しました。', 'warning');
                  }
                }}
              >
                {autoTrading ? '自動売買停止' : '自動売買開始'}
              </Button>
            </Stack>
          </Box>

          {/* メイン分析エリア */}
          {Object.keys(signals).length > 0 && (
            <Card sx={{ mb: 3 }}>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    エントリーシグナル
                  </Typography>
                  
                  <TableContainer component={Paper} variant="outlined">
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>通貨ペア</TableCell>
                          <TableCell>シグナル</TableCell>
                          <TableCell>信頼度</TableCell>
                          <TableCell>エントリー価格</TableCell>
                          <TableCell>ストップロス</TableCell>
                          <TableCell>テイクプロフィット</TableCell>
                          <TableCell>アクション</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {Array.from(selectedSymbols).map((symbol) => {
                          const signal = signals[symbol];
                          if (!signal) return null;
                          
                          console.log(`Signal for ${symbol}:`, signal); // デバッグ用
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
                              <TableCell>${signal.stop_loss.toFixed(2)}</TableCell>
                              <TableCell>{signal.take_profit[0] ? `$${signal.take_profit[0].toFixed(2)}` : '-'}</TableCell>
                              <TableCell>
                                {signal.action !== 'WAIT' && signal.confidence > 0.5 ? (
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
        </>
      )}

      {currentTab === 1 && (
        <ScalpingMode />
      )}
      
      {currentTab === 2 && (
        <MultiSymbolTrading />
      )}
    </Box>
  );
};

export default Trading;