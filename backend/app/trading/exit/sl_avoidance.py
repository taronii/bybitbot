"""
損切り回避インテリジェンス
一時的なノイズやフェイクアウトから損切りを保護
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

class StopLossAvoidanceIntelligence:
    """損切り回避インテリジェンス"""
    
    def __init__(self):
        self.regime_detector = MarketRegimeDetector()
        self.false_breakout_history = {}  # フェイクアウト履歴
        self.avoidance_active = {}  # 回避システム作動状況
        
    async def evaluate_stop_loss_trigger(
        self,
        position_id: str,
        entry_price: float,
        current_price: float,
        stop_loss_price: float,
        symbol: str,
        side: str,
        market_data: MarketData
    ) -> Dict:
        """
        損切りトリガーの評価と回避判定
        
        Returns:
            {
                "should_execute_stop": bool,
                "avoidance_triggered": bool,
                "avoidance_reason": str,
                "temporary_delay": int,  # 秒
                "alternative_action": str,
                "confidence_score": float,
                "analysis": {...}
            }
        """
        try:
            # 1. フェイクアウト検出
            fake_breakout_result = await self._detect_fake_breakout(
                current_price, stop_loss_price, side, market_data
            )
            
            # 2. 一時的ノイズの分析
            noise_result = await self._analyze_temporary_noise(
                current_price, stop_loss_price, side, market_data
            )
            
            # 3. 流動性分析
            liquidity_result = await self._analyze_liquidity_conditions(
                current_price, symbol, market_data
            )
            
            # 4. 市場操作の検出
            manipulation_result = await self._detect_market_manipulation(
                current_price, stop_loss_price, side, market_data
            )
            
            # 5. 総合判定
            final_decision = await self._make_avoidance_decision(
                position_id, fake_breakout_result, noise_result,
                liquidity_result, manipulation_result, side
            )
            
            # 6. 回避履歴の更新
            self._update_avoidance_history(position_id, final_decision)
            
            return final_decision
            
        except Exception as e:
            logger.error(f"Error in stop loss avoidance evaluation: {e}")
            return self._get_default_execution_decision()
    
    async def _detect_fake_breakout(
        self,
        current_price: float,
        stop_loss_price: float,
        side: str,
        market_data: MarketData
    ) -> Dict:
        """フェイクアウトの検出"""
        try:
            df_5m = market_data.df_5m
            df_15m = market_data.df_15m
            
            # 価格がストップロスを一時的に割り込んだかチェック
            if side == "Buy":
                recent_low = df_5m['low'].iloc[-5:].min()
                is_triggered = recent_low <= stop_loss_price
            else:
                recent_high = df_5m['high'].iloc[-5:].max()
                is_triggered = recent_high >= stop_loss_price
            
            if not is_triggered:
                return {"is_fake_breakout": False, "confidence": 0.0}
            
            # フェイクアウトの特徴を分析
            fake_signals = []
            
            # 1. 短時間での価格回復
            price_recovery = False
            if side == "Buy":
                if current_price > stop_loss_price * 1.002:  # 0.2%以上回復
                    price_recovery = True
                    fake_signals.append("短時間での価格回復")
            else:
                if current_price < stop_loss_price * 0.998:  # 0.2%以上回復
                    price_recovery = True
                    fake_signals.append("短時間での価格回復")
            
            # 2. 出来高の異常性
            recent_volume = df_5m['volume'].iloc[-3:].mean()
            avg_volume = df_5m['volume'].iloc[-50:].mean()
            
            if recent_volume > avg_volume * 2:
                fake_signals.append("異常出来高での突発的変動")
            
            # 3. RSIの過度な値
            current_rsi = df_5m['rsi'].iloc[-1]
            if (side == "Buy" and current_rsi < 25) or (side == "Sell" and current_rsi > 75):
                fake_signals.append("RSI極値での反転可能性")
            
            # 4. サポート・レジスタンスからの乖離
            support_resistance_violation = await self._check_key_level_violation(
                current_price, stop_loss_price, side, df_15m
            )
            
            if support_resistance_violation:
                fake_signals.append("重要水準からの過度な乖離")
            
            # フェイクアウトの可能性を評価
            confidence = min(len(fake_signals) * 0.25, 0.95)
            is_fake = len(fake_signals) >= 2 and confidence >= 0.5
            
            return {
                "is_fake_breakout": is_fake,
                "confidence": confidence,
                "signals": fake_signals,
                "price_recovery": price_recovery,
                "volume_anomaly": recent_volume > avg_volume * 2,
                "rsi_extreme": current_rsi
            }
            
        except Exception as e:
            logger.error(f"Error in fake breakout detection: {e}")
            return {"is_fake_breakout": False, "confidence": 0.0}
    
    async def _analyze_temporary_noise(
        self,
        current_price: float,
        stop_loss_price: float,
        side: str,
        market_data: MarketData
    ) -> Dict:
        """一時的ノイズの分析"""
        try:
            df_1m = market_data.df_1m if hasattr(market_data, 'df_1m') else market_data.df_5m
            
            # 最近の価格変動のボラティリティを計算
            price_changes = df_1m['close'].pct_change().iloc[-20:]
            recent_volatility = price_changes.std()
            
            # ストップロス到達が一時的ノイズかどうかを判定
            price_distance = abs(current_price - stop_loss_price) / current_price
            
            # ノイズレベルの分類
            noise_level = "低"
            if recent_volatility > 0.01:  # 1%以上のボラティリティ
                noise_level = "高"
            elif recent_volatility > 0.005:  # 0.5%以上のボラティリティ
                noise_level = "中"
            
            # 一時的ノイズの可能性
            is_temporary_noise = False
            noise_reasons = []
            
            if noise_level == "高" and price_distance < recent_volatility:
                is_temporary_noise = True
                noise_reasons.append("高ボラティリティ環境での通常変動範囲内")
            
            # ウィック分析
            recent_candles = df_1m.iloc[-5:]
            long_wicks = 0
            
            for _, candle in recent_candles.iterrows():
                body_size = abs(candle['close'] - candle['open'])
                if side == "Buy":
                    lower_wick = candle['open'] - candle['low'] if candle['close'] > candle['open'] else candle['close'] - candle['low']
                    if lower_wick > body_size * 2:
                        long_wicks += 1
                else:
                    upper_wick = candle['high'] - candle['open'] if candle['close'] < candle['open'] else candle['high'] - candle['close']
                    if upper_wick > body_size * 2:
                        long_wicks += 1
            
            if long_wicks >= 2:
                is_temporary_noise = True
                noise_reasons.append("長いウィックによる一時的変動")
            
            confidence = min(len(noise_reasons) * 0.4, 0.8)
            
            return {
                "is_temporary_noise": is_temporary_noise,
                "confidence": confidence,
                "noise_level": noise_level,
                "reasons": noise_reasons,
                "recent_volatility": recent_volatility,
                "long_wicks_count": long_wicks
            }
            
        except Exception as e:
            logger.error(f"Error in temporary noise analysis: {e}")
            return {"is_temporary_noise": False, "confidence": 0.0}
    
    async def _analyze_liquidity_conditions(
        self,
        current_price: float,
        symbol: str,
        market_data: MarketData
    ) -> Dict:
        """流動性状況の分析"""
        try:
            df = market_data.df_5m
            
            # 出来高の分析
            recent_volume = df['volume'].iloc[-10:].mean()
            avg_volume = df['volume'].iloc[-100:].mean()
            volume_ratio = recent_volume / avg_volume
            
            # 流動性レベルの判定
            liquidity_level = "正常"
            liquidity_issues = []
            
            if volume_ratio < 0.3:
                liquidity_level = "低流動性"
                liquidity_issues.append("異常に低い出来高")
            elif volume_ratio > 3.0:
                liquidity_level = "異常高出来高"
                liquidity_issues.append("異常に高い出来高")
            
            # スプレッド分析（簡易）
            price_volatility = df['high'].iloc[-10:] - df['low'].iloc[-10:]
            avg_spread = price_volatility.mean() / current_price
            
            if avg_spread > 0.005:  # 0.5%以上のスプレッド
                liquidity_issues.append("広いスプレッド")
            
            # 時間帯による流動性
            current_hour = datetime.now().hour
            low_liquidity_hours = [0, 1, 2, 3, 4, 5, 22, 23]  # 低流動性時間帯
            
            if current_hour in low_liquidity_hours:
                liquidity_issues.append("低流動性時間帯")
            
            poor_liquidity = len(liquidity_issues) >= 2
            confidence = min(len(liquidity_issues) * 0.3, 0.8)
            
            return {
                "poor_liquidity": poor_liquidity,
                "confidence": confidence,
                "liquidity_level": liquidity_level,
                "issues": liquidity_issues,
                "volume_ratio": volume_ratio,
                "avg_spread": avg_spread
            }
            
        except Exception as e:
            logger.error(f"Error in liquidity analysis: {e}")
            return {"poor_liquidity": False, "confidence": 0.0}
    
    async def _detect_market_manipulation(
        self,
        current_price: float,
        stop_loss_price: float,
        side: str,
        market_data: MarketData
    ) -> Dict:
        """市場操作の検出"""
        try:
            df = market_data.df_5m
            
            manipulation_signals = []
            
            # 1. 急激な価格変動後の即座の反転
            recent_prices = df['close'].iloc[-5:]
            price_changes = recent_prices.pct_change().abs()
            
            if price_changes.max() > 0.02:  # 2%以上の急変動
                if side == "Buy" and recent_prices.iloc[-1] > recent_prices.iloc[-2]:
                    manipulation_signals.append("急落後の即座反発")
                elif side == "Sell" and recent_prices.iloc[-1] < recent_prices.iloc[-2]:
                    manipulation_signals.append("急騰後の即座反落")
            
            # 2. 異常な出来高パターン
            volumes = df['volume'].iloc[-10:]
            volume_spikes = volumes[volumes > volumes.mean() * 3]
            
            if len(volume_spikes) >= 2:
                manipulation_signals.append("連続する異常出来高")
            
            # 3. 連続する長いウィック
            long_wick_count = 0
            for i in range(-5, 0):
                candle = df.iloc[i]
                body_size = abs(candle['close'] - candle['open'])
                total_range = candle['high'] - candle['low']
                
                if total_range > body_size * 3:  # ウィックが実体の3倍以上
                    long_wick_count += 1
            
            if long_wick_count >= 3:
                manipulation_signals.append("連続する長いウィック")
            
            # 4. ストップロス水準での価格反発
            price_distance = abs(current_price - stop_loss_price) / current_price
            if price_distance < 0.001:  # 0.1%以内で反発
                manipulation_signals.append("ストップロス水準での精密な反発")
            
            is_manipulation = len(manipulation_signals) >= 2
            confidence = min(len(manipulation_signals) * 0.3, 0.9)
            
            return {
                "is_manipulation": is_manipulation,
                "confidence": confidence,
                "signals": manipulation_signals,
                "volume_spikes": len(volume_spikes),
                "long_wick_count": long_wick_count
            }
            
        except Exception as e:
            logger.error(f"Error in manipulation detection: {e}")
            return {"is_manipulation": False, "confidence": 0.0}
    
    async def _check_key_level_violation(
        self,
        current_price: float,
        stop_loss_price: float,
        side: str,
        df: pd.DataFrame
    ) -> bool:
        """重要水準からの乖離をチェック"""
        try:
            # 簡易的なサポート・レジスタンス計算
            highs = df['high'].rolling(window=20).max()
            lows = df['low'].rolling(window=20).min()
            
            recent_support = lows.iloc[-10:].min()
            recent_resistance = highs.iloc[-10:].max()
            
            if side == "Buy":
                # サポートを大幅に下回っているか
                support_violation = stop_loss_price < recent_support * 0.995
                return support_violation
            else:
                # レジスタンスを大幅に上回っているか
                resistance_violation = stop_loss_price > recent_resistance * 1.005
                return resistance_violation
                
        except Exception as e:
            logger.error(f"Error checking key level violation: {e}")
            return False
    
    async def _make_avoidance_decision(
        self,
        position_id: str,
        fake_breakout_result: Dict,
        noise_result: Dict,
        liquidity_result: Dict,
        manipulation_result: Dict,
        side: str
    ) -> Dict:
        """最終的な回避判定"""
        try:
            # 各分析結果の重み付き評価
            avoidance_score = 0
            avoidance_reasons = []
            
            # フェイクアウト
            if fake_breakout_result.get("is_fake_breakout", False):
                avoidance_score += fake_breakout_result.get("confidence", 0) * 0.4
                avoidance_reasons.append(f"フェイクアウト検出（信頼度: {fake_breakout_result.get('confidence', 0):.1%}）")
            
            # 一時的ノイズ
            if noise_result.get("is_temporary_noise", False):
                avoidance_score += noise_result.get("confidence", 0) * 0.3
                avoidance_reasons.append(f"一時的ノイズ（{noise_result.get('noise_level', '')}ボラティリティ）")
            
            # 流動性問題
            if liquidity_result.get("poor_liquidity", False):
                avoidance_score += liquidity_result.get("confidence", 0) * 0.2
                avoidance_reasons.append(f"流動性問題（{liquidity_result.get('liquidity_level', '')}）")
            
            # 市場操作
            if manipulation_result.get("is_manipulation", False):
                avoidance_score += manipulation_result.get("confidence", 0) * 0.3
                avoidance_reasons.append(f"市場操作の可能性（{len(manipulation_result.get('signals', []))}個の兆候）")
            
            # 回避判定
            should_avoid = avoidance_score >= 0.6
            temporary_delay = 0
            alternative_action = "通常執行"
            
            if should_avoid:
                # 回避レベルに応じた対応
                if avoidance_score >= 0.8:
                    temporary_delay = 300  # 5分遅延
                    alternative_action = "5分間の監視後再評価"
                else:
                    temporary_delay = 120  # 2分遅延
                    alternative_action = "2分間の監視後再評価"
            
            return {
                "should_execute_stop": not should_avoid,
                "avoidance_triggered": should_avoid,
                "avoidance_reason": "、".join(avoidance_reasons) if avoidance_reasons else "回避条件なし",
                "temporary_delay": temporary_delay,
                "alternative_action": alternative_action,
                "confidence_score": avoidance_score,
                "analysis": {
                    "fake_breakout": fake_breakout_result,
                    "noise": noise_result,
                    "liquidity": liquidity_result,
                    "manipulation": manipulation_result
                }
            }
            
        except Exception as e:
            logger.error(f"Error in avoidance decision: {e}")
            return self._get_default_execution_decision()
    
    def _update_avoidance_history(self, position_id: str, decision: Dict):
        """回避履歴の更新"""
        if position_id not in self.false_breakout_history:
            self.false_breakout_history[position_id] = []
        
        self.false_breakout_history[position_id].append({
            "timestamp": datetime.now(),
            "decision": decision
        })
        
        # 履歴は最新の10件のみ保持
        if len(self.false_breakout_history[position_id]) > 10:
            self.false_breakout_history[position_id] = \
                self.false_breakout_history[position_id][-10:]
        
        # アクティブな回避状況を更新
        if decision.get("avoidance_triggered", False):
            self.avoidance_active[position_id] = {
                "start_time": datetime.now(),
                "delay_seconds": decision.get("temporary_delay", 0),
                "reason": decision.get("avoidance_reason", "")
            }
        elif position_id in self.avoidance_active:
            del self.avoidance_active[position_id]
    
    def _get_default_execution_decision(self) -> Dict:
        """デフォルトの実行判定"""
        return {
            "should_execute_stop": True,
            "avoidance_triggered": False,
            "avoidance_reason": "正常な損切り実行",
            "temporary_delay": 0,
            "alternative_action": "即座に実行",
            "confidence_score": 0.5
        }
    
    async def check_delayed_positions(self) -> List[Dict]:
        """遅延中のポジションをチェック"""
        try:
            expired_delays = []
            current_time = datetime.now()
            
            for position_id, avoidance_info in list(self.avoidance_active.items()):
                start_time = avoidance_info["start_time"]
                delay_seconds = avoidance_info["delay_seconds"]
                
                if current_time >= start_time + timedelta(seconds=delay_seconds):
                    expired_delays.append({
                        "position_id": position_id,
                        "avoidance_reason": avoidance_info["reason"],
                        "delay_duration": delay_seconds
                    })
                    
                    # アクティブリストから削除
                    del self.avoidance_active[position_id]
            
            return expired_delays
            
        except Exception as e:
            logger.error(f"Error checking delayed positions: {e}")
            return []