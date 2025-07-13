from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import json
import os
from pathlib import Path
from cryptography.fernet import Fernet
from pybit.unified_trading import HTTP
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

# 暗号化キー（本番環境では環境変数から取得すべき）
# 開発環境用の固定キー（本番環境では必ず環境変数から取得すること）
DEFAULT_KEY = "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg="
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", DEFAULT_KEY)
fernet = Fernet(ENCRYPTION_KEY.encode())

# プロジェクトルートディレクトリを取得
BASE_DIR = Path(__file__).resolve().parent.parent.parent
SETTINGS_FILE = os.path.join(BASE_DIR, "data", "api_settings.json")

class ApiSettings(BaseModel):
    apiKey: str
    apiSecret: str
    testnet: bool = True

class TestConnectionResponse(BaseModel):
    success: bool
    message: str

def load_settings() -> Optional[ApiSettings]:
    """保存された設定を読み込む"""
    try:
        if not os.path.exists(SETTINGS_FILE):
            return None
        
        with open(SETTINGS_FILE, "r") as f:
            data = json.load(f)
        
        # APIシークレットを復号化
        if data.get("apiSecret"):
            data["apiSecret"] = fernet.decrypt(data["apiSecret"].encode()).decode()
        
        return ApiSettings(**data)
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        return None

def save_settings(settings: ApiSettings) -> bool:
    """設定を保存する"""
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        
        # APIシークレットを暗号化
        data = settings.dict()
        if data.get("apiSecret"):
            data["apiSecret"] = fernet.encrypt(data["apiSecret"].encode()).decode()
        
        with open(SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=2)
        
        return True
    except Exception as e:
        logger.error(f"Failed to save settings: {e}")
        return False

class ApiSettingsResponse(BaseModel):
    apiKey: str
    apiSecret: str
    testnet: bool = True
    hasApiSecret: bool = False

@router.get("", response_model=ApiSettingsResponse)
async def get_settings():
    """API設定を取得"""
    settings = load_settings()
    if settings:
        # APIシークレットはマスクして返す
        has_secret = bool(settings.apiSecret)
        return ApiSettingsResponse(
            apiKey=settings.apiKey,
            apiSecret="*" * 10 if has_secret else "",
            testnet=settings.testnet,
            hasApiSecret=has_secret
        )
    return ApiSettingsResponse(apiKey="", apiSecret="", testnet=True, hasApiSecret=False)

@router.post("")
async def update_settings(settings: ApiSettings):
    """API設定を更新"""
    # 既存の設定を読み込む
    existing_settings = load_settings()
    
    # APIシークレットが空文字列またはマスクされている場合は、既存の値を使用
    if existing_settings and settings.apiSecret in ["", "*" * 10]:
        settings.apiSecret = existing_settings.apiSecret
    
    if not save_settings(settings):
        raise HTTPException(status_code=500, detail="設定の保存に失敗しました")
    
    # 設定保存後、Bybitクライアントを更新
    try:
        from ..services.bybit_client import create_bybit_client
        create_bybit_client(settings.apiKey, settings.apiSecret, settings.testnet)
        logger.info("Bybit client updated successfully")
    except Exception as e:
        logger.warning(f"Failed to update Bybit client: {e}")
    
    return {"message": "設定を保存しました"}

@router.post("/test", response_model=TestConnectionResponse)
async def test_connection(settings: ApiSettings):
    """API接続をテスト"""
    try:
        # 既存の設定を読み込む
        existing_settings = load_settings()
        
        # APIシークレットが空文字列の場合は、既存の値を使用
        if existing_settings and settings.apiSecret == "":
            settings.apiSecret = existing_settings.apiSecret
        # Bybit APIクライアントを作成
        session = HTTP(
            testnet=settings.testnet,
            api_key=settings.apiKey,
            api_secret=settings.apiSecret,
        )
        
        # アカウント情報を取得してテスト
        result = session.get_wallet_balance(accountType="UNIFIED")
        
        if result["retCode"] == 0:
            # 残高情報を取得
            balance_info = result["result"]["list"][0] if result["result"]["list"] else {}
            total_balance = float(balance_info.get("totalEquity", 0))
            
            return TestConnectionResponse(
                success=True,
                message=f"接続成功！アカウント残高: ${total_balance:,.2f}"
            )
        else:
            return TestConnectionResponse(
                success=False,
                message=f"APIエラー: {result.get('retMsg', 'Unknown error')}"
            )
            
    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        error_message = str(e)
        
        # エラーメッセージをより分かりやすく
        if "Invalid api_key" in error_message:
            error_message = "無効なAPIキーです。APIキーを確認してください。"
        elif "Signature" in error_message:
            error_message = "無効なAPIシークレットです。APIシークレットを確認してください。"
        elif "Network" in error_message:
            error_message = "ネットワークエラーです。インターネット接続を確認してください。"
        
        return TestConnectionResponse(
            success=False,
            message=error_message
        )