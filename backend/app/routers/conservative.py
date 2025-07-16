"""
慎重モード専用APIルーター
利確・損切り情報の提供とポジション管理
"""
import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..services.bybit_client import get_bybit_client, BybitClient
from ..trading.conservative.conservative_profit_system import conservative_profit_system
from ..trading.conservative.conservative_stop_system import conservative_stop_system
from ..trading.modes.trading_mode_manager import trading_mode_manager, TradingMode
from ..services.position_sync import position_sync_service
from ..trading.portfolio_manager import portfolio_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trading/conservative", tags=["conservative"])

class ConservativePositionRequest(BaseModel):
    """慎重モードポジション設定リクエスト"""
    position_id: str
    symbol: str
    entry_price: float
    position_size: float
    direction: str
    stop_loss: float
    confidence: float

@router.get("/status")
async def get_conservative_status() -> Dict:
    """
    慎重モードのステータス取得
    ポジション情報と利確・損切りレベルを含む
    """
    try:
        # モード状態を取得
        mode_status = trading_mode_manager.get_status()
        conservative_status = mode_status['modes'].get('conservative', {})
        
        # アクティブポジションを取得
        positions = []
        
        # conservative_profit_systemから直接ポジションを取得
        for pos_id, position in conservative_profit_system.active_positions.items():
                # 利確レベルを取得
                profit_targets = conservative_profit_system.get_profit_targets(pos_id)
                
                # 損切りレベルを取得
                stop_levels = conservative_stop_system.get_stop_levels(pos_id)
                
                # 追加情報を取得
                profit_info = conservative_profit_system.get_position_info(pos_id)
                
                positions.append({
                    "position_id": pos_id,
                    "symbol": position.get('symbol', 'N/A'),
                    "direction": position.get('direction', 'N/A'),
                    "entry_price": position.get('entry_price', 0),
                    "quantity": position.get('position_size', 0),
                    "current_profit": profit_info.get('current_profit', 0) if profit_info else 0,
                    "max_profit": profit_info.get('max_profit', 0) if profit_info else 0,
                    "profit_targets": profit_targets,
                    "stop_levels": stop_levels,
                    "trailing_stop": profit_info.get('trailing_stop') if profit_info else None,
                    "entry_time": position.get('entry_time', '').isoformat() if isinstance(position.get('entry_time'), datetime) else str(position.get('entry_time', '')),
                    "confidence": position.get('confidence', 0)
                })
        
        return {
            "mode_status": conservative_status,
            "active_positions": positions,
            "position_count": len(positions),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Conservative status retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/setup-position")
async def setup_conservative_position(
    request: ConservativePositionRequest
) -> Dict:
    """
    慎重モードのポジション設定
    利確・損切りレベルを設定
    """
    try:
        # 利確システムの設定
        profit_result = await conservative_profit_system.setup_conservative_profit(
            position_id=request.position_id,
            symbol=request.symbol,
            entry_price=request.entry_price,
            position_size=request.position_size,
            direction=request.direction,
            stop_loss=request.stop_loss,
            confidence=request.confidence
        )
        
        # 損切りシステムの設定
        stop_result = await conservative_stop_system.setup_conservative_stops(
            position_id=request.position_id,
            symbol=request.symbol,
            entry_price=request.entry_price,
            direction=request.direction,
            position_size=request.position_size,
            initial_stop_loss=request.stop_loss,
            confidence=request.confidence
        )
        
        if profit_result['success'] and stop_result['success']:
            return {
                "success": True,
                "position_id": request.position_id,
                "profit_targets": conservative_profit_system.get_profit_targets(request.position_id),
                "stop_levels": conservative_stop_system.get_stop_levels(request.position_id),
                "message": "慎重モードポジション設定完了"
            }
        else:
            return {
                "success": False,
                "error": "ポジション設定に失敗しました"
            }
            
    except Exception as e:
        logger.error(f"Conservative position setup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/position/{position_id}")
async def get_conservative_position(position_id: str) -> Dict:
    """
    特定のポジション詳細を取得
    """
    try:
        # 利確情報を取得
        profit_info = conservative_profit_system.get_position_info(position_id)
        profit_targets = conservative_profit_system.get_profit_targets(position_id)
        
        # 損切り情報を取得
        stop_levels = conservative_stop_system.get_stop_levels(position_id)
        
        if not profit_info:
            raise HTTPException(status_code=404, detail="Position not found")
        
        return {
            "position_id": position_id,
            "symbol": profit_info['symbol'],
            "direction": profit_info['direction'],
            "entry_price": profit_info['entry_price'],
            "position_size": profit_info['position_size'],
            "remaining_size": profit_info['remaining_size'],
            "current_profit": profit_info['current_profit'],
            "max_profit": profit_info['max_profit'],
            "profit_locked": profit_info['profit_locked'],
            "profit_targets": profit_targets,
            "stop_levels": stop_levels,
            "trailing_stop": profit_info['trailing_stop']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Position retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/check-conditions/{position_id}")
async def check_position_conditions(
    position_id: str,
    current_price: float,
    client: BybitClient = Depends(get_bybit_client)
) -> Dict:
    """
    ポジションの利確・損切り条件をチェック
    """
    try:
        # 市場データを取得（簡易版）
        market_data = {
            "current_price": current_price,
            "timestamp": datetime.now()
        }
        
        # 利確条件をチェック
        profit_action = await conservative_profit_system.check_profit_conditions(
            position_id, current_price, market_data
        )
        
        # 損切り条件をチェック
        stop_action = await conservative_stop_system.check_stop_conditions(
            position_id, current_price, market_data
        )
        
        return {
            "position_id": position_id,
            "current_price": current_price,
            "profit_action": profit_action,
            "stop_action": stop_action,
            "should_close": profit_action['action'] != 'NONE' or stop_action['action'] != 'NONE'
        }
        
    except Exception as e:
        logger.error(f"Condition check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cleanup-position/{position_id}")
async def cleanup_conservative_position(position_id: str) -> Dict:
    """
    ポジションのクリーンアップ
    """
    try:
        # 利確システムのクリーンアップ
        profit_cleanup = conservative_profit_system.cleanup_position(position_id)
        
        # 損切りシステムのクリーンアップ
        stop_cleanup = conservative_stop_system.cleanup_position(position_id)
        
        return {
            "success": profit_cleanup and stop_cleanup,
            "position_id": position_id,
            "message": "ポジションクリーンアップ完了"
        }
        
    except Exception as e:
        logger.error(f"Position cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/summary")
async def get_conservative_summary() -> Dict:
    """
    慎重モードのサマリー情報を取得
    """
    try:
        # 全ポジション情報を取得
        all_positions = conservative_profit_system.get_all_positions()
        
        # 統計情報を計算
        total_positions = all_positions['count']
        total_profit = 0
        positions_in_profit = 0
        
        for pos_id, position in all_positions['positions'].items():
            if position['current_profit'] > 0:
                positions_in_profit += 1
            total_profit += position['current_profit']
        
        return {
            "total_positions": total_positions,
            "positions_in_profit": positions_in_profit,
            "positions_in_loss": total_positions - positions_in_profit,
            "average_profit": total_profit / total_positions if total_positions > 0 else 0,
            "mode_enabled": trading_mode_manager.is_mode_active(TradingMode.CONSERVATIVE),
            "can_open_new": trading_mode_manager.can_open_position(TradingMode.CONSERVATIVE)['can_open']
        }
        
    except Exception as e:
        logger.error(f"Summary retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))