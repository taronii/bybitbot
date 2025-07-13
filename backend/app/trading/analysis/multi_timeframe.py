"""
マルチタイムフレーム分析システム
階層的な時間軸分析で大局観を把握
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging
import ta
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class TimeFrame(Enum):
    M5 = "5"      # 5分足
    M15 = "15"    # 15分足
    H1 = "60"     # 1時間足
    H4 = "240"    # 4時間足

@dataclass
class TimeFrameAnalysis:
    timeframe: TimeFrame
    trend_direction: int  # 1: 上昇, -1: 下降, 0: 横ばい
    ema_value: float
    price_position: str  # "ABOVE_EMA", "BELOW_EMA", "AT_EMA"
    strength: float  # 0.0-1.0
    
@dataclass
class DivergenceSignal:
    indicator: str  # "RSI" or "MACD"
    divergence_type: str  # "REGULAR_BULLISH", "REGULAR_BEARISH", "HIDDEN_BULLISH", "HIDDEN_BEARISH"
    strength: float  # 0.0-1.0
    timeframe: TimeFrame
    description: str

class MultiTimeframeAnalyzer:
    """
    階層的な時間軸分析で大局観を把握
    """
    
    def __init__(self, session):
        self.session = session
        self.timeframes = {
            TimeFrame.H4: {'ema_period': 200, 'lookback': 500},
            TimeFrame.H1: {'ema_period': 50, 'lookback': 200},
            TimeFrame.M15: {'ema_period': 20, 'lookback': 100},
            TimeFrame.M5: {'ema_period': 20, 'lookback': 60}
        }
        
    async def analyze_all_timeframes(self, symbol: str) -> Dict:
        """
        全時間足を分析
        
        Parameters:
        -----------
        symbol : str
            取引シンボル（例: "BTCUSDT"）
            
        Returns:
        --------
        Dict : 分析結果
        """
        try:
            analyses = {}
            
            # 各時間足のデータを取得して分析
            for timeframe in self.timeframes:
                df = await self._fetch_candles(symbol, timeframe)
                if df is not None and len(df) > 0:
                    analysis = self._analyze_timeframe(df, timeframe)
                    analyses[timeframe] = analysis
            
            # トレンドの一致度を計算
            alignment_score = self._calculate_trend_alignment(analyses)
            
            # キーレベルを特定
            key_levels = self._identify_key_levels(analyses)
            
            # ダイバージェンスを検出
            divergences = await self._detect_divergences(symbol)
            
            # エントリータイムフレーム（5分足）の準備状態を確認
            entry_ready = self._check_entry_timeframe_ready(analyses.get(TimeFrame.M5))
            
            return {
                'analyses': analyses,
                'trend_alignment_score': alignment_score,
                'key_levels': key_levels,
                'divergences': divergences,
                'entry_timeframe_ready': entry_ready,
                'recommendation': self._get_recommendation(alignment_score, analyses)
            }
            
        except Exception as e:
            logger.error(f"Failed to analyze timeframes: {e}")
            return self._get_default_analysis()
    
    async def _fetch_candles(self, symbol: str, timeframe: TimeFrame) -> Optional[pd.DataFrame]:
        """ローソク足データを取得"""
        try:
            interval = timeframe.value
            limit = self.timeframes[timeframe]['lookback']
            
            # Bybit APIからデータ取得
            response = self.session.get_kline(
                category="linear",
                symbol=symbol,
                interval=interval,
                limit=limit
            )
            
            if response["retCode"] != 0:
                logger.error(f"Failed to fetch candles: {response['retMsg']}")
                return None
            
            # DataFrameに変換
            data = response["result"]["list"]
            df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
            
            # データ型を変換
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col])
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            df.sort_index(inplace=True)
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching candles for {timeframe.value}: {e}")
            return None
    
    def _analyze_timeframe(self, df: pd.DataFrame, timeframe: TimeFrame) -> TimeFrameAnalysis:
        """特定の時間足を分析"""
        settings = self.timeframes[timeframe]
        ema_period = settings['ema_period']
        
        # EMA計算
        ema = df['close'].ewm(span=ema_period, adjust=False).mean()
        current_price = df['close'].iloc[-1]
        current_ema = ema.iloc[-1]
        
        # トレンド方向の判定
        ema_slope = (ema.iloc[-1] - ema.iloc[-10]) / ema.iloc[-10] * 100
        
        if ema_slope > 0.1:  # 0.1%以上の上昇
            trend_direction = 1
        elif ema_slope < -0.1:  # 0.1%以上の下降
            trend_direction = -1
        else:
            trend_direction = 0
        
        # 価格とEMAの位置関係
        price_diff = (current_price - current_ema) / current_ema * 100
        if price_diff > 0.5:  # 0.5%以上上
            price_position = "ABOVE_EMA"
        elif price_diff < -0.5:  # 0.5%以上下
            price_position = "BELOW_EMA"
        else:
            price_position = "AT_EMA"
        
        # トレンドの強さ（EMAからの乖離率とトレンドの一貫性）
        strength = min(1.0, abs(price_diff) / 5)  # 5%で最大強度
        
        return TimeFrameAnalysis(
            timeframe=timeframe,
            trend_direction=trend_direction,
            ema_value=current_ema,
            price_position=price_position,
            strength=strength
        )
    
    def _calculate_trend_alignment(self, analyses: Dict[TimeFrame, TimeFrameAnalysis]) -> float:
        """トレンドの一致度を計算"""
        if not analyses:
            return 0.0
        
        directions = [a.trend_direction for a in analyses.values()]
        
        # 全て同じ方向
        if all(d == directions[0] for d in directions) and directions[0] != 0:
            return 1.0
        
        # 3/4が一致
        trend_counts = {1: 0, -1: 0, 0: 0}
        for d in directions:
            trend_counts[d] += 1
        
        max_count = max(trend_counts.values())
        if max_count >= 3:
            return 0.75
        elif max_count >= 2:
            return 0.5
        
        return 0.25
    
    def _identify_key_levels(self, analyses: Dict[TimeFrame, TimeFrameAnalysis]) -> Dict[str, List[float]]:
        """キーレベル（サポート・レジスタンス）を特定"""
        key_levels = {'support': [], 'resistance': []}
        
        # 各時間足のEMAをキーレベルとして使用
        for analysis in analyses.values():
            if analysis.price_position == "ABOVE_EMA":
                key_levels['support'].append(analysis.ema_value)
            elif analysis.price_position == "BELOW_EMA":
                key_levels['resistance'].append(analysis.ema_value)
        
        # 重複を削除してソート
        key_levels['support'] = sorted(list(set(key_levels['support'])), reverse=True)
        key_levels['resistance'] = sorted(list(set(key_levels['resistance'])))
        
        return key_levels
    
    async def _detect_divergences(self, symbol: str) -> List[DivergenceSignal]:
        """ダイバージェンスを検出"""
        divergences = []
        
        try:
            # 5分足でダイバージェンスをチェック
            df = await self._fetch_candles(symbol, TimeFrame.M5)
            if df is None or len(df) < 50:
                return divergences
            
            # RSIダイバージェンス
            rsi = ta.momentum.RSIIndicator(close=df['close'], window=14)
            rsi_values = rsi.rsi()
            
            # 価格の高値・安値
            price_highs = df['high'].rolling(window=5).max()
            price_lows = df['low'].rolling(window=5).min()
            
            # RSIの高値・安値
            rsi_highs = rsi_values.rolling(window=5).max()
            rsi_lows = rsi_values.rolling(window=5).min()
            
            # レギュラーダイバージェンス（反転シグナル）
            # ベアリッシュダイバージェンス：価格は高値更新、RSIは高値更新せず
            if (df['high'].iloc[-1] > df['high'].iloc[-20:-1].max() and
                rsi_values.iloc[-1] < rsi_values.iloc[-20:-1].max()):
                divergences.append(DivergenceSignal(
                    indicator="RSI",
                    divergence_type="REGULAR_BEARISH",
                    strength=0.8,
                    timeframe=TimeFrame.M5,
                    description="価格は高値更新もRSIは更新せず→下落の可能性"
                ))
            
            # ブリッシュダイバージェンス：価格は安値更新、RSIは安値更新せず
            if (df['low'].iloc[-1] < df['low'].iloc[-20:-1].min() and
                rsi_values.iloc[-1] > rsi_values.iloc[-20:-1].min()):
                divergences.append(DivergenceSignal(
                    indicator="RSI",
                    divergence_type="REGULAR_BULLISH",
                    strength=0.8,
                    timeframe=TimeFrame.M5,
                    description="価格は安値更新もRSIは更新せず→上昇の可能性"
                ))
            
            # MACDダイバージェンス
            macd = ta.trend.MACD(close=df['close'])
            macd_line = macd.macd()
            
            # MACDでも同様のチェック
            if (df['high'].iloc[-1] > df['high'].iloc[-20:-1].max() and
                macd_line.iloc[-1] < macd_line.iloc[-20:-1].max()):
                divergences.append(DivergenceSignal(
                    indicator="MACD",
                    divergence_type="REGULAR_BEARISH",
                    strength=0.7,
                    timeframe=TimeFrame.M5,
                    description="MACDベアリッシュダイバージェンス"
                ))
            
        except Exception as e:
            logger.error(f"Error detecting divergences: {e}")
        
        return divergences
    
    def _check_entry_timeframe_ready(self, m5_analysis: Optional[TimeFrameAnalysis]) -> bool:
        """エントリータイムフレームの準備状態を確認"""
        if not m5_analysis:
            return False
        
        # 5分足が明確なトレンドを示している
        if m5_analysis.trend_direction != 0 and m5_analysis.strength > 0.5:
            return True
        
        return False
    
    def _get_recommendation(self, alignment_score: float, analyses: Dict) -> str:
        """推奨アクションを決定"""
        if alignment_score >= 0.75:
            # 上位時間足の方向を確認
            h4_direction = analyses.get(TimeFrame.H4, {}).trend_direction
            if h4_direction == 1:
                return "STRONG_BUY_SIGNAL"
            elif h4_direction == -1:
                return "STRONG_SELL_SIGNAL"
        
        elif alignment_score >= 0.5:
            return "WEAK_SIGNAL"
        
        return "NO_SIGNAL"
    
    def _get_default_analysis(self) -> Dict:
        """デフォルトの分析結果"""
        return {
            'analyses': {},
            'trend_alignment_score': 0.0,
            'key_levels': {'support': [], 'resistance': []},
            'divergences': [],
            'entry_timeframe_ready': False,
            'recommendation': "NO_SIGNAL"
        }