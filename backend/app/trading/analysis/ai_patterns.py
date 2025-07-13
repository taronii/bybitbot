"""
AIパターン認識エンジン
機械学習によるパターン認識と予測
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging
import ta
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)

@dataclass
class PatternDetection:
    name: str
    pattern_type: str  # "REVERSAL", "CONTINUATION", "BREAKOUT"
    confidence: float  # 0.0-1.0
    expected_move: float  # 期待される価格変動率
    historical_success_rate: float
    entry_point: float
    stop_loss: float
    take_profit: float

@dataclass
class MLPrediction:
    direction: str  # "UP", "DOWN", "NEUTRAL"
    confidence: float
    expected_return: float
    time_horizon: int  # 分単位
    risk_score: float

class AIPatternRecognition:
    """
    機械学習によるパターン認識と予測
    """
    
    def __init__(self):
        # パターンの成功率履歴（実際はDBから読み込む）
        self.pattern_history = {
            'head_and_shoulders': {'success_rate': 0.72, 'avg_move': -0.08},
            'double_top': {'success_rate': 0.68, 'avg_move': -0.06},
            'double_bottom': {'success_rate': 0.70, 'avg_move': 0.07},
            'triangle': {'success_rate': 0.65, 'avg_move': 0.05},
            'flag': {'success_rate': 0.75, 'avg_move': 0.04},
            'wedge': {'success_rate': 0.66, 'avg_move': 0.05},
            'cup_and_handle': {'success_rate': 0.73, 'avg_move': 0.09}
        }
        
        # キャンドルパターンの成功率
        self.candle_patterns = {
            'engulfing_bullish': {'success_rate': 0.65, 'avg_move': 0.02},
            'engulfing_bearish': {'success_rate': 0.64, 'avg_move': -0.02},
            'hammer': {'success_rate': 0.63, 'avg_move': 0.015},
            'shooting_star': {'success_rate': 0.62, 'avg_move': -0.015},
            'doji': {'success_rate': 0.55, 'avg_move': 0.0},
            'morning_star': {'success_rate': 0.70, 'avg_move': 0.03},
            'evening_star': {'success_rate': 0.69, 'avg_move': -0.03}
        }
    
    async def analyze_patterns(self, symbol: str, df: pd.DataFrame) -> Dict:
        """
        パターン分析を実行
        
        Parameters:
        -----------
        symbol : str
            取引シンボル
        df : pd.DataFrame
            価格データ
            
        Returns:
        --------
        Dict : パターン分析結果
        """
        try:
            # 各種パターンを検出
            classic_patterns = self._detect_classic_patterns(df)
            candle_patterns = self._detect_candle_patterns(df)
            
            # 機械学習予測
            ml_prediction = self._get_ml_prediction(df, classic_patterns, candle_patterns)
            
            # 検出されたパターンを統合
            all_patterns = classic_patterns + candle_patterns
            
            # 信頼度でソート
            all_patterns.sort(key=lambda x: x.confidence, reverse=True)
            
            return {
                'detected_patterns': all_patterns[:5],  # 上位5パターン
                'ml_prediction': ml_prediction,
                'pattern_summary': self._create_pattern_summary(all_patterns),
                'trading_bias': self._determine_trading_bias(all_patterns, ml_prediction)
            }
            
        except Exception as e:
            logger.error(f"Failed to analyze patterns: {e}")
            return self._get_default_analysis()
    
    def _detect_classic_patterns(self, df: pd.DataFrame) -> List[PatternDetection]:
        """クラシックチャートパターンを検出"""
        patterns = []
        
        # 必要なデータ長の確認
        if len(df) < 50:
            return patterns
        
        try:
            # ヘッドアンドショルダー
            hs_pattern = self._detect_head_and_shoulders(df)
            if hs_pattern:
                patterns.append(hs_pattern)
            
            # ダブルトップ/ボトム
            double_patterns = self._detect_double_patterns(df)
            patterns.extend(double_patterns)
            
            # 三角保ち合い
            triangle = self._detect_triangle(df)
            if triangle:
                patterns.append(triangle)
            
            # フラッグパターン
            flag = self._detect_flag(df)
            if flag:
                patterns.append(flag)
            
        except Exception as e:
            logger.error(f"Error detecting classic patterns: {e}")
        
        return patterns
    
    def _detect_head_and_shoulders(self, df: pd.DataFrame) -> Optional[PatternDetection]:
        """ヘッドアンドショルダーパターンの検出"""
        try:
            # 直近50本のローソク足を分析
            recent_df = df.iloc[-50:]
            highs = recent_df['high'].values
            
            # ピークを検出（簡易版）
            peaks = []
            for i in range(2, len(highs) - 2):
                if highs[i] > highs[i-1] and highs[i] > highs[i-2] and \
                   highs[i] > highs[i+1] and highs[i] > highs[i+2]:
                    peaks.append((i, highs[i]))
            
            # 3つのピークがあるかチェック
            if len(peaks) >= 3:
                # 中央のピーク（ヘッド）が最も高いかチェック
                peaks_sorted = sorted(peaks[-3:], key=lambda x: x[1], reverse=True)
                if peaks_sorted[0] == peaks[-2]:  # 中央が最高
                    # ネックラインを計算
                    neckline = min(recent_df['low'].iloc[peaks[-3][0]:peaks[-1][0]+1])
                    current_price = df['close'].iloc[-1]
                    
                    # パターンの高さ
                    pattern_height = peaks_sorted[0][1] - neckline
                    expected_move = -pattern_height / current_price  # 下落予想
                    
                    return PatternDetection(
                        name="head_and_shoulders",
                        pattern_type="REVERSAL",
                        confidence=0.75,
                        expected_move=expected_move,
                        historical_success_rate=self.pattern_history['head_and_shoulders']['success_rate'],
                        entry_point=neckline * 0.995,  # ネックライン割れ
                        stop_loss=peaks_sorted[0][1] * 1.01,  # ヘッドの上
                        take_profit=neckline - pattern_height  # 目標価格
                    )
            
        except Exception as e:
            logger.error(f"Error detecting H&S: {e}")
        
        return None
    
    def _detect_double_patterns(self, df: pd.DataFrame) -> List[PatternDetection]:
        """ダブルトップ/ダブルボトムの検出"""
        patterns = []
        
        try:
            recent_df = df.iloc[-40:]
            highs = recent_df['high'].values
            lows = recent_df['low'].values
            
            # ダブルトップの検出
            high_peaks = []
            for i in range(2, len(highs) - 2):
                if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
                    high_peaks.append((i, highs[i]))
            
            if len(high_peaks) >= 2:
                # 最後の2つのピークを比較
                peak1, peak2 = high_peaks[-2], high_peaks[-1]
                if abs(peak1[1] - peak2[1]) / peak1[1] < 0.02:  # 2%以内
                    # ダブルトップ確定
                    support = min(lows[peak1[0]:peak2[0]+1])
                    pattern_height = peak1[1] - support
                    
                    patterns.append(PatternDetection(
                        name="double_top",
                        pattern_type="REVERSAL",
                        confidence=0.70,
                        expected_move=-pattern_height / df['close'].iloc[-1],
                        historical_success_rate=self.pattern_history['double_top']['success_rate'],
                        entry_point=support * 0.995,
                        stop_loss=max(peak1[1], peak2[1]) * 1.01,
                        take_profit=support - pattern_height
                    ))
            
            # ダブルボトムの検出（同様のロジック）
            low_valleys = []
            for i in range(2, len(lows) - 2):
                if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
                    low_valleys.append((i, lows[i]))
            
            if len(low_valleys) >= 2:
                valley1, valley2 = low_valleys[-2], low_valleys[-1]
                if abs(valley1[1] - valley2[1]) / valley1[1] < 0.02:
                    resistance = max(highs[valley1[0]:valley2[0]+1])
                    pattern_height = resistance - valley1[1]
                    
                    patterns.append(PatternDetection(
                        name="double_bottom",
                        pattern_type="REVERSAL",
                        confidence=0.72,
                        expected_move=pattern_height / df['close'].iloc[-1],
                        historical_success_rate=self.pattern_history['double_bottom']['success_rate'],
                        entry_point=resistance * 1.005,
                        stop_loss=min(valley1[1], valley2[1]) * 0.99,
                        take_profit=resistance + pattern_height
                    ))
            
        except Exception as e:
            logger.error(f"Error detecting double patterns: {e}")
        
        return patterns
    
    def _detect_triangle(self, df: pd.DataFrame) -> Optional[PatternDetection]:
        """三角保ち合いの検出"""
        try:
            recent_df = df.iloc[-30:]
            
            # 高値と安値のトレンドラインを計算
            highs = recent_df['high'].values
            lows = recent_df['low'].values
            
            # 線形回帰で傾きを計算
            x = np.arange(len(highs))
            high_slope = np.polyfit(x, highs, 1)[0]
            low_slope = np.polyfit(x, lows, 1)[0]
            
            # 収束しているかチェック
            if high_slope < 0 and low_slope > 0:  # 対称三角形
                # 収束点を計算
                current_range = highs[-1] - lows[-1]
                initial_range = highs[0] - lows[0]
                
                if current_range < initial_range * 0.5:  # 50%以上収束
                    return PatternDetection(
                        name="triangle",
                        pattern_type="CONTINUATION",
                        confidence=0.65,
                        expected_move=initial_range / df['close'].iloc[-1],
                        historical_success_rate=self.pattern_history['triangle']['success_rate'],
                        entry_point=df['close'].iloc[-1] * 1.01,  # ブレイクアウト
                        stop_loss=lows[-1] * 0.99,
                        take_profit=df['close'].iloc[-1] + initial_range
                    )
            
        except Exception as e:
            logger.error(f"Error detecting triangle: {e}")
        
        return None
    
    def _detect_flag(self, df: pd.DataFrame) -> Optional[PatternDetection]:
        """フラッグパターンの検出"""
        try:
            # 直近のトレンドと調整を分析
            if len(df) < 20:
                return None
            
            # 急激な上昇後の調整を検出
            initial_move = df['close'].iloc[-20:-10].pct_change().sum()
            consolidation = df['close'].iloc[-10:].pct_change().sum()
            
            if initial_move > 0.05 and abs(consolidation) < 0.02:  # 5%上昇後、2%以内の調整
                return PatternDetection(
                    name="flag",
                    pattern_type="CONTINUATION",
                    confidence=0.70,
                    expected_move=initial_move * 0.7,  # 初動の70%
                    historical_success_rate=self.pattern_history['flag']['success_rate'],
                    entry_point=df['high'].iloc[-10:].max() * 1.002,
                    stop_loss=df['low'].iloc[-10:].min() * 0.995,
                    take_profit=df['close'].iloc[-1] * (1 + initial_move * 0.7)
                )
            
        except Exception as e:
            logger.error(f"Error detecting flag: {e}")
        
        return None
    
    def _detect_candle_patterns(self, df: pd.DataFrame) -> List[PatternDetection]:
        """キャンドルパターンを検出"""
        patterns = []
        
        try:
            # エングルフィングパターン
            engulfing = self._detect_engulfing(df)
            if engulfing:
                patterns.append(engulfing)
            
            # ハンマー/シューティングスター
            hammer_star = self._detect_hammer_shooting_star(df)
            if hammer_star:
                patterns.append(hammer_star)
            
            # 十字線
            doji = self._detect_doji(df)
            if doji:
                patterns.append(doji)
            
            # モーニングスター/イブニングスター
            star_patterns = self._detect_star_patterns(df)
            patterns.extend(star_patterns)
            
        except Exception as e:
            logger.error(f"Error detecting candle patterns: {e}")
        
        return patterns
    
    def _detect_engulfing(self, df: pd.DataFrame) -> Optional[PatternDetection]:
        """エングルフィングパターンの検出"""
        try:
            if len(df) < 2:
                return None
            
            prev_candle = df.iloc[-2]
            curr_candle = df.iloc[-1]
            
            prev_body = abs(prev_candle['close'] - prev_candle['open'])
            curr_body = abs(curr_candle['close'] - curr_candle['open'])
            
            # ブリッシュエングルフィング
            if (prev_candle['close'] < prev_candle['open'] and  # 前は陰線
                curr_candle['close'] > curr_candle['open'] and  # 今は陽線
                curr_candle['open'] < prev_candle['close'] and  # 今の始値 < 前の終値
                curr_candle['close'] > prev_candle['open'] and  # 今の終値 > 前の始値
                curr_body > prev_body * 1.5):  # ボディが1.5倍以上
                
                return PatternDetection(
                    name="engulfing_bullish",
                    pattern_type="REVERSAL",
                    confidence=0.65,
                    expected_move=self.candle_patterns['engulfing_bullish']['avg_move'],
                    historical_success_rate=self.candle_patterns['engulfing_bullish']['success_rate'],
                    entry_point=curr_candle['close'] * 1.001,
                    stop_loss=min(prev_candle['low'], curr_candle['low']) * 0.995,
                    take_profit=curr_candle['close'] * 1.02
                )
            
            # ベアリッシュエングルフィング
            elif (prev_candle['close'] > prev_candle['open'] and  # 前は陽線
                  curr_candle['close'] < curr_candle['open'] and  # 今は陰線
                  curr_candle['open'] > prev_candle['close'] and  # 今の始値 > 前の終値
                  curr_candle['close'] < prev_candle['open'] and  # 今の終値 < 前の始値
                  curr_body > prev_body * 1.5):
                
                return PatternDetection(
                    name="engulfing_bearish",
                    pattern_type="REVERSAL",
                    confidence=0.64,
                    expected_move=self.candle_patterns['engulfing_bearish']['avg_move'],
                    historical_success_rate=self.candle_patterns['engulfing_bearish']['success_rate'],
                    entry_point=curr_candle['close'] * 0.999,
                    stop_loss=max(prev_candle['high'], curr_candle['high']) * 1.005,
                    take_profit=curr_candle['close'] * 0.98
                )
            
        except Exception as e:
            logger.error(f"Error detecting engulfing: {e}")
        
        return None
    
    def _detect_hammer_shooting_star(self, df: pd.DataFrame) -> Optional[PatternDetection]:
        """ハンマー/シューティングスターの検出"""
        try:
            if len(df) < 1:
                return None
            
            candle = df.iloc[-1]
            body = abs(candle['close'] - candle['open'])
            total_range = candle['high'] - candle['low']
            
            if total_range == 0:
                return None
            
            # 下ヒゲの長さ
            lower_wick = min(candle['open'], candle['close']) - candle['low']
            # 上ヒゲの長さ
            upper_wick = candle['high'] - max(candle['open'], candle['close'])
            
            # ハンマー（下ヒゲが長い）
            if lower_wick > body * 2 and upper_wick < body * 0.5:
                # 下降トレンドの底で出現
                if df['close'].iloc[-10:-1].mean() > df['close'].iloc[-1]:
                    return PatternDetection(
                        name="hammer",
                        pattern_type="REVERSAL",
                        confidence=0.63,
                        expected_move=self.candle_patterns['hammer']['avg_move'],
                        historical_success_rate=self.candle_patterns['hammer']['success_rate'],
                        entry_point=candle['high'] * 1.001,
                        stop_loss=candle['low'] * 0.995,
                        take_profit=candle['close'] * 1.015
                    )
            
            # シューティングスター（上ヒゲが長い）
            elif upper_wick > body * 2 and lower_wick < body * 0.5:
                # 上昇トレンドの天井で出現
                if df['close'].iloc[-10:-1].mean() < df['close'].iloc[-1]:
                    return PatternDetection(
                        name="shooting_star",
                        pattern_type="REVERSAL",
                        confidence=0.62,
                        expected_move=self.candle_patterns['shooting_star']['avg_move'],
                        historical_success_rate=self.candle_patterns['shooting_star']['success_rate'],
                        entry_point=candle['low'] * 0.999,
                        stop_loss=candle['high'] * 1.005,
                        take_profit=candle['close'] * 0.985
                    )
            
        except Exception as e:
            logger.error(f"Error detecting hammer/shooting star: {e}")
        
        return None
    
    def _detect_doji(self, df: pd.DataFrame) -> Optional[PatternDetection]:
        """十字線の検出"""
        try:
            if len(df) < 1:
                return None
            
            candle = df.iloc[-1]
            body = abs(candle['close'] - candle['open'])
            total_range = candle['high'] - candle['low']
            
            # ボディが全体の10%以下なら十字線
            if total_range > 0 and body / total_range < 0.1:
                return PatternDetection(
                    name="doji",
                    pattern_type="REVERSAL",
                    confidence=0.55,
                    expected_move=0.0,  # 方向性なし
                    historical_success_rate=self.candle_patterns['doji']['success_rate'],
                    entry_point=candle['close'],
                    stop_loss=candle['low'] * 0.99,
                    take_profit=candle['high'] * 1.01
                )
            
        except Exception as e:
            logger.error(f"Error detecting doji: {e}")
        
        return None
    
    def _detect_star_patterns(self, df: pd.DataFrame) -> List[PatternDetection]:
        """モーニングスター/イブニングスターの検出"""
        patterns = []
        
        try:
            if len(df) < 3:
                return patterns
            
            first = df.iloc[-3]
            second = df.iloc[-2]
            third = df.iloc[-1]
            
            # モーニングスター（上昇反転）
            if (first['close'] < first['open'] and  # 1本目は大陰線
                abs(second['close'] - second['open']) < abs(first['close'] - first['open']) * 0.3 and  # 2本目は小さい
                third['close'] > third['open'] and  # 3本目は大陽線
                third['close'] > (first['open'] + first['close']) / 2):  # 1本目の中心を超える
                
                patterns.append(PatternDetection(
                    name="morning_star",
                    pattern_type="REVERSAL",
                    confidence=0.70,
                    expected_move=self.candle_patterns['morning_star']['avg_move'],
                    historical_success_rate=self.candle_patterns['morning_star']['success_rate'],
                    entry_point=third['close'] * 1.001,
                    stop_loss=second['low'] * 0.995,
                    take_profit=third['close'] * 1.03
                ))
            
            # イブニングスター（下降反転）
            elif (first['close'] > first['open'] and  # 1本目は大陽線
                  abs(second['close'] - second['open']) < abs(first['close'] - first['open']) * 0.3 and  # 2本目は小さい
                  third['close'] < third['open'] and  # 3本目は大陰線
                  third['close'] < (first['open'] + first['close']) / 2):  # 1本目の中心を下回る
                
                patterns.append(PatternDetection(
                    name="evening_star",
                    pattern_type="REVERSAL",
                    confidence=0.69,
                    expected_move=self.candle_patterns['evening_star']['avg_move'],
                    historical_success_rate=self.candle_patterns['evening_star']['success_rate'],
                    entry_point=third['close'] * 0.999,
                    stop_loss=second['high'] * 1.005,
                    take_profit=third['close'] * 0.97
                ))
            
        except Exception as e:
            logger.error(f"Error detecting star patterns: {e}")
        
        return patterns
    
    def _get_ml_prediction(self, df: pd.DataFrame, classic_patterns: List, candle_patterns: List) -> MLPrediction:
        """機械学習による予測（簡易版）"""
        try:
            # 特徴量を抽出
            features = self._extract_features(df)
            
            # パターンからの予測
            pattern_bias = 0.0
            if classic_patterns:
                for pattern in classic_patterns:
                    pattern_bias += pattern.expected_move * pattern.confidence
            
            if candle_patterns:
                for pattern in candle_patterns:
                    pattern_bias += pattern.expected_move * pattern.confidence * 0.5  # キャンドルは重み半分
            
            # テクニカル指標からの予測
            rsi = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi().iloc[-1]
            macd = ta.trend.MACD(close=df['close']).macd_diff().iloc[-1]
            
            # 総合的な方向性を判定
            if pattern_bias > 0.02 and rsi < 70 and macd > 0:
                direction = "UP"
                confidence = min(0.85, abs(pattern_bias) * 10)
                expected_return = pattern_bias
            elif pattern_bias < -0.02 and rsi > 30 and macd < 0:
                direction = "DOWN"
                confidence = min(0.85, abs(pattern_bias) * 10)
                expected_return = pattern_bias
            else:
                direction = "NEUTRAL"
                confidence = 0.3
                expected_return = 0.0
            
            # リスクスコア計算
            volatility = df['close'].pct_change().std()
            risk_score = min(1.0, volatility * 100)
            
            return MLPrediction(
                direction=direction,
                confidence=confidence,
                expected_return=expected_return,
                time_horizon=30,  # 30分
                risk_score=risk_score
            )
            
        except Exception as e:
            logger.error(f"Error in ML prediction: {e}")
            return MLPrediction(
                direction="NEUTRAL",
                confidence=0.0,
                expected_return=0.0,
                time_horizon=30,
                risk_score=0.5
            )
    
    def _extract_features(self, df: pd.DataFrame) -> Dict:
        """特徴量を抽出"""
        features = {}
        
        try:
            # 価格変動
            features['returns_1h'] = df['close'].pct_change(12).iloc[-1]
            features['returns_4h'] = df['close'].pct_change(48).iloc[-1]
            features['returns_24h'] = df['close'].pct_change(288).iloc[-1]
            
            # ボラティリティ
            features['volatility'] = df['close'].pct_change().std()
            
            # 出来高
            features['volume_ratio'] = df['volume'].iloc[-1] / df['volume'].mean()
            
            # テクニカル指標
            features['rsi'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi().iloc[-1]
            features['macd'] = ta.trend.MACD(close=df['close']).macd_diff().iloc[-1]
            
        except Exception as e:
            logger.error(f"Error extracting features: {e}")
        
        return features
    
    def _create_pattern_summary(self, patterns: List[PatternDetection]) -> Dict:
        """パターンのサマリーを作成"""
        if not patterns:
            return {'total': 0, 'bullish': 0, 'bearish': 0, 'neutral': 0}
        
        bullish = sum(1 for p in patterns if p.expected_move > 0)
        bearish = sum(1 for p in patterns if p.expected_move < 0)
        neutral = len(patterns) - bullish - bearish
        
        return {
            'total': len(patterns),
            'bullish': bullish,
            'bearish': bearish,
            'neutral': neutral,
            'strongest_pattern': patterns[0].name if patterns else None
        }
    
    def _determine_trading_bias(self, patterns: List[PatternDetection], ml_prediction: MLPrediction) -> str:
        """総合的なトレーディングバイアスを決定"""
        if not patterns:
            return ml_prediction.direction
        
        # パターンの方向性を集計
        pattern_score = sum(p.expected_move * p.confidence for p in patterns)
        
        if pattern_score > 0.02 and ml_prediction.direction == "UP":
            return "STRONG_BULLISH"
        elif pattern_score < -0.02 and ml_prediction.direction == "DOWN":
            return "STRONG_BEARISH"
        elif pattern_score > 0.01:
            return "BULLISH"
        elif pattern_score < -0.01:
            return "BEARISH"
        else:
            return "NEUTRAL"
    
    def _get_default_analysis(self) -> Dict:
        """デフォルトの分析結果"""
        return {
            'detected_patterns': [],
            'ml_prediction': MLPrediction(
                direction="NEUTRAL",
                confidence=0.0,
                expected_return=0.0,
                time_horizon=30,
                risk_score=0.5
            ),
            'pattern_summary': {'total': 0, 'bullish': 0, 'bearish': 0, 'neutral': 0},
            'trading_bias': "NEUTRAL"
        }