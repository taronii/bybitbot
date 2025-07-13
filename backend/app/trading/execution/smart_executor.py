"""
スマートエントリー実行エンジン
最適なエントリー執行
"""
import asyncio
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging
from datetime import datetime, timedelta
import json

from ..signals.genius_entry import EntrySignal, EntryAction, EntryType

logger = logging.getLogger(__name__)

class OrderType(Enum):
    MARKET = "Market"
    LIMIT = "Limit"
    STOP = "Stop"
    STOP_MARKET = "StopMarket"

@dataclass
class ExecutionResult:
    executed: bool
    order_id: Optional[str]
    entry_price: Optional[float]
    position_size: float
    slippage: float
    execution_time: int  # ミリ秒
    next_actions: List[str]
    error: Optional[str]

@dataclass
class SplitEntry:
    size: float
    price: float
    order_type: OrderType

class SmartEntryExecutor:
    """
    最適なエントリー執行
    """
    
    def __init__(self, session, config: Dict):
        self.session = session
        self.config = config
        self.max_slippage = config.get('max_slippage', 0.001)  # 0.1%
        self.max_position_size = config.get('max_position_size', 10000)  # $10,000
        self.risk_per_trade = config.get('risk_per_trade', 0.02)  # 2%
        
    async def execute_entry(self, signal: EntrySignal, symbol: str, 
                          account_balance: float) -> ExecutionResult:
        """
        エントリーを実行
        
        Parameters:
        -----------
        signal : EntrySignal
            エントリーシグナル
        symbol : str
            取引シンボル
        account_balance : float
            アカウント残高
            
        Returns:
        --------
        ExecutionResult : 実行結果
        """
        start_time = datetime.now()
        
        try:
            # エントリー前の最終チェック
            if not await self._pre_entry_checks(symbol, signal):
                return self._create_failed_result("エントリー前チェックに失敗")
            
            # ポジションサイズを計算
            position_size = self._calculate_position_size(
                signal, account_balance, symbol
            )
            
            # エントリー方法を決定
            order_type, entries = self._determine_entry_method(signal, position_size)
            
            # 注文を実行
            results = []
            for entry in entries:
                result = await self._place_order(
                    symbol, signal.action, entry, signal
                )
                results.append(result)
                
                if not result['success']:
                    logger.error(f"Failed to place order: {result.get('error')}")
                    break
            
            # 実行結果をまとめる
            if any(r['success'] for r in results):
                executed_orders = [r for r in results if r['success']]
                total_size = sum(r['size'] for r in executed_orders)
                avg_price = sum(r['price'] * r['size'] for r in executed_orders) / total_size
                
                # ストップロスを設定
                await self._set_stop_loss(symbol, signal.stop_loss, total_size)
                
                # テイクプロフィットを設定
                await self._set_take_profits(symbol, signal.take_profit, total_size)
                
                execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
                
                return ExecutionResult(
                    executed=True,
                    order_id=executed_orders[0]['order_id'],
                    entry_price=avg_price,
                    position_size=total_size,
                    slippage=abs(avg_price - signal.entry_price) / signal.entry_price,
                    execution_time=execution_time,
                    next_actions=['monitor_position', 'update_trailing_stop'],
                    error=None
                )
            else:
                return self._create_failed_result("全ての注文が失敗しました")
            
        except Exception as e:
            logger.error(f"Failed to execute entry: {e}")
            return self._create_failed_result(str(e))
    
    async def _pre_entry_checks(self, symbol: str, signal: EntrySignal) -> bool:
        """エントリー前の最終チェック"""
        try:
            # 1. 重要ニュースのチェック
            if await self._check_upcoming_news():
                logger.warning("Important news event detected, skipping entry")
                return False
            
            # 2. スプレッドのチェック
            ticker = self.session.get_tickers(
                category="linear",
                symbol=symbol
            )
            
            if ticker["retCode"] == 0:
                data = ticker["result"]["list"][0]
                bid = float(data["bid1Price"])
                ask = float(data["ask1Price"])
                spread = (ask - bid) / bid
                
                if spread > self.max_slippage * 2:
                    logger.warning(f"Spread too wide: {spread:.4%}")
                    return False
            
            # 3. 流動性の確認
            if not await self._check_liquidity(symbol, signal.position_size_multiplier):
                logger.warning("Insufficient liquidity")
                return False
            
            # 4. 相関ポジションのチェック
            if await self._check_correlated_positions(symbol):
                logger.warning("Correlated position already exists")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Pre-entry check failed: {e}")
            return False
    
    async def _check_upcoming_news(self) -> bool:
        """重要ニュースをチェック（簡易版）"""
        # 実際の実装では、経済カレンダーAPIを使用
        return False
    
    async def _check_liquidity(self, symbol: str, size_multiplier: float) -> bool:
        """流動性をチェック"""
        try:
            # オーダーブックを取得
            orderbook = self.session.get_orderbook(
                category="linear",
                symbol=symbol,
                limit=50
            )
            
            if orderbook["retCode"] != 0:
                return False
            
            # ビッド・アスクの深さを確認
            bids = orderbook["result"]["b"]
            asks = orderbook["result"]["a"]
            
            # 想定ポジションサイズに対して十分な流動性があるか
            required_liquidity = self.max_position_size * size_multiplier
            
            bid_liquidity = sum(float(bid[0]) * float(bid[1]) for bid in bids[:10])
            ask_liquidity = sum(float(ask[0]) * float(ask[1]) for ask in asks[:10])
            
            return min(bid_liquidity, ask_liquidity) > required_liquidity * 2
            
        except Exception as e:
            logger.error(f"Liquidity check failed: {e}")
            return True  # エラーの場合はチェックをスキップ
    
    async def _check_correlated_positions(self, symbol: str) -> bool:
        """相関ポジションをチェック"""
        try:
            # 現在のポジションを取得
            positions = self.session.get_positions(
                category="linear",
                settleCoin="USDT"
            )
            
            if positions["retCode"] != 0:
                return False
            
            # 相関通貨ペアのマッピング（簡易版）
            correlations = {
                'BTCUSDT': ['ETHUSDT', 'BNBUSDT'],
                'ETHUSDT': ['BTCUSDT', 'BNBUSDT'],
                # 他の相関ペアを追加
            }
            
            correlated_symbols = correlations.get(symbol, [])
            
            for position in positions["result"]["list"]:
                if position["symbol"] in correlated_symbols and float(position["size"]) > 0:
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Correlation check failed: {e}")
            return False
    
    def _calculate_position_size(self, signal: EntrySignal, 
                               account_balance: float, symbol: str) -> float:
        """ポジションサイズを計算"""
        # リスク額を計算
        risk_amount = account_balance * self.risk_per_trade
        
        # ストップまでの距離
        stop_distance = abs(signal.entry_price - signal.stop_loss) / signal.entry_price
        
        # 基本ポジションサイズ
        base_size = risk_amount / stop_distance
        
        # シグナルの倍率を適用
        position_size = base_size * signal.position_size_multiplier
        
        # 最大サイズを制限
        position_size = min(position_size, self.max_position_size)
        
        # 最小取引単位に調整
        position_size = self._round_to_min_qty(position_size, symbol)
        
        return position_size
    
    def _round_to_min_qty(self, size: float, symbol: str) -> float:
        """最小取引単位に丸める"""
        # シンボルごとの最小単位（実際はAPIから取得）
        min_qtys = {
            'BTCUSDT': 0.001,
            'ETHUSDT': 0.01,
            'default': 0.1
        }
        
        min_qty = min_qtys.get(symbol, min_qtys['default'])
        return round(size / min_qty) * min_qty
    
    def _determine_entry_method(self, signal: EntrySignal, 
                              position_size: float) -> Tuple[OrderType, List[SplitEntry]]:
        """エントリー方法を決定"""
        entries = []
        
        if signal.entry_type == EntryType.PULLBACK:
            # 指値注文でプルバックを待つ
            entries.append(SplitEntry(
                size=position_size,
                price=signal.entry_price,
                order_type=OrderType.LIMIT
            ))
            
        elif signal.entry_type == EntryType.BREAKOUT:
            # ストップ注文でブレイクアウトを捕捉
            entries.append(SplitEntry(
                size=position_size,
                price=signal.entry_price,
                order_type=OrderType.STOP_MARKET
            ))
            
        elif signal.confidence < 0.75:
            # 確信度が低い場合は分割エントリー
            entries = [
                SplitEntry(
                    size=position_size * 0.3,
                    price=signal.entry_price,
                    order_type=OrderType.LIMIT
                ),
                SplitEntry(
                    size=position_size * 0.3,
                    price=signal.entry_price * 0.995,
                    order_type=OrderType.LIMIT
                ),
                SplitEntry(
                    size=position_size * 0.4,
                    price=signal.entry_price * 0.99,
                    order_type=OrderType.LIMIT
                )
            ]
        else:
            # 通常は成行注文
            entries.append(SplitEntry(
                size=position_size,
                price=signal.entry_price,
                order_type=OrderType.MARKET
            ))
        
        return entries[0].order_type, entries
    
    async def _place_order(self, symbol: str, action: EntryAction, 
                         entry: SplitEntry, signal: EntrySignal) -> Dict:
        """注文を実行"""
        try:
            side = "Buy" if action == EntryAction.BUY else "Sell"
            
            order_params = {
                "category": "linear",
                "symbol": symbol,
                "side": side,
                "orderType": entry.order_type.value,
                "qty": str(entry.size),
                "timeInForce": "GTC",
                "positionIdx": 0,  # One-way mode
                "reduceOnly": False
            }
            
            # 注文タイプに応じてパラメータを追加
            if entry.order_type == OrderType.LIMIT:
                order_params["price"] = str(entry.price)
            elif entry.order_type in [OrderType.STOP, OrderType.STOP_MARKET]:
                order_params["stopPrice"] = str(entry.price)
                order_params["triggerBy"] = "LastPrice"
            
            # 注文を送信
            response = self.session.place_order(**order_params)
            
            if response["retCode"] == 0:
                order_data = response["result"]
                return {
                    'success': True,
                    'order_id': order_data["orderId"],
                    'price': float(order_data.get("price", entry.price)),
                    'size': entry.size
                }
            else:
                return {
                    'success': False,
                    'error': response["retMsg"]
                }
                
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _set_stop_loss(self, symbol: str, stop_price: float, position_size: float):
        """ストップロスを設定"""
        try:
            # ポジション情報を取得して方向を確認
            positions = self.session.get_positions(
                category="linear",
                symbol=symbol
            )
            
            if positions["retCode"] != 0:
                return
            
            for position in positions["result"]["list"]:
                if float(position["size"]) > 0:
                    side = "Sell" if position["side"] == "Buy" else "Buy"
                    
                    # ストップロス注文
                    sl_order = self.session.place_order(
                        category="linear",
                        symbol=symbol,
                        side=side,
                        orderType="StopMarket",
                        qty=str(position_size),
                        stopPrice=str(stop_price),
                        triggerBy="LastPrice",
                        timeInForce="GTC",
                        positionIdx=0,
                        reduceOnly=True
                    )
                    
                    if sl_order["retCode"] == 0:
                        logger.info(f"Stop loss set at {stop_price}")
                    else:
                        logger.error(f"Failed to set stop loss: {sl_order['retMsg']}")
                        
        except Exception as e:
            logger.error(f"Failed to set stop loss: {e}")
    
    async def _set_take_profits(self, symbol: str, take_profits: List[float], 
                               position_size: float):
        """テイクプロフィットを設定"""
        try:
            if not take_profits:
                return
            
            # ポジション情報を取得
            positions = self.session.get_positions(
                category="linear",
                symbol=symbol
            )
            
            if positions["retCode"] != 0:
                return
            
            for position in positions["result"]["list"]:
                if float(position["size"]) > 0:
                    side = "Sell" if position["side"] == "Buy" else "Buy"
                    
                    # 各TPに対して部分決済注文を設定
                    tp_size = position_size / len(take_profits)
                    
                    for i, tp_price in enumerate(take_profits):
                        tp_order = self.session.place_order(
                            category="linear",
                            symbol=symbol,
                            side=side,
                            orderType="Limit",
                            qty=str(tp_size),
                            price=str(tp_price),
                            timeInForce="GTC",
                            positionIdx=0,
                            reduceOnly=True
                        )
                        
                        if tp_order["retCode"] == 0:
                            logger.info(f"Take profit {i+1} set at {tp_price}")
                        else:
                            logger.error(f"Failed to set TP {i+1}: {tp_order['retMsg']}")
                            
        except Exception as e:
            logger.error(f"Failed to set take profits: {e}")
    
    def _create_failed_result(self, error: str) -> ExecutionResult:
        """失敗結果を作成"""
        return ExecutionResult(
            executed=False,
            order_id=None,
            entry_price=None,
            position_size=0.0,
            slippage=0.0,
            execution_time=0,
            next_actions=[],
            error=error
        )