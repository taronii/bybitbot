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