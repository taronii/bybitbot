"""
相場環境別利確戦略
市場状況に完全適応する利確システム
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging
from datetime import datetime, timedelta

from ..analysis.market_regime import MarketRegime

logger = logging.getLogger(__name__)

class TPStrategyType(Enum):
    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    QUICK_SCALP = "quick_scalp"
    BREAKOUT_CAPTURE = "breakout_capture"
    VOLATILITY_HARVEST = "volatility_harvest"

@dataclass
class TPStrategy:
    type: TPStrategyType
    initial_tp: float
    trailing_type: str  # 'aggressive', 'conservative', 'tight'
    partial_exits: List[float]  # 部分決済の割合リスト
    extension_allowed: bool
    max_extension: float  # 最大延長倍率
    time_limit: Optional[int]  # 秒単位のタイムリミット
    special_conditions: Dict  # 特殊条件

class MarketAdaptiveTakeProfit:
    """
    相場環境に完全適応する利確システム
    """
    
    def __init__(self, session, config: Dict):
        self.session = session
        self.config = config
        
        # デフォルト戦略パラメータ
        self.default_strategies = {
            MarketRegime.STRONG_TREND: {
                'initial_tp_multiplier': 1.05,  # 5%
                'trailing': 'aggressive',
                'partials': [0.3, 0.3, 0.4],
                'extension': True,
                'max_extension': 3.0
            },
            MarketRegime.WEAK_TREND: {
                'initial_tp_multiplier': 1.03,  # 3%
                'trailing': 'moderate',
                'partials': [0.4, 0.3, 0.3],
                'extension': True,
                'max_extension': 2.0
            },
            MarketRegime.RANGE: {
                'initial_tp_multiplier': 1.015,  # 1.5%
                'trailing': 'conservative',
                'partials': [0.5, 0.3, 0.2],
                'extension': False,
                'max_extension': 1.0
            },
            MarketRegime.VOLATILE: {
                'initial_tp_multiplier': 1.02,  # 2%
                'trailing': 'tight',
                'partials': [0.6, 0.3, 0.1],
                'extension': False,
                'time_limit': 300  # 5分
            },
            MarketRegime.BREAKOUT: {
                'initial_tp_multiplier': 1.04,  # 4%
                'trailing': 'aggressive',
                'partials': [0.25, 0.25, 0.25, 0.25],
                'extension': True,
                'max_extension': 2.5
            }
        }
    
    async def select_tp_strategy(self, market_regime: str, 
                               position: Dict, 
                               market_data: Dict) -> TPStrategy:
        """
        市場環境に応じた最適な利確戦略を選択
        
        Parameters:
        -----------
        market_regime : str
            現在の市場レジーム
        position : dict
            ポジション情報
        market_data : dict
            市場データ（ボラティリティ、流動性等）
            
        Returns:
        --------
        TPStrategy : 選択された利確戦略
        """
        try:
            # 基本戦略を取得
            regime_enum = MarketRegime[market_regime.upper()]
            base_strategy = self.default_strategies.get(
                regime_enum, 
                self.default_strategies[MarketRegime.RANGE]
            )
            
            # 市場状況に応じて戦略を調整
            strategy = await self._adjust_strategy_for_conditions(
                base_strategy, position, market_data
            )
            
            return strategy
            
        except Exception as e:
            logger.error(f"Failed to select TP strategy: {e}")
            return self._get_fallback_strategy(position)
    
    async def _adjust_strategy_for_conditions(self, base_strategy: Dict,
                                            position: Dict,
                                            market_data: Dict) -> TPStrategy:
        """市場条件に応じて戦略を調整"""
        entry_price = position['entry_price']
        side = position['side']
        
        # 戦略タイプを決定
        strategy_type = self._determine_strategy_type(market_data)
        
        # 初期利確価格を計算
        if strategy_type == TPStrategyType.TREND_FOLLOWING:
            initial_tp = await self._calculate_trend_following_tp(
                entry_price, side, market_data
            )
        elif strategy_type == TPStrategyType.MEAN_REVERSION:
            initial_tp = await self._calculate_mean_reversion_tp(
                entry_price, side, market_data
            )
        elif strategy_type == TPStrategyType.QUICK_SCALP:
            initial_tp = self._calculate_quick_scalp_tp(
                entry_price, side, base_strategy
            )
        elif strategy_type == TPStrategyType.BREAKOUT_CAPTURE:
            initial_tp = await self._calculate_breakout_tp(
                entry_price, side, market_data
            )
        else:  # VOLATILITY_HARVEST
            initial_tp = self._calculate_volatility_harvest_tp(
                entry_price, side, market_data
            )
        
        # 特殊条件を設定
        special_conditions = self._set_special_conditions(market_data)
        
        return TPStrategy(
            type=strategy_type,
            initial_tp=initial_tp,
            trailing_type=base_strategy['trailing'],
            partial_exits=base_strategy['partials'],
            extension_allowed=base_strategy.get('extension', False),
            max_extension=base_strategy.get('max_extension', 1.0),
            time_limit=base_strategy.get('time_limit'),
            special_conditions=special_conditions
        )
    
    def _determine_strategy_type(self, market_data: Dict) -> TPStrategyType:
        """市場データから戦略タイプを決定"""
        regime = market_data.get('regime', 'RANGE')
        volatility = market_data.get('volatility_level', 'MEDIUM')
        momentum = market_data.get('momentum', 0)
        
        if regime == 'STRONG_TREND' and abs(momentum) > 0.7:
            return TPStrategyType.TREND_FOLLOWING
        elif regime == 'RANGE':
            return TPStrategyType.MEAN_REVERSION
        elif volatility == 'HIGH':
            if regime == 'BREAKOUT':
                return TPStrategyType.BREAKOUT_CAPTURE
            else:
                return TPStrategyType.QUICK_SCALP
        elif volatility == 'EXTREME':
            return TPStrategyType.VOLATILITY_HARVEST
        else:
            # デフォルト
            if abs(momentum) > 0.5:
                return TPStrategyType.TREND_FOLLOWING
            else:
                return TPStrategyType.MEAN_REVERSION
    
    async def _calculate_trend_following_tp(self, entry_price: float,
                                          side: str, market_data: Dict) -> float:
        """トレンドフォロー戦略の利確価格"""
        try:
            # トレンドの強さに応じて利確幅を調整
            trend_strength = market_data.get('trend_strength', 0.5)
            atr = market_data.get('atr', entry_price * 0.02)
            
            # 基本利確幅（ATRの倍数）
            if trend_strength > 0.8:
                tp_distance = atr * 4.0  # 非常に強いトレンド
            elif trend_strength > 0.6:
                tp_distance = atr * 3.0  # 強いトレンド
            else:
                tp_distance = atr * 2.0  # 通常のトレンド
            
            # 重要なテクニカルレベルを考慮
            symbol = market_data.get('symbol')
            if symbol:
                tech_levels = await self._get_technical_levels(symbol, entry_price, side)
                
                # 最も近いレジスタンス/サポートを利確目標に
                if side == 'BUY' and tech_levels.get('resistance'):
                    nearest_resistance = min(tech_levels['resistance'])
                    if nearest_resistance > entry_price:
                        tp_distance = min(tp_distance, nearest_resistance - entry_price)
                elif side == 'SELL' and tech_levels.get('support'):
                    nearest_support = max(tech_levels['support'])
                    if nearest_support < entry_price:
                        tp_distance = min(tp_distance, entry_price - nearest_support)
            
            if side == 'BUY':
                return entry_price + tp_distance
            else:
                return entry_price - tp_distance
                
        except Exception as e:
            logger.error(f"Failed to calculate trend following TP: {e}")
            # フォールバック
            if side == 'BUY':
                return entry_price * 1.05
            else:
                return entry_price * 0.95
    
    async def _calculate_mean_reversion_tp(self, entry_price: float,
                                         side: str, market_data: Dict) -> float:
        """レンジ相場の利確価格"""
        try:
            # レンジの境界を特定
            symbol = market_data.get('symbol')
            if not symbol:
                # デフォルト値
                if side == 'BUY':
                    return entry_price * 1.015
                else:
                    return entry_price * 0.985
            
            # レンジ境界を取得
            range_data = await self._identify_range_boundaries(symbol)
            
            if side == 'BUY':
                # レンジ上限の少し手前
                range_top = range_data.get('resistance', entry_price * 1.02)
                return range_top * 0.995
            else:
                # レンジ下限の少し手前
                range_bottom = range_data.get('support', entry_price * 0.98)
                return range_bottom * 1.005
                
        except Exception as e:
            logger.error(f"Failed to calculate mean reversion TP: {e}")
            # フォールバック
            if side == 'BUY':
                return entry_price * 1.015
            else:
                return entry_price * 0.985
    
    def _calculate_quick_scalp_tp(self, entry_price: float,
                                side: str, base_strategy: Dict) -> float:
        """素早いスキャルピングの利確価格"""
        # 小さく確実な利確
        multiplier = base_strategy.get('initial_tp_multiplier', 1.015)
        
        if side == 'BUY':
            return entry_price * multiplier
        else:
            return entry_price * (2 - multiplier)
    
    async def _calculate_breakout_tp(self, entry_price: float,
                                   side: str, market_data: Dict) -> float:
        """ブレイクアウト戦略の利確価格"""
        try:
            # ブレイクアウトの測定幅を基に利確目標を設定
            symbol = market_data.get('symbol')
            if symbol:
                # 直近のレンジ幅を取得
                range_data = await self._identify_range_boundaries(symbol)
                range_height = abs(range_data.get('resistance', 0) - 
                                 range_data.get('support', 0))
                
                # ブレイクアウト後は通常レンジ幅の1.5倍を目標
                tp_distance = range_height * 1.5
                
                if side == 'BUY':
                    return entry_price + tp_distance
                else:
                    return entry_price - tp_distance
            else:
                # デフォルト
                if side == 'BUY':
                    return entry_price * 1.04
                else:
                    return entry_price * 0.96
                    
        except Exception as e:
            logger.error(f"Failed to calculate breakout TP: {e}")
            if side == 'BUY':
                return entry_price * 1.04
            else:
                return entry_price * 0.96
    
    def _calculate_volatility_harvest_tp(self, entry_price: float,
                                       side: str, market_data: Dict) -> float:
        """高ボラティリティ収穫戦略の利確価格"""
        # ボラティリティの半分を利確目標に
        atr = market_data.get('atr', entry_price * 0.02)
        
        if side == 'BUY':
            return entry_price + (atr * 0.5)
        else:
            return entry_price - (atr * 0.5)
    
    async def _get_technical_levels(self, symbol: str, 
                                  current_price: float, side: str) -> Dict:
        """テクニカルレベルを取得"""
        try:
            # 1時間足データを取得
            kline_response = self.session.get_kline(
                category="linear",
                symbol=symbol,
                interval="60",
                limit=100
            )
            
            if kline_response["retCode"] != 0:
                return {}
            
            klines = kline_response["result"]["list"]
            
            # サポート/レジスタンスを計算
            highs = [float(k[2]) for k in klines]
            lows = [float(k[3]) for k in klines]
            
            # スイングポイントを特定
            resistance_levels = []
            support_levels = []
            
            for i in range(2, len(highs) - 2):
                # レジスタンス
                if (highs[i] > highs[i-1] and highs[i] > highs[i-2] and
                    highs[i] > highs[i+1] and highs[i] > highs[i+2]):
                    if highs[i] > current_price:
                        resistance_levels.append(highs[i])
                
                # サポート
                if (lows[i] < lows[i-1] and lows[i] < lows[i-2] and
                    lows[i] < lows[i+1] and lows[i] < lows[i+2]):
                    if lows[i] < current_price:
                        support_levels.append(lows[i])
            
            return {
                'resistance': sorted(resistance_levels)[:3],
                'support': sorted(support_levels, reverse=True)[:3]
            }
            
        except Exception as e:
            logger.error(f"Failed to get technical levels: {e}")
            return {}
    
    async def _identify_range_boundaries(self, symbol: str) -> Dict:
        """レンジの境界を特定"""
        try:
            # 4時間足データを使用
            kline_response = self.session.get_kline(
                category="linear",
                symbol=symbol,
                interval="240",
                limit=50
            )
            
            if kline_response["retCode"] != 0:
                return {}
            
            klines = kline_response["result"]["list"]
            
            # 最近20本の高値・安値
            recent_highs = [float(k[2]) for k in klines[:20]]
            recent_lows = [float(k[3]) for k in klines[:20]]
            
            # レンジの上限と下限
            range_top = max(recent_highs)
            range_bottom = min(recent_lows)
            
            # レンジの中心
            range_center = (range_top + range_bottom) / 2
            
            return {
                'resistance': range_top,
                'support': range_bottom,
                'center': range_center,
                'height': range_top - range_bottom
            }
            
        except Exception as e:
            logger.error(f"Failed to identify range boundaries: {e}")
            return {}
    
    def _set_special_conditions(self, market_data: Dict) -> Dict:
        """特殊条件を設定"""
        conditions = {}
        
        # ニュースイベント前後
        if market_data.get('upcoming_news'):
            conditions['news_event'] = True
            conditions['tighten_tp'] = True
        
        # 週末接近
        current_time = datetime.now()
        if current_time.weekday() >= 4:  # 金曜日以降
            conditions['weekend_approaching'] = True
            conditions['reduce_exposure'] = True
        
        # 極端なRSI
        rsi = market_data.get('rsi', 50)
        if rsi > 80 or rsi < 20:
            conditions['extreme_rsi'] = True
            conditions['quick_exit'] = True
        
        # 異常なボリューム
        volume_ratio = market_data.get('volume_ratio', 1.0)
        if volume_ratio > 3.0:
            conditions['abnormal_volume'] = True
            conditions['monitor_closely'] = True
        
        return conditions
    
    def _get_fallback_strategy(self, position: Dict) -> TPStrategy:
        """フォールバック戦略"""
        entry_price = position['entry_price']
        side = position['side']
        
        if side == 'BUY':
            initial_tp = entry_price * 1.02  # 2%利確
        else:
            initial_tp = entry_price * 0.98
        
        return TPStrategy(
            type=TPStrategyType.QUICK_SCALP,
            initial_tp=initial_tp,
            trailing_type='conservative',
            partial_exits=[0.5, 0.3, 0.2],
            extension_allowed=False,
            max_extension=1.0,
            time_limit=None,
            special_conditions={}
        )
    
    def adjust_strategy_realtime(self, current_strategy: TPStrategy,
                               market_update: Dict) -> TPStrategy:
        """リアルタイムで戦略を調整"""
        # 市場状況の急変に対応
        if market_update.get('regime_change'):
            # レジーム変更時は戦略を即座に調整
            logger.info(f"Market regime changed, adjusting strategy")
            current_strategy.trailing_type = 'tight'
            current_strategy.extension_allowed = False
        
        if market_update.get('volatility_spike'):
            # ボラティリティスパイク時
            current_strategy.time_limit = 60  # 1分以内に決済
            current_strategy.partial_exits = [0.8, 0.2]  # 大部分を即決済
        
        return current_strategy