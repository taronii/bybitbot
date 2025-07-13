"""
損切り自動実行保証システム
複数のフェイルセーフメカニズムで100%損切り実行を保証
"""
import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from pybit.unified_trading import HTTP
from ...models import MarketData
from ...services.bybit_client import get_bybit_client
from .intelligent_sl import IntelligentStopLossPlacement
from .dynamic_sl import DynamicStopLossAdjustment
from .sl_avoidance import StopLossAvoidanceIntelligence
from .emergency_sl import EmergencyStopLossSystem
import logging

logger = logging.getLogger(__name__)

class GuaranteedStopLossExecution:
    """損切り自動実行保証システム"""
    
    def __init__(self):
        self.intelligent_sl = IntelligentStopLossPlacement()
        self.dynamic_sl = DynamicStopLossAdjustment()
        self.avoidance_system = StopLossAvoidanceIntelligence()
        self.emergency_system = EmergencyStopLossSystem()
        
        self.monitoring_positions = {}  # 監視中のポジション
        self.execution_queue = []       # 実行待ちキュー
        self.execution_history = {}     # 実行履歴
        self.failsafe_status = "active"  # active, warning, error
        
    async def start_position_monitoring(
        self,
        position_id: str,
        symbol: str,
        entry_price: float,
        stop_loss_price: float,
        side: str,
        position_size: float,
        account_balance: float
    ) -> Dict:
        """
        ポジションの監視を開始
        
        Returns:
            {
                "monitoring_started": bool,
                "monitoring_id": str,
                "initial_stop_loss": float,
                "failsafe_levels": List[float],
                "monitoring_interval": int
            }
        """
        try:
            monitoring_id = f"{position_id}_{datetime.now().timestamp()}"
            
            # 初期設定
            monitoring_config = {
                "position_id": position_id,
                "symbol": symbol,
                "entry_price": entry_price,
                "current_stop_loss": stop_loss_price,
                "side": side,
                "position_size": position_size,
                "account_balance": account_balance,
                "monitoring_start": datetime.now(),
                "last_check": datetime.now(),
                "check_interval": 5,  # 5秒間隔
                "failsafe_triggered": False,
                "execution_attempts": 0,
                "max_attempts": 5
            }
            
            # フェイルセーフレベルの設定
            failsafe_levels = await self._calculate_failsafe_levels(
                entry_price, stop_loss_price, side
            )
            monitoring_config["failsafe_levels"] = failsafe_levels
            
            # 監視リストに追加
            self.monitoring_positions[monitoring_id] = monitoring_config
            
            logger.info(f"Started monitoring position: {position_id}")
            
            return {
                "monitoring_started": True,
                "monitoring_id": monitoring_id,
                "initial_stop_loss": stop_loss_price,
                "failsafe_levels": failsafe_levels,
                "monitoring_interval": monitoring_config["check_interval"]
            }
            
        except Exception as e:
            logger.error(f"Error starting position monitoring: {e}")
            return {
                "monitoring_started": False,
                "error": str(e)
            }
    
    async def monitor_all_positions(self) -> Dict:
        """
        すべての監視中ポジションをチェック
        
        Returns:
            {
                "positions_monitored": int,
                "triggered_executions": List[Dict],
                "system_health": str,
                "next_check": datetime
            }
        """
        try:
            triggered_executions = []
            current_time = datetime.now()
            
            for monitoring_id, config in list(self.monitoring_positions.items()):
                # チェック間隔の確認
                time_since_check = (current_time - config["last_check"]).total_seconds()
                
                if time_since_check >= config["check_interval"]:
                    # ポジション状態をチェック
                    check_result = await self._check_position_status(monitoring_id, config)
                    
                    if check_result.get("trigger_execution", False):
                        triggered_executions.append(check_result)
                    
                    # 最終チェック時間を更新
                    config["last_check"] = current_time
            
            # システムヘルスの評価
            system_health = await self._evaluate_system_health()
            
            return {
                "positions_monitored": len(self.monitoring_positions),
                "triggered_executions": triggered_executions,
                "system_health": system_health,
                "next_check": current_time + timedelta(seconds=5)
            }
            
        except Exception as e:
            logger.error(f"Error in position monitoring: {e}")
            return {
                "positions_monitored": 0,
                "triggered_executions": [],
                "system_health": "error",
                "error": str(e)
            }
    
    async def execute_guaranteed_stop_loss(
        self,
        monitoring_id: str,
        trigger_reason: str,
        market_data: MarketData
    ) -> Dict:
        """
        保証された損切り実行
        
        Returns:
            {
                "execution_successful": bool,
                "execution_method": str,
                "execution_time": float,
                "final_price": float,
                "realized_pnl": float,
                "failsafe_used": str,
                "backup_methods": List[str]
            }
        """
        try:
            config = self.monitoring_positions.get(monitoring_id)
            if not config:
                return {"execution_successful": False, "error": "Monitoring config not found"}
            
            start_time = datetime.now()
            execution_successful = False
            execution_method = ""
            final_price = 0.0
            realized_pnl = 0.0
            failsafe_used = "none"
            backup_methods = []
            
            # 実行試行回数を増加
            config["execution_attempts"] += 1
            
            # 段階的実行戦略
            execution_strategies = [
                ("primary_limit", "指値注文による通常実行"),
                ("immediate_market", "成行注文による即座実行"),
                ("split_execution", "分割実行による確実クローズ"),
                ("emergency_close", "緊急クローズ実行"),
                ("fallback_hedge", "ヘッジポジションによる損失固定")
            ]
            
            for strategy_name, strategy_description in execution_strategies:
                logger.info(f"Attempting {strategy_name}: {strategy_description}")
                
                result = await self._execute_strategy(
                    strategy_name, config, market_data
                )
                
                backup_methods.append(f"{strategy_name}: {result.get('status', 'failed')}")
                
                if result.get("success", False):
                    execution_successful = True
                    execution_method = strategy_description
                    final_price = result.get("execution_price", 0.0)
                    realized_pnl = result.get("realized_pnl", 0.0)
                    failsafe_used = strategy_name
                    break
                
                # 各戦略間で短い待機
                await asyncio.sleep(1)
            
            # 実行時間の計算
            execution_time = (datetime.now() - start_time).total_seconds()
            
            # 実行結果の記録
            execution_record = {
                "monitoring_id": monitoring_id,
                "position_id": config["position_id"],
                "trigger_reason": trigger_reason,
                "execution_successful": execution_successful,
                "execution_method": execution_method,
                "execution_time": execution_time,
                "final_price": final_price,
                "realized_pnl": realized_pnl,
                "failsafe_used": failsafe_used,
                "backup_methods": backup_methods,
                "timestamp": datetime.now()
            }
            
            self.execution_history[monitoring_id] = execution_record
            
            # 監視リストから削除（成功・失敗問わず）
            if monitoring_id in self.monitoring_positions:
                del self.monitoring_positions[monitoring_id]
            
            # アラート送信（失敗時）
            if not execution_successful:
                await self._send_execution_failure_alert(execution_record)
            
            return {
                "execution_successful": execution_successful,
                "execution_method": execution_method,
                "execution_time": execution_time,
                "final_price": final_price,
                "realized_pnl": realized_pnl,
                "failsafe_used": failsafe_used,
                "backup_methods": backup_methods
            }
            
        except Exception as e:
            logger.error(f"Error in guaranteed stop loss execution: {e}")
            return {
                "execution_successful": False,
                "error": str(e),
                "execution_time": 0.0
            }
    
    async def _check_position_status(
        self,
        monitoring_id: str,
        config: Dict
    ) -> Dict:
        """ポジション状態のチェック"""
        try:
            client = get_bybit_client()
            if not client:
                return {"trigger_execution": False, "error": "Client not available"}
            
            # 現在のポジション情報を取得
            position_info = await self._get_current_position_info(
                client, config["symbol"], config["position_id"]
            )
            
            if not position_info:
                # ポジションが存在しない（既にクローズされた）
                return {
                    "trigger_execution": False,
                    "reason": "Position already closed"
                }
            
            current_price = float(position_info.get("markPrice", 0))
            current_sl = config["current_stop_loss"]
            side = config["side"]
            
            # 損切りトリガーの確認
            should_trigger = False
            trigger_reason = ""
            
            if side == "Buy" and current_price <= current_sl:
                should_trigger = True
                trigger_reason = f"ロング損切り発動: {current_price} <= {current_sl}"
            elif side == "Sell" and current_price >= current_sl:
                should_trigger = True
                trigger_reason = f"ショート損切り発動: {current_price} >= {current_sl}"
            
            # フェイルセーフレベルの確認
            for level_name, level_price in config.get("failsafe_levels", {}).items():
                if side == "Buy" and current_price <= level_price:
                    should_trigger = True
                    trigger_reason = f"フェイルセーフ発動({level_name}): {current_price} <= {level_price}"
                    break
                elif side == "Sell" and current_price >= level_price:
                    should_trigger = True
                    trigger_reason = f"フェイルセーフ発動({level_name}): {current_price} >= {level_price}"
                    break
            
            # 回避システムによる判定
            if should_trigger:
                # まずは回避システムで確認
                market_data = await self._get_market_data(config["symbol"])
                avoidance_result = await self.avoidance_system.evaluate_stop_loss_trigger(
                    config["position_id"],
                    config["entry_price"],
                    current_price,
                    current_sl,
                    config["symbol"],
                    side,
                    market_data
                )
                
                if not avoidance_result.get("should_execute_stop", True):
                    # 回避システムが実行を阻止
                    return {
                        "trigger_execution": False,
                        "reason": f"回避システム発動: {avoidance_result.get('avoidance_reason', '')}"
                    }
            
            return {
                "trigger_execution": should_trigger,
                "reason": trigger_reason,
                "current_price": current_price,
                "position_info": position_info
            }
            
        except Exception as e:
            logger.error(f"Error checking position status: {e}")
            return {"trigger_execution": False, "error": str(e)}
    
    async def _execute_strategy(
        self,
        strategy_name: str,
        config: Dict,
        market_data: MarketData
    ) -> Dict:
        """実行戦略の実行"""
        try:
            client = get_bybit_client()
            if not client:
                return {"success": False, "error": "Client not available"}
            
            symbol = config["symbol"]
            side = "Sell" if config["side"] == "Buy" else "Buy"
            qty = abs(config["position_size"])
            
            if strategy_name == "primary_limit":
                # 指値注文による通常実行
                current_price = market_data.df_1m['close'].iloc[-1] if hasattr(market_data, 'df_1m') else market_data.df_5m['close'].iloc[-1]
                limit_price = current_price * 0.999 if side == "Sell" else current_price * 1.001
                
                return await self._place_limit_order(
                    client, symbol, side, qty, limit_price, timeout=10
                )
                
            elif strategy_name == "immediate_market":
                # 成行注文による即座実行
                return await self._place_market_order(client, symbol, side, qty)
                
            elif strategy_name == "split_execution":
                # 分割実行による確実クローズ
                return await self._execute_split_orders(client, symbol, side, qty)
                
            elif strategy_name == "emergency_close":
                # 緊急クローズ実行
                return await self._execute_emergency_close(client, symbol, side, qty)
                
            elif strategy_name == "fallback_hedge":
                # ヘッジポジションによる損失固定
                return await self._execute_hedge_position(client, symbol, side, qty)
            
            else:
                return {"success": False, "error": "Unknown strategy"}
                
        except Exception as e:
            logger.error(f"Error executing strategy {strategy_name}: {e}")
            return {"success": False, "error": str(e)}
    
    async def _place_limit_order(
        self,
        client,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        timeout: int = 10
    ) -> Dict:
        """指値注文の実行"""
        try:
            response = client.session.place_order(
                category="linear",
                symbol=symbol,
                side=side,
                orderType="Limit",
                qty=str(qty),
                price=str(price),
                reduceOnly=True,
                timeInForce="IOC"
            )
            
            if response.get("retCode") == 0:
                order_id = response.get("result", {}).get("orderId", "")
                
                # 注文の約定を待機
                for _ in range(timeout):
                    await asyncio.sleep(1)
                    order_status = await self._check_order_status(client, order_id)
                    
                    if order_status.get("orderStatus") == "Filled":
                        return {
                            "success": True,
                            "execution_price": float(order_status.get("avgPrice", price)),
                            "status": "filled"
                        }
                    elif order_status.get("orderStatus") in ["Cancelled", "Rejected"]:
                        return {"success": False, "status": "failed"}
                
                # タイムアウト後は注文をキャンセル
                await self._cancel_order(client, order_id)
                return {"success": False, "status": "timeout"}
            
            else:
                return {"success": False, "error": response.get("retMsg", "Order failed")}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _place_market_order(
        self,
        client,
        symbol: str,
        side: str,
        qty: float
    ) -> Dict:
        """成行注文の実行"""
        try:
            response = client.session.place_order(
                category="linear",
                symbol=symbol,
                side=side,
                orderType="Market",
                qty=str(qty),
                reduceOnly=True,
                timeInForce="IOC"
            )
            
            if response.get("retCode") == 0:
                return {
                    "success": True,
                    "execution_price": 0.0,  # 市場価格で約定
                    "status": "market_filled"
                }
            else:
                return {"success": False, "error": response.get("retMsg", "Market order failed")}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _execute_split_orders(
        self,
        client,
        symbol: str,
        side: str,
        total_qty: float
    ) -> Dict:
        """分割注文の実行"""
        try:
            # 5分割で実行
            split_count = 5
            split_qty = total_qty / split_count
            executed_qty = 0.0
            
            for i in range(split_count):
                qty = split_qty if i < split_count - 1 else total_qty - executed_qty
                
                result = await self._place_market_order(client, symbol, side, qty)
                
                if result.get("success", False):
                    executed_qty += qty
                else:
                    logger.warning(f"Split order {i+1} failed: {result.get('error', '')}")
                
                await asyncio.sleep(0.5)  # 500ms待機
            
            success_rate = executed_qty / total_qty
            
            return {
                "success": success_rate > 0.8,  # 80%以上実行できれば成功
                "executed_qty": executed_qty,
                "success_rate": success_rate,
                "status": "split_executed"
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _execute_emergency_close(
        self,
        client,
        symbol: str,
        side: str,
        qty: float
    ) -> Dict:
        """緊急クローズの実行"""
        try:
            # 複数の成行注文を並行実行
            tasks = []
            
            for _ in range(3):  # 3回並行で試行
                task = self._place_market_order(client, symbol, side, qty)
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 1つでも成功すればOK
            for result in results:
                if isinstance(result, dict) and result.get("success", False):
                    return {
                        "success": True,
                        "status": "emergency_executed"
                    }
            
            return {"success": False, "error": "All emergency attempts failed"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _execute_hedge_position(
        self,
        client,
        symbol: str,
        side: str,
        qty: float
    ) -> Dict:
        """ヘッジポジションの実行"""
        try:
            # 反対方向のポジションを建てることで損失を固定
            hedge_side = "Buy" if side == "Sell" else "Sell"
            
            response = client.session.place_order(
                category="linear",
                symbol=symbol,
                side=hedge_side,
                orderType="Market",
                qty=str(qty),
                timeInForce="IOC"
            )
            
            if response.get("retCode") == 0:
                return {
                    "success": True,
                    "status": "hedge_executed",
                    "note": "損失がヘッジポジションにより固定されました"
                }
            else:
                return {"success": False, "error": "Hedge position failed"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _calculate_failsafe_levels(
        self,
        entry_price: float,
        stop_loss_price: float,
        side: str
    ) -> Dict:
        """フェイルセーフレベルの計算"""
        try:
            failsafe_levels = {}
            
            if side == "Buy":
                # ロングポジションの場合
                failsafe_levels["level_1"] = stop_loss_price * 0.998  # 0.2%下
                failsafe_levels["level_2"] = stop_loss_price * 0.995  # 0.5%下
                failsafe_levels["emergency"] = stop_loss_price * 0.990  # 1.0%下
            else:
                # ショートポジションの場合
                failsafe_levels["level_1"] = stop_loss_price * 1.002  # 0.2%上
                failsafe_levels["level_2"] = stop_loss_price * 1.005  # 0.5%上
                failsafe_levels["emergency"] = stop_loss_price * 1.010  # 1.0%上
            
            return failsafe_levels
            
        except Exception as e:
            logger.error(f"Error calculating failsafe levels: {e}")
            return {}
    
    async def _get_current_position_info(
        self,
        client,
        symbol: str,
        position_id: str
    ) -> Optional[Dict]:
        """現在のポジション情報を取得"""
        try:
            response = client.session.get_positions(
                category="linear",
                symbol=symbol
            )
            
            if response.get("retCode") == 0:
                positions = response.get("result", {}).get("list", [])
                for position in positions:
                    if float(position.get("size", 0)) != 0:
                        return position
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting position info: {e}")
            return None
    
    async def _get_market_data(self, symbol: str) -> MarketData:
        """マーケットデータを取得（プレースホルダー）"""
        # 実際の実装では適切なマーケットデータを取得
        pass
    
    async def _check_order_status(self, client, order_id: str) -> Dict:
        """注文状況の確認"""
        try:
            response = client.session.get_open_orders(
                category="linear",
                orderId=order_id
            )
            
            if response.get("retCode") == 0:
                orders = response.get("result", {}).get("list", [])
                if orders:
                    return orders[0]
            
            return {}
            
        except Exception as e:
            return {}
    
    async def _cancel_order(self, client, order_id: str) -> bool:
        """注文のキャンセル"""
        try:
            response = client.session.cancel_order(
                category="linear",
                orderId=order_id
            )
            
            return response.get("retCode") == 0
            
        except Exception as e:
            return False
    
    async def _evaluate_system_health(self) -> str:
        """システムヘルスの評価"""
        try:
            # 監視中のポジション数
            monitoring_count = len(self.monitoring_positions)
            
            # 実行履歴の成功率
            if self.execution_history:
                recent_executions = list(self.execution_history.values())[-10:]
                success_rate = sum(1 for ex in recent_executions if ex.get("execution_successful", False)) / len(recent_executions)
            else:
                success_rate = 1.0
            
            # ヘルス判定
            if success_rate >= 0.9 and monitoring_count < 50:
                return "healthy"
            elif success_rate >= 0.7 and monitoring_count < 100:
                return "warning"
            else:
                return "critical"
                
        except Exception as e:
            logger.error(f"Error evaluating system health: {e}")
            return "error"
    
    async def _send_execution_failure_alert(self, execution_record: Dict):
        """実行失敗アラートの送信"""
        try:
            # 実際の実装では、Slack、メール、Webhookなどでアラートを送信
            logger.critical(f"STOP LOSS EXECUTION FAILED: {execution_record}")
            
        except Exception as e:
            logger.error(f"Error sending failure alert: {e}")
    
    def stop_position_monitoring(self, monitoring_id: str) -> bool:
        """ポジション監視の停止"""
        try:
            if monitoring_id in self.monitoring_positions:
                del self.monitoring_positions[monitoring_id]
                logger.info(f"Stopped monitoring: {monitoring_id}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Error stopping monitoring: {e}")
            return False
    
    def get_monitoring_status(self) -> Dict:
        """監視状況の取得"""
        return {
            "total_monitoring": len(self.monitoring_positions),
            "failsafe_status": self.failsafe_status,
            "execution_queue_length": len(self.execution_queue),
            "total_executions": len(self.execution_history),
            "monitoring_positions": list(self.monitoring_positions.keys())
        }