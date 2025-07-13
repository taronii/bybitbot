"""
動的利確ターゲット計算エンジン
市場状況に応じて最適な利確レベルを動的に計算
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)

@dataclass
class TakeProfitLevel:
    level: int
    price: float
    percentage: float  # ポジションサイズの何%を決済
    reason: str
    executed: bool = False

@dataclass
class DynamicTPResult:
    levels: List[TakeProfitLevel]
    weighted_average_tp: float
    expected_return: float
    confidence: float
    strategy_type: str

class DynamicTakeProfitCalculator:
    """
    市場状況に応じて最適な利確レベルを動的に計算
    """
    
    def __init__(self, session):
        self.session = session
        self.fib_extensions = [1.272, 1.618, 2.0, 2.618, 3.618]
        self.round_number_threshold = 0.001  # 0.1%以内を心理的節目とする
        
    async def calculate_take_profit_levels(self, 
                                         entry_price: float,
                                         symbol: str,
                                         side: str,
                                         market_data: Dict) -> DynamicTPResult:
        """
        動的な利確レベルを計算
        
        Parameters:
        -----------
        entry_price : float
            エントリー価格
        symbol : str
            取引シンボル
        side : str
            'BUY' or 'SELL'
        market_data : dict
            市場データ（ATR、レジーム、ボラティリティ等）
            
        Returns:
        --------
        DynamicTPResult : 計算された利確レベル
        """
        try:
            # 1. ボラティリティベースの利確計算
            base_tp = self._calculate_volatility_based_tp(
                entry_price, market_data['atr'], side
            )
            
            # 2. テクニカルレベルの特定
            technical_levels = await self._find_technical_levels(
                symbol, entry_price, side
            )
            
            # 3. 段階的利確レベルの設定
            tp_levels = self._create_staged_tp_levels(
                entry_price, base_tp, technical_levels, 
                market_data, side
            )
            
            # 4. 加重平均TPと期待リターンの計算
            weighted_avg = self._calculate_weighted_average_tp(tp_levels, entry_price)
            expected_return = (weighted_avg - entry_price) / entry_price
            
            # 5. 信頼度の計算
            confidence = self._calculate_confidence(market_data, technical_levels)
            
            # 6. 戦略タイプの決定
            strategy_type = self._determine_strategy_type(market_data)
            
            return DynamicTPResult(
                levels=tp_levels,
                weighted_average_tp=weighted_avg,
                expected_return=expected_return,
                confidence=confidence,
                strategy_type=strategy_type
            )
            
        except Exception as e:
            logger.error(f"Failed to calculate TP levels: {e}")
            # フォールバック：固定利確
            return self._get_fallback_tp_levels(entry_price, side)
    
    def _calculate_volatility_based_tp(self, entry_price: float, 
                                     atr: float, side: str) -> float:
        """ボラティリティベースの利確価格を計算"""
        volatility_ratio = atr / entry_price
        
        # ボラティリティに応じた利確幅
        if volatility_ratio > 0.03:  # 高ボラ（3%以上）
            tp_multiplier = 3.0
        elif volatility_ratio > 0.015:  # 中ボラ（1.5-3%）
            tp_multiplier = 2.5
        else:  # 低ボラ（1.5%未満）
            tp_multiplier = 2.0
        
        if side == 'BUY':
            return entry_price + (atr * tp_multiplier)
        else:
            return entry_price - (atr * tp_multiplier)
    
    async def _find_technical_levels(self, symbol: str, 
                                   entry_price: float, side: str) -> Dict:
        """重要なテクニカルレベルを特定"""
        try:
            # 日足データを取得
            kline_response = self.session.get_kline(
                category="linear",
                symbol=symbol,
                interval="D",
                limit=100
            )
            
            if kline_response["retCode"] != 0:
                return self._get_default_technical_levels(entry_price, side)
            
            df = self._create_dataframe(kline_response["result"]["list"])
            
            # レジスタンス/サポートレベルの特定
            resistance_levels = []
            support_levels = []
            
            if side == 'BUY':
                # ロングの場合、上のレジスタンスを探す
                resistance_levels = self._find_resistance_levels(df, entry_price)
                pivot_levels = self._calculate_pivot_points(df)
                round_numbers = self._find_round_numbers(entry_price, 'up')
            else:
                # ショートの場合、下のサポートを探す
                support_levels = self._find_support_levels(df, entry_price)
                pivot_levels = self._calculate_pivot_points(df)
                round_numbers = self._find_round_numbers(entry_price, 'down')
            
            # フィボナッチエクステンション
            fib_targets = self._calculate_fibonacci_extensions(
                df, entry_price, side
            )
            
            return {
                'resistance': resistance_levels,
                'support': support_levels,
                'pivot': pivot_levels,
                'fibonacci': fib_targets,
                'round_numbers': round_numbers
            }
            
        except Exception as e:
            logger.error(f"Failed to find technical levels: {e}")
            return self._get_default_technical_levels(entry_price, side)
    
    def _find_resistance_levels(self, df: pd.DataFrame, 
                               current_price: float) -> List[float]:
        """レジスタンスレベルを特定"""
        highs = df['high'].values
        levels = []
        
        # スイングハイを探す
        for i in range(2, len(highs) - 2):
            if (highs[i] > highs[i-1] and highs[i] > highs[i-2] and
                highs[i] > highs[i+1] and highs[i] > highs[i+2]):
                if highs[i] > current_price:
                    levels.append(highs[i])
        
        # 重複を除去して価格順にソート
        levels = sorted(list(set(levels)))
        
        # 最も近い3つのレジスタンスを返す
        return levels[:3] if levels else [current_price * 1.02, 
                                         current_price * 1.05, 
                                         current_price * 1.10]
    
    def _find_support_levels(self, df: pd.DataFrame, 
                            current_price: float) -> List[float]:
        """サポートレベルを特定"""
        lows = df['low'].values
        levels = []
        
        # スイングローを探す
        for i in range(2, len(lows) - 2):
            if (lows[i] < lows[i-1] and lows[i] < lows[i-2] and
                lows[i] < lows[i+1] and lows[i] < lows[i+2]):
                if lows[i] < current_price:
                    levels.append(lows[i])
        
        # 重複を除去して価格順にソート（降順）
        levels = sorted(list(set(levels)), reverse=True)
        
        # 最も近い3つのサポートを返す
        return levels[:3] if levels else [current_price * 0.98, 
                                        current_price * 0.95, 
                                        current_price * 0.90]
    
    def _calculate_pivot_points(self, df: pd.DataFrame) -> Dict:
        """ピボットポイントを計算"""
        # 前日のデータ
        last_candle = df.iloc[-1]
        high = last_candle['high']
        low = last_candle['low']
        close = last_candle['close']
        
        # 標準ピボットポイント
        pivot = (high + low + close) / 3
        
        # レジスタンスとサポート
        r1 = 2 * pivot - low
        r2 = pivot + (high - low)
        r3 = high + 2 * (pivot - low)
        
        s1 = 2 * pivot - high
        s2 = pivot - (high - low)
        s3 = low - 2 * (high - pivot)
        
        return {
            'pivot': pivot,
            'resistance': [r1, r2, r3],
            'support': [s1, s2, s3]
        }
    
    def _calculate_fibonacci_extensions(self, df: pd.DataFrame, 
                                      entry_price: float, side: str) -> List[float]:
        """フィボナッチエクステンションを計算"""
        # 直近のスイングを特定
        recent_high = df['high'].iloc[-20:].max()
        recent_low = df['low'].iloc[-20:].min()
        swing_range = recent_high - recent_low
        
        fib_levels = []
        
        if side == 'BUY':
            # ロングの場合、上方向のエクステンション
            for ratio in self.fib_extensions:
                level = recent_low + (swing_range * ratio)
                if level > entry_price:
                    fib_levels.append(level)
        else:
            # ショートの場合、下方向のエクステンション
            for ratio in self.fib_extensions:
                level = recent_high - (swing_range * ratio)
                if level < entry_price:
                    fib_levels.append(level)
        
        return fib_levels[:5]  # 最大5レベル
    
    def _find_round_numbers(self, price: float, direction: str) -> List[float]:
        """心理的節目（ラウンドナンバー）を特定"""
        round_numbers = []
        
        # 価格の桁数に応じて刻み幅を決定
        if price >= 10000:
            step = 1000
        elif price >= 1000:
            step = 100
        elif price >= 100:
            step = 10
        elif price >= 10:
            step = 1
        else:
            step = 0.1
        
        # 現在価格から上下のラウンドナンバーを探す
        base = int(price / step) * step
        
        if direction == 'up':
            for i in range(1, 6):
                round_num = base + (step * i)
                if round_num > price * 1.001:  # 0.1%以上離れている
                    round_numbers.append(round_num)
        else:
            for i in range(1, 6):
                round_num = base - (step * i)
                if round_num < price * 0.999:  # 0.1%以上離れている
                    round_numbers.append(round_num)
        
        return round_numbers[:3]
    
    def _create_staged_tp_levels(self, entry_price: float, base_tp: float,
                               technical_levels: Dict, market_data: Dict,
                               side: str) -> List[TakeProfitLevel]:
        """段階的な利確レベルを作成"""
        tp_levels = []
        
        if side == 'BUY':
            # TP1: 最初のテクニカルレベル（40%）
            first_resistance = technical_levels['resistance'][0] if technical_levels['resistance'] else base_tp * 0.4
            tp1_price = min(base_tp * 0.5, first_resistance)
            
            # TP2: ATRベースターゲット（30%）
            tp2_price = base_tp
            
            # TP3: フィボナッチ1.618（20%）
            fib_target = technical_levels['fibonacci'][1] if len(technical_levels['fibonacci']) > 1 else base_tp * 1.5
            tp3_price = max(base_tp * 1.5, fib_target)
            
            # TP4: ムーンショット（10%）
            if market_data.get('regime') == 'STRONG_TREND':
                tp4_price = entry_price * 1.10  # 強トレンドなら10%狙い
            else:
                tp4_price = technical_levels['fibonacci'][2] if len(technical_levels['fibonacci']) > 2 else base_tp * 2.0
            
        else:  # SELL
            # ショートの場合は逆方向
            first_support = technical_levels['support'][0] if technical_levels['support'] else base_tp * 0.4
            tp1_price = max(base_tp * 0.5, first_support)
            tp2_price = base_tp
            fib_target = technical_levels['fibonacci'][1] if len(technical_levels['fibonacci']) > 1 else base_tp * 1.5
            tp3_price = min(base_tp * 1.5, fib_target)
            
            if market_data.get('regime') == 'STRONG_TREND':
                tp4_price = entry_price * 0.90
            else:
                tp4_price = technical_levels['fibonacci'][2] if len(technical_levels['fibonacci']) > 2 else base_tp * 2.0
        
        # 利確レベルを作成
        tp_levels.append(TakeProfitLevel(
            level=1,
            price=tp1_price,
            percentage=40,
            reason="最初のテクニカルレジスタンス"
        ))
        
        tp_levels.append(TakeProfitLevel(
            level=2,
            price=tp2_price,
            percentage=30,
            reason="ATRベースターゲット"
        ))
        
        tp_levels.append(TakeProfitLevel(
            level=3,
            price=tp3_price,
            percentage=20,
            reason="フィボナッチエクステンション1.618"
        ))
        
        tp_levels.append(TakeProfitLevel(
            level=4,
            price=tp4_price,
            percentage=10,
            reason="ムーンショットターゲット"
        ))
        
        return tp_levels
    
    def _calculate_weighted_average_tp(self, tp_levels: List[TakeProfitLevel],
                                     entry_price: float) -> float:
        """加重平均利確価格を計算"""
        total_weight = 0
        weighted_sum = 0
        
        for tp in tp_levels:
            weighted_sum += tp.price * tp.percentage
            total_weight += tp.percentage
        
        return weighted_sum / total_weight if total_weight > 0 else entry_price
    
    def _calculate_confidence(self, market_data: Dict, 
                            technical_levels: Dict) -> float:
        """利確レベルの信頼度を計算"""
        confidence_factors = []
        
        # 1. レジーム適合度
        if market_data.get('regime') in ['STRONG_TREND', 'BREAKOUT']:
            confidence_factors.append(0.9)
        elif market_data.get('regime') == 'RANGE':
            confidence_factors.append(0.7)
        else:
            confidence_factors.append(0.5)
        
        # 2. テクニカルレベルの明確さ
        tech_level_count = (len(technical_levels.get('resistance', [])) + 
                          len(technical_levels.get('support', [])))
        if tech_level_count >= 5:
            confidence_factors.append(0.8)
        elif tech_level_count >= 3:
            confidence_factors.append(0.6)
        else:
            confidence_factors.append(0.4)
        
        # 3. ボラティリティ適正度
        atr = market_data.get('atr', 0)
        if 0.01 < atr / market_data.get('price', 1) < 0.03:
            confidence_factors.append(0.8)  # 適正ボラティリティ
        else:
            confidence_factors.append(0.5)
        
        return sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.5
    
    def _determine_strategy_type(self, market_data: Dict) -> str:
        """市場環境に応じた戦略タイプを決定"""
        regime = market_data.get('regime', 'UNKNOWN')
        volatility = market_data.get('volatility_level', 'MEDIUM')
        
        if regime == 'STRONG_TREND':
            return 'trend_following'
        elif regime == 'RANGE':
            return 'mean_reversion'
        elif volatility == 'HIGH':
            return 'quick_scalp'
        elif regime == 'BREAKOUT':
            return 'breakout_capture'
        else:
            return 'balanced'
    
    def _create_dataframe(self, kline_data: List) -> pd.DataFrame:
        """KlineデータからDataFrameを作成"""
        df = pd.DataFrame(kline_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])
        
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)
        
        return df
    
    def _get_default_technical_levels(self, entry_price: float, side: str) -> Dict:
        """デフォルトのテクニカルレベル"""
        if side == 'BUY':
            return {
                'resistance': [entry_price * 1.02, entry_price * 1.05, entry_price * 1.10],
                'support': [],
                'pivot': {'resistance': [entry_price * 1.015, entry_price * 1.03], 'support': []},
                'fibonacci': [entry_price * 1.027, entry_price * 1.062, entry_price * 1.10],
                'round_numbers': []
            }
        else:
            return {
                'resistance': [],
                'support': [entry_price * 0.98, entry_price * 0.95, entry_price * 0.90],
                'pivot': {'support': [entry_price * 0.985, entry_price * 0.97], 'resistance': []},
                'fibonacci': [entry_price * 0.973, entry_price * 0.938, entry_price * 0.90],
                'round_numbers': []
            }
    
    def _get_fallback_tp_levels(self, entry_price: float, side: str) -> DynamicTPResult:
        """フォールバック用の固定利確レベル"""
        if side == 'BUY':
            levels = [
                TakeProfitLevel(1, entry_price * 1.01, 40, "固定1%利確"),
                TakeProfitLevel(2, entry_price * 1.02, 30, "固定2%利確"),
                TakeProfitLevel(3, entry_price * 1.04, 20, "固定4%利確"),
                TakeProfitLevel(4, entry_price * 1.06, 10, "固定6%利確")
            ]
        else:
            levels = [
                TakeProfitLevel(1, entry_price * 0.99, 40, "固定1%利確"),
                TakeProfitLevel(2, entry_price * 0.98, 30, "固定2%利確"),
                TakeProfitLevel(3, entry_price * 0.96, 20, "固定4%利確"),
                TakeProfitLevel(4, entry_price * 0.94, 10, "固定6%利確")
            ]
        
        weighted_avg = self._calculate_weighted_average_tp(levels, entry_price)
        
        return DynamicTPResult(
            levels=levels,
            weighted_average_tp=weighted_avg,
            expected_return=abs(weighted_avg - entry_price) / entry_price,
            confidence=0.5,
            strategy_type='fallback'
        )