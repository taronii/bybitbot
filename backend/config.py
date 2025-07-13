import os
from typing import Optional
from pydantic import BaseSettings

class Settings(BaseSettings):
    # API設定
    bybit_api_key: Optional[str] = None
    bybit_api_secret: Optional[str] = None
    bybit_testnet: bool = True
    
    # データベース設定
    database_url: str = "sqlite:///./database/trading.db"
    
    # サーバー設定
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True
    
    # セキュリティ設定
    secret_key: str = "your-secret-key-here"
    
    class Config:
        env_file = ".env"

settings = Settings()