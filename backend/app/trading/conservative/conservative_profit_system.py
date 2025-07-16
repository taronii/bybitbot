"""
慎重モード専用利確システム
段階的な利確とトレーリングストップ機能
"""
import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class ConservativeProfitTarget:
    """慎重モード利確ターゲット"""
    target_price: float
    percentage: float  # ポジションの何%を利確するか
    priority: int      # 実行優先度（1が最高）
    trigger_type: str  # 'PRICE', 'TIME', 'MOMENTUM'
    conditions: Dict   # 追加条件
    description: str   # 表示用の説明

@dataclass
class ProfitLockConfig:
    """利益確保設定"""
    lock_profit_threshold: float  # 利益確保開始閾値（%）
    lock_percentage: float        # 確保する利益の割合
    trailing_distance: float      # トレーリング距離（%）
    min_profit_to_lock: float    # 最低確保利益（%）

class ConservativeProfitSystem:
    """
    慎重モード専用利確システム
    段階的な利確とトレーリングストップで着実に利益を確保
    """
    
    def __init__(self):
        # デフォルト設定
        self.default_profit_config = ProfitLockConfig(
            lock_profit_threshold=0.5,   # 0.5%の利益で利益確保開始
            lock_percentage=0.7,          # 70%の利益を確保
            trailing_distance=0.3,        # 0.3%のトレーリング
            min_profit_to_lock=0.3       # 最低0.3%の利益を確保
        )
        
        # アクティブポジション管理
        self.active_positions: Dict[str, Dict] = {}
        self.profit_targets: Dict[str, List[ConservativeProfitTarget]] = {}
        self.profit_configs: Dict[str, ProfitLockConfig] = {}
        
        # トレーリング管理
        self.trailing_stops: Dict[str, Dict] = {}
        self.highest_profits: Dict[str, float] = {}
        
    async def setup_conservative_profit(
        self,
        position_id: str,
        symbol: str,
        entry_price: float,
        position_size: float,
        direction: str,
        stop_loss: float,
        confidence: float
    ) -> Dict:
        """
        慎重モード利確の設定
        
        Parameters:
        -----------
        position_id : str
            ポジションID
        symbol : str
            シンボル（例: 'BTCUSDT'）
        entry_price : float
            エントリー価格
        position_size : float
            ポジションサイズ（数量）
        direction : str
            方向 ('BUY' or 'SELL')
        stop_loss : float
            ストップロス価格
        confidence : float
            シグナル信頼度
            
        Returns:
        --------
        Dict : 設定結果
        """
        try:
            # ポジション情報を保存
            self.active_positions[position_id] = {
                'symbol': symbol,
                'entry_price': entry_price,
                'position_size': position_size,
                'direction': direction,
                'stop_loss': stop_loss,
                'entry_time': datetime.now(),
                'confidence': confidence,
                'current_profit': 0.0,
                'max_profit': 0.0,
                'profit_locked': 0.0,
                'remaining_size': position_size
            }
            
            # リスクリワード比を計算
            risk_amount = abs(entry_price - stop_loss)
            
            # 利確ターゲットを作成（慎重モード用の保守的な設定）
            targets = []
            
            if direction == 'BUY':
                # レベル1: 1:1のリスクリワード（50%決済）
                tp1 = entry_price + risk_amount * 1.0
                targets.append(ConservativeProfitTarget(
                    target_price=tp1,
                    percentage=0.5,
                    priority=1,
                    trigger_type='PRICE',
                    conditions={},
                    description=f"利確レベル1: {tp1:.2f} (リスクリワード 1:1)"
                ))
                
                # レベル2: 1:2のリスクリワード（30%決済）
                tp2 = entry_price + risk_amount * 2.0
                targets.append(ConservativeProfitTarget(
                    target_price=tp2,
                    percentage=0.3,
                    priority=2,
                    trigger_type='PRICE',
                    conditions={},
                    description=f"利確レベル2: {tp2:.2f} (リスクリワード 1:2)"
                ))
                
                # レベル3: 1:3のリスクリワード（残り20%決済）
                tp3 = entry_price + risk_amount * 3.0
                targets.append(ConservativeProfitTarget(
                    target_price=tp3,
                    percentage=0.2,
                    priority=3,
                    trigger_type='PRICE',
                    conditions={},
                    description=f"利確レベル3: {tp3:.2f} (リスクリワード 1:3)"
                ))
                
            else:  # SELL
                # レベル1: 1:1のリスクリワード（50%決済）
                tp1 = entry_price - risk_amount * 1.0
                targets.append(ConservativeProfitTarget(
                    target_price=tp1,
                    percentage=0.5,
                    priority=1,
                    trigger_type='PRICE',
                    conditions={},
                    description=f"利確レベル1: {tp1:.2f} (リスクリワード 1:1)"
                ))
                
                # レベル2: 1:2のリスクリワード（30%決済）
                tp2 = entry_price - risk_amount * 2.0
                targets.append(ConservativeProfitTarget(
                    target_price=tp2,
                    percentage=0.3,
                    priority=2,
                    trigger_type='PRICE',
                    conditions={},
                    description=f"利確レベル2: {tp2:.2f} (リスクリワード 1:2)"
                ))
                
                # レベル3: 1:3のリスクリワード（残り20%決済）
                tp3 = entry_price - risk_amount * 3.0
                targets.append(ConservativeProfitTarget(
                    target_price=tp3,
                    percentage=0.2,
                    priority=3,
                    trigger_type='PRICE',
                    conditions={},
                    description=f"利確レベル3: {tp3:.2f} (リスクリワード 1:3)"
                ))
            
            self.profit_targets[position_id] = targets
            
            # 信頼度に基づいて利益確保設定を調整
            config = ProfitLockConfig(
                lock_profit_threshold=0.5 if confidence > 0.7 else 0.8,
                lock_percentage=0.8 if confidence > 0.7 else 0.7,
                trailing_distance=0.3 if confidence > 0.7 else 0.4,
                min_profit_to_lock=0.3 if confidence > 0.7 else 0.5
            )
            self.profit_configs[position_id] = config
            
            # トレーリングストップの初期化
            self.trailing_stops[position_id] = {
                'active': False,
                'stop_price': stop_loss,
                'locked_profit': 0.0
            }
            self.highest_profits[position_id] = 0.0
            
            logger.info(f"Conservative profit setup completed for {position_id}")
            
            return {
                'success': True,
                'position_id': position_id,
                'profit_targets': len(targets),
                'initial_stop_loss': stop_loss,
                'profit_lock_config': {
                    'threshold': config.lock_profit_threshold,
                    'lock_percentage': config.lock_percentage,
                    'trailing_distance': config.trailing_distance
                }
            }
            
        except Exception as e:
            logger.error(f"Conservative profit setup failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def check_profit_conditions(
        self,
        position_id: str,
        current_price: float,
        market_data: Dict
    ) -> Dict:
        """
        利確条件のチェック
        
        Parameters:
        -----------
        position_id : str
            ポジションID
        current_price : float
            現在価格
        market_data : Dict
            市場データ
            
        Returns:
        --------
        Dict : 利確アクション
        """
        if position_id not in self.active_positions:
            return {'action': 'NONE', 'reason': 'Position not found'}
        
        try:
            position = self.active_positions[position_id]
            targets = self.profit_targets[position_id]
            config = self.profit_configs[position_id]
            
            # 現在の利益率を計算
            entry_price = position['entry_price']
            direction = position['direction']
            
            if direction == 'BUY':
                current_profit = ((current_price - entry_price) / entry_price) * 100
            else:
                current_profit = ((entry_price - current_price) / entry_price) * 100
            
            position['current_profit'] = current_profit
            position['max_profit'] = max(position['max_profit'], current_profit)
            self.highest_profits[position_id] = position['max_profit']
            
            # トレーリングストップのチェック
            trailing_action = await self._check_trailing_stop(
                position_id, current_price, current_profit, config
            )
            if trailing_action['action'] != 'NONE':
                return trailing_action
            
            # 通常の利確ターゲットのチェック
            for target in sorted(targets, key=lambda x: x.priority):
                if self._is_target_reached(target, current_price, direction):
                    # 利確実行
                    take_profit_size = position['remaining_size'] * target.percentage
                    
                    return {
                        'action': 'TAKE_PROFIT',
                        'price': current_price,
                        'target_price': target.target_price,
                        'size': take_profit_size,
                        'percentage': target.percentage,
                        'priority': target.priority,
                        'current_profit': current_profit,
                        'description': target.description,
                        'reason': f"{target.description} に到達"
                    }
            
            return {'action': 'NONE', 'reason': 'No profit targets reached'}
            
        except Exception as e:
            logger.error(f"Profit conditions check failed: {e}")
            return {'action': 'NONE', 'error': str(e)}
    
    async def _check_trailing_stop(
        self,
        position_id: str,
        current_price: float,
        current_profit: float,
        config: ProfitLockConfig
    ) -> Dict:
        """トレーリングストップのチェック"""
        try:
            position = self.active_positions[position_id]
            trailing = self.trailing_stops[position_id]
            direction = position['direction']
            
            # トレーリングストップの開始条件
            if current_profit >= config.lock_profit_threshold and not trailing['active']:
                trailing['active'] = True
                trailing['locked_profit'] = current_profit * config.lock_percentage
                
                # トレーリングストップ価格を設定
                if direction == 'BUY':
                    trailing['stop_price'] = current_price * (1 - config.trailing_distance / 100)
                else:
                    trailing['stop_price'] = current_price * (1 + config.trailing_distance / 100)
                
                logger.info(f"Trailing stop activated for {position_id} at profit {current_profit:.2f}%")
            
            # トレーリングストップの更新
            elif trailing['active'] and current_profit > self.highest_profits[position_id]:
                # 新高値更新時にトレーリングストップを引き上げ
                if direction == 'BUY':
                    new_stop = current_price * (1 - config.trailing_distance / 100)
                    if new_stop > trailing['stop_price']:
                        trailing['stop_price'] = new_stop
                        trailing['locked_profit'] = (current_profit - config.trailing_distance) * config.lock_percentage
                else:
                    new_stop = current_price * (1 + config.trailing_distance / 100)
                    if new_stop < trailing['stop_price']:
                        trailing['stop_price'] = new_stop
                        trailing['locked_profit'] = (current_profit - config.trailing_distance) * config.lock_percentage
            
            # トレーリングストップのトリガーチェック
            if trailing['active']:
                triggered = False
                if direction == 'BUY':
                    triggered = current_price <= trailing['stop_price']
                else:
                    triggered = current_price >= trailing['stop_price']
                
                if triggered:
                    return {
                        'action': 'TRAILING_STOP',
                        'price': current_price,
                        'stop_price': trailing['stop_price'],
                        'size': position['remaining_size'],
                        'locked_profit': trailing['locked_profit'],
                        'current_profit': current_profit,
                        'max_profit': self.highest_profits[position_id],
                        'description': f"トレーリングストップ: {trailing['stop_price']:.2f}",
                        'reason': 'トレーリングストップ発動'
                    }
            
            return {'action': 'NONE'}
            
        except Exception as e:
            logger.error(f"Trailing stop check failed: {e}")
            return {'action': 'NONE', 'error': str(e)}
    
    def _is_target_reached(self, target: ConservativeProfitTarget, current_price: float, direction: str) -> bool:
        """利確ターゲットに到達したかチェック"""
        if target.trigger_type == 'PRICE':
            if direction == 'BUY':
                return current_price >= target.target_price
            else:
                return current_price <= target.target_price
        return False
    
    def get_profit_targets(self, position_id: str) -> List[Dict]:
        """ポジションの利確ターゲットを取得"""
        targets = self.profit_targets.get(position_id, [])
        position = self.active_positions.get(position_id, {})
        result = []
        
        for target in targets:
            result.append({
                "price": target.target_price,
                "percentage": target.percentage * 100,
                "priority": target.priority,
                "trigger_type": target.trigger_type,
                "description": target.description
            })
        
        # トレーリングストップ情報も追加
        if position_id in self.trailing_stops:
            trailing = self.trailing_stops[position_id]
            if trailing['active']:
                result.append({
                    "price": trailing['stop_price'],
                    "percentage": 100,  # 全量決済
                    "priority": 0,  # 最高優先度
                    "trigger_type": "TRAILING",
                    "description": f"トレーリングストップ: {trailing['stop_price']:.2f} (利益確保 {trailing['locked_profit']:.2f}%)"
                })
        
        return result
    
    def get_position_info(self, position_id: str) -> Optional[Dict]:
        """ポジション情報の取得"""
        if position_id not in self.active_positions:
            return None
        
        position = self.active_positions[position_id]
        trailing = self.trailing_stops.get(position_id, {})
        
        return {
            'symbol': position['symbol'],
            'entry_price': position['entry_price'],
            'direction': position['direction'],
            'position_size': position['position_size'],
            'remaining_size': position['remaining_size'],
            'current_profit': position['current_profit'],
            'max_profit': position['max_profit'],
            'profit_locked': position['profit_locked'],
            'trailing_stop': {
                'active': trailing.get('active', False),
                'stop_price': trailing.get('stop_price', 0),
                'locked_profit': trailing.get('locked_profit', 0)
            } if trailing else None
        }
    
    def cleanup_position(self, position_id: str) -> bool:
        """ポジション情報のクリーンアップ"""
        try:
            if position_id in self.active_positions:
                del self.active_positions[position_id]
            if position_id in self.profit_targets:
                del self.profit_targets[position_id]
            if position_id in self.profit_configs:
                del self.profit_configs[position_id]
            if position_id in self.trailing_stops:
                del self.trailing_stops[position_id]
            if position_id in self.highest_profits:
                del self.highest_profits[position_id]
            
            logger.info(f"Conservative profit cleanup completed: {position_id}")
            return True
            
        except Exception as e:
            logger.error(f"Conservative profit cleanup failed: {e}")
            return False
    
    def get_all_positions(self) -> Dict:
        """全ポジション情報の取得"""
        return {
            'positions': self.active_positions.copy(),
            'count': len(self.active_positions)
        }

# グローバルインスタンス
conservative_profit_system = ConservativeProfitSystem()