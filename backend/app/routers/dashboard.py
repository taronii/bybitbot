from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from datetime import datetime, timedelta
from pybit.unified_trading import HTTP
from app.routers.settings import load_settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

def get_bybit_client():
    """Bybit APIクライアントを取得"""
    settings = load_settings()
    if not settings:
        raise HTTPException(status_code=400, detail="API設定が見つかりません")
    
    try:
        return HTTP(
            testnet=settings.testnet,
            api_key=settings.apiKey,
            api_secret=settings.apiSecret,
        )
    except Exception as e:
        logger.error(f"Failed to create Bybit client: {e}")
        raise HTTPException(status_code=500, detail="APIクライアントの作成に失敗しました")

@router.get("")
async def get_dashboard_data():
    """ダッシュボードデータを取得"""
    try:
        session = get_bybit_client()
        
        # アカウント残高を取得
        account_balance = 0
        total_wallet_balance = 0
        
        try:
            # ウォレット残高を取得（標準的な方法）
            wallet_response = session.get_wallet_balance(accountType="UNIFIED")
            
            if wallet_response["retCode"] == 0 and wallet_response["result"]["list"]:
                wallet_data = wallet_response["result"]["list"][0]
                account_balance = float(wallet_data.get("totalEquity", 0))
                total_wallet_balance = float(wallet_data.get("totalWalletBalance", 0))
                logger.info(f"Account balance: {account_balance}, Wallet balance: {total_wallet_balance}")
            else:
                logger.warning(f"Failed to get wallet balance: {wallet_response}")
                
        except Exception as e:
            logger.error(f"Failed to get account balance: {e}")
            account_balance = 0
        
        # ポジション情報を取得
        positions_response = session.get_positions(
            category="linear",
            settleCoin="USDT"
        )
        
        open_positions = []
        total_unrealized_pnl = 0
        
        if positions_response["retCode"] == 0:
            for pos in positions_response["result"]["list"][:10]:  # 最大10件
                if float(pos.get("size", 0)) > 0:  # ポジションがある場合のみ
                    unrealized_pnl = float(pos.get("unrealisedPnl", 0))
                    total_unrealized_pnl += unrealized_pnl
                    
                    open_positions.append({
                        "id": pos.get("positionIdx", ""),
                        "symbol": pos.get("symbol", ""),
                        "side": pos.get("side", ""),
                        "size": float(pos.get("size", 0)),
                        "entryPrice": float(pos.get("avgPrice", 0)),
                        "currentPrice": float(pos.get("markPrice", 0)),
                        "unrealizedPnL": unrealized_pnl,
                        "timestamp": pos.get("createdTime", datetime.now().isoformat())
                    })
        
        # 最近の取引履歴を取得
        trades_response = session.get_executions(
            category="linear",
            limit=20
        )
        
        recent_trades = []
        today_pnl = 0
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        if trades_response["retCode"] == 0:
            for trade in trades_response["result"]["list"][:10]:  # 最大10件
                trade_time = datetime.fromtimestamp(int(trade.get("execTime", 0)) / 1000)
                realized_pnl = float(trade.get("closedPnl", 0))
                
                # 今日の損益を計算
                if trade_time >= today_start:
                    today_pnl += realized_pnl
                
                recent_trades.append({
                    "id": trade.get("execId", ""),
                    "symbol": trade.get("symbol", ""),
                    "side": trade.get("side", ""),
                    "quantity": float(trade.get("execQty", 0)),
                    "price": float(trade.get("execPrice", 0)),
                    "fee": float(trade.get("execFee", 0)),
                    "realizedPnL": realized_pnl,
                    "timestamp": trade_time.isoformat()
                })
        
        # PnL履歴から総損益を計算
        total_pnl = total_unrealized_pnl  # まず未実現損益を設定
        
        try:
            # 決済済み損益を取得
            pnl_response = session.get_closed_pnl(
                category="linear",
                limit=200
            )
            
            if pnl_response["retCode"] == 0:
                for pnl in pnl_response["result"]["list"]:
                    total_pnl += float(pnl.get("closedPnl", 0))
        except Exception as e:
            logger.warning(f"Failed to get PnL history: {e}")
            # エラーの場合は取引履歴から計算
            total_pnl += sum(trade["realizedPnL"] for trade in recent_trades)
        
        return {
            "accountBalance": account_balance,
            "totalPnL": total_pnl,
            "todayPnL": today_pnl,
            "openPositions": open_positions,
            "recentTrades": recent_trades,
            "systemStatus": "running"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch dashboard data: {e}", exc_info=True)
        
        # エラー時は詳細なエラー情報を含める
        return {
            "accountBalance": 0,
            "totalPnL": 0,
            "todayPnL": 0,
            "openPositions": [],
            "recentTrades": [],
            "systemStatus": "error",
            "error": str(e)
        }