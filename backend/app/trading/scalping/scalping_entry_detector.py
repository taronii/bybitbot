"""
スキャルピング高速エントリー検出エンジン
1分足での超高速シグナル検出（勝率70%以上を目指す）
"""
import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import numpy as np
import pandas as pd

# from ..analysis.market_regime import RegimeAnalysis, MarketRegime
# from ..analysis.mtf_analysis import MultiTimeframeAnalysis
# from ..analysis.smart_money import SmartMoneyAnalysis
# from ..analysis.pattern_recognition import PatternAnalysis
from ..modes.trading_mode_manager import TradingMode

# モック実装
class MarketRegime:
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING = "RANGING"

logger = logging.getLogger(__name__)

@dataclass
class ScalpingSignal:
    """スキャルピングシグナル"""
    action: str  # 'BUY', 'SELL', 'WAIT'
    confidence: float  # 0.0-1.0
    entry_price: float
    stop_loss: float
    take_profit: List[float]
    position_size_multiplier: float
    speed_score: float  # スピードスコア（0.0-1.0）
    risk_reward_ratio: float
    expected_duration_minutes: int  # 予想保有時間（分）
    entry_reasons: List[Dict]
    invalidation_price: float
    metadata: Dict

@dataclass
class ScalpingMetrics:
    """スキャルピング指標"""
    volume_surge: float  # ボリューム急増率
    price_velocity: float  # 価格変動速度
    orderbook_imbalance: float  # オーダーブック不均衡
    momentum_strength: float  # モメンタム強度
    liquidity_depth: float  # 流動性の深さ
    spread_tightness: float  # スプレッドの狭さ
    tick_intensity: float  # ティック強度

class ScalpingEntryDetector:
    """
    スキャルピング専用高速エントリー検出エンジン
    1分足での勝率70%以上を目指す超高速シグナル検出
    """
    
    def __init__(self):
        self.min_confidence = 0.65  # 本番用：安全な信頼度レベル
        self.max_spread_percent = 0.1  # 最大スプレッド（0.1%）
        self.min_volume_multiplier = 2.0  # 最小ボリューム倍率（2倍以上）
        self.quick_profit_target = 0.2  # 迅速利確目標（0.2%）
        self.tight_stop_loss = 0.1  # タイトストップロス（0.1%）
        
        # キャッシュ
        self.cached_analysis: Dict = {}
        self.last_analysis_time: Dict = {}
        
    async def detect_scalping_entry(
        self,
        symbol: str,
        price_data: pd.DataFrame,
        orderbook_data: Dict,
        volume_data: Dict
    ) -> ScalpingSignal:
        """
        スキャルピングエントリーシグナルを検出
        
        Parameters:
        -----------
        symbol : str
            取引ペア
        price_data : pd.DataFrame
            価格データ（1分足 + より短い時間足）
        orderbook_data : Dict
            オーダーブックデータ
        volume_data : Dict
            ボリュームデータ
            
        Returns:
        --------
        ScalpingSignal : 検出されたスキャルピングシグナル
        """
        try:
            current_price = float(price_data['close'].iloc[-1])
            
            # Step 1: 市場状況の高速判定
            market_condition = await self._assess_market_condition(
                symbol, price_data, orderbook_data
            )
            
            if not market_condition['suitable_for_scalping']:
                return self._create_wait_signal(current_price, market_condition['reason'])
            
            # Step 2: スキャルピング指標の計算
            scalping_metrics = await self._calculate_scalping_metrics(
                price_data, orderbook_data, volume_data
            )
            
            # Step 3: 高速エントリーパターンの検出
            entry_patterns = await self._detect_entry_patterns(
                price_data, scalping_metrics
            )
            
            # Step 4: リスク・リワード計算
            risk_reward = await self._calculate_risk_reward(
                current_price, entry_patterns, scalping_metrics
            )
            
            # Step 5: 総合判定とシグナル生成
            signal = await self._generate_scalping_signal(
                symbol, current_price, entry_patterns, 
                scalping_metrics, risk_reward, market_condition
            )
            
            return signal
            
        except Exception as e:
            logger.error(f"Scalping entry detection failed: {e}")
            return self._create_error_signal(
                price_data['close'].iloc[-1] if len(price_data) > 0 else 0.0
            )
    
    async def _assess_market_condition(
        self, 
        symbol: str, 
        price_data: pd.DataFrame, 
        orderbook_data: Dict
    ) -> Dict:
        """市場状況の高速判定"""
        try:
            # スプレッドチェック
            bid_price = float(orderbook_data.get('bids', [[0]])[0][0])
            ask_price = float(orderbook_data.get('asks', [[0]])[0][0])
            spread_percent = ((ask_price - bid_price) / bid_price) * 100 if bid_price > 0 else 10.0
            
            if spread_percent > self.max_spread_percent:
                return {
                    'suitable_for_scalping': False,
                    'reason': f'スプレッドが広すぎます ({spread_percent:.3f}%)',
                    'spread_percent': spread_percent
                }
            
            # ボラティリティチェック（過去20分）
            recent_data = price_data.tail(20)
            volatility = (recent_data['high'].max() - recent_data['low'].min()) / recent_data['close'].iloc[-1]
            
            if volatility < 0.002:  # 0.2%未満
                return {
                    'suitable_for_scalping': False,
                    'reason': 'ボラティリティが低すぎます',
                    'volatility': volatility
                }
            
            if volatility > 0.03:  # 3%超過（本番用）
                return {
                    'suitable_for_scalping': False,
                    'reason': 'ボラティリティが高すぎます（危険）',
                    'volatility': volatility
                }
            
            # ボリュームチェック
            avg_volume = price_data['volume'].tail(20).mean()
            current_volume = price_data['volume'].iloc[-1]
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
            
            if volume_ratio < 0.5:
                return {
                    'suitable_for_scalping': False,
                    'reason': 'ボリュームが不足しています',
                    'volume_ratio': volume_ratio
                }
            
            return {
                'suitable_for_scalping': True,
                'reason': 'スキャルピング適合',
                'spread_percent': spread_percent,
                'volatility': volatility,
                'volume_ratio': volume_ratio
            }
            
        except Exception as e:
            logger.error(f"Market condition assessment failed: {e}")
            return {
                'suitable_for_scalping': False,
                'reason': f'市場状況判定エラー: {str(e)}'
            }
    
    async def _calculate_scalping_metrics(
        self,
        price_data: pd.DataFrame,
        orderbook_data: Dict,
        volume_data: Dict
    ) -> ScalpingMetrics:
        """スキャルピング指標の計算"""
        try:
            # ボリューム急増率
            recent_volume = price_data['volume'].tail(5).mean()
            baseline_volume = price_data['volume'].tail(20).mean()
            volume_surge = recent_volume / baseline_volume if baseline_volume > 0 else 1.0
            
            # 価格変動速度（1分間での変動率）
            price_change = abs(price_data['close'].iloc[-1] - price_data['close'].iloc[-2])
            price_velocity = price_change / price_data['close'].iloc[-1] if price_data['close'].iloc[-1] > 0 else 0
            
            # オーダーブック不均衡
            bids = orderbook_data.get('bids', [])
            asks = orderbook_data.get('asks', [])
            
            bid_volume = sum(float(bid[1]) for bid in bids[:5]) if bids else 0
            ask_volume = sum(float(ask[1]) for ask in asks[:5]) if asks else 0
            total_volume = bid_volume + ask_volume
            
            orderbook_imbalance = abs(bid_volume - ask_volume) / total_volume if total_volume > 0 else 0
            
            # モメンタム強度（RSI_2期間）
            close_prices = price_data['close'].tail(10)
            price_changes = close_prices.diff().dropna()
            
            if len(price_changes) >= 3:
                gains = price_changes[price_changes > 0].sum()
                losses = abs(price_changes[price_changes < 0].sum())
                rs = gains / losses if losses > 0 else 100
                rsi_2 = 100 - (100 / (1 + rs))
                momentum_strength = abs(rsi_2 - 50) / 50  # 0-1に正規化
            else:
                momentum_strength = 0.0
            
            # 流動性の深さ
            bid_depth = sum(float(bid[1]) for bid in bids[:10]) if bids else 0
            ask_depth = sum(float(ask[1]) for ask in asks[:10]) if asks else 0
            liquidity_depth = min(bid_depth, ask_depth)
            
            # スプレッドの狭さ
            if bids and asks:
                bid_price = float(bids[0][0])
                ask_price = float(asks[0][0])
                spread = (ask_price - bid_price) / bid_price
                spread_tightness = max(0, 1 - (spread / 0.001))  # 0.1%基準で正規化
            else:
                spread_tightness = 0.0
            
            # ティック強度（価格変動の頻度と強度）
            price_changes_abs = abs(price_data['close'].tail(10).diff()).dropna()
            tick_intensity = price_changes_abs.mean() / price_data['close'].iloc[-1] if len(price_changes_abs) > 0 else 0
            
            return ScalpingMetrics(
                volume_surge=min(volume_surge, 10.0),  # 上限設定
                price_velocity=min(price_velocity * 1000, 10.0),  # スケール調整
                orderbook_imbalance=orderbook_imbalance,
                momentum_strength=momentum_strength,
                liquidity_depth=min(liquidity_depth / 100000, 1.0),  # 正規化
                spread_tightness=spread_tightness,
                tick_intensity=min(tick_intensity * 1000, 10.0)  # スケール調整
            )
            
        except Exception as e:
            logger.error(f"Scalping metrics calculation failed: {e}")
            return ScalpingMetrics(0, 0, 0, 0, 0, 0, 0)
    
    async def _detect_entry_patterns(
        self,
        price_data: pd.DataFrame,
        metrics: ScalpingMetrics
    ) -> List[Dict]:
        """高速エントリーパターンの検出"""
        patterns = []
        
        try:
            recent_data = price_data.tail(10)
            current_price = recent_data['close'].iloc[-1]
            
            # パターン1: ボリューム急増 + 価格突破（本番用）
            if metrics.volume_surge > 1.2 and metrics.price_velocity > 0.1:
                direction = 'BUY' if recent_data['close'].iloc[-1] > recent_data['close'].iloc[-2] else 'SELL'
                confidence = min(0.9, 0.65 + (metrics.volume_surge / 5.0) + (metrics.price_velocity / 2.0))
                
                patterns.append({
                    'name': 'ボリューム急増突破',
                    'direction': direction,
                    'confidence': confidence,
                    'entry_type': 'MOMENTUM',
                    'speed_score': 0.9,
                    'expected_duration': 3  # 3分
                })
            
            # パターン2: オーダーブック不均衡 + モメンタム
            if metrics.orderbook_imbalance > 0.35 and metrics.momentum_strength > 0.65:
                direction = 'BUY' if metrics.momentum_strength > 0.5 else 'SELL'
                confidence = min(0.85, 0.5 + metrics.orderbook_imbalance + (metrics.momentum_strength / 2))
                
                patterns.append({
                    'name': 'オーダーブック不均衡',
                    'direction': direction,
                    'confidence': confidence,
                    'entry_type': 'ORDERFLOW',
                    'speed_score': 0.8,
                    'expected_duration': 5  # 5分
                })
            
            # パターン3: 高速リバーサル（逆張り）
            if metrics.momentum_strength > 0.75 and metrics.tick_intensity > 1.5:
                # 現在のトレンドと逆方向
                recent_change = recent_data['close'].iloc[-1] - recent_data['close'].iloc[-5]
                direction = 'SELL' if recent_change > 0 else 'BUY'
                confidence = min(0.8, 0.55 + (metrics.momentum_strength + metrics.tick_intensity / 5.0) / 2)
                
                patterns.append({
                    'name': '高速リバーサル',
                    'direction': direction,
                    'confidence': confidence,
                    'entry_type': 'REVERSAL',
                    'speed_score': 0.95,
                    'expected_duration': 2  # 2分
                })
            
            # パターン4: 完璧なスプレッド環境での順張り
            if metrics.spread_tightness > 0.7 and metrics.liquidity_depth > 0.4:
                # 短期トレンド確認
                sma_3 = recent_data['close'].tail(3).mean()
                sma_7 = recent_data['close'].tail(7).mean()
                
                if abs(sma_3 - sma_7) / current_price > 0.0005:  # 0.05%以上の差
                    direction = 'BUY' if sma_3 > sma_7 else 'SELL'
                    confidence = min(0.8, 0.5 + metrics.spread_tightness + (metrics.liquidity_depth / 2))
                    
                    patterns.append({
                        'name': '完璧環境順張り',
                        'direction': direction,
                        'confidence': confidence,
                        'entry_type': 'TREND_FOLLOW',
                        'speed_score': 0.7,
                        'expected_duration': 7  # 7分
                    })
            
            # パターンの重複排除と優先順位付け
            if len(patterns) > 1:
                patterns = sorted(patterns, key=lambda x: x['confidence'] * x['speed_score'], reverse=True)
                patterns = patterns[:2]  # 上位2パターンのみ
            
            return patterns
            
        except Exception as e:
            logger.error(f"Entry pattern detection failed: {e}")
            return []
        finally:
            # 本番用：デモシグナルを無効化
            pass
    
    async def _calculate_risk_reward(
        self,
        current_price: float,
        patterns: List[Dict],
        metrics: ScalpingMetrics
    ) -> Dict:
        """リスク・リワード計算"""
        if not patterns:
            return {'ratio': 0, 'stop_loss': current_price, 'take_profits': []}
        
        try:
            best_pattern = patterns[0]
            direction = best_pattern['direction']
            
            # ストップロス計算（タイト設定）
            base_stop_distance = current_price * self.tight_stop_loss / 100
            
            # ボラティリティ調整
            volatility_multiplier = 1 + (metrics.tick_intensity / 10)
            stop_distance = base_stop_distance * volatility_multiplier
            
            if direction == 'BUY':
                stop_loss = current_price - stop_distance
                take_profit_1 = current_price + (stop_distance * 2)  # 2:1比率
                take_profit_2 = current_price + (stop_distance * 3)  # 3:1比率
            else:
                stop_loss = current_price + stop_distance
                take_profit_1 = current_price - (stop_distance * 2)
                take_profit_2 = current_price - (stop_distance * 3)
            
            # 流動性を考慮した利確調整
            if metrics.liquidity_depth < 0.3:
                # 流動性が低い場合は利確を保守的に
                take_profit_1 = current_price + (stop_distance * 1.5) if direction == 'BUY' else current_price - (stop_distance * 1.5)
                take_profit_2 = current_price + (stop_distance * 2) if direction == 'BUY' else current_price - (stop_distance * 2)
            
            return {
                'ratio': abs(take_profit_1 - current_price) / abs(stop_loss - current_price),
                'stop_loss': stop_loss,
                'take_profits': [take_profit_1, take_profit_2],
                'stop_distance': stop_distance
            }
            
        except Exception as e:
            logger.error(f"Risk reward calculation failed: {e}")
            return {'ratio': 0, 'stop_loss': current_price, 'take_profits': []}
    
    async def _generate_scalping_signal(
        self,
        symbol: str,
        current_price: float,
        patterns: List[Dict],
        metrics: ScalpingMetrics,
        risk_reward: Dict,
        market_condition: Dict
    ) -> ScalpingSignal:
        """スキャルピングシグナルの生成"""
        
        if not patterns or risk_reward['ratio'] < 1.5:
            return self._create_wait_signal(current_price, "適切なパターンなし")
        
        try:
            best_pattern = patterns[0]
            
            # 総合信頼度計算
            base_confidence = best_pattern['confidence']
            
            # 市場環境ボーナス
            env_bonus = 0
            if market_condition['spread_percent'] < 0.02:  # 0.02%未満
                env_bonus += 0.05
            if market_condition['volume_ratio'] > 1.5:
                env_bonus += 0.05
            if metrics.liquidity_depth > 0.5:
                env_bonus += 0.05
            
            final_confidence = min(0.95, base_confidence + env_bonus)
            
            # 信頼度フィルター
            if final_confidence < self.min_confidence:
                return self._create_wait_signal(current_price, f"信頼度不足 ({final_confidence:.2f})")
            
            # ポジションサイズ計算（スキャルピング用）
            confidence_multiplier = (final_confidence - 0.5) * 2  # 0.5-1.0を0-1.0にマップ
            speed_multiplier = best_pattern['speed_score']
            position_size = min(0.03, 0.015 * confidence_multiplier * speed_multiplier)  # 最大3%
            
            # エントリー理由の生成
            entry_reasons = [
                {
                    'factor': best_pattern['name'],
                    'score': best_pattern['confidence'],
                    'description': f"{best_pattern['entry_type']}パターン検出"
                },
                {
                    'factor': 'ボリューム',
                    'score': min(1.0, metrics.volume_surge / 3.0),
                    'description': f"ボリューム急増 ({metrics.volume_surge:.1f}倍)"
                },
                {
                    'factor': '市場環境',
                    'score': min(1.0, (metrics.spread_tightness + metrics.liquidity_depth) / 2),
                    'description': f"最適な取引環境 (スプレッド: {market_condition['spread_percent']:.3f}%)"
                }
            ]
            
            # 無効化価格の計算
            invalidation_distance = risk_reward['stop_distance'] * 1.5
            if best_pattern['direction'] == 'BUY':
                invalidation_price = current_price - invalidation_distance
            else:
                invalidation_price = current_price + invalidation_distance
            
            return ScalpingSignal(
                action=best_pattern['direction'],
                confidence=final_confidence,
                entry_price=current_price,
                stop_loss=risk_reward['stop_loss'],
                take_profit=risk_reward['take_profits'],
                position_size_multiplier=position_size,
                speed_score=best_pattern['speed_score'],
                risk_reward_ratio=risk_reward['ratio'],
                expected_duration_minutes=best_pattern['expected_duration'],
                entry_reasons=entry_reasons,
                invalidation_price=invalidation_price,
                metadata={
                    'pattern_type': best_pattern['entry_type'],
                    'market_condition': market_condition,
                    'scalping_metrics': {
                        'volume_surge': metrics.volume_surge,
                        'price_velocity': metrics.price_velocity,
                        'orderbook_imbalance': metrics.orderbook_imbalance,
                        'momentum_strength': metrics.momentum_strength,
                        'liquidity_depth': metrics.liquidity_depth,
                        'spread_tightness': metrics.spread_tightness,
                        'tick_intensity': metrics.tick_intensity
                    },
                    'timestamp': datetime.now().isoformat(),
                    'symbol': symbol
                }
            )
            
        except Exception as e:
            logger.error(f"Signal generation failed: {e}")
            return self._create_error_signal(current_price)
    
    def _create_wait_signal(self, price: float, reason: str) -> ScalpingSignal:
        """待機シグナルの作成"""
        # 価格が0の場合はエラー
        if price <= 0:
            price = 1.0  # デフォルト値
            
        return ScalpingSignal(
            action='WAIT',
            confidence=0.0,  # WAITシグナルは信頼度0
            entry_price=price,
            stop_loss=price * 0.995,
            take_profit=[price * 1.005],
            position_size_multiplier=0.0,
            speed_score=0.0,
            risk_reward_ratio=1.0,
            expected_duration_minutes=5,
            entry_reasons=[{
                'factor': '待機',
                'score': 0.0,
                'description': reason
            }],
            invalidation_price=price * 0.99,
            metadata={
                'reason': reason,
                'timestamp': datetime.now().isoformat()
            }
        )
    
    def _create_error_signal(self, price: float) -> ScalpingSignal:
        """エラーシグナルの作成"""
        return ScalpingSignal(
            action='WAIT',
            confidence=0.0,
            entry_price=price,
            stop_loss=price,
            take_profit=[],
            position_size_multiplier=0.0,
            speed_score=0.0,
            risk_reward_ratio=0.0,
            expected_duration_minutes=0,
            entry_reasons=[{
                'factor': 'エラー',
                'score': 0.0,
                'description': 'システムエラーが発生しました'
            }],
            invalidation_price=price,
            metadata={
                'error': True,
                'timestamp': datetime.now().isoformat()
            }
        )

# グローバルインスタンス
scalping_detector = ScalpingEntryDetector()