from fastapi import APIRouter, HTTPException
from app.routers.settings import load_settings
from pybit.unified_trading import HTTP
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/debug", tags=["debug"])

@router.get("/test-connection")
async def test_connection_debug():
    """デバッグ用: API接続の詳細テスト"""
    settings = load_settings()
    if not settings:
        return {"error": "No API settings found"}
    
    try:
        session = HTTP(
            testnet=settings.testnet,
            api_key=settings.apiKey,
            api_secret=settings.apiSecret,
        )
        
        # APIキー情報を取得
        api_key_info = session.get_api_key_information()
        
        # ウォレット情報を取得
        wallet_info = session.get_wallet_balance(accountType="UNIFIED")
        
        # アカウント情報を取得
        account_info = session.get_account_info()
        
        return {
            "connection": "success",
            "testnet": settings.testnet,
            "api_key_info": api_key_info,
            "wallet_info": wallet_info,
            "account_info": account_info
        }
        
    except Exception as e:
        logger.error(f"Debug test failed: {e}")
        return {
            "connection": "failed",
            "error": str(e),
            "testnet": settings.testnet
        }