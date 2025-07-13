"""
マーケットレジーム識別エンジン
市場状態を正確に識別し、最適な戦略を選択する
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging
import ta

logger = logging.getLogger(__name__)

class MarketRegime(Enum):
    STRONG_TREND = "STRONG_TREND"
    WEAK_TREND = "WEAK_TREND"
    RANGE = "RANGE"
    VOLATILE = "VOLATILE"
    BREAKOUT = "BREAKOUT"

class VolatilityLevel(Enum):
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"

@dataclass
class RegimeAnalysis:
    regime: MarketRegime
    trend_direction: int  # 1: 上昇, -1: 下降, 0: 横ばい
    trend_strength: float  # 0.0-1.0 - トレンドの強さ
    volatility_level: VolatilityLevel
    liquidity_score: float  # 0.0-1.0
    confidence: float  # 0.0-1.0
    details: Dict[str, any]

class MarketRegimeDetector:
    """
    市場状態を正確に識別し、最適な戦略を選択する
    """
    
    def __init__(self, lookback_periods: int = 200):
        self.lookback_periods = lookback_periods
        self.ma_periods = [10, 20, 50, 200]
        self.adx_period = 14
        self.atr_period = 14
        self.bb_period = 20
        self.bb_std = 2
        
    def detect_regime(self, df: pd.DataFrame) -> RegimeAnalysis:
        """
        市場レジームを検出
        
        Parameters:
        -----------
        df : pd.DataFrame
            価格データ（columns: open, high, low, close, volume）
            
        Returns:
        --------
        RegimeAnalysis : 市場レジーム分析結果
        """
        try:
            # 必要なデータ長の確認
            if len(df) < self.lookback_periods:
                logger.warning(f"Insufficient data: {len(df)} < {self.lookback_periods}")
                return self._get_default_regime()
            
            # 各種分析を実行
            trend_analysis = self._analyze_trend(df)
            volatility_analysis = self._analyze_volatility(df)
            liquidity_analysis = self._analyze_liquidity(df)
            
            # レジームを判定
            regime = self._determine_regime(trend_analysis, volatility_analysis)
            
            # 信頼度を計算
            confidence = self._calculate_confidence(
                trend_analysis, volatility_analysis, liquidity_analysis
            )
            
            return RegimeAnalysis(
                regime=regime,
                trend_direction=trend_analysis['direction'],
                trend_strength=trend_analysis['strength'],
                volatility_level=volatility_analysis['level'],
                liquidity_score=liquidity_analysis['score'],
                confidence=confidence,
                details={
                    'trend': trend_analysis,
                    'volatility': volatility_analysis,
                    'liquidity': liquidity_analysis
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to detect regime: {e}")
            return self._get_default_regime()
    
    def _analyze_trend(self, df: pd.DataFrame) -> Dict:
        """トレンド分析"""
        # ADX計算
        adx = ta.trend.ADXIndicator(
            high=df['high'], 
            low=df['low'], 
            close=df['close'], 
            window=self.adx_period
        )
        adx_value = adx.adx().iloc[-1]
        
        # 移動平均の計算と並び
        mas = {}
        for period in self.ma_periods:
            mas[f'ma{period}'] = df['close'].rolling(window=period).mean()
        
        current_price = df['close'].iloc[-1]
        
        # パーフェクトオーダーのチェック
        perfect_order_bull = (
            mas['ma10'].iloc[-1] > mas['ma20'].iloc[-1] > 
            mas['ma50'].iloc[-1] > mas['ma200'].iloc[-1]
        )
        perfect_order_bear = (
            mas['ma10'].iloc[-1] < mas['ma20'].iloc[-1] < 
            mas['ma50'].iloc[-1] < mas['ma200'].iloc[-1]
        )
        
        # 価格と各MAとの乖離率
        deviations = {}
        for period in self.ma_periods:
            ma_value = mas[f'ma{period}'].iloc[-1]
            deviations[f'dev_ma{period}'] = (current_price - ma_value) / ma_value * 100
        
        # トレンド方向の判定
        if perfect_order_bull:
            direction = 1
        elif perfect_order_bear:
            direction = -1
        else:
            # MAの傾きで判定
            ma50_slope = (mas['ma50'].iloc[-1] - mas['ma50'].iloc[-10]) / mas['ma50'].iloc[-10]
            direction = 1 if ma50_slope > 0.001 else (-1 if ma50_slope < -0.001 else 0)
        
        # トレンド強度
        trend_strength = adx_value / 100  # 0-1に正規化
        
        return {
            'direction': direction,
            'strength': trend_strength,
            'adx': adx_value,
            'perfect_order': perfect_order_bull or perfect_order_bear,
            'deviations': deviations,
            'mas_current': {f'ma{p}': mas[f'ma{p}'].iloc[-1] for p in self.ma_periods}
        }
    
    def _analyze_volatility(self, df: pd.DataFrame) -> Dict:
        """ボラティリティ分析"""
        # ATR計算
        atr = ta.volatility.AverageTrueRange(
            high=df['high'],
            low=df['low'],
            close=df['close'],
            window=self.atr_period
        )
        atr_value = atr.average_true_range().iloc[-1]
        
        # ATR/価格比率
        atr_ratio = atr_value / df['close'].iloc[-1]
        
        # ボリンジャーバンド
        bb = ta.volatility.BollingerBands(
            close=df['close'],
            window=self.bb_period,
            window_dev=self.bb_std
        )
        bb_width = bb.bollinger_wband().iloc[-1]
        
        # 過去30日との比較
        historical_atr = atr.average_true_range().iloc[-30:].mean()
        volatility_change = (atr_value - historical_atr) / historical_atr
        
        # ボラティリティレベルの判定
        if atr_ratio > 0.03:  # 3%以上
            level = VolatilityLevel.HIGH
        elif atr_ratio < 0.01:  # 1%未満
            level = VolatilityLevel.LOW
        else:
            level = VolatilityLevel.NORMAL
        
        return {
            'level': level,
            'atr': atr_value,
            'atr_ratio': atr_ratio,
            'bb_width': bb_width,
            'volatility_change': volatility_change,
            'expanding': volatility_change > 0.2,  # 20%以上の拡大
            'contracting': volatility_change < -0.2  # 20%以上の縮小
        }
    
    def _analyze_liquidity(self, df: pd.DataFrame) -> Dict:
        """流動性評価"""
        # 出来高分析
        volume_ma = df['volume'].rolling(window=20).mean()
        current_volume = df['volume'].iloc[-1]
        volume_ratio = current_volume / volume_ma.iloc[-1] if volume_ma.iloc[-1] > 0 else 1
        
        # 出来高スパイクの検出
        volume_spike = volume_ratio > 3.0
        
        # 価格変動に対する出来高の反応
        price_change = abs(df['close'].pct_change().iloc[-1])
        volume_price_ratio = volume_ratio / (price_change + 0.0001)  # ゼロ除算回避
        
        # 流動性スコアの計算（0-1）
        liquidity_score = min(1.0, volume_ratio / 2)  # 平均の2倍で最大
        
        # 大口注文の可能性
        large_order_detected = volume_spike and price_change < 0.001  # 大量出来高だが価格変動小
        
        return {
            'score': liquidity_score,
            'volume_ratio': volume_ratio,
            'volume_spike': volume_spike,
            'large_order_detected': large_order_detected,
            'volume_price_ratio': volume_price_ratio,
            'average_volume': volume_ma.iloc[-1]
        }
    
    def _determine_regime(self, trend: Dict, volatility: Dict) -> MarketRegime:
        """レジームを判定"""
        # ブレイクアウトの検出
        if volatility['expanding'] and trend['strength'] > 30:
            return MarketRegime.BREAKOUT
        
        # 高ボラティリティ
        if volatility['level'] == VolatilityLevel.HIGH:
            return MarketRegime.VOLATILE
        
        # 強いトレンド
        if trend['adx'] > 25 and trend['perfect_order']:
            return MarketRegime.STRONG_TREND
        
        # 弱いトレンド
        if trend['adx'] > 20:
            return MarketRegime.WEAK_TREND
        
        # レンジ
        return MarketRegime.RANGE
    
    def _calculate_confidence(self, trend: Dict, volatility: Dict, liquidity: Dict) -> float:
        """信頼度を計算"""
        confidence_factors = []
        
        # トレンドの明確さ
        if trend['perfect_order']:
            confidence_factors.append(0.9)
        else:
            confidence_factors.append(0.5 + trend['strength'] * 0.4)
        
        # ボラティリティの適正さ
        if volatility['level'] == VolatilityLevel.NORMAL:
            confidence_factors.append(0.8)
        else:
            confidence_factors.append(0.5)
        
        # 流動性
        confidence_factors.append(liquidity['score'])
        
        # 平均を計算
        return sum(confidence_factors) / len(confidence_factors)
    
    def _get_default_regime(self) -> RegimeAnalysis:
        """デフォルトのレジーム（エラー時など）"""
        return RegimeAnalysis(
            regime=MarketRegime.RANGE,
            trend_direction=0,
            trend_strength=0.0,
            volatility_level=VolatilityLevel.NORMAL,
            liquidity_score=0.5,
            confidence=0.0,
            details={}
        )