"""
ダイナミック損切り調整システム
相場状況に応じて損切りを動的に調整し、利益を最大化
"""
import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from pybit.unified_trading import HTTP
from ...models import MarketData
from ...services.bybit_client import get_bybit_client
from ..analysis.market_regime import MarketRegimeDetector
import logging

logger = logging.getLogger(__name__)

class DynamicStopLossAdjustment:
    """ダイナミック損切り調整システム"""
    
    def __init__(self):
        self.regime_detector = MarketRegimeDetector()
        self.adjustment_history = {}  # ポジション別の調整履歴
        
    async def adjust_stop_loss(
        self,
        position_id: str,
        entry_price: float,
        current_price: float,
        current_sl: float,
        symbol: str,
        side: str,
        market_data: MarketData,
        unrealized_pnl: float
    ) -> Dict:
        """
        損切りをダイナミックに調整
        
        Returns:
            {
                "new_stop_loss": float,
                "adjustment_type": str,
                "adjustment_reason": str,
                "breakeven_triggered": bool,
                "trailing_distance": float,
                "confidence_score": float
            }
        """
        try:
            # 1. ブレークイーブン移動の評価
            breakeven_result = await self._evaluate_breakeven_move(
                position_id, entry_price, current_price, current_sl, side, unrealized_pnl
            )
            
            # 2. トレーリングストップの評価
            trailing_result = await self._evaluate_trailing_stop(
                position_id, entry_price, current_price, current_sl, side, market_data
            )
            
            # 3. ボラティリティベース調整の評価
            volatility_result = await self._evaluate_volatility_adjustment(
                current_price, current_sl, side, market_data
            )
            
            # 4. 相場環境ベース調整の評価
            regime_result = await self._evaluate_regime_adjustment(
                current_price, current_sl, side, market_data
            )
            
            # 5. 最適な調整方法を決定
            final_adjustment = await self._optimize_adjustment(
                current_sl, breakeven_result, trailing_result, 
                volatility_result, regime_result, side
            )
            
            # 6. 調整履歴を更新
            self._update_adjustment_history(position_id, final_adjustment)
            
            return final_adjustment
            
        except Exception as e:
            logger.error(f"Error in dynamic stop loss adjustment: {e}")
            return self._get_no_adjustment_result(current_sl)
    
    async def _evaluate_breakeven_move(
        self,
        position_id: str,
        entry_price: float,
        current_price: float,
        current_sl: float,
        side: str,
        unrealized_pnl: float
    ) -> Dict:
        """ブレークイーブン移動の評価"""
        try:
            profit_percentage = abs(unrealized_pnl) / abs(current_price - entry_price) * 100
            
            # ブレークイーブン移動の条件
            should_move_to_breakeven = False
            move_reason = ""
            
            if side == "Buy":
                is_profitable = current_price > entry_price
                profit_threshold = (current_price - entry_price) / entry_price >= 0.015  # 1.5%以上の含み益
            else:
                is_profitable = current_price < entry_price
                profit_threshold = (entry_price - current_price) / entry_price >= 0.015  # 1.5%以上の含み益
            
            # まだブレークイーブンに移動していない場合
            history = self.adjustment_history.get(position_id, {})
            already_at_breakeven = history.get("breakeven_triggered", False)
            
            if not already_at_breakeven and is_profitable and profit_threshold:
                should_move_to_breakeven = True
                move_reason = f"1.5%以上の含み益達成（現在: {profit_percentage:.1f}%）"
            
            # ブレークイーブン価格の計算（わずかなバッファを含む）
            if side == "Buy":
                breakeven_price = entry_price * 1.001  # 0.1%のバッファ
            else:
                breakeven_price = entry_price * 0.999  # 0.1%のバッファ
            
            return {
                "should_adjust": should_move_to_breakeven,
                "new_stop_loss": breakeven_price if should_move_to_breakeven else current_sl,
                "adjustment_type": "breakeven",
                "reason": move_reason,
                "confidence": 0.95 if should_move_to_breakeven else 0.0,
                "profit_percentage": profit_percentage
            }
            
        except Exception as e:
            logger.error(f"Error in breakeven evaluation: {e}")
            return {"should_adjust": False, "new_stop_loss": current_sl, "confidence": 0.0}
    
    async def _evaluate_trailing_stop(
        self,
        position_id: str,
        entry_price: float,
        current_price: float,
        current_sl: float,
        side: str,
        market_data: MarketData
    ) -> Dict:
        """トレーリングストップの評価"""
        try:
            df = market_data.df_15m
            current_atr = df['atr'].iloc[-1]
            
            # トレーリング距離の計算（ATRベース）
            trailing_distance = current_atr * 2.0
            
            # 新しいトレーリングストップの計算
            if side == "Buy":
                new_trailing_sl = current_price - trailing_distance
                should_trail = new_trailing_sl > current_sl
            else:
                new_trailing_sl = current_price + trailing_distance
                should_trail = new_trailing_sl < current_sl
            
            # トレーリング条件の確認
            trail_reason = ""
            if should_trail:
                price_move_percentage = abs(current_price - entry_price) / entry_price * 100
                if price_move_percentage >= 2.0:  # 2%以上の価格変動
                    trail_reason = f"価格が{price_move_percentage:.1f}%変動、ATR×2でトレーリング"
                else:
                    should_trail = False
            
            return {
                "should_adjust": should_trail,
                "new_stop_loss": new_trailing_sl if should_trail else current_sl,
                "adjustment_type": "trailing",
                "reason": trail_reason,
                "confidence": 0.80 if should_trail else 0.0,
                "trailing_distance": trailing_distance
            }
            
        except Exception as e:
            logger.error(f"Error in trailing stop evaluation: {e}")
            return {"should_adjust": False, "new_stop_loss": current_sl, "confidence": 0.0}
    
    async def _evaluate_volatility_adjustment(
        self,
        current_price: float,
        current_sl: float,
        side: str,
        market_data: MarketData
    ) -> Dict:
        """ボラティリティベース調整の評価"""
        try:
            df = market_data.df_1h
            
            # ボラティリティの変化を計算
            current_atr = df['atr'].iloc[-1]
            previous_atr = df['atr'].iloc[-24:].mean()  # 24時間平均
            
            volatility_ratio = current_atr / previous_atr
            
            should_adjust = False
            adjustment_reason = ""
            new_sl = current_sl
            
            # ボラティリティが大幅に変化した場合の調整
            if volatility_ratio > 1.5:
                # ボラティリティ急増：損切りを遠ざける
                adjustment_factor = min(volatility_ratio, 2.0)
                current_distance = abs(current_price - current_sl)
                new_distance = current_distance * adjustment_factor
                
                if side == "Buy":
                    new_sl = current_price - new_distance
                else:
                    new_sl = current_price + new_distance
                
                should_adjust = True
                adjustment_reason = f"ボラティリティ急増（{volatility_ratio:.1f}倍）により損切り調整"
                
            elif volatility_ratio < 0.6:
                # ボラティリティ急減：損切りを近づける
                adjustment_factor = max(volatility_ratio, 0.5)
                current_distance = abs(current_price - current_sl)
                new_distance = current_distance * adjustment_factor
                
                if side == "Buy":
                    new_sl = current_price - new_distance
                else:
                    new_sl = current_price + new_distance
                
                should_adjust = True
                adjustment_reason = f"ボラティリティ急減（{volatility_ratio:.1f}倍）により損切り調整"
            
            return {
                "should_adjust": should_adjust,
                "new_stop_loss": new_sl,
                "adjustment_type": "volatility",
                "reason": adjustment_reason,
                "confidence": 0.70 if should_adjust else 0.0,
                "volatility_ratio": volatility_ratio
            }
            
        except Exception as e:
            logger.error(f"Error in volatility adjustment evaluation: {e}")
            return {"should_adjust": False, "new_stop_loss": current_sl, "confidence": 0.0}
    
    async def _evaluate_regime_adjustment(
        self,
        current_price: float,
        current_sl: float,
        side: str,
        market_data: MarketData
    ) -> Dict:
        """相場環境ベース調整の評価"""
        try:
            regime = self.regime_detector.detect_regime(market_data.df_1h)
            
            should_adjust = False
            adjustment_reason = ""
            new_sl = current_sl
            
            # 相場環境に応じた調整
            if regime.regime_type == "STRONG_TREND" and regime.confidence_score > 0.8:
                # 強いトレンド：より攻撃的なトレーリング
                current_distance = abs(current_price - current_sl)
                new_distance = current_distance * 0.8  # 20%近づける
                
                if side == "Buy":
                    new_sl = current_price - new_distance
                    should_adjust = new_sl > current_sl
                else:
                    new_sl = current_price + new_distance
                    should_adjust = new_sl < current_sl
                
                if should_adjust:
                    adjustment_reason = f"強トレンド環境（信頼度{regime.confidence_score:.1%}）によりアグレッシブ調整"
                
            elif regime.regime_type == "VOLATILE" and regime.confidence_score > 0.7:
                # 高ボラティリティ：より保守的な損切り
                current_distance = abs(current_price - current_sl)
                new_distance = current_distance * 1.2  # 20%遠ざける
                
                if side == "Buy":
                    new_sl = current_price - new_distance
                    should_adjust = new_sl < current_sl
                else:
                    new_sl = current_price + new_distance
                    should_adjust = new_sl > current_sl
                
                if should_adjust:
                    adjustment_reason = f"高ボラティリティ環境（信頼度{regime.confidence_score:.1%}）により保守的調整"
            
            return {
                "should_adjust": should_adjust,
                "new_stop_loss": new_sl,
                "adjustment_type": "regime",
                "reason": adjustment_reason,
                "confidence": 0.75 if should_adjust else 0.0,
                "regime_type": regime.regime_type,
                "regime_confidence": regime.confidence_score
            }
            
        except Exception as e:
            logger.error(f"Error in regime adjustment evaluation: {e}")
            return {"should_adjust": False, "new_stop_loss": current_sl, "confidence": 0.0}
    
    async def _optimize_adjustment(
        self,
        current_sl: float,
        breakeven_result: Dict,
        trailing_result: Dict,
        volatility_result: Dict,
        regime_result: Dict,
        side: str
    ) -> Dict:
        """最適な調整方法を決定"""
        try:
            # 各調整方法の信頼度を取得
            adjustments = [
                breakeven_result,
                trailing_result,
                volatility_result,
                regime_result
            ]
            
            # 調整が必要な方法をフィルタリング
            valid_adjustments = [adj for adj in adjustments if adj.get("should_adjust", False)]
            
            if not valid_adjustments:
                return self._get_no_adjustment_result(current_sl)
            
            # 最も信頼度の高い調整を選択
            best_adjustment = max(valid_adjustments, key=lambda x: x.get("confidence", 0))
            
            # ブレークイーブンは優先度が高い
            breakeven_adjustment = next(
                (adj for adj in valid_adjustments if adj.get("adjustment_type") == "breakeven"),
                None
            )
            
            if breakeven_adjustment:
                final_adjustment = breakeven_adjustment
            else:
                final_adjustment = best_adjustment
            
            # 最終的な損切り価格の決定
            new_sl = final_adjustment["new_stop_loss"]
            
            # 安全性チェック：損切りが逆方向に動かないようにする
            if side == "Buy" and new_sl < current_sl:
                new_sl = current_sl
                final_adjustment["reason"] += "（安全性チェックにより据え置き）"
            elif side == "Sell" and new_sl > current_sl:
                new_sl = current_sl
                final_adjustment["reason"] += "（安全性チェックにより据え置き）"
            
            return {
                "new_stop_loss": new_sl,
                "adjustment_type": final_adjustment.get("adjustment_type", "none"),
                "adjustment_reason": final_adjustment.get("reason", "調整なし"),
                "breakeven_triggered": final_adjustment.get("adjustment_type") == "breakeven",
                "trailing_distance": final_adjustment.get("trailing_distance", 0),
                "confidence_score": final_adjustment.get("confidence", 0),
                "original_sl": current_sl,
                "adjustment_amount": abs(new_sl - current_sl),
                "all_evaluations": {
                    "breakeven": breakeven_result,
                    "trailing": trailing_result,
                    "volatility": volatility_result,
                    "regime": regime_result
                }
            }
            
        except Exception as e:
            logger.error(f"Error in adjustment optimization: {e}")
            return self._get_no_adjustment_result(current_sl)
    
    def _update_adjustment_history(self, position_id: str, adjustment: Dict):
        """調整履歴を更新"""
        if position_id not in self.adjustment_history:
            self.adjustment_history[position_id] = {
                "adjustments": [],
                "breakeven_triggered": False
            }
        
        self.adjustment_history[position_id]["adjustments"].append({
            "timestamp": datetime.now(),
            "adjustment": adjustment
        })
        
        if adjustment.get("breakeven_triggered", False):
            self.adjustment_history[position_id]["breakeven_triggered"] = True
        
        # 履歴は最新の20件のみ保持
        if len(self.adjustment_history[position_id]["adjustments"]) > 20:
            self.adjustment_history[position_id]["adjustments"] = \
                self.adjustment_history[position_id]["adjustments"][-20:]
    
    def _get_no_adjustment_result(self, current_sl: float) -> Dict:
        """調整なしの結果"""
        return {
            "new_stop_loss": current_sl,
            "adjustment_type": "none",
            "adjustment_reason": "現在の損切り位置が最適",
            "breakeven_triggered": False,
            "trailing_distance": 0,
            "confidence_score": 0.5,
            "original_sl": current_sl,
            "adjustment_amount": 0
        }
    
    async def get_adjustment_suggestions(
        self,
        symbol: str,
        positions: List[Dict]
    ) -> List[Dict]:
        """全ポジションの調整提案を取得"""
        try:
            suggestions = []
            
            for position in positions:
                if position.get("size", 0) == 0:
                    continue
                
                # マーケットデータを取得（実際の実装では適切なデータ取得）
                market_data = await self._get_market_data(symbol)
                
                adjustment = await self.adjust_stop_loss(
                    position_id=position.get("position_id", ""),
                    entry_price=float(position.get("avg_price", 0)),
                    current_price=float(position.get("mark_price", 0)),
                    current_sl=float(position.get("stop_loss", 0)),
                    symbol=symbol,
                    side=position.get("side", ""),
                    market_data=market_data,
                    unrealized_pnl=float(position.get("unrealised_pnl", 0))
                )
                
                if adjustment["adjustment_type"] != "none":
                    suggestions.append({
                        "position_id": position.get("position_id"),
                        "symbol": symbol,
                        "current_sl": adjustment["original_sl"],
                        "suggested_sl": adjustment["new_stop_loss"],
                        "adjustment_type": adjustment["adjustment_type"],
                        "reason": adjustment["adjustment_reason"],
                        "confidence": adjustment["confidence_score"]
                    })
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Error getting adjustment suggestions: {e}")
            return []
    
    async def _get_market_data(self, symbol: str) -> MarketData:
        """マーケットデータを取得（プレースホルダー）"""
        # 実際の実装では適切なマーケットデータを取得
        pass