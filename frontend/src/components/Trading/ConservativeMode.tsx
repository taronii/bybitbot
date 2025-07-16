import React, { useState, useEffect } from 'react';
import { 
  Brain, 
  TrendingUp, 
  Shield, 
  DollarSign,
  Target,
  StopCircle,
  Activity,
  AlertCircle,
  CheckCircle,
  Clock,
  RefreshCw
} from 'lucide-react';
import { apiService } from '../../services/api';

interface ProfitTarget {
  price: number;
  percentage: number;
  priority: number;
  trigger_type: string;
  description: string;
}

interface StopLevel {
  price: number;
  name: string;
  trigger_conditions: string[];
  priority: number;
  description: string;
}

interface ConservativePosition {
  position_id: string;
  symbol: string;
  direction: string;
  entry_price: number;
  quantity: number;
  current_profit: number;
  max_profit: number;
  profit_targets: ProfitTarget[];
  stop_levels: StopLevel[];
  trailing_stop: {
    active: boolean;
    stop_price: number;
    locked_profit: number;
  } | null;
  entry_time: string;
  confidence: number;
}

interface ConservativeStatus {
  mode_status: {
    name: string;
    enabled: boolean;
    active_positions: number;
    max_positions: number;
    daily_trades: number;
    max_daily_trades: number;
    position_size_percent: number;
    can_open_new: boolean;
  };
  active_positions: ConservativePosition[];
  position_count: number;
}

export default function ConservativeMode() {
  const [status, setStatus] = useState<ConservativeStatus | null>(null);
  const [selectedPosition, setSelectedPosition] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedSymbols, setSelectedSymbols] = useState<Set<string>>(new Set(['BTCUSDT']));
  const [autoTrading, setAutoTrading] = useState(false);
  const [signals, setSignals] = useState<Record<string, any>>({});
  const [resetting, setResetting] = useState(false);

  // 人気のトレーディングペア
  const symbols = [
    'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT',
    'ADAUSDT', 'MATICUSDT', 'DOTUSDT', 'AVAXUSDT', 'LINKUSDT',
    'LTCUSDT', 'ATOMUSDT', 'UNIUSDT', 'NEARUSDT', 'FTMUSDT'
  ];

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000); // 5秒ごとに更新
    return () => clearInterval(interval);
  }, []);

  const fetchStatus = async () => {
    try {
      const response = await apiService.get<ConservativeStatus>('/api/trading/conservative/status');
      setStatus(response.data);
    } catch (error) {
      console.error('Failed to fetch conservative status:', error);
    }
  };

  const getProfitColor = (profit: number) => {
    if (profit > 0) return 'text-green-400';
    if (profit < 0) return 'text-red-400';
    return 'text-gray-400';
  };

  const formatPrice = (price: number) => {
    return price.toFixed(price > 100 ? 2 : 4);
  };

  const handleSymbolToggle = (symbol: string) => {
    const newSelected = new Set(selectedSymbols);
    if (newSelected.has(symbol)) {
      newSelected.delete(symbol);
    } else {
      if (newSelected.size < 10) {
        newSelected.add(symbol);
      }
    }
    setSelectedSymbols(newSelected);
  };

  const fetchSignals = async () => {
    setLoading(true);
    try {
      const signalPromises = Array.from(selectedSymbols).map(async (symbol) => {
        const response = await apiService.get<{ signal: any }>(`/api/trading/entry-signal/${symbol}`);
        return { symbol, signal: response.data.signal };
      });
      
      const results = await Promise.all(signalPromises);
      const newSignals: Record<string, any> = {};
      results.forEach(({ symbol, signal }) => {
        newSignals[symbol] = signal;
      });
      setSignals(newSignals);
    } catch (error) {
      console.error('Failed to fetch signals:', error);
    } finally {
      setLoading(false);
    }
  };

  const executeEntry = async (symbol: string, signal: any) => {
    try {
      const response = await apiService.post<{ result: { executed: boolean; error?: string } }>('/api/trading/execute-entry', {
        symbol,
        signal
      });
      
      if (response.data.result.executed) {
        alert(`エントリー成功: ${symbol} ${signal.action}`);
        fetchStatus(); // ステータスを更新
      } else {
        alert(`エントリー失敗: ${response.data.result.error}`);
      }
    } catch (error) {
      console.error('Entry execution failed:', error);
      alert('エントリー実行エラー');
    }
  };

  const handlePortfolioReset = async () => {
    if (!window.confirm('ポートフォリオをリセットしますか？\n\n手動取引後の不整合を解消し、新しいエントリーを可能にします。')) {
      return;
    }

    setResetting(true);
    try {
      const response = await apiService.post<{ status: string; message: string }>('/api/trading/portfolio/reset', {});
      if (response.data.status === 'success') {
        alert('ポートフォリオがリセットされました');
        fetchStatus(); // ステータスを更新
      } else {
        alert('リセットに失敗しました');
      }
    } catch (error) {
      console.error('Portfolio reset failed:', error);
      alert('リセットエラーが発生しました');
    } finally {
      setResetting(false);
    }
  };

  if (!status) {
    return (
      <div className="bg-gray-800 rounded-lg p-6">
        <div className="flex items-center justify-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* ヘッダー */}
      <div className="bg-gray-800 rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center space-x-3">
            <Shield className="h-8 w-8 text-blue-400" />
            <div>
              <h2 className="text-2xl font-bold text-white">慎重モード</h2>
              <p className="text-gray-400">安全第一の堅実取引</p>
            </div>
          </div>
          <div className={`px-4 py-2 rounded-full ${status.mode_status.enabled ? 'bg-green-500/20 text-green-400' : 'bg-gray-600 text-gray-400'}`}>
            {status.mode_status.enabled ? '有効' : '無効'}
          </div>
        </div>

        {/* 統計情報 */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-gray-700 rounded-lg p-4">
            <div className="text-sm text-gray-400">アクティブポジション</div>
            <div className="text-2xl font-bold text-white">
              {status.mode_status.active_positions} / {status.mode_status.max_positions}
            </div>
          </div>
          <div className="bg-gray-700 rounded-lg p-4">
            <div className="text-sm text-gray-400">本日の取引数</div>
            <div className="text-2xl font-bold text-white">
              {status.mode_status.daily_trades} / {status.mode_status.max_daily_trades}
            </div>
          </div>
          <div className="bg-gray-700 rounded-lg p-4">
            <div className="text-sm text-gray-400">ポジションサイズ</div>
            <div className="text-2xl font-bold text-white">
              {(status.mode_status.position_size_percent * 100).toFixed(1)}%
            </div>
          </div>
          <div className="bg-gray-700 rounded-lg p-4">
            <div className="text-sm text-gray-400">新規エントリー</div>
            <div className="text-2xl font-bold">
              <span className={status.mode_status.can_open_new ? 'text-green-400' : 'text-red-400'}>
                {status.mode_status.can_open_new ? '可能' : '不可'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* シンボル選択と自動売買コントロール */}
      <div className="bg-gray-800 rounded-lg p-6">
        <div className="mb-4">
          <h3 className="text-lg font-semibold text-white mb-2">
            🐢 慎重モード（1日3-10回の厳選取引） - 選択中: {selectedSymbols.size}通貨（最大10通貨）
          </h3>
          <div className="flex flex-wrap gap-2">
            {symbols.map((symbol) => (
              <button
                key={symbol}
                onClick={() => handleSymbolToggle(symbol)}
                className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${
                  selectedSymbols.has(symbol)
                    ? 'bg-blue-500 text-white'
                    : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                }`}
                disabled={!selectedSymbols.has(symbol) && selectedSymbols.size >= 10}
              >
                {symbol.replace('USDT', '')}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <button
              onClick={fetchSignals}
              disabled={loading || selectedSymbols.size === 0}
              className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:bg-gray-600 disabled:cursor-not-allowed flex items-center space-x-2"
            >
              {loading ? (
                <>
                  <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                  <span>分析中...</span>
                </>
              ) : (
                <>
                  <Activity className="h-5 w-5" />
                  <span>シグナル取得</span>
                </>
              )}
            </button>
            
            <button
              onClick={() => setAutoTrading(!autoTrading)}
              className={`px-4 py-2 rounded-lg flex items-center space-x-2 ${
                autoTrading
                  ? 'bg-green-500 hover:bg-green-600 text-white'
                  : 'bg-gray-600 hover:bg-gray-500 text-white'
              }`}
            >
              <Shield className="h-5 w-5" />
              <span>{autoTrading ? '自動売買ON' : '自動売買OFF'}</span>
            </button>

            <button
              onClick={handlePortfolioReset}
              disabled={resetting}
              className="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 disabled:bg-gray-600 disabled:cursor-not-allowed flex items-center space-x-2"
              title="手動取引後の不整合を解消"
            >
              {resetting ? (
                <>
                  <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                  <span>リセット中...</span>
                </>
              ) : (
                <>
                  <RefreshCw className="h-5 w-5" />
                  <span>ポートフォリオリセット</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* シグナル表示 */}
      {Object.keys(signals).length > 0 && (
        <div className="bg-gray-800 rounded-lg p-6">
          <h3 className="text-xl font-semibold text-white mb-4">取引シグナル</h3>
          <div className="grid gap-4">
            {Object.entries(signals).map(([symbol, signal]) => (
              <div key={symbol} className="bg-gray-700 rounded-lg p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-white font-medium">{symbol}</span>
                    <span className={`ml-3 px-2 py-1 rounded text-sm ${
                      signal.action === 'BUY' ? 'bg-green-500/20 text-green-400' :
                      signal.action === 'SELL' ? 'bg-red-500/20 text-red-400' :
                      'bg-gray-600 text-gray-400'
                    }`}>
                      {signal.action}
                    </span>
                    <span className="ml-2 text-gray-400">
                      信頼度: {(signal.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  {signal.action !== 'WAIT' && signal.confidence > 0.5 && (
                    <button
                      onClick={() => executeEntry(symbol, signal)}
                      className="px-3 py-1 bg-blue-500 text-white rounded hover:bg-blue-600"
                    >
                      実行
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* アクティブポジション */}
      <div className="bg-gray-800 rounded-lg p-6">
        <h3 className="text-xl font-semibold text-white mb-4">アクティブポジション</h3>
        
        {status.active_positions.length === 0 ? (
          <div className="text-center py-8 text-gray-400">
            <AlertCircle className="h-12 w-12 mx-auto mb-2" />
            <p>現在アクティブなポジションはありません</p>
          </div>
        ) : (
          <div className="space-y-4">
            {status.active_positions.map((position) => (
              <div 
                key={position.position_id}
                className={`bg-gray-700 rounded-lg p-4 cursor-pointer transition-all ${
                  selectedPosition === position.position_id ? 'ring-2 ring-blue-500' : ''
                }`}
                onClick={() => setSelectedPosition(
                  selectedPosition === position.position_id ? null : position.position_id
                )}
              >
                {/* ポジション概要 */}
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center space-x-3">
                    <div className={`px-3 py-1 rounded-full text-sm font-medium ${
                      position.direction === 'BUY' 
                        ? 'bg-green-500/20 text-green-400' 
                        : 'bg-red-500/20 text-red-400'
                    }`}>
                      {position.direction}
                    </div>
                    <span className="text-white font-medium">{position.symbol}</span>
                    <span className="text-gray-400 text-sm">
                      信頼度: {(position.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className={`text-xl font-bold ${getProfitColor(position.current_profit)}`}>
                    {position.current_profit > 0 ? '+' : ''}{position.current_profit.toFixed(2)}%
                  </div>
                </div>

                {/* 基本情報 */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
                  <div>
                    <span className="text-gray-400">エントリー価格:</span>
                    <span className="text-white ml-2">{formatPrice(position.entry_price)}</span>
                  </div>
                  <div>
                    <span className="text-gray-400">数量:</span>
                    <span className="text-white ml-2">{position.quantity.toFixed(4)}</span>
                  </div>
                  <div>
                    <span className="text-gray-400">最大利益:</span>
                    <span className="text-green-400 ml-2">+{position.max_profit.toFixed(2)}%</span>
                  </div>
                  <div>
                    <span className="text-gray-400">保有時間:</span>
                    <span className="text-white ml-2">
                      {new Date(position.entry_time).toLocaleTimeString()}
                    </span>
                  </div>
                </div>

                {/* 展開時の詳細情報 */}
                {selectedPosition === position.position_id && (
                  <div className="mt-4 pt-4 border-t border-gray-600">
                    <div className="grid md:grid-cols-2 gap-4">
                      {/* 利確レベル */}
                      <div>
                        <h4 className="text-white font-medium mb-2 flex items-center">
                          <Target className="h-4 w-4 mr-2 text-green-400" />
                          利確レベル
                        </h4>
                        <div className="space-y-2">
                          {position.profit_targets.map((target, index) => (
                            <div key={index} className="bg-gray-600 rounded p-2">
                              <div className="flex justify-between items-center">
                                <span className="text-sm text-gray-300">{target.description}</span>
                                <span className="text-green-400 font-medium">
                                  {formatPrice(target.price)}
                                </span>
                              </div>
                              <div className="text-xs text-gray-400 mt-1">
                                {target.percentage}%のポジションを決済
                              </div>
                            </div>
                          ))}
                          {position.trailing_stop && position.trailing_stop.active && (
                            <div className="bg-blue-600/20 rounded p-2 border border-blue-500">
                              <div className="flex justify-between items-center">
                                <span className="text-sm text-blue-300">トレーリングストップ</span>
                                <span className="text-blue-400 font-medium">
                                  {formatPrice(position.trailing_stop.stop_price)}
                                </span>
                              </div>
                              <div className="text-xs text-blue-300 mt-1">
                                利益確保: {position.trailing_stop.locked_profit.toFixed(2)}%
                              </div>
                            </div>
                          )}
                        </div>
                      </div>

                      {/* 損切りレベル */}
                      <div>
                        <h4 className="text-white font-medium mb-2 flex items-center">
                          <StopCircle className="h-4 w-4 mr-2 text-red-400" />
                          損切りレベル
                        </h4>
                        <div className="space-y-2">
                          {position.stop_levels.map((stop, index) => (
                            <div key={index} className="bg-gray-600 rounded p-2">
                              <div className="flex justify-between items-center">
                                <span className="text-sm text-gray-300">{stop.description}</span>
                                <span className="text-red-400 font-medium">
                                  {stop.price > 0 ? formatPrice(stop.price) : '市場価格'}
                                </span>
                              </div>
                              <div className="text-xs text-gray-400 mt-1">
                                条件: {stop.trigger_conditions.join(', ')}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 安全性インジケーター */}
      <div className="bg-gray-800 rounded-lg p-6">
        <h3 className="text-xl font-semibold text-white mb-4">安全性インジケーター</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="text-center">
            <div className="relative w-20 h-20 mx-auto mb-2">
              <svg className="transform -rotate-90 w-20 h-20">
                <circle
                  cx="40"
                  cy="40"
                  r="36"
                  stroke="currentColor"
                  strokeWidth="8"
                  fill="none"
                  className="text-gray-600"
                />
                <circle
                  cx="40"
                  cy="40"
                  r="36"
                  stroke="currentColor"
                  strokeWidth="8"
                  fill="none"
                  strokeDasharray={`${2 * Math.PI * 36}`}
                  strokeDashoffset={`${2 * Math.PI * 36 * (1 - 0.8)}`}
                  className="text-green-400"
                />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-lg font-bold text-white">80%</span>
              </div>
            </div>
            <div className="text-sm text-gray-400">リスク管理</div>
          </div>
          
          <div className="text-center">
            <CheckCircle className="h-12 w-12 text-green-400 mx-auto mb-2" />
            <div className="text-2xl font-bold text-white">3/5</div>
            <div className="text-sm text-gray-400">ポジション数</div>
          </div>
          
          <div className="text-center">
            <Activity className="h-12 w-12 text-blue-400 mx-auto mb-2" />
            <div className="text-2xl font-bold text-white">安定</div>
            <div className="text-sm text-gray-400">市場状況</div>
          </div>
          
          <div className="text-center">
            <Clock className="h-12 w-12 text-yellow-400 mx-auto mb-2" />
            <div className="text-2xl font-bold text-white">良好</div>
            <div className="text-sm text-gray-400">タイミング</div>
          </div>
        </div>
      </div>
    </div>
  );
}