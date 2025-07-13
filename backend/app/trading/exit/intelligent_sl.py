"""
インテリジェント損切り配置システム
市場構造を理解し、最も論理的な損切り位置を自動決定
"""
import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import pandas as pd
import numpy as np
from pybit.unified_trading import HTTP
from ...models import MarketData
from ...services.bybit_client import get_bybit_client
from ..analysis.market_regime import MarketRegimeDetector
import logging

logger = logging.getLogger(__name__)

class IntelligentStopLossPlacement:
    """インテリジェント損切り配置システム"""
    
    def __init__(self):
        self.regime_detector = MarketRegimeDetector()
        self.kelly_fraction = 0.25  # ケリー基準の安全係数
        
    async def calculate_intelligent_stop_loss(
        self,
        entry_price: float,
        symbol: str,
        side: str,  # "Buy" or "Sell"
        market_data: MarketData,
        position_size: float,
        account_balance: float
    ) -> Dict:
        """
        インテリジェントな損切り位置を計算
        
        Returns:
            {
                "stop_loss_price": float,
                "stop_loss_distance": float,
                "stop_loss_percentage": float,
                "placement_reason": str,
                "confidence_score": float,
                "risk_amount": float,
                "methods_analysis": {
                    "structure_based": {...},
                    "volatility_based": {...},
                    "risk_based": {...}
                }
            }
        """
        try:
            # 1. 市場構造ベースの損切り計算
            structure_sl = await self._calculate_structure_based_sl(
                entry_price, symbol, side, market_data
            )
            
            # 2. ボラティリティ適応型損切り計算
            volatility_sl = await self._calculate_volatility_based_sl(
                entry_price, symbol, side, market_data
            )
            
            # 3. リスクベース損切り計算（ケリー基準）
            risk_sl = await self._calculate_risk_based_sl(
                entry_price, symbol, side, position_size, account_balance, market_data
            )
            
            # 4. 複合最適化で最終的な損切り位置を決定
            final_sl = await self._optimize_stop_loss_placement(
                entry_price, side, structure_sl, volatility_sl, risk_sl, market_data
            )
            
            return final_sl
            
        except Exception as e:
            logger.error(f"Error calculating intelligent stop loss: {e}")
            # エラー時は安全な固定損切りを返す
            return self._get_emergency_stop_loss(entry_price, side)
    
    async def _calculate_structure_based_sl(
        self,
        entry_price: float,
        symbol: str,
        side: str,
        market_data: MarketData
    ) -> Dict:
        """市場構造ベースの損切り計算"""
        try:
            df = market_data.df_1h  # 1時間足で構造分析
            
            # サポート・レジスタンスレベルの特定
            support_levels, resistance_levels = await self._identify_key_levels(df)
            
            # スイングハイ・ローの特定
            swing_highs, swing_lows = await self._identify_swing_points(df)
            
            # 損切り位置の決定
            if side == "Buy":
                # ロングの場合：最近のサポートまたはスイングローの下
                key_levels = support_levels + swing_lows
                key_levels = [level for level in key_levels if level < entry_price]
                if key_levels:
                    sl_price = max(key_levels) * 0.995  # 0.5%のバッファ
                else:
                    sl_price = entry_price * 0.97  # デフォルト3%
            else:
                # ショートの場合：最近のレジスタンスまたはスイングハイの上
                key_levels = resistance_levels + swing_highs
                key_levels = [level for level in key_levels if level > entry_price]
                if key_levels:
                    sl_price = min(key_levels) * 1.005  # 0.5%のバッファ
                else:
                    sl_price = entry_price * 1.03  # デフォルト3%
            
            distance = abs(entry_price - sl_price)
            percentage = (distance / entry_price) * 100
            
            return {
                "price": sl_price,
                "distance": distance,
                "percentage": percentage,
                "method": "structure_based",
                "confidence": 0.85,
                "key_levels_found": len(key_levels) if 'key_levels' in locals() else 0
            }
            
        except Exception as e:
            logger.error(f"Error in structure-based SL calculation: {e}")
            return self._get_default_structure_sl(entry_price, side)
    
    async def _calculate_volatility_based_sl(
        self,
        entry_price: float,
        symbol: str,
        side: str,
        market_data: MarketData
    ) -> Dict:
        """ボラティリティ適応型損切り計算"""
        try:
            df = market_data.df_15m  # 15分足でボラティリティ分析
            
            # ATR計算
            atr = df['atr'].iloc[-1]
            current_volatility = (atr / entry_price) * 100
            
            # ボラティリティレジームの判定
            volatility_regime = await self._classify_volatility_regime(current_volatility)
            
            # ボラティリティに応じた乗数
            multipliers = {
                "低ボラティリティ": 1.5,
                "中ボラティリティ": 2.0,
                "高ボラティリティ": 2.5,
                "極高ボラティリティ": 3.0
            }
            
            multiplier = multipliers.get(volatility_regime, 2.0)
            
            # 損切り価格の計算
            if side == "Buy":
                sl_price = entry_price - (atr * multiplier)
            else:
                sl_price = entry_price + (atr * multiplier)
            
            distance = abs(entry_price - sl_price)
            percentage = (distance / entry_price) * 100
            
            return {
                "price": sl_price,
                "distance": distance,
                "percentage": percentage,
                "method": "volatility_based",
                "confidence": 0.80,
                "volatility_regime": volatility_regime,
                "atr_multiplier": multiplier
            }
            
        except Exception as e:
            logger.error(f"Error in volatility-based SL calculation: {e}")
            return self._get_default_volatility_sl(entry_price, side)
    
    async def _calculate_risk_based_sl(
        self,
        entry_price: float,
        symbol: str,
        side: str,
        position_size: float,
        account_balance: float,
        market_data: MarketData
    ) -> Dict:
        """リスクベース損切り計算（ケリー基準）"""
        try:
            # 勝率と期待リターンの推定
            win_rate, avg_win, avg_loss = await self._estimate_trade_statistics(market_data)
            
            # ケリー基準によるリスク計算
            kelly_percentage = self._calculate_kelly_criterion(win_rate, avg_win, avg_loss)
            
            # 最大リスク額の計算（口座残高の2%を上限）
            max_risk_amount = min(
                account_balance * kelly_percentage * self.kelly_fraction,
                account_balance * 0.02
            )
            
            # 損切り価格の計算
            max_loss_per_unit = max_risk_amount / position_size
            
            if side == "Buy":
                sl_price = entry_price - max_loss_per_unit
            else:
                sl_price = entry_price + max_loss_per_unit
            
            distance = abs(entry_price - sl_price)
            percentage = (distance / entry_price) * 100
            
            return {
                "price": sl_price,
                "distance": distance,
                "percentage": percentage,
                "method": "risk_based",
                "confidence": 0.90,
                "kelly_percentage": kelly_percentage,
                "max_risk_amount": max_risk_amount,
                "risk_per_unit": max_loss_per_unit
            }
            
        except Exception as e:
            logger.error(f"Error in risk-based SL calculation: {e}")
            return self._get_default_risk_sl(entry_price, side, account_balance, position_size)
    
    async def _optimize_stop_loss_placement(
        self,
        entry_price: float,
        side: str,
        structure_sl: Dict,
        volatility_sl: Dict,
        risk_sl: Dict,
        market_data: MarketData
    ) -> Dict:
        """複合最適化で最終的な損切り位置を決定"""
        try:
            # 市場レジームの取得
            regime = self.regime_detector.detect_regime(market_data.df_1h)
            
            # レジームに応じた重み付け
            if regime.regime_type in ["STRONG_TREND", "BREAKOUT"]:
                # トレンド相場：構造ベースを重視
                weights = {
                    "structure": 0.5,
                    "volatility": 0.3,
                    "risk": 0.2
                }
            elif regime.regime_type == "RANGE":
                # レンジ相場：ボラティリティベースを重視
                weights = {
                    "structure": 0.3,
                    "volatility": 0.5,
                    "risk": 0.2
                }
            else:
                # その他：バランス型
                weights = {
                    "structure": 0.4,
                    "volatility": 0.3,
                    "risk": 0.3
                }
            
            # 加重平均で最終的な損切り価格を計算
            weighted_sl_price = (
                structure_sl["price"] * weights["structure"] +
                volatility_sl["price"] * weights["volatility"] +
                risk_sl["price"] * weights["risk"]
            )
            
            # 最も保守的な損切りを下限として設定
            if side == "Buy":
                final_sl_price = max(
                    weighted_sl_price,
                    max(structure_sl["price"], volatility_sl["price"], risk_sl["price"])
                )
            else:
                final_sl_price = min(
                    weighted_sl_price,
                    min(structure_sl["price"], volatility_sl["price"], risk_sl["price"])
                )
            
            distance = abs(entry_price - final_sl_price)
            percentage = (distance / entry_price) * 100
            
            # 配置理由の決定
            placement_reason = self._determine_placement_reason(
                weights, structure_sl, volatility_sl, risk_sl
            )
            
            # 信頼スコアの計算
            confidence_score = (
                structure_sl["confidence"] * weights["structure"] +
                volatility_sl["confidence"] * weights["volatility"] +
                risk_sl["confidence"] * weights["risk"]
            )
            
            return {
                "stop_loss_price": final_sl_price,
                "stop_loss_distance": distance,
                "stop_loss_percentage": percentage,
                "placement_reason": placement_reason,
                "confidence_score": confidence_score,
                "risk_amount": distance * risk_sl.get("position_size", 1),
                "methods_analysis": {
                    "structure_based": structure_sl,
                    "volatility_based": volatility_sl,
                    "risk_based": risk_sl
                },
                "optimization_weights": weights,
                "market_regime": regime.regime_type
            }
            
        except Exception as e:
            logger.error(f"Error in stop loss optimization: {e}")
            return self._get_emergency_stop_loss(entry_price, side)
    
    async def _identify_key_levels(self, df: pd.DataFrame) -> Tuple[List[float], List[float]]:
        """サポート・レジスタンスレベルの特定"""
        try:
            highs = df['high'].rolling(window=20).max()
            lows = df['low'].rolling(window=20).min()
            
            # 価格が複数回タッチしたレベルを特定
            support_levels = []
            resistance_levels = []
            
            for i in range(20, len(df)):
                # サポートレベル
                if df['low'].iloc[i] == lows.iloc[i]:
                    level = df['low'].iloc[i]
                    touches = sum(abs(df['low'] - level) / level < 0.001)
                    if touches >= 2:
                        support_levels.append(level)
                
                # レジスタンスレベル
                if df['high'].iloc[i] == highs.iloc[i]:
                    level = df['high'].iloc[i]
                    touches = sum(abs(df['high'] - level) / level < 0.001)
                    if touches >= 2:
                        resistance_levels.append(level)
            
            # 重複を除去して最新の5レベルのみ保持
            support_levels = list(set(support_levels))[-5:]
            resistance_levels = list(set(resistance_levels))[-5:]
            
            return support_levels, resistance_levels
            
        except Exception as e:
            logger.error(f"Error identifying key levels: {e}")
            return [], []
    
    async def _identify_swing_points(self, df: pd.DataFrame) -> Tuple[List[float], List[float]]:
        """スイングハイ・ローの特定"""
        try:
            swing_highs = []
            swing_lows = []
            
            for i in range(2, len(df) - 2):
                # スイングハイ
                if (df['high'].iloc[i] > df['high'].iloc[i-1] and 
                    df['high'].iloc[i] > df['high'].iloc[i-2] and
                    df['high'].iloc[i] > df['high'].iloc[i+1] and 
                    df['high'].iloc[i] > df['high'].iloc[i+2]):
                    swing_highs.append(df['high'].iloc[i])
                
                # スイングロー
                if (df['low'].iloc[i] < df['low'].iloc[i-1] and 
                    df['low'].iloc[i] < df['low'].iloc[i-2] and
                    df['low'].iloc[i] < df['low'].iloc[i+1] and 
                    df['low'].iloc[i] < df['low'].iloc[i+2]):
                    swing_lows.append(df['low'].iloc[i])
            
            # 最新の5つのみ保持
            return swing_highs[-5:], swing_lows[-5:]
            
        except Exception as e:
            logger.error(f"Error identifying swing points: {e}")
            return [], []
    
    async def _classify_volatility_regime(self, volatility_percentage: float) -> str:
        """ボラティリティレジームの分類"""
        if volatility_percentage < 0.5:
            return "低ボラティリティ"
        elif volatility_percentage < 1.0:
            return "中ボラティリティ"
        elif volatility_percentage < 2.0:
            return "高ボラティリティ"
        else:
            return "極高ボラティリティ"
    
    async def _estimate_trade_statistics(self, market_data: MarketData) -> Tuple[float, float, float]:
        """過去の取引統計を推定"""
        try:
            df = market_data.df_1h
            
            # 簡易的な取引シミュレーション
            trades = []
            for i in range(20, len(df) - 1):
                # RSIベースの簡易エントリー
                if df['rsi'].iloc[i] < 30:  # ロングエントリー
                    entry = df['close'].iloc[i]
                    exit = df['close'].iloc[i + 1]
                    trades.append((exit - entry) / entry)
                elif df['rsi'].iloc[i] > 70:  # ショートエントリー
                    entry = df['close'].iloc[i]
                    exit = df['close'].iloc[i + 1]
                    trades.append((entry - exit) / entry)
            
            if not trades:
                return 0.5, 0.02, 0.02  # デフォルト値
            
            wins = [t for t in trades if t > 0]
            losses = [t for t in trades if t < 0]
            
            win_rate = len(wins) / len(trades) if trades else 0.5
            avg_win = np.mean(wins) if wins else 0.02
            avg_loss = abs(np.mean(losses)) if losses else 0.02
            
            return win_rate, avg_win, avg_loss
            
        except Exception as e:
            logger.error(f"Error estimating trade statistics: {e}")
            return 0.5, 0.02, 0.02
    
    def _calculate_kelly_criterion(self, win_rate: float, avg_win: float, avg_loss: float) -> float:
        """ケリー基準によるリスク率の計算"""
        if avg_loss == 0:
            return 0.02  # デフォルト2%
        
        b = avg_win / avg_loss
        p = win_rate
        q = 1 - p
        
        kelly = (p * b - q) / b
        
        # 0〜25%の範囲に制限
        return max(0, min(kelly, 0.25))
    
    def _determine_placement_reason(
        self,
        weights: Dict,
        structure_sl: Dict,
        volatility_sl: Dict,
        risk_sl: Dict
    ) -> str:
        """損切り配置の理由を決定"""
        reasons = []
        
        if weights["structure"] >= 0.4:
            reasons.append(f"市場構造（キーレベル: {structure_sl.get('key_levels_found', 0)}個）")
        
        if weights["volatility"] >= 0.4:
            reasons.append(f"ボラティリティ（{volatility_sl.get('volatility_regime', '')}）")
        
        if weights["risk"] >= 0.3:
            reasons.append(f"リスク管理（ケリー基準: {risk_sl.get('kelly_percentage', 0):.1%}）")
        
        return "、".join(reasons) + "に基づく最適配置"
    
    def _get_emergency_stop_loss(self, entry_price: float, side: str) -> Dict:
        """緊急時のデフォルト損切り"""
        if side == "Buy":
            sl_price = entry_price * 0.95  # 5%損切り
        else:
            sl_price = entry_price * 1.05  # 5%損切り
        
        distance = abs(entry_price - sl_price)
        percentage = 5.0
        
        return {
            "stop_loss_price": sl_price,
            "stop_loss_distance": distance,
            "stop_loss_percentage": percentage,
            "placement_reason": "緊急デフォルト損切り（5%）",
            "confidence_score": 0.5,
            "risk_amount": distance,
            "methods_analysis": {
                "structure_based": {"method": "emergency"},
                "volatility_based": {"method": "emergency"},
                "risk_based": {"method": "emergency"}
            }
        }
    
    def _get_default_structure_sl(self, entry_price: float, side: str) -> Dict:
        """デフォルトの構造ベース損切り"""
        if side == "Buy":
            sl_price = entry_price * 0.97
        else:
            sl_price = entry_price * 1.03
        
        return {
            "price": sl_price,
            "distance": abs(entry_price - sl_price),
            "percentage": 3.0,
            "method": "structure_based_default",
            "confidence": 0.6,
            "key_levels_found": 0
        }
    
    def _get_default_volatility_sl(self, entry_price: float, side: str) -> Dict:
        """デフォルトのボラティリティベース損切り"""
        if side == "Buy":
            sl_price = entry_price * 0.96
        else:
            sl_price = entry_price * 1.04
        
        return {
            "price": sl_price,
            "distance": abs(entry_price - sl_price),
            "percentage": 4.0,
            "method": "volatility_based_default",
            "confidence": 0.6,
            "volatility_regime": "不明",
            "atr_multiplier": 2.0
        }
    
    def _get_default_risk_sl(
        self,
        entry_price: float,
        side: str,
        account_balance: float,
        position_size: float
    ) -> Dict:
        """デフォルトのリスクベース損切り"""
        max_risk_amount = account_balance * 0.02  # 2%リスク
        max_loss_per_unit = max_risk_amount / position_size if position_size > 0 else entry_price * 0.02
        
        if side == "Buy":
            sl_price = entry_price - max_loss_per_unit
        else:
            sl_price = entry_price + max_loss_per_unit
        
        return {
            "price": sl_price,
            "distance": abs(entry_price - sl_price),
            "percentage": (abs(entry_price - sl_price) / entry_price) * 100,
            "method": "risk_based_default",
            "confidence": 0.7,
            "kelly_percentage": 0.02,
            "max_risk_amount": max_risk_amount,
            "risk_per_unit": max_loss_per_unit
        }