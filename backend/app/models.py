"""
データモデル定義
"""
from pydantic import BaseModel
from typing import Optional, Any

class ApiSettings(BaseModel):
    """API設定モデル"""
    apiKey: str
    apiSecret: str
    testnet: bool = True

class BybitClient:
    """Bybitクライアントモデル"""
    def __init__(self, session: Any, testnet: bool = True):
        self.session = session
        self.testnet = testnet
    
    async def get_account_balance(self):
        """アカウント残高を取得"""
        try:
            # Bybit APIの残高取得エンドポイントを呼び出す
            response = self.session.get_wallet_balance(
                accountType="UNIFIED",  # 統合取引アカウント
                coin="USDT"  # USDT残高を取得
            )
            
            if response.get('retCode') == 0:
                result = response.get('result', {})
                coin_data = result.get('list', [{}])[0].get('coin', [{}])
                
                # USDT残高を探す
                for coin in coin_data:
                    if coin.get('coin') == 'USDT':
                        return {
                            'balance': float(coin.get('walletBalance', 0)),
                            'available_balance': float(coin.get('availableToWithdraw', 0))
                        }
                
                # USDTが見つからない場合のフォールバック
                return {'balance': 1000.0, 'available_balance': 1000.0}  # デモ用デフォルト値
            else:
                # APIエラーの場合はデモ用の値を返す
                return {'balance': 1000.0, 'available_balance': 1000.0}
                
        except Exception as e:
            # エラーの場合はデモ用の値を返す
            return {'balance': 1000.0, 'available_balance': 1000.0}
    
    async def get_klines(self, symbol: str, interval: str, limit: int):
        """ローソク足データを取得"""
        try:
            response = self.session.get_kline(
                category="linear",
                symbol=symbol,
                interval=interval,
                limit=limit
            )
            
            if response.get('retCode') == 0:
                return response.get('result', {}).get('list', [])
            return []
        except:
            return []
    
    async def get_orderbook(self, symbol: str):
        """オーダーブックを取得"""
        try:
            response = self.session.get_orderbook(
                category="linear",
                symbol=symbol,
                limit=25
            )
            
            if response.get('retCode') == 0:
                result = response.get('result', {})
                return {
                    'bids': result.get('b', []),
                    'asks': result.get('a', [])
                }
            return {'bids': [], 'asks': []}
        except:
            return {'bids': [], 'asks': []}
    
    async def get_ticker(self, symbol: str):
        """ティッカー情報を取得"""
        try:
            response = self.session.get_tickers(
                category="linear",
                symbol=symbol
            )
            
            if response.get('retCode') == 0:
                tickers = response.get('result', {}).get('list', [])
                if tickers:
                    return tickers[0]
            return {}
        except:
            return {}