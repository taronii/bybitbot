"""
緊急損切りシステム
ブラックスワンイベントや異常事態における緊急損切り実行
"""
import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from pybit.unified_trading import HTTP
from ...models import MarketData
from ...services.bybit_client import get_bybit_client
from ..analysis.market_regime import MarketRegimeDetector
import logging

logger = logging.getLogger(__name__)

class EmergencyStopLossSystem:
    """緊急損切りシステム"""
    
    def __init__(self):
        self.regime_detector = MarketRegimeDetector()
        self.emergency_triggers = {}  # 緊急トリガー履歴
        self.system_status = "normal"  # normal, alert, emergency
        self.last_emergency_check = datetime.now()
        
    async def monitor_emergency_conditions(
        self,
        positions: List[Dict],
        market_data: MarketData,
        account_info: Dict
    ) -> Dict:
        """
        緊急事態の監視と判定
        
        Returns:
            {
                "emergency_level": str,  # normal, warning, critical, emergency
                "triggers": List[str],
                "affected_positions": List[str],
                "recommended_actions": List[str],
                "immediate_action_required": bool
            }
        """
        try:
            # 1. ブラックスワンイベントの検出
            black_swan_result = await self._detect_black_swan_events(market_data)
            
            # 2. 急激な価格変動の検出
            extreme_volatility_result = await self._detect_extreme_volatility(market_data)
            
            # 3. 流動性クライシスの検出
            liquidity_crisis_result = await self._detect_liquidity_crisis(market_data)
            
            # 4. ドローダウン危機の検出
            drawdown_crisis_result = await self._detect_drawdown_crisis(
                positions, account_info
            )
            
            # 5. システム障害の検出
            system_failure_result = await self._detect_system_failures(market_data)
            
            # 6. 総合的な緊急レベル判定
            emergency_assessment = await self._assess_emergency_level(
                black_swan_result,
                extreme_volatility_result,
                liquidity_crisis_result,
                drawdown_crisis_result,
                system_failure_result
            )
            
            # 7. 緊急履歴の更新
            self._update_emergency_history(emergency_assessment)
            
            return emergency_assessment
            
        except Exception as e:
            logger.error(f"Error in emergency monitoring: {e}")
            return self._get_default_emergency_result()
    
    async def execute_emergency_stop_loss(
        self,
        positions: List[Dict],
        emergency_level: str,
        triggers: List[str]
    ) -> Dict:
        """
        緊急損切りの実行
        
        Returns:
            {
                "execution_results": List[Dict],
                "total_positions_closed": int,
                "total_loss": float,
                "execution_time": float,
                "failed_executions": List[Dict]
            }
        """
        try:
            start_time = datetime.now()
            execution_results = []
            failed_executions = []
            total_loss = 0.0
            
            # 緊急レベルに応じた実行戦略
            if emergency_level == "emergency":
                # 最高優先度：すべてのポジションを即座にクローズ
                for position in positions:
                    result = await self._emergency_close_position(
                        position, "market", "immediate"
                    )
                    if result["success"]:
                        execution_results.append(result)
                        total_loss += result.get("realized_pnl", 0)
                    else:
                        failed_executions.append(result)
            
            elif emergency_level == "critical":
                # 高優先度：損失の大きいポジションを優先的にクローズ
                sorted_positions = sorted(
                    positions, 
                    key=lambda p: float(p.get("unrealised_pnl", 0))
                )
                
                for position in sorted_positions:
                    if float(position.get("unrealised_pnl", 0)) < 0:  # 損失ポジションのみ
                        result = await self._emergency_close_position(
                            position, "limit_then_market", "high"
                        )
                        if result["success"]:
                            execution_results.append(result)
                            total_loss += result.get("realized_pnl", 0)
                        else:
                            failed_executions.append(result)
            
            elif emergency_level == "warning":
                # 中優先度：リスクの高いポジションのみクローズ
                for position in positions:
                    if await self._is_high_risk_position(position):
                        result = await self._emergency_close_position(
                            position, "limit", "medium"
                        )
                        if result["success"]:
                            execution_results.append(result)
                            total_loss += result.get("realized_pnl", 0)
                        else:
                            failed_executions.append(result)
            
            # 実行時間の計算
            execution_time = (datetime.now() - start_time).total_seconds()
            
            return {
                "execution_results": execution_results,
                "total_positions_closed": len(execution_results),
                "total_loss": total_loss,
                "execution_time": execution_time,
                "failed_executions": failed_executions,
                "emergency_level": emergency_level,
                "triggers": triggers
            }
            
        except Exception as e:
            logger.error(f"Error in emergency stop loss execution: {e}")
            return {
                "execution_results": [],
                "total_positions_closed": 0,
                "total_loss": 0.0,
                "execution_time": 0.0,
                "failed_executions": [],
                "error": str(e)
            }
    
    async def _detect_black_swan_events(self, market_data: MarketData) -> Dict:
        """ブラックスワンイベントの検出"""
        try:
            df = market_data.df_5m
            black_swan_signals = []
            
            # 1. 極端な価格変動（1分間で10%以上）
            recent_prices = df['close'].iloc[-12:]  # 1時間分
            max_change = recent_prices.pct_change().abs().max()
            
            if max_change > 0.10:  # 10%以上の変動
                black_swan_signals.append(f"極端価格変動: {max_change:.1%}")
            
            # 2. ボラティリティの異常急増
            current_atr = df['atr'].iloc[-1]
            historical_atr = df['atr'].iloc[-288:].mean()  # 24時間平均
            
            if current_atr > historical_atr * 5:  # 5倍以上の増加
                black_swan_signals.append(f"ボラティリティ異常急増: {current_atr/historical_atr:.1f}倍")
            
            # 3. 連続する巨大なギャップ
            gaps = abs(df['open'] - df['close'].shift(1)) / df['close'].shift(1)
            recent_gaps = gaps.iloc[-12:]
            large_gaps = recent_gaps[recent_gaps > 0.05].count()  # 5%以上のギャップ
            
            if large_gaps >= 3:
                black_swan_signals.append(f"連続する巨大ギャップ: {large_gaps}回")
            
            # 4. 出来高の異常急増
            current_volume = df['volume'].iloc[-6:].mean()  # 30分平均
            normal_volume = df['volume'].iloc[-288:].mean()  # 24時間平均
            
            if current_volume > normal_volume * 10:  # 10倍以上の増加
                black_swan_signals.append(f"出来高異常急増: {current_volume/normal_volume:.1f}倍")
            
            severity = len(black_swan_signals)
            confidence = min(severity * 0.3, 1.0)
            
            return {
                "detected": severity >= 2,
                "severity": severity,
                "confidence": confidence,
                "signals": black_swan_signals
            }
            
        except Exception as e:
            logger.error(f"Error in black swan detection: {e}")
            return {"detected": False, "severity": 0, "confidence": 0.0}
    
    async def _detect_extreme_volatility(self, market_data: MarketData) -> Dict:
        """極端なボラティリティの検出"""
        try:
            df = market_data.df_5m
            volatility_signals = []
            
            # 1. ATRの急激な増加
            current_atr = df['atr'].iloc[-1]
            short_atr = df['atr'].iloc[-12:].mean()  # 1時間平均
            long_atr = df['atr'].iloc[-72:].mean()   # 6時間平均
            
            if short_atr > long_atr * 3:
                volatility_signals.append(f"ATR急増: {short_atr/long_atr:.1f}倍")
            
            # 2. 価格変動の標準偏差
            price_changes = df['close'].pct_change().iloc[-24:]
            current_std = price_changes.std()
            historical_std = df['close'].pct_change().iloc[-288:].std()
            
            if current_std > historical_std * 4:
                volatility_signals.append(f"標準偏差急増: {current_std/historical_std:.1f}倍")
            
            # 3. 連続する大きな実体
            recent_candles = df.iloc[-12:]
            large_bodies = 0
            
            for _, candle in recent_candles.iterrows():
                body_size = abs(candle['close'] - candle['open']) / candle['open']
                if body_size > 0.03:  # 3%以上の実体
                    large_bodies += 1
            
            if large_bodies >= 6:  # 半数以上が大きな実体
                volatility_signals.append(f"連続する大きな実体: {large_bodies}/12")
            
            severity = len(volatility_signals)
            confidence = min(severity * 0.35, 1.0)
            
            return {
                "detected": severity >= 2,
                "severity": severity,
                "confidence": confidence,
                "signals": volatility_signals
            }
            
        except Exception as e:
            logger.error(f"Error in extreme volatility detection: {e}")
            return {"detected": False, "severity": 0, "confidence": 0.0}
    
    async def _detect_liquidity_crisis(self, market_data: MarketData) -> Dict:
        """流動性クライシスの検出"""
        try:
            df = market_data.df_5m
            liquidity_signals = []
            
            # 1. 出来高の急激な減少
            current_volume = df['volume'].iloc[-6:].mean()
            normal_volume = df['volume'].iloc[-72:].mean()
            
            if current_volume < normal_volume * 0.1:  # 90%減少
                liquidity_signals.append(f"出来高急減: {current_volume/normal_volume:.1%}")
            
            # 2. スプレッドの拡大
            spreads = (df['high'] - df['low']) / df['close']
            current_spread = spreads.iloc[-6:].mean()
            normal_spread = spreads.iloc[-72:].mean()
            
            if current_spread > normal_spread * 5:
                liquidity_signals.append(f"スプレッド拡大: {current_spread/normal_spread:.1f}倍")
            
            # 3. 価格の不連続性
            price_gaps = abs(df['open'] - df['close'].shift(1)) / df['close'].shift(1)
            recent_gaps = price_gaps.iloc[-12:]
            gap_count = recent_gaps[recent_gaps > 0.01].count()  # 1%以上のギャップ
            
            if gap_count >= 6:
                liquidity_signals.append(f"価格不連続: {gap_count}/12")
            
            severity = len(liquidity_signals)
            confidence = min(severity * 0.4, 1.0)
            
            return {
                "detected": severity >= 1,
                "severity": severity,
                "confidence": confidence,
                "signals": liquidity_signals
            }
            
        except Exception as e:
            logger.error(f"Error in liquidity crisis detection: {e}")
            return {"detected": False, "severity": 0, "confidence": 0.0}
    
    async def _detect_drawdown_crisis(
        self,
        positions: List[Dict],
        account_info: Dict
    ) -> Dict:
        """ドローダウン危機の検出"""
        try:
            drawdown_signals = []
            
            # 1. 総未実現損失の計算
            total_unrealized_pnl = sum(
                float(pos.get("unrealised_pnl", 0)) for pos in positions
            )
            account_balance = float(account_info.get("totalWalletBalance", 0))
            
            if account_balance > 0:
                unrealized_percentage = abs(total_unrealized_pnl) / account_balance
                
                if unrealized_percentage > 0.20:  # 20%以上の未実現損失
                    drawdown_signals.append(f"未実現損失: {unrealized_percentage:.1%}")
            
            # 2. マージン使用率
            margin_ratio = float(account_info.get("totalMarginBalance", 0)) / account_balance if account_balance > 0 else 0
            
            if margin_ratio > 0.90:  # 90%以上のマージン使用
                drawdown_signals.append(f"高マージン使用率: {margin_ratio:.1%}")
            
            # 3. 連続する損失ポジション
            loss_positions = sum(
                1 for pos in positions 
                if float(pos.get("unrealised_pnl", 0)) < 0
            )
            total_positions = len(positions)
            
            if total_positions > 0 and loss_positions / total_positions > 0.80:  # 80%以上が損失
                drawdown_signals.append(f"損失ポジション比率: {loss_positions}/{total_positions}")
            
            severity = len(drawdown_signals)
            confidence = min(severity * 0.45, 1.0)
            
            return {
                "detected": severity >= 1,
                "severity": severity,
                "confidence": confidence,
                "signals": drawdown_signals,
                "unrealized_pnl": total_unrealized_pnl,
                "margin_ratio": margin_ratio
            }
            
        except Exception as e:
            logger.error(f"Error in drawdown crisis detection: {e}")
            return {"detected": False, "severity": 0, "confidence": 0.0}
    
    async def _detect_system_failures(self, market_data: MarketData) -> Dict:
        """システム障害の検出"""
        try:
            system_signals = []
            
            # 1. データフィードの遅延
            last_update = market_data.df_5m.index[-1]
            current_time = datetime.now()
            
            # データが5分以上古い場合
            if hasattr(last_update, 'to_pydatetime'):
                data_delay = (current_time - last_update.to_pydatetime()).total_seconds()
            else:
                data_delay = 0
            
            if data_delay > 300:  # 5分以上
                system_signals.append(f"データ遅延: {data_delay/60:.1f}分")
            
            # 2. 価格データの異常
            recent_prices = market_data.df_5m['close'].iloc[-6:]
            if recent_prices.isna().any():
                system_signals.append("価格データ欠損")
            
            # 3. 出来高データの異常
            recent_volumes = market_data.df_5m['volume'].iloc[-6:]
            if recent_volumes.isna().any() or (recent_volumes == 0).all():
                system_signals.append("出来高データ異常")
            
            severity = len(system_signals)
            confidence = min(severity * 0.5, 1.0)
            
            return {
                "detected": severity >= 1,
                "severity": severity,
                "confidence": confidence,
                "signals": system_signals
            }
            
        except Exception as e:
            logger.error(f"Error in system failure detection: {e}")
            return {"detected": False, "severity": 0, "confidence": 0.0}
    
    async def _assess_emergency_level(
        self,
        black_swan_result: Dict,
        extreme_volatility_result: Dict,
        liquidity_crisis_result: Dict,
        drawdown_crisis_result: Dict,
        system_failure_result: Dict
    ) -> Dict:
        """総合的な緊急レベル判定"""
        try:
            all_triggers = []
            severity_score = 0
            
            # 各結果の評価
            results = [
                ("ブラックスワン", black_swan_result),
                ("極端ボラティリティ", extreme_volatility_result),
                ("流動性クライシス", liquidity_crisis_result),
                ("ドローダウン危機", drawdown_crisis_result),
                ("システム障害", system_failure_result)
            ]
            
            for trigger_type, result in results:
                if result.get("detected", False):
                    severity = result.get("severity", 0)
                    confidence = result.get("confidence", 0)
                    signals = result.get("signals", [])
                    
                    all_triggers.append(f"{trigger_type}: {', '.join(signals)}")
                    severity_score += severity * confidence
            
            # 緊急レベルの決定
            if severity_score >= 3.0:
                emergency_level = "emergency"
                immediate_action = True
                actions = [
                    "すべてのポジションを即座に成行クローズ",
                    "新規取引を停止",
                    "システム管理者に通知"
                ]
            elif severity_score >= 2.0:
                emergency_level = "critical"
                immediate_action = True
                actions = [
                    "損失ポジションを優先的にクローズ",
                    "新規取引を一時停止",
                    "リスク管理を強化"
                ]
            elif severity_score >= 1.0:
                emergency_level = "warning"
                immediate_action = False
                actions = [
                    "高リスクポジションの監視強化",
                    "損切り水準の見直し",
                    "ポジションサイズの縮小検討"
                ]
            else:
                emergency_level = "normal"
                immediate_action = False
                actions = ["通常運用継続"]
            
            affected_positions = []
            # 緊急レベルに応じて影響を受けるポジションを特定
            if emergency_level in ["emergency", "critical"]:
                affected_positions = ["all"]
            elif emergency_level == "warning":
                affected_positions = ["high_risk"]
            
            return {
                "emergency_level": emergency_level,
                "triggers": all_triggers,
                "affected_positions": affected_positions,
                "recommended_actions": actions,
                "immediate_action_required": immediate_action,
                "severity_score": severity_score,
                "timestamp": datetime.now()
            }
            
        except Exception as e:
            logger.error(f"Error in emergency level assessment: {e}")
            return self._get_default_emergency_result()
    
    async def _emergency_close_position(
        self,
        position: Dict,
        order_type: str,  # market, limit, limit_then_market
        priority: str     # immediate, high, medium
    ) -> Dict:
        """緊急ポジションクローズ"""
        try:
            client = get_bybit_client()
            if not client:
                return {"success": False, "error": "Bybit client not available"}
            
            symbol = position.get("symbol", "")
            side = "Sell" if position.get("side") == "Buy" else "Buy"
            qty = abs(float(position.get("size", 0)))
            
            if qty == 0:
                return {"success": False, "error": "Invalid position size"}
            
            # 注文タイプに応じた実行
            if order_type == "market":
                # 成行注文で即座にクローズ
                result = await self._place_market_close_order(
                    client, symbol, side, qty
                )
                
            elif order_type == "limit":
                # 指値注文でクローズ
                current_price = float(position.get("markPrice", 0))
                limit_price = current_price * 0.999 if side == "Sell" else current_price * 1.001
                
                result = await self._place_limit_close_order(
                    client, symbol, side, qty, limit_price
                )
                
            elif order_type == "limit_then_market":
                # 指値注文を試行し、失敗したら成行注文
                current_price = float(position.get("markPrice", 0))
                limit_price = current_price * 0.999 if side == "Sell" else current_price * 1.001
                
                result = await self._place_limit_close_order(
                    client, symbol, side, qty, limit_price
                )
                
                if not result.get("success", False):
                    # 指値が失敗したら成行で実行
                    await asyncio.sleep(1)  # 1秒待機
                    result = await self._place_market_close_order(
                        client, symbol, side, qty
                    )
            
            else:
                result = {"success": False, "error": "Invalid order type"}
            
            # 結果の記録
            if result.get("success", False):
                logger.info(f"Emergency close successful: {symbol} {side} {qty}")
            else:
                logger.error(f"Emergency close failed: {symbol} - {result.get('error', 'Unknown error')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error in emergency position close: {e}")
            return {"success": False, "error": str(e)}
    
    async def _place_market_close_order(
        self,
        client,
        symbol: str,
        side: str,
        qty: float
    ) -> Dict:
        """成行クローズ注文"""
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
                    "order_id": response.get("result", {}).get("orderId", ""),
                    "order_type": "market"
                }
            else:
                return {
                    "success": False,
                    "error": response.get("retMsg", "Market order failed")
                }
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _place_limit_close_order(
        self,
        client,
        symbol: str,
        side: str,
        qty: float,
        price: float
    ) -> Dict:
        """指値クローズ注文"""
        try:
            response = client.session.place_order(
                category="linear",
                symbol=symbol,
                side=side,
                orderType="Limit",
                qty=str(qty),
                price=str(price),
                reduceOnly=True,
                timeInForce="GTC"
            )
            
            if response.get("retCode") == 0:
                return {
                    "success": True,
                    "order_id": response.get("result", {}).get("orderId", ""),
                    "order_type": "limit",
                    "limit_price": price
                }
            else:
                return {
                    "success": False,
                    "error": response.get("retMsg", "Limit order failed")
                }
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _is_high_risk_position(self, position: Dict) -> bool:
        """高リスクポジションかどうかを判定"""
        try:
            unrealized_pnl = float(position.get("unrealised_pnl", 0))
            mark_price = float(position.get("markPrice", 0))
            avg_price = float(position.get("avgPrice", 0))
            
            if mark_price == 0 or avg_price == 0:
                return True  # 価格情報が不正な場合は高リスクとみなす
            
            # 未実現損失が5%以上
            loss_percentage = abs(unrealized_pnl) / (abs(float(position.get("size", 0))) * avg_price)
            
            return loss_percentage > 0.05
            
        except Exception as e:
            logger.error(f"Error checking high risk position: {e}")
            return True  # エラーの場合は安全側に高リスクとみなす
    
    def _update_emergency_history(self, assessment: Dict):
        """緊急事態履歴の更新"""
        current_time = datetime.now()
        
        if assessment.get("emergency_level", "normal") != "normal":
            self.emergency_triggers[current_time] = assessment
            
            # 履歴は最新の50件のみ保持
            if len(self.emergency_triggers) > 50:
                oldest_key = min(self.emergency_triggers.keys())
                del self.emergency_triggers[oldest_key]
        
        # システムステータスの更新
        self.system_status = assessment.get("emergency_level", "normal")
        self.last_emergency_check = current_time
    
    def _get_default_emergency_result(self) -> Dict:
        """デフォルトの緊急結果"""
        return {
            "emergency_level": "normal",
            "triggers": [],
            "affected_positions": [],
            "recommended_actions": ["通常運用継続"],
            "immediate_action_required": False,
            "severity_score": 0.0,
            "timestamp": datetime.now()
        }
    
    async def get_emergency_status(self) -> Dict:
        """現在の緊急状態を取得"""
        return {
            "system_status": self.system_status,
            "last_check": self.last_emergency_check,
            "recent_triggers": list(self.emergency_triggers.values())[-5:],
            "total_emergency_events": len(self.emergency_triggers)
        }