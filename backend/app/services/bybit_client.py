"""
Bybitクライアント管理サービス
"""
from typing import Optional
from ..models import BybitClient

# グローバルなBybitクライアントインスタンス
_bybit_client: Optional[BybitClient] = None

def get_bybit_client() -> Optional[BybitClient]:
    """現在のBybitクライアントを取得"""
    return _bybit_client

def set_bybit_client(client: BybitClient):
    """Bybitクライアントを設定"""
    global _bybit_client
    _bybit_client = client

def create_bybit_client(api_key: str, api_secret: str, testnet: bool = True) -> BybitClient:
    """新しいBybitクライアントを作成"""
    from pybit.unified_trading import HTTP
    
    # テストネットまたはメインネットのセッションを作成
    session = HTTP(
        testnet=testnet,
        api_key=api_key,
        api_secret=api_secret
    )
    
    client = BybitClient(session=session, testnet=testnet)
    set_bybit_client(client)
    
    return client