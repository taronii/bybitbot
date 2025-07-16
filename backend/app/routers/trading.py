"""
Trading router - エントリーシグナルとトレーディング機能
"""
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Dict, List, Optional
import asyncio
import json
import logging
from datetime import datetime

from ..trading.signals.genius_entry import GeniusEntrySignalGenerator, EntrySignal
from ..trading.entry_executor import SmartEntryExecutor
from ..trading.portfolio_manager import portfolio_manager, PortfolioPosition
from ..services.bybit_client import get_bybit_client
from ..models import BybitClient
from ..trading.modes.trading_mode_manager import trading_mode_manager, TradingMode

logger = logging.getLogger(__name__)

router = APIRouter()

# WebSocket接続を管理
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                pass

manager = ConnectionManager()

@router.get("/entry-signal/{symbol}")
async def get_entry_signal(
    symbol: str,
    client: BybitClient = Depends(get_bybit_client)
) -> Dict:
    """
    指定されたシンボルのエントリーシグナルを取得
    """
    try:
        # クライアントが設定されているか確認
        if not client or not client.session:
            raise HTTPException(status_code=400, detail="Bybit APIが設定されていません")
        
        # シグナルジェネレーターを初期化
        signal_generator = GeniusEntrySignalGenerator(client.session)
        
        # エントリーシグナルを生成
        signal = await signal_generator.generate_entry_signal(symbol)
        
        # シグナルをシリアライズ可能な形式に変換
        signal_dict = {
            "action": signal.action.value,
            "confidence": signal.confidence,
            "entry_type": signal.entry_type.value,
            "entry_price": signal.entry_price,
            "position_size_multiplier": signal.position_size_multiplier,
            "reasons": signal.reasons,
            "invalidation_price": signal.invalidation_price,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "metadata": signal.metadata
        }
        
        # WebSocket経由でブロードキャスト
        await manager.broadcast(json.dumps({
            "type": "entry_signal",
            "symbol": symbol,
            "signal": signal_dict,
            "timestamp": datetime.now().isoformat()
        }))
        
        return {
            "symbol": symbol,
            "signal": signal_dict,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to generate entry signal: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class ExecuteEntryRequest(BaseModel):
    symbol: str
    signal: Dict

@router.post("/execute-entry")
async def execute_entry(
    request: ExecuteEntryRequest,
    client: BybitClient = Depends(get_bybit_client)
) -> Dict:
    """
    エントリーシグナルを実行
    """
    logger.info(f"Execute entry called for {request.symbol} with signal: {request.signal}")
    try:
        # クライアントが設定されているか確認
        if not client or not client.session:
            raise HTTPException(status_code=400, detail="Bybit APIが設定されていません")
        
        # アカウント残高を取得
        wallet = client.session.get_wallet_balance(
            accountType="UNIFIED",
            coin="USDT"
        )
        
        if wallet["retCode"] != 0:
            raise HTTPException(status_code=400, detail="ウォレット情報の取得に失敗しました")
        
        account_balance = float(wallet["result"]["list"][0]["totalEquity"])
        
        # エントリー実行エンジンを初期化
        executor = SmartEntryExecutor(
            client.session,
            {
                "max_slippage": 0.001,
                "max_position_size": 10000,
                "risk_per_trade": 0.02
            }
        )
        
        # シグナルを再構築
        from ..trading.signals.genius_entry import EntrySignal, EntryAction, EntryType
        
        signal = request.signal
        symbol = request.symbol
        
        entry_signal = EntrySignal(
            action=EntryAction(signal["action"]),
            confidence=signal["confidence"],
            entry_type=EntryType(signal["entry_type"]),
            entry_price=signal["entry_price"],
            position_size_multiplier=signal["position_size_multiplier"],
            reasons=signal["reasons"],
            invalidation_price=signal["invalidation_price"],
            stop_loss=signal["stop_loss"],
            take_profit=signal["take_profit"],
            metadata=signal["metadata"]
        )
        
        # ポートフォリオマネージャーでポジション開設可能かチェック
        portfolio_manager.total_portfolio_value = account_balance
        position_check = await portfolio_manager.can_open_position(
            symbol,
            account_balance * 0.02,  # リスク金額
            account_balance * signal["position_size_multiplier"] * 0.1  # ポジションサイズ
        )
        
        if not position_check['allowed']:
            return {
                "result": {
                    "executed": False,
                    "error": position_check['reason']
                }
            }
        
        # エントリーを実行
        result = await executor.execute_entry(symbol, entry_signal, account_balance)
        
        # 実行成功時はポートフォリオに追加
        if result["executed"]:
            position = PortfolioPosition(
                symbol=symbol,
                side=signal["action"],
                entry_price=result["entry_price"],
                current_price=result["entry_price"],
                quantity=result["position_size"],
                stop_loss=signal["stop_loss"],
                take_profit=signal["take_profit"],
                entry_time=datetime.now()
            )
            portfolio_manager.add_position(position)
            
            # 慎重モードの場合、専用の利確・損切りシステムを設定
            if trading_mode_manager.is_mode_active(TradingMode.CONSERVATIVE):
                from ..trading.conservative.conservative_profit_system import conservative_profit_system
                from ..trading.conservative.conservative_stop_system import conservative_stop_system
                
                position_id = f"conservative_{symbol}_{datetime.now().timestamp()}"
                
                # 利確システムの設定
                await conservative_profit_system.setup_conservative_profit(
                    position_id=position_id,
                    symbol=symbol,
                    entry_price=result["entry_price"],
                    position_size=result["position_size"],
                    direction=signal["action"],
                    stop_loss=signal["stop_loss"],
                    confidence=signal["confidence"]
                )
                
                # 損切りシステムの設定
                await conservative_stop_system.setup_conservative_stops(
                    position_id=position_id,
                    symbol=symbol,
                    entry_price=result["entry_price"],
                    direction=signal["action"],
                    position_size=result["position_size"],
                    initial_stop_loss=signal["stop_loss"],
                    confidence=signal["confidence"]
                )
                
                # ポジション情報を更新
                position_info = {
                    "symbol": symbol,
                    "direction": signal["action"],
                    "entry_price": result["entry_price"],
                    "quantity": result["position_size"],
                    "position_id": position_id,
                    "signal_confidence": signal["confidence"],
                    "expected_duration": 1440,  # 24時間（慎重モード）
                    "mode": "conservative"
                }
                
                # trading_mode_managerに登録
                trading_mode_manager.register_position(TradingMode.CONSERVATIVE, position_info)
                
                # position_syncを強制実行して即座に同期
                from ..services.position_sync import position_sync_service
                await position_sync_service.force_sync()
        
        # 結果をシリアライズ可能な形式に変換
        result_dict = result
        
        # WebSocket経由でブロードキャスト
        await manager.broadcast(json.dumps({
            "type": "execution_result",
            "symbol": symbol,
            "result": result_dict,
            "timestamp": datetime.now().isoformat()
        }))
        
        return {
            "symbol": symbol,
            "result": result_dict,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to execute entry: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/market-analysis/{symbol}")
async def get_market_analysis(
    symbol: str,
    client: BybitClient = Depends(get_bybit_client)
) -> Dict:
    """
    市場分析の詳細を取得
    """
    try:
        # クライアントが設定されているか確認
        if not client or not client.session:
            raise HTTPException(status_code=400, detail="Bybit APIが設定されていません")
        
        # 各種分析を実行
        signal_generator = GeniusEntrySignalGenerator(client.session)
        
        # 価格データを取得
        df = await signal_generator._fetch_price_data(symbol)
        if df is None:
            raise HTTPException(status_code=400, detail="価格データの取得に失敗しました")
        
        # 並列で分析を実行
        tasks = [
            signal_generator._run_regime_analysis(df),
            signal_generator._run_mtf_analysis(symbol),
            signal_generator._run_smart_money_analysis(symbol),
            signal_generator._run_pattern_analysis(symbol, df)
        ]
        
        results = await asyncio.gather(*tasks)
        
        return {
            "symbol": symbol,
            "regime_analysis": {
                "regime": results[0].regime.value,
                "trend_direction": results[0].trend_direction,
                "trend_strength": results[0].trend_strength,
                "volatility_level": results[0].volatility_level.value,
                "liquidity_score": results[0].liquidity_score,
                "confidence": results[0].confidence
            },
            "mtf_analysis": results[1],
            "smart_money_analysis": {
                "direction": results[2]["smart_money_direction"].value,
                "order_flow_imbalance": results[2]["order_flow_imbalance"],
                "confidence": results[2]["confidence"],
                "large_orders_count": results[2]["large_orders"].get("large_orders_count", 0)
            },
            "pattern_analysis": {
                "detected_patterns": [
                    {
                        "name": p.name,
                        "type": p.pattern_type,
                        "confidence": p.confidence,
                        "expected_move": p.expected_move
                    }
                    for p in results[3]["detected_patterns"]
                ],
                "ml_prediction": {
                    "direction": results[3]["ml_prediction"].direction,
                    "confidence": results[3]["ml_prediction"].confidence,
                    "expected_return": results[3]["ml_prediction"].expected_return
                },
                "trading_bias": results[3]["trading_bias"]
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get market analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.websocket("/ws/signals")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocketエンドポイント - リアルタイムシグナル配信
    """
    await manager.connect(websocket)
    try:
        while True:
            # クライアントからのメッセージを待つ
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("action") == "subscribe":
                symbols = message.get("symbols", [])
                # サブスクライブメッセージを送信
                await websocket.send_text(json.dumps({
                    "type": "subscribed",
                    "symbols": symbols,
                    "timestamp": datetime.now().isoformat()
                }))
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# 定期的なシグナルチェック（バックグラウンドタスク）
async def periodic_signal_check(symbols: List[str], interval: int = 60):
    """
    定期的にシグナルをチェック
    """
    while True:
        try:
            client = get_bybit_client()
            if client and client.session:
                signal_generator = GeniusEntrySignalGenerator(client.session)
                
                for symbol in symbols:
                    try:
                        signal = await signal_generator.generate_entry_signal(symbol)
                        
                        # 強いシグナルの場合のみ通知
                        if signal.confidence >= 0.65 and signal.action.value != "WAIT":
                            signal_dict = {
                                "action": signal.action.value,
                                "confidence": signal.confidence,
                                "entry_type": signal.entry_type.value,
                                "entry_price": signal.entry_price,
                                "position_size_multiplier": signal.position_size_multiplier,
                                "reasons": signal.reasons,
                                "invalidation_price": signal.invalidation_price,
                                "stop_loss": signal.stop_loss,
                                "take_profit": signal.take_profit,
                                "metadata": signal.metadata
                            }
                            
                            await manager.broadcast(json.dumps({
                                "type": "alert",
                                "symbol": symbol,
                                "signal": signal_dict,
                                "timestamp": datetime.now().isoformat()
                            }))
                    except Exception as e:
                        logger.error(f"Error checking signal for {symbol}: {e}")
            
        except Exception as e:
            logger.error(f"Error in periodic signal check: {e}")
        
        await asyncio.sleep(interval)

@router.get("/portfolio/summary")
async def get_portfolio_summary() -> Dict:
    """
    ポートフォリオサマリーを取得
    """
    try:
        summary = portfolio_manager.get_portfolio_summary()
        allocation = portfolio_manager.get_symbol_allocation()
        
        return {
            "summary": summary,
            "allocation": allocation,
            "settings": {
                "max_concurrent_positions": portfolio_manager.settings.max_concurrent_positions,
                "max_portfolio_risk": portfolio_manager.settings.max_portfolio_risk,
                "max_single_position_risk": portfolio_manager.settings.max_single_position_risk
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get portfolio summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/portfolio/recommended-symbols")
async def get_recommended_symbols() -> Dict:
    """
    推奨シンボルを取得（分散投資のため）
    """
    try:
        all_symbols = [
            'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'XRPUSDT', 'SOLUSDT',
            'ADAUSDT', 'DOGEUSDT', 'DOTUSDT', 'LINKUSDT', 'MATICUSDT',
            'AVAXUSDT', 'UNIUSDT', 'ATOMUSDT', 'LTCUSDT', 'NEARUSDT',
            'FTMUSDT', 'ALGOUSDT', 'VETUSDT', 'ICPUSDT', 'FILUSDT'
        ]
        
        recommended = portfolio_manager.get_recommended_symbols(all_symbols)
        
        return {
            "recommended_symbols": recommended,
            "active_symbols": list(portfolio_manager.active_symbols),
            "diversification_score": len(set(g for s in portfolio_manager.active_symbols 
                                          for g, syms in portfolio_manager.currency_groups.items() 
                                          if s in syms)) / len(portfolio_manager.currency_groups) * 100
        }
        
    except Exception as e:
        logger.error(f"Failed to get recommended symbols: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class MultiSymbolSignalRequest(BaseModel):
    symbols: List[str]

@router.post("/multi-symbol-signals")
async def get_multi_symbol_signals(
    request: MultiSymbolSignalRequest,
    client: BybitClient = Depends(get_bybit_client)
) -> Dict:
    """
    複数シンボルのシグナルを一括取得
    """
    try:
        if not client or not client.session:
            raise HTTPException(status_code=400, detail="Bybit APIが設定されていません")
        
        signals = {}
        signal_generator = GeniusEntrySignalGenerator(client.session)
        
        # 並列でシグナルを生成
        tasks = []
        for symbol in request.symbols[:10]:  # 最大10シンボル
            task = signal_generator.generate_entry_signal(symbol)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, symbol in enumerate(request.symbols[:10]):
            if isinstance(results[i], Exception):
                logger.error(f"Failed to generate signal for {symbol}: {results[i]}")
                signals[symbol] = None
            else:
                signal = results[i]
                signals[symbol] = {
                    "action": signal.action.value,
                    "confidence": signal.confidence,
                    "entry_type": signal.entry_type.value,
                    "entry_price": signal.entry_price,
                    "stop_loss": signal.stop_loss,
                    "take_profit": signal.take_profit,
                    "risk_reward_ratio": (signal.take_profit[0] - signal.entry_price) / (signal.entry_price - signal.stop_loss) if signal.take_profit and signal.action.value != "WAIT" else 0
                }
        
        return {
            "signals": signals,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get multi-symbol signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/portfolio/reset")
async def reset_portfolio() -> Dict:
    """
    ポートフォリオをリセット（手動取引後の状態不整合を解消）
    """
    try:
        logger.warning("Portfolio reset requested")
        
        # ポートフォリオマネージャーをリセット
        await portfolio_manager.reset_portfolio()
        
        # position_syncサービスで全ポジションをクリーンアップ
        from ..services.position_sync import position_sync_service
        await position_sync_service.cleanup_all_positions()
        
        # 強制的に同期を実行
        await position_sync_service.force_sync()
        
        return {
            "status": "success",
            "message": "ポートフォリオがリセットされました",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to reset portfolio: {e}")
        raise HTTPException(status_code=500, detail=str(e))