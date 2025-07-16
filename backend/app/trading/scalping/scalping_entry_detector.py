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
from ..modes.trading_mode_manager import TradingMode, trading_mode_manager
from ..data.market_data_fetcher import market_data_fetcher

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
        self.min_confidence = 0.35  # さらに緩和：35%以上で取引可能（より多くのエントリー機会）
        self.max_spread_percent = 0.20  # 緩和：最大スプレッド（0.20%）
        self.min_volume_multiplier = 1.05  # さらに緩和：最小ボリューム倍率（1.05倍以上）
        self.quick_profit_target = 0.15  # 迅速利確目標（0.15%）
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
            # スキャルピングモードがアクティブかチェック
            if not trading_mode_manager.is_mode_active(TradingMode.SCALPING):
                logger.info("Scalping mode is not active")
                current_price = float(price_data['close'].iloc[-1]) if price_data is not None and len(price_data) > 0 else 1.0
                return self._create_wait_signal(current_price, "スキャルピングモードが無効です")
            
            # 価格データの検証
            if price_data is None or len(price_data) == 0:
                logger.error(f"No price data for {symbol}")
                return self._create_error_signal(1.0)
            
            current_price = float(price_data['close'].iloc[-1])
            logger.debug(f"Current price for {symbol}: {current_price}")
            
            if current_price <= 0:
                logger.error(f"Invalid price for {symbol}: {current_price}")
                return self._create_error_signal(1.0)
            
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
            try:
                default_price = price_data['close'].iloc[-1] if len(price_data) > 0 else 1.0
            except:
                default_price = 1.0
            return self._create_error_signal(default_price)
    
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
            
            logger.debug(f"Volume calculation - Recent: {recent_volume:.2f}, Baseline: {baseline_volume:.2f}, Surge: {volume_surge:.3f}")
            
            # 価格変動速度（1分間での変動率）
            price_change = abs(price_data['close'].iloc[-1] - price_data['close'].iloc[-2])
            price_velocity = price_change / price_data['close'].iloc[-1] if price_data['close'].iloc[-1] > 0 else 0
            
            logger.debug(f"Price velocity - Change: {price_change:.6f}, Current price: {price_data['close'].iloc[-1]:.2f}, Velocity: {price_velocity:.6f}")
            
            # オーダーブック不均衡
            bids = orderbook_data.get('bids', [])
            asks = orderbook_data.get('asks', [])
            
            bid_volume = sum(float(bid[1]) for bid in bids[:5]) if bids else 0
            ask_volume = sum(float(ask[1]) for ask in asks[:5]) if asks else 0
            total_volume = bid_volume + ask_volume
            
            orderbook_imbalance = abs(bid_volume - ask_volume) / total_volume if total_volume > 0 else 0
            
            logger.debug(f"Orderbook - Bid vol: {bid_volume:.2f}, Ask vol: {ask_volume:.2f}, Imbalance: {orderbook_imbalance:.3f}")
            
            # モメンタム強度（RSI_2期間）
            close_prices = price_data['close'].tail(10)
            price_changes = close_prices.diff().dropna()
            
            if len(price_changes) >= 3:
                gains = price_changes[price_changes > 0].sum()
                losses = abs(price_changes[price_changes < 0].sum())
                
                if losses > 0:
                    rs = gains / losses
                    rsi_2 = 100 - (100 / (1 + rs))
                else:
                    # 全て上昇している場合
                    rsi_2 = 100 if gains > 0 else 50
                
                momentum_strength = abs(rsi_2 - 50) / 50  # 0-1に正規化
                logger.debug(f"Momentum - Gains: {gains:.6f}, Losses: {losses:.6f}, RSI: {rsi_2:.2f}, Strength: {momentum_strength:.3f}")
            else:
                momentum_strength = 0.0
                logger.debug(f"Momentum - Not enough data points ({len(price_changes)}), Strength: {momentum_strength:.3f}")
            
            # 流動性の深さ
            bid_depth = sum(float(bid[1]) for bid in bids[:10]) if bids else 0
            ask_depth = sum(float(ask[1]) for ask in asks[:10]) if asks else 0
            liquidity_depth = min(bid_depth, ask_depth)
            
            logger.debug(f"Liquidity - Bid depth: {bid_depth:.2f}, Ask depth: {ask_depth:.2f}, Min depth: {liquidity_depth:.2f}")
            
            # スプレッドの狭さ
            if bids and asks:
                bid_price = float(bids[0][0])
                ask_price = float(asks[0][0])
                spread = (ask_price - bid_price) / bid_price
                spread_tightness = max(0, 1 - (spread / 0.001))  # 0.1%基準で正規化
            else:
                spread_tightness = 0.0
                
            logger.debug(f"Spread - Spread %: {spread * 100 if 'spread' in locals() else 'N/A'}%, Tightness: {spread_tightness:.3f}")
            
            # ティック強度（価格変動の頻度と強度）
            price_changes_abs = abs(price_data['close'].tail(10).diff()).dropna()
            tick_intensity = price_changes_abs.mean() / price_data['close'].iloc[-1] if len(price_changes_abs) > 0 else 0
            
            logger.debug(f"Tick intensity - Raw: {tick_intensity:.6f}")
            
            # より現実的なスケーリング調整
            scaled_metrics = ScalpingMetrics(
                volume_surge=min(volume_surge, 10.0),  # 上限設定
                price_velocity=min(price_velocity * 100, 10.0),  # より感度を高く
                orderbook_imbalance=min(orderbook_imbalance * 2, 1.0),  # 増幅
                momentum_strength=momentum_strength,
                liquidity_depth=min(liquidity_depth / 10000, 1.0),  # より現実的な正規化
                spread_tightness=spread_tightness,
                tick_intensity=min(tick_intensity * 100, 10.0)  # より感度を高く
            )
            
            logger.debug(f"Scaled metrics - Volume surge: {scaled_metrics.volume_surge:.3f}, "
                        f"Price velocity: {scaled_metrics.price_velocity:.3f}, "
                        f"Orderbook imbalance: {scaled_metrics.orderbook_imbalance:.3f}, "
                        f"Liquidity depth: {scaled_metrics.liquidity_depth:.3f}, "
                        f"Tick intensity: {scaled_metrics.tick_intensity:.3f}")
            
            return scaled_metrics
            
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
            
            # デバッグログ追加
            logger.info(f"Pattern detection metrics - Volume surge: {metrics.volume_surge:.3f}, "
                       f"Price velocity: {metrics.price_velocity:.6f}, "
                       f"Orderbook imbalance: {metrics.orderbook_imbalance:.3f}, "
                       f"Momentum strength: {metrics.momentum_strength:.3f}, "
                       f"Tick intensity: {metrics.tick_intensity:.3f}, "
                       f"Spread tightness: {metrics.spread_tightness:.3f}, "
                       f"Liquidity depth: {metrics.liquidity_depth:.3f}")
            
            # パターン1: ボリューム急増 + 価格突破（緩和版）
            if metrics.volume_surge > 0.8 and metrics.price_velocity > 0.00001:  # 大幅に緩和
                direction = 'BUY' if recent_data['close'].iloc[-1] > recent_data['close'].iloc[-2] else 'SELL'
                confidence = min(0.9, 0.45 + (metrics.volume_surge - 0.8) * 3 + metrics.price_velocity * 100)
                
                logger.info(f"Pattern 1 detected: Volume surge pattern - Direction: {direction}, Confidence: {confidence:.3f}")
                
                patterns.append({
                    'name': 'ボリューム急増突破',
                    'direction': direction,
                    'confidence': confidence,
                    'entry_type': 'MOMENTUM',
                    'speed_score': 0.9,
                    'expected_duration': 3  # 3分
                })
            else:
                logger.debug(f"Pattern 1 not met: Volume surge {metrics.volume_surge:.3f} <= 0.8 or Price velocity {metrics.price_velocity:.6f} <= 0.00001")
            
            # パターン2: オーダーブック不均衡 + モメンタム（緩和版）
            if metrics.orderbook_imbalance > 0.1 and metrics.momentum_strength > 0.2:  # 大幅に緩和
                # ビッド側が強い場合はBUY、アスク側が強い場合はSELL
                recent_change = recent_data['close'].iloc[-1] - recent_data['close'].iloc[-3]
                direction = 'BUY' if recent_change > 0 else 'SELL'
                confidence = min(0.85, 0.45 + metrics.orderbook_imbalance * 3 + metrics.momentum_strength * 1.5)
                
                logger.info(f"Pattern 2 detected: Orderbook imbalance - Direction: {direction}, Confidence: {confidence:.3f}")
                
                patterns.append({
                    'name': 'オーダーブック不均衡',
                    'direction': direction,
                    'confidence': confidence,
                    'entry_type': 'ORDERFLOW',
                    'speed_score': 0.8,
                    'expected_duration': 5  # 5分
                })
            else:
                logger.debug(f"Pattern 2 not met: Orderbook imbalance {metrics.orderbook_imbalance:.3f} <= 0.1 or Momentum {metrics.momentum_strength:.3f} <= 0.2")
            
            # パターン3: 高速リバーサル（逆張り）
            if metrics.momentum_strength > 0.4 and metrics.tick_intensity > 0.5:  # 大幅に緩和
                # 現在のトレンドと逆方向
                recent_change = recent_data['close'].iloc[-1] - recent_data['close'].iloc[-5]
                direction = 'SELL' if recent_change > 0 else 'BUY'
                confidence = min(0.8, 0.5 + metrics.momentum_strength * 0.7 + metrics.tick_intensity * 0.3)
                
                logger.info(f"Pattern 3 detected: Fast reversal - Direction: {direction}, Confidence: {confidence:.3f}")
                
                patterns.append({
                    'name': '高速リバーサル',
                    'direction': direction,
                    'confidence': confidence,
                    'entry_type': 'REVERSAL',
                    'speed_score': 0.95,
                    'expected_duration': 2  # 2分
                })
            else:
                logger.debug(f"Pattern 3 not met: Momentum {metrics.momentum_strength:.3f} <= 0.4 or Tick intensity {metrics.tick_intensity:.3f} <= 0.5")
            
            # パターン4: 完璧なスプレッド環境での順張り
            if metrics.spread_tightness > 0.3 and metrics.liquidity_depth > 0.1:  # 大幅に緩和
                # 短期トレンド確認
                sma_3 = recent_data['close'].tail(3).mean()
                sma_7 = recent_data['close'].tail(7).mean()
                
                if abs(sma_3 - sma_7) / current_price > 0.0001:  # 0.01%以上の差に緩和
                    direction = 'BUY' if sma_3 > sma_7 else 'SELL'
                    confidence = min(0.8, 0.45 + metrics.spread_tightness * 0.7 + metrics.liquidity_depth * 2)
                    
                    logger.info(f"Pattern 4 detected: Perfect spread trend - Direction: {direction}, Confidence: {confidence:.3f}")
                    
                    patterns.append({
                        'name': '完璧環境順張り',
                        'direction': direction,
                        'confidence': confidence,
                        'entry_type': 'TREND_FOLLOW',
                        'speed_score': 0.7,
                        'expected_duration': 7  # 7分
                    })
                else:
                    logger.debug(f"Pattern 4 not met: SMA difference {abs(sma_3 - sma_7) / current_price:.6f} <= 0.0001")
            else:
                logger.debug(f"Pattern 4 not met: Spread tightness {metrics.spread_tightness:.3f} <= 0.3 or Liquidity {metrics.liquidity_depth:.3f} <= 0.1")
            
            # パターン5: フォールバックパターン（常に何かシグナルを出す）
            if len(patterns) == 0:
                # 基本的な方向性判定
                recent_change = recent_data['close'].iloc[-1] - recent_data['close'].iloc[-5]
                direction = 'BUY' if recent_change > 0 else 'SELL'
                
                # 最低限の信頼度を計算
                base_confidence = 0.45
                if metrics.volume_surge > 1.0:
                    base_confidence += 0.05
                if metrics.orderbook_imbalance > 0.2:
                    base_confidence += 0.05
                if metrics.momentum_strength > 0.5:
                    base_confidence += 0.05
                
                confidence = min(0.65, base_confidence)
                
                logger.info(f"Pattern 5 (Fallback) detected: Basic trend - Direction: {direction}, Confidence: {confidence:.3f}")
                
                patterns.append({
                    'name': '基本トレンドフォロー',
                    'direction': direction,
                    'confidence': confidence,
                    'entry_type': 'BASIC_TREND',
                    'speed_score': 0.6,
                    'expected_duration': 5  # 5分
                })
            
            # パターンの重複排除と優先順位付け
            if len(patterns) > 1:
                patterns = sorted(patterns, key=lambda x: x['confidence'] * x['speed_score'], reverse=True)
                patterns = patterns[:2]  # 上位2パターンのみ
            
            logger.info(f"Total patterns detected: {len(patterns)}")
            
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
            logger.warning(f"Invalid price in wait signal: {price}, using default")
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
        # 価格の検証
        if price <= 0:
            logger.warning(f"Invalid price in error signal: {price}, using default")
            price = 1.0
            
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