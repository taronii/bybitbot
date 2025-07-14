"""
超高速利確システム
スキャルピング専用の高速利確とトレーリング機能
"""
import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class RapidProfitTarget:
    """高速利確ターゲット"""
    target_price: float
    percentage: float  # ポジションの何%を利確するか
    priority: int  # 優先度（1が最高）
    trigger_type: str  # 'PRICE', 'TIME', 'VOLUME', 'MOMENTUM'
    conditions: Dict  # 追加条件
    is_active: bool = True

@dataclass
class TrailingConfig:
    """トレーリング設定"""
    activation_profit: float  # トレーリング開始利益（%）
    trail_distance: float  # トレーリング距離（%）
    max_trail_distance: float  # 最大トレーリング距離（%）
    acceleration_factor: float  # 加速係数
    time_decay_factor: float  # 時間減衰係数

@dataclass
class ProfitProtection:
    """利益保護設定"""
    min_profit_lock: float  # 最小利益固定（%）
    breakeven_time: int  # 損益分岐点までの時間（秒）
    profit_steps: List[Tuple[float, float]]  # (利益%, 保護%)のリスト

class RapidProfitSystem:
    """
    超高速利確システム
    スキャルピング専用の高速利確とトレーリング機能
    """
    
    def __init__(self):
        # 基本設定
        self.quick_profit_targets = [0.2, 0.3, 0.5]  # 高速利確目標（%）
        self.partial_profit_ratios = [0.5, 0.3, 0.2]  # 部分利確比率
        self.max_holding_time = 600  # 最大保有時間（秒）
        
        # アクティブポジション管理
        self.active_positions: Dict[str, Dict] = {}
        self.profit_targets: Dict[str, List[RapidProfitTarget]] = {}
        self.trailing_configs: Dict[str, TrailingConfig] = {}
        
    async def setup_rapid_profit(
        self,
        position_id: str,
        entry_price: float,
        position_size: float,
        direction: str,
        expected_duration: int,
        confidence: float
    ) -> Dict:
        """
        高速利確の設定
        
        Parameters:
        -----------
        position_id : str
            ポジションID
        entry_price : float
            エントリー価格
        position_size : float
            ポジションサイズ
        direction : str
            方向 ('BUY' or 'SELL')
        expected_duration : int
            予想保有時間（分）
        confidence : float
            シグナル信頼度
            
        Returns:
        --------
        Dict : 設定結果
        """
        try:
            # ポジション情報を記録
            self.active_positions[position_id] = {
                'entry_price': entry_price,
                'position_size': position_size,
                'direction': direction,
                'entry_time': datetime.now(),
                'expected_duration': expected_duration,
                'confidence': confidence,
                'current_profit': 0.0,
                'max_profit': 0.0,
                'profit_locked': 0.0,
                'remaining_size': position_size
            }
            
            # 高速利確ターゲットの設定
            profit_targets = await self._create_profit_targets(
                entry_price, direction, confidence, expected_duration
            )
            self.profit_targets[position_id] = profit_targets
            
            # トレーリング設定
            trailing_config = await self._create_trailing_config(
                confidence, expected_duration
            )
            self.trailing_configs[position_id] = trailing_config
            
            logger.info(f"Rapid profit setup completed for {position_id}")
            
            return {
                'success': True,
                'position_id': position_id,
                'profit_targets': len(profit_targets),
                'trailing_enabled': True,
                'max_holding_time': self.max_holding_time
            }
            
        except Exception as e:
            logger.error(f"Rapid profit setup failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def update_profit_status(
        self,
        position_id: str,
        current_price: float,
        current_volume: float,
        market_momentum: float
    ) -> Dict:
        """
        利確状況の更新とシグナル生成
        
        Parameters:
        -----------
        position_id : str
            ポジションID
        current_price : float
            現在価格
        current_volume : float
            現在ボリューム
        market_momentum : float
            市場モメンタム
            
        Returns:
        --------
        Dict : 利確アクション
        """
        if position_id not in self.active_positions:
            return {'action': 'NONE', 'reason': 'Position not found'}
        
        try:
            position = self.active_positions[position_id]
            entry_price = position['entry_price']
            direction = position['direction']
            
            # 現在の利益計算
            if direction == 'BUY':
                profit_percent = ((current_price - entry_price) / entry_price) * 100
            else:
                profit_percent = ((entry_price - current_price) / entry_price) * 100
            
            position['current_profit'] = profit_percent
            position['max_profit'] = max(position['max_profit'], profit_percent)
            
            # 時間チェック
            hold_time = (datetime.now() - position['entry_time']).total_seconds()
            if hold_time > self.max_holding_time:
                return await self._force_close_position(position_id, 'Time limit exceeded')
            
            # 利確ターゲットチェック
            target_action = await self._check_profit_targets(
                position_id, current_price, profit_percent, current_volume, market_momentum
            )
            
            if target_action['action'] != 'NONE':
                return target_action
            
            # トレーリングストップチェック
            trailing_action = await self._check_trailing_stop(
                position_id, current_price, profit_percent
            )
            
            if trailing_action['action'] != 'NONE':
                return trailing_action
            
            # 利益保護チェック
            protection_action = await self._check_profit_protection(
                position_id, profit_percent, hold_time
            )
            
            return protection_action
            
        except Exception as e:
            logger.error(f"Profit status update failed: {e}")
            return {'action': 'NONE', 'error': str(e)}
    
    async def _create_profit_targets(
        self,
        entry_price: float,
        direction: str,
        confidence: float,
        expected_duration: int
    ) -> List[RapidProfitTarget]:
        """利確ターゲットの作成"""
        targets = []
        
        try:
            # 信頼度に基づく利確目標調整
            confidence_multiplier = 0.5 + (confidence * 0.5)  # 0.5-1.0
            adjusted_targets = [target * confidence_multiplier for target in self.quick_profit_targets]
            
            # 期間に基づく調整
            if expected_duration <= 3:  # 3分以下
                time_multiplier = 1.2  # より積極的
            elif expected_duration <= 5:  # 5分以下
                time_multiplier = 1.0
            else:
                time_multiplier = 0.8  # より保守的
            
            for i, (target_percent, ratio) in enumerate(zip(adjusted_targets, self.partial_profit_ratios)):
                target_percent *= time_multiplier
                
                if direction == 'BUY':
                    target_price = entry_price * (1 + target_percent / 100)
                else:
                    target_price = entry_price * (1 - target_percent / 100)
                
                targets.append(RapidProfitTarget(
                    target_price=target_price,
                    percentage=ratio,
                    priority=i + 1,
                    trigger_type='PRICE',
                    conditions={
                        'min_volume_ratio': 0.8,  # 最小ボリューム比率
                        'momentum_threshold': 0.3  # モメンタム閾値
                    }
                ))
            
            # 時間ベース利確も追加
            time_target_percent = min(adjusted_targets) * 0.7  # 最小目標の70%
            if direction == 'BUY':
                time_target_price = entry_price * (1 + time_target_percent / 100)
            else:
                time_target_price = entry_price * (1 - time_target_percent / 100)
            
            targets.append(RapidProfitTarget(
                target_price=time_target_price,
                percentage=0.8,  # 80%利確
                priority=0,  # 最高優先度
                trigger_type='TIME',
                conditions={
                    'min_hold_time': expected_duration * 60 * 0.8  # 予想時間の80%
                }
            ))
            
            return targets
            
        except Exception as e:
            logger.error(f"Profit targets creation failed: {e}")
            return []
    
    async def _create_trailing_config(
        self,
        confidence: float,
        expected_duration: int
    ) -> TrailingConfig:
        """トレーリング設定の作成"""
        try:
            # 信頼度に基づくトレーリング調整
            base_activation = 0.15  # 0.15%で開始
            base_trail_distance = 0.08  # 0.08%のトレーリング距離
            
            # 高信頼度ほど早期にトレーリング開始
            activation_profit = base_activation * (2.0 - confidence)
            
            # 短期間ほどタイトなトレーリング
            if expected_duration <= 3:
                trail_distance = base_trail_distance * 0.8
                max_trail_distance = base_trail_distance * 1.5
            elif expected_duration <= 5:
                trail_distance = base_trail_distance
                max_trail_distance = base_trail_distance * 2.0
            else:
                trail_distance = base_trail_distance * 1.2
                max_trail_distance = base_trail_distance * 2.5
            
            return TrailingConfig(
                activation_profit=activation_profit,
                trail_distance=trail_distance,
                max_trail_distance=max_trail_distance,
                acceleration_factor=1.1,  # 利益が増えるほど加速
                time_decay_factor=0.95   # 時間経過で減衰
            )
            
        except Exception as e:
            logger.error(f"Trailing config creation failed: {e}")
            return TrailingConfig(0.15, 0.08, 0.2, 1.0, 1.0)
    
    async def _check_profit_targets(
        self,
        position_id: str,
        current_price: float,
        profit_percent: float,
        current_volume: float,
        market_momentum: float
    ) -> Dict:
        """利確ターゲットのチェック"""
        if position_id not in self.profit_targets:
            return {'action': 'NONE', 'reason': 'No targets'}
        
        try:
            position = self.active_positions[position_id]
            targets = self.profit_targets[position_id]
            hold_time = (datetime.now() - position['entry_time']).total_seconds()
            
            for target in targets:
                if not target.is_active:
                    continue
                
                triggered = False
                
                # 価格ベーストリガー
                if target.trigger_type == 'PRICE':
                    if position['direction'] == 'BUY':
                        triggered = current_price >= target.target_price
                    else:
                        triggered = current_price <= target.target_price
                    
                    # 追加条件チェック
                    if triggered and 'min_volume_ratio' in target.conditions:
                        # ボリューム条件（実装簡略化）
                        triggered = triggered and current_volume > 0
                    
                    if triggered and 'momentum_threshold' in target.conditions:
                        triggered = triggered and market_momentum > target.conditions['momentum_threshold']
                
                # 時間ベーストリガー
                elif target.trigger_type == 'TIME':
                    triggered = (
                        hold_time >= target.conditions.get('min_hold_time', 0) and
                        profit_percent > 0  # 利益が出ている
                    )
                
                if triggered:
                    # 部分利確実行
                    profit_size = position['remaining_size'] * target.percentage
                    position['remaining_size'] -= profit_size
                    position['profit_locked'] += profit_percent * target.percentage
                    
                    target.is_active = False  # このターゲットを無効化
                    
                    logger.info(f"Profit target triggered: {position_id}, {target.percentage*100:.0f}% at {profit_percent:.2f}%")
                    
                    return {
                        'action': 'PARTIAL_CLOSE',
                        'percentage': target.percentage,
                        'price': current_price,
                        'profit_percent': profit_percent,
                        'reason': f'{target.trigger_type} target reached',
                        'remaining_size': position['remaining_size']
                    }
            
            return {'action': 'NONE', 'reason': 'No targets triggered'}
            
        except Exception as e:
            logger.error(f"Profit targets check failed: {e}")
            return {'action': 'NONE', 'error': str(e)}
    
    async def _check_trailing_stop(
        self,
        position_id: str,
        current_price: float,
        profit_percent: float
    ) -> Dict:
        """トレーリングストップのチェック"""
        if position_id not in self.trailing_configs:
            return {'action': 'NONE', 'reason': 'No trailing config'}
        
        try:
            position = self.active_positions[position_id]
            config = self.trailing_configs[position_id]
            
            # トレーリング開始条件
            if profit_percent < config.activation_profit:
                return {'action': 'NONE', 'reason': 'Trailing not activated'}
            
            # 最大利益からの下落をチェック
            max_profit = position['max_profit']
            drawdown_from_peak = max_profit - profit_percent
            
            # 時間経過による減衰を考慮
            hold_time = (datetime.now() - position['entry_time']).total_seconds()
            time_factor = config.time_decay_factor ** (hold_time / 60)  # 分単位
            
            # 動的トレーリング距離
            current_trail_distance = min(
                config.max_trail_distance,
                config.trail_distance * (1 + max_profit * config.acceleration_factor) * time_factor
            )
            
            # トレーリングストップ判定
            if drawdown_from_peak > current_trail_distance:
                logger.info(f"Trailing stop triggered: {position_id}, drawdown: {drawdown_from_peak:.2f}%")
                
                return {
                    'action': 'FULL_CLOSE',
                    'price': current_price,
                    'profit_percent': profit_percent,
                    'max_profit': max_profit,
                    'drawdown': drawdown_from_peak,
                    'reason': 'Trailing stop triggered'
                }
            
            return {'action': 'NONE', 'reason': 'Trailing stop not triggered'}
            
        except Exception as e:
            logger.error(f"Trailing stop check failed: {e}")
            return {'action': 'NONE', 'error': str(e)}
    
    async def _check_profit_protection(
        self,
        position_id: str,
        profit_percent: float,
        hold_time: float
    ) -> Dict:
        """利益保護のチェック"""
        try:
            position = self.active_positions[position_id]
            
            # 損益分岐点までの時間チェック
            if profit_percent < 0 and hold_time > 120:  # 2分経過で損失
                return {
                    'action': 'FULL_CLOSE',
                    'price': 0,  # 現在価格で終了
                    'profit_percent': profit_percent,
                    'reason': 'Stop loss protection (time + loss)'
                }
            
            # 段階的利益保護
            protection_steps = [
                (0.3, 0.1),   # 0.3%利益で0.1%保護
                (0.5, 0.2),   # 0.5%利益で0.2%保護
                (0.8, 0.4),   # 0.8%利益で0.4%保護
            ]
            
            for profit_threshold, protection_level in protection_steps:
                if position['max_profit'] > profit_threshold and profit_percent < protection_level:
                    return {
                        'action': 'FULL_CLOSE',
                        'price': 0,
                        'profit_percent': profit_percent,
                        'max_profit': position['max_profit'],
                        'reason': f'Profit protection at {protection_level}%'
                    }
            
            return {'action': 'NONE', 'reason': 'No protection triggered'}
            
        except Exception as e:
            logger.error(f"Profit protection check failed: {e}")
            return {'action': 'NONE', 'error': str(e)}
    
    async def _force_close_position(self, position_id: str, reason: str) -> Dict:
        """強制ポジションクローズ"""
        try:
            position = self.active_positions[position_id]
            
            logger.warning(f"Force closing position {position_id}: {reason}")
            
            return {
                'action': 'FULL_CLOSE',
                'price': 0,  # 市場価格で終了
                'profit_percent': position['current_profit'],
                'reason': reason,
                'force_close': True
            }
            
        except Exception as e:
            logger.error(f"Force close failed: {e}")
            return {'action': 'NONE', 'error': str(e)}
    
    def cleanup_position(self, position_id: str) -> bool:
        """ポジション情報のクリーンアップ"""
        try:
            if position_id in self.active_positions:
                del self.active_positions[position_id]
            if position_id in self.profit_targets:
                del self.profit_targets[position_id]
            if position_id in self.trailing_configs:
                del self.trailing_configs[position_id]
            
            logger.info(f"Position cleaned up: {position_id}")
            return True
            
        except Exception as e:
            logger.error(f"Position cleanup failed: {e}")
            return False
    
    def get_position_status(self, position_id: str) -> Optional[Dict]:
        """ポジション状況の取得"""
        return self.active_positions.get(position_id)
    
    def get_all_positions(self) -> Dict:
        """全ポジション情報の取得"""
        return {
            'active_positions': len(self.active_positions),
            'positions': self.active_positions
        }
    
    def get_profit_targets(self, position_id: str) -> List[Dict]:
        """ポジションの利確ターゲットを取得"""
        targets = self.profit_targets.get(position_id, [])
        result = []
        
        for target in targets:
            if target.is_active:
                result.append({
                    "price": target.target_price,
                    "percentage": target.percentage,
                    "type": target.trigger_type,
                    "priority": target.priority,
                    "description": f"利確レベル{target.priority}: {target.target_price:.2f} ({target.percentage*100:.0f}%)"
                })
        
        return result

# グローバルインスタンス
rapid_profit_system = RapidProfitSystem()