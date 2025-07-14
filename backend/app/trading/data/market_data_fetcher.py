"""
Bybit マーケットデータ取得サービス
"""
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging
from pybit.unified_trading import HTTP
from ...services.bybit_client import get_bybit_client

logger = logging.getLogger(__name__)

class MarketDataFetcher:
    def __init__(self):
        self.client = None
        self._cache = {}
        self._cache_ttl = 5  # 5秒キャッシュ
        
    def initialize(self):
        """初期化"""
        bybit_client = get_bybit_client()
        if bybit_client:
            self.client = bybit_client.session
        else:
            # デフォルトクライアント（テストネット）
            self.client = HTTP(testnet=True)
            
    async def get_kline_data(
        self, 
        symbol: str, 
        interval: str = '1',
        limit: int = 200
    ) -> pd.DataFrame:
        """KLineデータを取得"""
        try:
            cache_key = f"kline_{symbol}_{interval}"
            cached_data = self._get_cached_data(cache_key)
            if cached_data is not None:
                return cached_data
                
            if not self.client:
                self.initialize()
                
            # Bybit APIからKLineデータを取得
            response = self.client.get_kline(
                category="linear",
                symbol=symbol,
                interval=interval,
                limit=limit
            )
            
            if response['retCode'] != 0:
                logger.error(f"Failed to fetch kline data: {response['retMsg']}")
                return self._get_mock_kline_data(symbol, limit)
                
            klines = response['result']['list']
            
            # DataFrameに変換
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
            ])
            
            # データ型を変換
            df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume', 'turnover']:
                df[col] = df[col].astype(float)
                
            # タイムスタンプでソート
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            # キャッシュに保存
            self._cache_data(cache_key, df)
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching kline data: {e}")
            return self._get_mock_kline_data(symbol, limit)
            
    async def get_orderbook_data(self, symbol: str, limit: int = 50) -> Dict:
        """オーダーブックデータを取得"""
        try:
            cache_key = f"orderbook_{symbol}"
            cached_data = self._get_cached_data(cache_key)
            if cached_data is not None:
                return cached_data
                
            if not self.client:
                self.initialize()
                
            # Bybit APIからオーダーブックを取得
            response = self.client.get_orderbook(
                category="linear",
                symbol=symbol,
                limit=limit
            )
            
            if response['retCode'] != 0:
                logger.error(f"Failed to fetch orderbook data: {response['retMsg']}")
                return self._get_mock_orderbook_data(symbol)
                
            orderbook = response['result']
            
            # データを整形
            result = {
                'bids': [(float(bid[0]), float(bid[1])) for bid in orderbook['b']],
                'asks': [(float(ask[0]), float(ask[1])) for ask in orderbook['a']],
                'timestamp': datetime.now()
            }
            
            # キャッシュに保存
            self._cache_data(cache_key, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching orderbook data: {e}")
            return self._get_mock_orderbook_data(symbol)
            
    async def get_recent_trades(self, symbol: str, limit: int = 100) -> List[Dict]:
        """最近の約定データを取得"""
        try:
            cache_key = f"trades_{symbol}"
            cached_data = self._get_cached_data(cache_key)
            if cached_data is not None:
                return cached_data
                
            if not self.client:
                self.initialize()
                
            # Bybit APIから最近の約定を取得
            response = self.client.get_public_trade_history(
                category="linear",
                symbol=symbol,
                limit=limit
            )
            
            if response['retCode'] != 0:
                logger.error(f"Failed to fetch trade data: {response['retMsg']}")
                return self._get_mock_trades_data(symbol, limit)
                
            trades = response['result']['list']
            
            # データを整形
            result = []
            for trade in trades:
                result.append({
                    'timestamp': pd.to_datetime(int(trade['time']), unit='ms'),
                    'price': float(trade['price']),
                    'quantity': float(trade['size']),
                    'side': trade['side'],
                    'trade_id': trade.get('execId', '')
                })
                
            # キャッシュに保存
            self._cache_data(cache_key, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching trade data: {e}")
            return self._get_mock_trades_data(symbol, limit)
            
    async def get_ticker_data(self, symbol: str) -> Dict:
        """ティッカーデータを取得"""
        try:
            cache_key = f"ticker_{symbol}"
            cached_data = self._get_cached_data(cache_key)
            if cached_data is not None:
                return cached_data
                
            if not self.client:
                self.initialize()
                
            # Bybit APIからティッカーを取得
            response = self.client.get_tickers(
                category="linear",
                symbol=symbol
            )
            
            if response['retCode'] != 0:
                logger.error(f"Failed to fetch ticker data: {response['retMsg']}")
                return self._get_mock_ticker_data(symbol)
                
            ticker = response['result']['list'][0]
            
            # データを整形
            result = {
                'symbol': ticker['symbol'],
                'last_price': float(ticker['lastPrice']),
                'bid_price': float(ticker['bid1Price']),
                'ask_price': float(ticker['ask1Price']),
                'bid_size': float(ticker['bid1Size']),
                'ask_size': float(ticker['ask1Size']),
                'volume_24h': float(ticker['volume24h']),
                'turnover_24h': float(ticker['turnover24h']),
                'price_change_24h': float(ticker['price24hPcnt']),
                'high_24h': float(ticker['highPrice24h']),
                'low_24h': float(ticker['lowPrice24h']),
                'timestamp': datetime.now()
            }
            
            # キャッシュに保存
            self._cache_data(cache_key, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching ticker data: {e}")
            return self._get_mock_ticker_data(symbol)
            
    def _get_cached_data(self, key: str) -> Optional[Any]:
        """キャッシュからデータを取得"""
        if key in self._cache:
            data, timestamp = self._cache[key]
            if datetime.now() - timestamp < timedelta(seconds=self._cache_ttl):
                return data
        return None
        
    def _cache_data(self, key: str, data: Any):
        """データをキャッシュに保存"""
        self._cache[key] = (data, datetime.now())
        
    def _get_mock_kline_data(self, symbol: str, limit: int) -> pd.DataFrame:
        """モックKLineデータを生成"""
        now = datetime.now()
        base_price = 30000 if 'BTC' in symbol else 2000 if 'ETH' in symbol else 100
        
        timestamps = [now - timedelta(minutes=i) for i in range(limit, 0, -1)]
        
        # より現実的な価格変動を生成
        prices = []
        current_price = base_price
        for _ in range(limit):
            change = np.random.normal(0, base_price * 0.0002)  # 0.02%の標準偏差
            current_price += change
            prices.append(current_price)
            
        df = pd.DataFrame({
            'timestamp': timestamps,
            'open': prices,
            'high': [p + abs(np.random.normal(0, base_price * 0.0001)) for p in prices],
            'low': [p - abs(np.random.normal(0, base_price * 0.0001)) for p in prices],
            'close': [p + np.random.normal(0, base_price * 0.00005) for p in prices],
            'volume': [np.random.uniform(10, 100) for _ in range(limit)],
            'turnover': [np.random.uniform(10000, 100000) for _ in range(limit)]
        })
        
        return df
        
    def _get_mock_orderbook_data(self, symbol: str) -> Dict:
        """モックオーダーブックデータを生成"""
        base_price = 30000 if 'BTC' in symbol else 2000 if 'ETH' in symbol else 100
        spread = base_price * 0.0001  # 0.01%スプレッド
        
        bids = []
        asks = []
        
        for i in range(20):
            bid_price = base_price - spread/2 - i * spread/10
            ask_price = base_price + spread/2 + i * spread/10
            
            bid_size = np.random.uniform(0.1, 5.0)
            ask_size = np.random.uniform(0.1, 5.0)
            
            bids.append((bid_price, bid_size))
            asks.append((ask_price, ask_size))
            
        return {
            'bids': bids,
            'asks': asks,
            'timestamp': datetime.now()
        }
        
    def _get_mock_trades_data(self, symbol: str, limit: int) -> List[Dict]:
        """モック約定データを生成"""
        base_price = 30000 if 'BTC' in symbol else 2000 if 'ETH' in symbol else 100
        now = datetime.now()
        
        trades = []
        for i in range(limit):
            trades.append({
                'timestamp': now - timedelta(seconds=i),
                'price': base_price + np.random.normal(0, base_price * 0.0001),
                'quantity': np.random.uniform(0.01, 1.0),
                'side': np.random.choice(['Buy', 'Sell']),
                'trade_id': f"mock_{i}"
            })
            
        return trades
        
    def _get_mock_ticker_data(self, symbol: str) -> Dict:
        """モックティッカーデータを生成"""
        base_price = 30000 if 'BTC' in symbol else 2000 if 'ETH' in symbol else 100
        spread = base_price * 0.0001
        
        return {
            'symbol': symbol,
            'last_price': base_price,
            'bid_price': base_price - spread/2,
            'ask_price': base_price + spread/2,
            'bid_size': np.random.uniform(1, 10),
            'ask_size': np.random.uniform(1, 10),
            'volume_24h': np.random.uniform(1000, 10000),
            'turnover_24h': np.random.uniform(1000000, 10000000),
            'price_change_24h': np.random.uniform(-0.05, 0.05),
            'high_24h': base_price * 1.02,
            'low_24h': base_price * 0.98,
            'timestamp': datetime.now()
        }

# シングルトンインスタンス
market_data_fetcher = MarketDataFetcher()