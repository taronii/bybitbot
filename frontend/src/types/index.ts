// API設定の型定義
export interface ApiSettings {
  apiKey: string;
  apiSecret: string;
  testnet: boolean;
}

// ダッシュボードデータの型定義
export interface DashboardData {
  accountBalance: number;
  totalPnL: number;
  todayPnL: number;
  openPositions: Position[];
  recentTrades: Trade[];
  systemStatus: 'running' | 'stopped' | 'error';
}

// ポジション情報
export interface Position {
  id: string;
  symbol: string;
  side: 'Buy' | 'Sell';
  size: number;
  entryPrice: number;
  currentPrice: number;
  unrealizedPnL: number;
  timestamp: string;
}

// 取引履歴
export interface Trade {
  id: string;
  symbol: string;
  side: 'Buy' | 'Sell';
  quantity: number;
  price: number;
  fee: number;
  realizedPnL: number;
  timestamp: string;
}

// WebSocketメッセージ
export interface WebSocketMessage {
  type: 'price_update' | 'position_update' | 'trade_update' | 'account_update';
  data: any;
  timestamp: number;
}

// システムステータス
export interface SystemStatus {
  status: 'running' | 'stopped' | 'error';
  version: string;
  uptime: number;
  lastUpdate: string;
}