"""
スキャルピング専用APIルーター（シンプル版）
高頻度取引とリアルタイム最適化機能
"""
import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import numpy as np
import pandas as pd

from ..services.bybit_client import get_bybit_client, BybitClient
from ..trading.scalping.scalping_entry_detector import scalping_detector
from ..trading.scalping.rapid_profit_system import rapid_profit_system
from ..trading.scalping.aggressive_stop_system import aggressive_stop_system
from ..trading.scalping.high_frequency_optimizer import hf_optimizer
from ..trading.scalping.performance_tracker import performance_tracker
from ..trading.modes.trading_mode_manager import trading_mode_manager, TradingMode
from ..trading.data.market_data_fetcher import market_data_fetcher

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trading/scalping", tags=["scalping"])

class ScalpingToggleRequest(BaseModel):
    enabled: bool

class ScalpingExecuteRequest(BaseModel):
    symbol: str
    signal: Dict

@router.post("/toggle")
async def toggle_scalping_mode(
    request: ScalpingToggleRequest,
    client: BybitClient = Depends(get_bybit_client)
) -> Dict:
    """
    スキャルピングモードのON/OFF切り替え
    """
    try:
        result = trading_mode_manager.toggle_mode(TradingMode.SCALPING, request.enabled)
        
        if result["success"]:
            logger.info(f"Scalping mode {'enabled' if request.enabled else 'disabled'}")
        
        return result
        
    except Exception as e:
        logger.error(f"Scalping mode toggle failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/signal/{symbol}")
async def get_scalping_signal(
    symbol: str,
    client: BybitClient = Depends(get_bybit_client)
) -> Dict:
    """
    スキャルピングエントリーシグナル取得
    """
    try:
        # スキャルピングモードがアクティブかチェック
        if not trading_mode_manager.is_mode_active(TradingMode.SCALPING):
            return {
                "signal": {
                    "action": "WAIT",
                    "confidence": 0.0,
                    "entry_price": 0.0,
                    "stop_loss": 0.0,
                    "take_profit": [],
                    "position_size_multiplier": 0.0,
                    "speed_score": 0.0,
                    "risk_reward_ratio": 0.0,
                    "expected_duration_minutes": 0,
                    "entry_reasons": [{
                        "factor": "モード無効",
                        "score": 0.0,
                        "description": "スキャルピングモードが無効です"
                    }],
                    "invalidation_price": 0.0,
                    "metadata": {
                        "reason": "Scalping mode disabled",
                        "timestamp": datetime.now().isoformat()
                    }
                }
            }
        
        # シンプルなモックデータ生成
        price_data = await _get_simple_price_data(symbol)
        orderbook_data = await _get_simple_orderbook_data(symbol)
        volume_data = await _get_simple_volume_data(symbol)
        
        # スキャルピングシグナル検出
        signal = await scalping_detector.detect_scalping_entry(
            symbol, price_data, orderbook_data, volume_data
        )
        
        return {
            "signal": {
                "action": signal.action,
                "confidence": signal.confidence,
                "entry_price": signal.entry_price,
                "stop_loss": signal.stop_loss,
                "take_profit": signal.take_profit,
                "position_size_multiplier": signal.position_size_multiplier,
                "speed_score": signal.speed_score,
                "risk_reward_ratio": signal.risk_reward_ratio,
                "expected_duration_minutes": signal.expected_duration_minutes,
                "entry_reasons": signal.entry_reasons,
                "invalidation_price": signal.invalidation_price,
                "metadata": signal.metadata
            }
        }
        
    except Exception as e:
        logger.error(f"Scalping signal generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/execute")
async def execute_scalping_entry(
    request: ScalpingExecuteRequest,
    client: BybitClient = Depends(get_bybit_client)
) -> Dict:
    """
    スキャルピングエントリー実行
    """
    try:
        symbol = request.symbol
        signal = request.signal
        
        # ポジション開始可能かチェック
        can_open = trading_mode_manager.can_open_position(TradingMode.SCALPING)
        if not can_open["can_open"]:
            return {
                "success": False,
                "error": can_open["reason"]
            }
        
        # 口座残高取得
        account_info = await client.get_account_balance()
        account_balance = float(account_info.get('balance', 0))
        
        # ポジションサイズ計算
        position_size = trading_mode_manager.get_position_size(
            TradingMode.SCALPING, account_balance
        )
        
        # 数量の小数点精度を調整（Bybitの要件に合わせて）
        quantity = position_size / signal["entry_price"]
        
        # シンボルごとの精度調整
        precision_map = {
            'BTCUSDT': 3,
            'ETHUSDT': 3,
            'default': 4
        }
        precision = precision_map.get(symbol, precision_map['default'])
        quantity = round(quantity, precision)
        
        # 高頻度取引最適化
        order_request = {
            "symbol": symbol,
            "side": signal["action"],
            "quantity": quantity,
            "price": signal["entry_price"],
            "order_type": "LIMIT",
            "time_in_force": "GTC"  # Good Till Cancel（より安定）
        }
        
        # 最適化実行
        execution_result = await hf_optimizer.optimize_order_execution(
            order_request, priority="high"
        )
        
        if execution_result["success"]:
            # ポジション登録
            position_info = {
                "symbol": symbol,
                "direction": signal["action"],
                "entry_price": signal["entry_price"],
                "quantity": order_request["quantity"],
                "signal_confidence": signal["confidence"],
                "expected_duration": signal["expected_duration_minutes"]
            }
            
            position_registered = trading_mode_manager.register_position(
                TradingMode.SCALPING, position_info
            )
            
            if position_registered:
                position_id = position_info["position_id"]
                
                # 高速利確システムセットアップ
                await rapid_profit_system.setup_rapid_profit(
                    position_id,
                    signal["entry_price"],
                    order_request["quantity"],
                    signal["action"],
                    signal["expected_duration_minutes"],
                    signal["confidence"]
                )
                
                # アグレッシブ損切りシステムセットアップ
                await aggressive_stop_system.setup_aggressive_stops(
                    position_id,
                    signal["entry_price"],
                    signal["action"],
                    order_request["quantity"],
                    signal["confidence"],
                    signal["expected_duration_minutes"]
                )
                
                logger.info(f"Scalping entry executed: {symbol}, Position ID: {position_id}")
                
                return {
                    "success": True,
                    "position_id": position_id,
                    "execution_details": execution_result,
                    "profit_targets_set": True,
                    "stop_loss_set": True
                }
        
        return {
            "success": False,
            "error": execution_result.get("error", "Execution failed"),
            "execution_details": execution_result
        }
        
    except Exception as e:
        logger.error(f"Scalping execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/performance")
async def get_scalping_performance() -> Dict:
    """
    スキャルピングパフォーマンス取得
    """
    try:
        performance_summary = performance_tracker.get_performance_summary()
        hf_performance = hf_optimizer.get_performance_report()
        
        return {
            **performance_summary,
            "execution_performance": hf_performance
        }
        
    except Exception as e:
        logger.error(f"Performance retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/suggestions")
async def get_optimization_suggestions() -> List[Dict]:
    """
    最適化提案取得
    """
    try:
        suggestions = performance_tracker.get_optimization_suggestions()
        return suggestions
        
    except Exception as e:
        logger.error(f"Suggestions retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/equity-curve")
async def get_equity_curve(period_hours: int = 24) -> List[Dict]:
    """
    エクイティカーブデータ取得
    """
    try:
        equity_data = performance_tracker.get_equity_curve_data(period_hours)
        return equity_data
        
    except Exception as e:
        logger.error(f"Equity curve retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/trade-history")
async def get_trade_history(limit: int = 50) -> List[Dict]:
    """
    取引履歴取得
    """
    try:
        trade_history = performance_tracker.get_trade_history(limit)
        return trade_history
        
    except Exception as e:
        logger.error(f"Trade history retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def get_scalping_status() -> Dict:
    """
    スキャルピングシステム状態取得
    """
    try:
        mode_status = trading_mode_manager.get_status()
        positions_data = rapid_profit_system.get_all_positions()
        active_positions = positions_data.get('positions', {})
        hf_performance = hf_optimizer.get_performance_report()
        
        # 各ポジションの利確・損切り情報を追加
        positions_with_levels = []
        for position_id, position in active_positions.items():
            try:
                # 利確レベル取得
                profit_levels = rapid_profit_system.get_profit_targets(position_id)
            except Exception as e:
                logger.warning(f"Failed to get profit targets for {position_id}: {e}")
                profit_levels = []
            
            try:
                # 損切りレベル取得
                stop_levels = aggressive_stop_system.get_stop_levels(position_id)
            except Exception as e:
                logger.warning(f"Failed to get stop levels for {position_id}: {e}")
                stop_levels = []
            
            positions_with_levels.append({
                **position,
                "position_id": position_id,
                "profit_targets": profit_levels,
                "stop_levels": stop_levels
            })
        
        return {
            "mode_status": mode_status,
            "active_positions": positions_with_levels,
            "execution_performance": hf_performance,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Status retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/clear-positions")
async def clear_positions() -> Dict:
    """
    ポジション情報をクリア（デバッグ用）
    """
    try:
        # スキャルピングモードのポジションをクリア
        trading_mode_manager.active_positions[TradingMode.SCALPING] = []
        trading_mode_manager.active_positions[TradingMode.CONSERVATIVE] = []
        
        # 日次カウンタをリセット
        trading_mode_manager.daily_trades[TradingMode.SCALPING] = 0
        trading_mode_manager.daily_trades[TradingMode.CONSERVATIVE] = 0
        
        logger.info("All positions and daily counters cleared")
        
        return {
            "success": True,
            "message": "ポジション情報をクリアしました",
            "status": trading_mode_manager.get_status()
        }
        
    except Exception as e:
        logger.error(f"Position clearing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# シンプルなヘルパー関数

async def _get_simple_price_data(symbol: str):
    """Bybitから実際の価格データを取得"""
    try:
        # market_data_fetcherを初期化
        market_data_fetcher.initialize()
        
        # 実際のKLineデータを取得（1分足、100本）
        df = await market_data_fetcher.get_kline_data(symbol, interval='1', limit=100)
        
        # データが有効か確認
        if df is not None and not df.empty:
            logger.info(f"Successfully fetched {len(df)} candles for {symbol}")
            return df
        else:
            logger.warning(f"No data received for {symbol}, using mock data")
            return _get_mock_price_data(symbol)
            
    except Exception as e:
        logger.error(f"Failed to fetch price data for {symbol}: {e}")
        return _get_mock_price_data(symbol)

def _get_mock_price_data(symbol: str):
    """モック価格データ生成（フォールバック用）"""
    # 通貨ごとの現実的な価格を設定
    price_map = {
        'BTCUSDT': 50000,
        'ETHUSDT': 3000,
        'BNBUSDT': 400,
        'XRPUSDT': 0.65,
        'SOLUSDT': 100,
        'ADAUSDT': 0.5,
        'MATICUSDT': 1.0,
        'DOTUSDT': 8.5,
        'AVAXUSDT': 40,
        'LINKUSDT': 15,
        'LTCUSDT': 100,
        'ATOMUSDT': 12,
        'UNIUSDT': 10,
        'NEARUSDT': 5,
        'FTMUSDT': 0.6,
        'ALGOUSDT': 0.25,
        'VETUSDT': 0.03,
        'ICPUSDT': 10,
        'FILUSDT': 6,
        'DOGEUSDT': 0.1
    }
    
    base_price = price_map.get(symbol, 50000)
    
    # 現在の時刻をシードに使用
    current_time = datetime.now()
    random_seed = int(current_time.timestamp() * 1000) % 10000
    np.random.seed(random_seed)
    
    # 価格変動を生成
    price_variation = np.random.uniform(-0.01, 0.01)  # ±1%の変動
    current_price = base_price * (1 + price_variation)
    
    # 100本のOHLCデータを生成
    price_series = []
    volume_series = []
    
    for i in range(100):
        noise = np.random.normal(0, 0.001)  # 0.1%のノイズ
        price = current_price * (1 + noise)
        price_series.append(price)
        
        # ボリュームデータ
        base_volume = 1000
        volume_noise = np.random.normal(0, 0.2)
        volume = base_volume * (1 + volume_noise)
        volume_series.append(max(100, volume))
    
    # 最後の10本でボリューム急増パターンを追加
    if np.random.random() > 0.5:
        for i in range(90, 100):
            volume_series[i] = volume_series[i] * np.random.uniform(1.5, 2.5)
    
    data = {
        'timestamp': [datetime.now().timestamp() - i*60 for i in range(100, 0, -1)],
        'open': price_series,
        'high': [p * 1.001 for p in price_series],
        'low': [p * 0.999 for p in price_series],
        'close': price_series,
        'volume': volume_series
    }
    
    return pd.DataFrame(data)

async def _get_simple_orderbook_data(symbol: str):
    """Bybitから実際のオーダーブックデータを取得"""
    try:
        # market_data_fetcherを初期化
        market_data_fetcher.initialize()
        
        # 実際のオーダーブックデータを取得
        orderbook = await market_data_fetcher.get_orderbook_data(symbol, limit=50)
        
        # データが有効か確認
        if orderbook and 'bids' in orderbook and 'asks' in orderbook:
            logger.info(f"Successfully fetched orderbook for {symbol}")
            return orderbook
        else:
            logger.warning(f"No orderbook data received for {symbol}, using mock data")
            return _get_mock_orderbook_data(symbol)
            
    except Exception as e:
        logger.error(f"Failed to fetch orderbook data for {symbol}: {e}")
        return _get_mock_orderbook_data(symbol)

def _get_mock_orderbook_data(symbol: str):
    """モックオーダーブックデータ生成（フォールバック用）"""
    price_map = {
        'BTCUSDT': 50000,
        'ETHUSDT': 3000,
        'BNBUSDT': 400,
        'XRPUSDT': 0.65,
        'SOLUSDT': 100,
        'ADAUSDT': 0.5,
        'MATICUSDT': 1.0,
        'DOTUSDT': 8.5,
        'AVAXUSDT': 40,
        'LINKUSDT': 15
    }
    
    base_price = price_map.get(symbol, 50000)
    
    # 現在の時刻をシードに使用
    current_time = datetime.now()
    random_seed = int(current_time.timestamp() * 1000) % 10000
    np.random.seed(random_seed + 1)
    
    # 現在価格
    price_variation = np.random.uniform(-0.01, 0.01)
    current_price = base_price * (1 + price_variation)
    
    bids = []
    asks = []
    
    # 不均衡パターン
    imbalance = np.random.choice(['buy', 'sell', 'balanced'], p=[0.4, 0.4, 0.2])
    
    for i in range(10):
        spread = 0.0001 * (i + 1)
        bid_price = current_price * (1 - spread)
        ask_price = current_price * (1 + spread)
        
        base_volume = np.random.uniform(50, 150) * (10 - i)
        
        if imbalance == 'buy':
            bid_volume = base_volume * 2
            ask_volume = base_volume
        elif imbalance == 'sell':
            bid_volume = base_volume
            ask_volume = base_volume * 2
        else:
            bid_volume = base_volume
            ask_volume = base_volume
        
        bids.append([bid_price, bid_volume])
        asks.append([ask_price, ask_volume])
    
    return {
        'bids': bids,
        'asks': asks
    }

async def _get_simple_volume_data(symbol: str):
    """Bybitから実際のボリュームデータを取得"""
    try:
        # market_data_fetcherを初期化
        market_data_fetcher.initialize()
        
        # ティッカーデータから24時間ボリュームを取得
        ticker = await market_data_fetcher.get_ticker_data(symbol)
        
        if ticker and 'volume_24h' in ticker:
            # 最近の取引データも取得
            recent_trades = await market_data_fetcher.get_recent_trades(symbol, limit=100)
            
            # 直近5分のボリュームを計算
            recent_volume = 0
            if recent_trades:
                cutoff_time = datetime.now() - timedelta(minutes=5)
                for trade in recent_trades:
                    if trade['timestamp'] > cutoff_time:
                        recent_volume += trade['quantity']
            
            logger.info(f"Successfully fetched volume data for {symbol}")
            return {
                'volume_24h': ticker['volume_24h'],
                'volume_recent': recent_volume
            }
        else:
            logger.warning(f"No volume data received for {symbol}, using mock data")
            return _get_mock_volume_data(symbol)
            
    except Exception as e:
        logger.error(f"Failed to fetch volume data for {symbol}: {e}")
        return _get_mock_volume_data(symbol)

def _get_mock_volume_data(symbol: str):
    """モックボリュームデータ生成（フォールバック用）"""
    # 現在の時刻をシードに使用
    current_time = datetime.now()
    random_seed = int(current_time.timestamp() * 1000) % 10000
    np.random.seed(random_seed + 2)
    
    base_volume = np.random.uniform(50000, 100000)
    recent_multiplier = np.random.choice([1.0, 1.5, 2.0], p=[0.5, 0.3, 0.2])
    
    return {
        'volume_24h': base_volume,
        'volume_recent': (base_volume / 24) * recent_multiplier
    }