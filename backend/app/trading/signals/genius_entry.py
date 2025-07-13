"""
統合エントリーシグナル生成
全ての分析を統合して最終的なエントリー判断
"""
import asyncio
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging
from datetime import datetime

from ..analysis.market_regime import MarketRegimeDetector, MarketRegime
from ..analysis.multi_timeframe import MultiTimeframeAnalyzer
from ..analysis.smart_money import SmartMoneyAnalyzer, SmartMoneyDirection
from ..analysis.ai_patterns import AIPatternRecognition

logger = logging.getLogger(__name__)

class EntryAction(Enum):
    BUY = "BUY"
    SELL = "SELL"
    WAIT = "WAIT"

class EntryType(Enum):
    PULLBACK = "PULLBACK"
    RANGE_BOTTOM = "RANGE_BOTTOM"
    RANGE_TOP = "RANGE_TOP"
    BREAKOUT = "BREAKOUT"
    MOMENTUM = "MOMENTUM"
    REVERSAL = "REVERSAL"

@dataclass
class EntrySignal:
    action: EntryAction
    confidence: float  # 0.0-1.0
    entry_type: EntryType
    entry_price: float
    position_size_multiplier: float  # 0.25, 0.5, 1.0
    reasons: List[Dict]
    invalidation_price: float
    stop_loss: float
    take_profit: List[float]  # 複数のTP
    metadata: Dict

class GeniusEntrySignalGenerator:
    """
    全ての分析を統合して最終的なエントリー判断
    """
    
    def __init__(self, session):
        self.session = session
        self.market_regime = MarketRegimeDetector()
        self.mtf_analyzer = MultiTimeframeAnalyzer(session)
        self.smart_money = SmartMoneyAnalyzer(session)
        self.ai_patterns = AIPatternRecognition()
        
        # スコアリングの重み
        self.weights = {
            'regime_match': 0.25,      # 市場環境との適合
            'mtf_alignment': 0.25,     # 時間軸の一致
            'smart_money': 0.20,       # スマートマネーの方向
            'pattern_confidence': 0.20, # パターンの信頼度
            'risk_reward': 0.10       # リスクリワード比
        }
        
        # エントリー閾値
        self.entry_thresholds = {
            'strong': 0.80,   # フルサイズ
            'normal': 0.65,   # 半分サイズ
            'weak': 0.50      # 1/4サイズ
        }
    
    async def generate_entry_signal(self, symbol: str) -> EntrySignal:
        """
        エントリーシグナルを生成
        
        Parameters:
        -----------
        symbol : str
            取引シンボル（例: "BTCUSDT"）
            
        Returns:
        --------
        EntrySignal : エントリーシグナル
        """
        try:
            # 現在の価格データを取得
            df = await self._fetch_price_data(symbol)
            if df is None or len(df) < 200:
                return self._get_wait_signal("データ不足")
            
            # 全ての分析を並列実行
            tasks = [
                self._run_regime_analysis(df),
                self._run_mtf_analysis(symbol),
                self._run_smart_money_analysis(symbol),
                self._run_pattern_analysis(symbol, df)
            ]
            
            results = await asyncio.gather(*tasks)
            
            regime_analysis = results[0]
            mtf_analysis = results[1]
            smart_money_analysis = results[2]
            pattern_analysis = results[3]
            
            # スコアを計算
            scores = self._calculate_scores(
                regime_analysis,
                mtf_analysis,
                smart_money_analysis,
                pattern_analysis,
                df
            )
            
            # 総合スコアを計算
            total_score = self._calculate_total_score(scores)
            
            # エントリー判断
            if total_score < self.entry_thresholds['weak']:
                return self._get_wait_signal(f"スコア不足: {total_score:.2f}")
            
            # エントリーシグナルを生成
            signal = self._create_entry_signal(
                scores,
                total_score,
                regime_analysis,
                mtf_analysis,
                smart_money_analysis,
                pattern_analysis,
                df
            )
            
            return signal
            
        except Exception as e:
            logger.error(f"Failed to generate entry signal: {e}")
            return self._get_wait_signal(f"エラー: {str(e)}")
    
    async def _fetch_price_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """価格データを取得"""
        try:
            response = self.session.get_kline(
                category="linear",
                symbol=symbol,
                interval="5",
                limit=200
            )
            
            if response["retCode"] != 0:
                logger.error(f"Failed to fetch price data: {response['retMsg']}")
                return None
            
            data = response["result"]["list"]
            df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
            
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col])
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            df.sort_index(inplace=True)
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching price data: {e}")
            return None
    
    async def _run_regime_analysis(self, df: pd.DataFrame) -> Dict:
        """レジーム分析を実行"""
        return self.market_regime.detect_regime(df)
    
    async def _run_mtf_analysis(self, symbol: str) -> Dict:
        """マルチタイムフレーム分析を実行"""
        return await self.mtf_analyzer.analyze_all_timeframes(symbol)
    
    async def _run_smart_money_analysis(self, symbol: str) -> Dict:
        """スマートマネー分析を実行"""
        return await self.smart_money.detect_smart_money(symbol)
    
    async def _run_pattern_analysis(self, symbol: str, df: pd.DataFrame) -> Dict:
        """パターン分析を実行"""
        return await self.ai_patterns.analyze_patterns(symbol, df)
    
    def _calculate_scores(self, regime, mtf, smart_money, patterns, df) -> Dict[str, float]:
        """各要素のスコアを計算"""
        scores = {}
        
        # 1. レジームマッチスコア
        current_price_trend = self._get_price_trend(df)
        if regime.regime == MarketRegime.STRONG_TREND:
            if regime.trend_direction == current_price_trend:
                scores['regime_match'] = 0.9
            else:
                scores['regime_match'] = 0.3
        elif regime.regime == MarketRegime.RANGE:
            scores['regime_match'] = 0.7
        else:
            scores['regime_match'] = 0.5
        
        # 2. マルチタイムフレーム整合性スコア
        scores['mtf_alignment'] = mtf.get('trend_alignment_score', 0.0)
        
        # 3. スマートマネースコア
        if smart_money['smart_money_direction'] == SmartMoneyDirection.BUYING:
            scores['smart_money'] = 0.8 if current_price_trend > 0 else 0.3
        elif smart_money['smart_money_direction'] == SmartMoneyDirection.SELLING:
            scores['smart_money'] = 0.8 if current_price_trend < 0 else 0.3
        else:
            scores['smart_money'] = 0.5
        
        # 4. パターン信頼度スコア
        if patterns['detected_patterns']:
            best_pattern = patterns['detected_patterns'][0]
            scores['pattern_confidence'] = best_pattern.confidence
        else:
            scores['pattern_confidence'] = 0.4
        
        # 5. リスクリワードスコア
        risk_reward = self._calculate_risk_reward(patterns, df)
        scores['risk_reward'] = min(1.0, risk_reward / 3.0)  # RR3で最大スコア
        
        return scores
    
    def _calculate_total_score(self, scores: Dict[str, float]) -> float:
        """重み付けして総合スコアを計算"""
        total = 0.0
        for key, weight in self.weights.items():
            total += scores.get(key, 0.0) * weight
        return total
    
    def _create_entry_signal(self, scores, total_score, regime, mtf, smart_money, patterns, df) -> EntrySignal:
        """エントリーシグナルを作成"""
        current_price = df['close'].iloc[-1]
        
        # エントリー方向を決定
        direction = self._determine_entry_direction(regime, mtf, smart_money, patterns)
        if direction == 0:
            return self._get_wait_signal("方向性が不明確")
        
        action = EntryAction.BUY if direction > 0 else EntryAction.SELL
        
        # エントリータイプを決定
        entry_type = self._determine_entry_type(regime, patterns)
        
        # エントリー価格を計算
        entry_price = self._calculate_entry_price(current_price, entry_type, direction, df)
        
        # ポジションサイズ倍率を決定
        if total_score >= self.entry_thresholds['strong']:
            size_multiplier = 1.0
        elif total_score >= self.entry_thresholds['normal']:
            size_multiplier = 0.5
        else:
            size_multiplier = 0.25
        
        # ストップロスとテイクプロフィットを計算
        stop_loss = self._calculate_stop_loss(entry_price, direction, regime, df)
        take_profits = self._calculate_take_profits(entry_price, direction, stop_loss, patterns)
        
        # 無効化価格（シナリオが崩れる価格）
        invalidation_price = self._calculate_invalidation_price(direction, mtf, df)
        
        # 理由をまとめる
        reasons = self._compile_reasons(scores, regime, mtf, smart_money, patterns)
        
        return EntrySignal(
            action=action,
            confidence=total_score,
            entry_type=entry_type,
            entry_price=entry_price,
            position_size_multiplier=size_multiplier,
            reasons=reasons,
            invalidation_price=invalidation_price,
            stop_loss=stop_loss,
            take_profit=take_profits,
            metadata={
                'regime': regime.regime.value,
                'volatility': regime.volatility_level.value,
                'liquidity': regime.liquidity_score,
                'timestamp': datetime.now().isoformat(),
                'scores': scores
            }
        )
    
    def _get_price_trend(self, df: pd.DataFrame) -> int:
        """現在の価格トレンドを判定"""
        ma20 = df['close'].rolling(window=20).mean()
        ma50 = df['close'].rolling(window=50).mean()
        
        if df['close'].iloc[-1] > ma20.iloc[-1] > ma50.iloc[-1]:
            return 1
        elif df['close'].iloc[-1] < ma20.iloc[-1] < ma50.iloc[-1]:
            return -1
        else:
            return 0
    
    def _calculate_risk_reward(self, patterns: Dict, df: pd.DataFrame) -> float:
        """リスクリワード比を計算"""
        if patterns['detected_patterns']:
            pattern = patterns['detected_patterns'][0]
            risk = abs(pattern.entry_point - pattern.stop_loss)
            reward = abs(pattern.take_profit - pattern.entry_point)
            return reward / risk if risk > 0 else 1.0
        return 1.5  # デフォルト
    
    def _determine_entry_direction(self, regime, mtf, smart_money, patterns) -> int:
        """エントリー方向を決定（1: ロング, -1: ショート, 0: なし）"""
        votes = []
        
        # レジームの方向
        votes.append(regime.trend_direction)
        
        # MTFの推奨
        if mtf.get('recommendation') == "STRONG_BUY_SIGNAL":
            votes.append(1)
        elif mtf.get('recommendation') == "STRONG_SELL_SIGNAL":
            votes.append(-1)
        else:
            votes.append(0)
        
        # スマートマネーの方向
        if smart_money['smart_money_direction'] == SmartMoneyDirection.BUYING:
            votes.append(1)
        elif smart_money['smart_money_direction'] == SmartMoneyDirection.SELLING:
            votes.append(-1)
        else:
            votes.append(0)
        
        # パターンの方向
        if patterns['ml_prediction'].direction == "UP":
            votes.append(1)
        elif patterns['ml_prediction'].direction == "DOWN":
            votes.append(-1)
        else:
            votes.append(0)
        
        # 多数決
        total = sum(votes)
        if total >= 2:
            return 1
        elif total <= -2:
            return -1
        else:
            return 0
    
    def _determine_entry_type(self, regime, patterns) -> EntryType:
        """エントリータイプを決定"""
        if regime.regime == MarketRegime.STRONG_TREND:
            return EntryType.PULLBACK
        elif regime.regime == MarketRegime.RANGE:
            return EntryType.RANGE_BOTTOM
        elif regime.regime == MarketRegime.BREAKOUT:
            return EntryType.BREAKOUT
        elif patterns['detected_patterns'] and patterns['detected_patterns'][0].pattern_type == "REVERSAL":
            return EntryType.REVERSAL
        else:
            return EntryType.MOMENTUM
    
    def _calculate_entry_price(self, current_price: float, entry_type: EntryType, 
                             direction: int, df: pd.DataFrame) -> float:
        """エントリー価格を計算"""
        if entry_type == EntryType.PULLBACK:
            # フィボナッチリトレースメント
            recent_high = df['high'].iloc[-20:].max()
            recent_low = df['low'].iloc[-20:].min()
            fib_382 = recent_low + (recent_high - recent_low) * 0.382
            fib_618 = recent_low + (recent_high - recent_low) * 0.618
            
            if direction > 0:
                return min(current_price * 0.995, fib_618)
            else:
                return max(current_price * 1.005, fib_382)
        
        elif entry_type == EntryType.RANGE_BOTTOM:
            support = df['low'].iloc[-50:].min()
            return support * 1.001
        
        elif entry_type == EntryType.BREAKOUT:
            resistance = df['high'].iloc[-50:].max()
            return resistance * 1.002
        
        else:
            # 現在価格でエントリー
            return current_price
    
    def _calculate_stop_loss(self, entry_price: float, direction: int, 
                           regime, df: pd.DataFrame) -> float:
        """ストップロスを計算"""
        atr = df['high'].rolling(14).max() - df['low'].rolling(14).min()
        atr_value = atr.iloc[-1]
        
        # レジームに応じて調整
        if regime.regime == MarketRegime.VOLATILE:
            multiplier = 2.5
        elif regime.regime == MarketRegime.STRONG_TREND:
            multiplier = 2.0
        else:
            multiplier = 1.5
        
        if direction > 0:
            return entry_price - (atr_value * multiplier)
        else:
            return entry_price + (atr_value * multiplier)
    
    def _calculate_take_profits(self, entry_price: float, direction: int, 
                               stop_loss: float, patterns: Dict) -> List[float]:
        """複数のテイクプロフィットを計算"""
        risk = abs(entry_price - stop_loss)
        
        # デフォルトのTP（リスクリワード比）
        tps = []
        rr_ratios = [1.0, 2.0, 3.0]
        
        for rr in rr_ratios:
            if direction > 0:
                tps.append(entry_price + (risk * rr))
            else:
                tps.append(entry_price - (risk * rr))
        
        # パターンベースのTPがあれば追加
        if patterns['detected_patterns']:
            pattern_tp = patterns['detected_patterns'][0].take_profit
            if pattern_tp not in tps:
                tps.append(pattern_tp)
                tps.sort(reverse=(direction < 0))
        
        return tps[:3]  # 最大3つのTP
    
    def _calculate_invalidation_price(self, direction: int, mtf: Dict, df: pd.DataFrame) -> float:
        """無効化価格を計算"""
        # 重要なサポート/レジスタンスレベル
        if direction > 0:
            # ロングの場合、重要なサポートを下回ったら無効
            key_supports = mtf.get('key_levels', {}).get('support', [])
            if key_supports:
                return min(key_supports) * 0.995
            else:
                return df['low'].iloc[-50:].min() * 0.995
        else:
            # ショートの場合、重要なレジスタンスを上回ったら無効
            key_resistances = mtf.get('key_levels', {}).get('resistance', [])
            if key_resistances:
                return max(key_resistances) * 1.005
            else:
                return df['high'].iloc[-50:].max() * 1.005
    
    def _compile_reasons(self, scores, regime, mtf, smart_money, patterns) -> List[Dict]:
        """エントリー理由をまとめる"""
        reasons = []
        
        # レジーム
        reasons.append({
            'factor': 'regime',
            'score': scores['regime_match'],
            'description': f'{regime.regime.value} - {self._get_trend_description(regime.trend_direction)}'
        })
        
        # MTF
        reasons.append({
            'factor': 'mtf',
            'score': scores['mtf_alignment'],
            'description': f'時間軸整合性: {scores["mtf_alignment"]:.1%}'
        })
        
        # スマートマネー
        reasons.append({
            'factor': 'smart_money',
            'score': scores['smart_money'],
            'description': f'スマートマネー: {smart_money["smart_money_direction"].value}'
        })
        
        # パターン
        if patterns['detected_patterns']:
            pattern = patterns['detected_patterns'][0]
            reasons.append({
                'factor': 'pattern',
                'score': scores['pattern_confidence'],
                'description': f'{pattern.name} (信頼度: {pattern.confidence:.1%})'
            })
        
        return sorted(reasons, key=lambda x: x['score'], reverse=True)
    
    def _get_trend_description(self, direction: int) -> str:
        """トレンド方向の説明"""
        if direction > 0:
            return "上昇トレンド"
        elif direction < 0:
            return "下降トレンド"
        else:
            return "横ばい"
    
    def _get_wait_signal(self, reason: str) -> EntrySignal:
        """待機シグナルを返す"""
        return EntrySignal(
            action=EntryAction.WAIT,
            confidence=0.0,
            entry_type=EntryType.MOMENTUM,
            entry_price=0.0,
            position_size_multiplier=0.0,
            reasons=[{'factor': 'wait', 'score': 0.0, 'description': reason}],
            invalidation_price=0.0,
            stop_loss=0.0,
            take_profit=[],
            metadata={'timestamp': datetime.now().isoformat()}
        )