"""
慎重モード専用損切りシステム
保守的な損切りとリスク管理
"""
import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class ConservativeStopLevel:
    """慎重モード損切りレベル"""
    level_name: str
    stop_price: float
    trigger_conditions: List[str]
    priority: int  # 1が最高優先度
    is_active: bool = True
    description: str = ""

@dataclass
class ConservativeStopConfig:
    """慎重モード損切り設定"""
    initial_stop_percent: float      # 初期ストップロス（%）
    max_loss_percent: float          # 最大損失（%）
    time_stop_hours: int            # 時間ストップ（時間）
    breakeven_move_percent: float   # ブレークイーブン移動条件（%）
    partial_stop_percent: float     # 部分損切り開始（%）

class ConservativeStopSystem:
    """
    慎重モード専用損切りシステム
    保守的なリスク管理で資産を保護
    """
    
    def __init__(self):
        # デフォルト設定（慎重モード用の保守的な設定）
        self.default_config = ConservativeStopConfig(
            initial_stop_percent=2.0,      # 2%の初期ストップ
            max_loss_percent=3.0,          # 最大3%の損失
            time_stop_hours=24,            # 24時間の時間制限
            breakeven_move_percent=1.0,    # 1%の利益でブレークイーブンへ
            partial_stop_percent=1.5       # 1.5%の損失で部分損切り
        )
        
        # アクティブストップ管理
        self.active_stops: Dict[str, List[ConservativeStopLevel]] = {}
        self.stop_configs: Dict[str, ConservativeStopConfig] = {}
        
        # ポジション情報管理
        self.active_positions: Dict[str, Dict] = {}
        
        # ブレークイーブン管理
        self.breakeven_moved: Dict[str, bool] = {}
        
    async def setup_conservative_stops(
        self,
        position_id: str,
        symbol: str,
        entry_price: float,
        direction: str,
        position_size: float,
        initial_stop_loss: float,
        confidence: float
    ) -> Dict:
        """
        慎重モード損切りの設定
        
        Parameters:
        -----------
        position_id : str
            ポジションID
        symbol : str
            シンボル（例: 'BTCUSDT'）
        entry_price : float
            エントリー価格
        direction : str
            方向 ('BUY' or 'SELL')
        position_size : float
            ポジションサイズ
        initial_stop_loss : float
            初期ストップロス価格
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
                'direction': direction,
                'position_size': position_size,
                'entry_time': datetime.now(),
                'confidence': confidence,
                'initial_stop_loss': initial_stop_loss
            }
            
            # 信頼度に基づく設定調整
            config = await self._create_custom_config(confidence)
            self.stop_configs[position_id] = config
            
            # 損切りレベルの作成
            stop_levels = await self._create_stop_levels(
                entry_price, direction, initial_stop_loss, config
            )
            self.active_stops[position_id] = stop_levels
            
            # ブレークイーブン管理の初期化
            self.breakeven_moved[position_id] = False
            
            logger.info(f"Conservative stops setup completed for {position_id}")
            
            return {
                'success': True,
                'position_id': position_id,
                'stop_levels': len(stop_levels),
                'initial_stop_loss': initial_stop_loss,
                'config': {
                    'initial_stop': config.initial_stop_percent,
                    'max_loss': config.max_loss_percent,
                    'time_stop': config.time_stop_hours,
                    'breakeven_move': config.breakeven_move_percent
                }
            }
            
        except Exception as e:
            logger.error(f"Conservative stops setup failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def check_stop_conditions(
        self,
        position_id: str,
        current_price: float,
        market_data: Dict
    ) -> Dict:
        """
        損切り条件のチェック
        
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
        Dict : 損切りアクション
        """
        if position_id not in self.active_positions:
            return {'action': 'NONE', 'reason': 'Position not found'}
        
        try:
            position = self.active_positions[position_id]
            config = self.stop_configs[position_id]
            
            # 現在の損益を計算
            entry_price = position['entry_price']
            direction = position['direction']
            
            if direction == 'BUY':
                current_pnl = ((current_price - entry_price) / entry_price) * 100
            else:
                current_pnl = ((entry_price - current_price) / entry_price) * 100
            
            # ブレークイーブンチェック
            breakeven_action = await self._check_breakeven_move(
                position_id, current_price, current_pnl, config
            )
            if breakeven_action['action'] != 'NONE':
                return breakeven_action
            
            # 通常の損切りレベルチェック
            stop_action = await self._check_stop_levels(
                position_id, current_price, current_pnl
            )
            if stop_action['action'] != 'NONE':
                return stop_action
            
            # 時間ベース損切りチェック
            time_action = await self._check_time_stop(position_id, config)
            if time_action['action'] != 'NONE':
                return time_action
            
            # 部分損切りチェック
            partial_action = await self._check_partial_stop(
                position_id, current_pnl, config
            )
            
            return partial_action
            
        except Exception as e:
            logger.error(f"Stop conditions check failed: {e}")
            return {'action': 'NONE', 'error': str(e)}
    
    async def _create_custom_config(self, confidence: float) -> ConservativeStopConfig:
        """信頼度に基づくカスタム設定の作成"""
        try:
            # 高信頼度ほど少し広めのストップ（長期保有を許容）
            if confidence > 0.8:
                return ConservativeStopConfig(
                    initial_stop_percent=2.5,
                    max_loss_percent=3.5,
                    time_stop_hours=48,
                    breakeven_move_percent=0.8,
                    partial_stop_percent=2.0
                )
            elif confidence > 0.6:
                return ConservativeStopConfig(
                    initial_stop_percent=2.0,
                    max_loss_percent=3.0,
                    time_stop_hours=24,
                    breakeven_move_percent=1.0,
                    partial_stop_percent=1.5
                )
            else:
                # 低信頼度はより厳格なストップ
                return ConservativeStopConfig(
                    initial_stop_percent=1.5,
                    max_loss_percent=2.5,
                    time_stop_hours=12,
                    breakeven_move_percent=1.2,
                    partial_stop_percent=1.0
                )
                
        except Exception as e:
            logger.error(f"Custom config creation failed: {e}")
            return self.default_config
    
    async def _create_stop_levels(
        self,
        entry_price: float,
        direction: str,
        initial_stop: float,
        config: ConservativeStopConfig
    ) -> List[ConservativeStopLevel]:
        """損切りレベルの作成"""
        levels = []
        
        try:
            # レベル1: 初期ストップロス（シグナルベース）
            levels.append(ConservativeStopLevel(
                level_name='初期ストップ',
                stop_price=initial_stop,
                trigger_conditions=['PRICE'],
                priority=2,
                description=f"初期ストップ: {initial_stop:.2f}"
            ))
            
            # レベル2: 最大損失ストップ
            if direction == 'BUY':
                max_loss_price = entry_price * (1 - config.max_loss_percent / 100)
            else:
                max_loss_price = entry_price * (1 + config.max_loss_percent / 100)
            
            levels.append(ConservativeStopLevel(
                level_name='最大損失ストップ',
                stop_price=max_loss_price,
                trigger_conditions=['PRICE', 'EMERGENCY'],
                priority=1,
                description=f"最大損失ストップ: {max_loss_price:.2f} (-{config.max_loss_percent}%)"
            ))
            
            # レベル3: 時間ストップ（価格無関係）
            levels.append(ConservativeStopLevel(
                level_name='時間ストップ',
                stop_price=0.0,  # 市場価格で決済
                trigger_conditions=['TIME'],
                priority=3,
                description=f"時間ストップ: {config.time_stop_hours}時間後"
            ))
            
            return levels
            
        except Exception as e:
            logger.error(f"Stop levels creation failed: {e}")
            return []
    
    async def _check_breakeven_move(
        self,
        position_id: str,
        current_price: float,
        current_pnl: float,
        config: ConservativeStopConfig
    ) -> Dict:
        """ブレークイーブンへの移動チェック"""
        try:
            if self.breakeven_moved[position_id]:
                return {'action': 'NONE'}
            
            # 利益が指定％を超えたらストップをブレークイーブンに移動
            if current_pnl >= config.breakeven_move_percent:
                position = self.active_positions[position_id]
                entry_price = position['entry_price']
                direction = position['direction']
                
                # 手数料分を考慮して少し有利な位置に設定
                if direction == 'BUY':
                    new_stop = entry_price * 1.001  # 0.1%の利益確保
                else:
                    new_stop = entry_price * 0.999  # 0.1%の利益確保
                
                # 既存のストップレベルを更新
                for level in self.active_stops[position_id]:
                    if level.level_name == '初期ストップ':
                        level.stop_price = new_stop
                        level.description = f"ブレークイーブンストップ: {new_stop:.2f}"
                
                self.breakeven_moved[position_id] = True
                
                logger.info(f"Stop moved to breakeven for {position_id}")
                
                return {
                    'action': 'UPDATE_STOP',
                    'new_stop_price': new_stop,
                    'reason': 'ブレークイーブンへストップ移動',
                    'current_profit': current_pnl
                }
            
            return {'action': 'NONE'}
            
        except Exception as e:
            logger.error(f"Breakeven check failed: {e}")
            return {'action': 'NONE', 'error': str(e)}
    
    async def _check_stop_levels(
        self,
        position_id: str,
        current_price: float,
        current_pnl: float
    ) -> Dict:
        """通常の損切りレベルチェック"""
        try:
            stop_levels = self.active_stops[position_id]
            position = self.active_positions[position_id]
            direction = position['direction']
            
            for level in sorted(stop_levels, key=lambda x: x.priority):
                if not level.is_active or level.stop_price == 0.0:
                    continue
                
                triggered = False
                
                if 'PRICE' in level.trigger_conditions:
                    if direction == 'BUY':
                        triggered = current_price <= level.stop_price
                    else:
                        triggered = current_price >= level.stop_price
                
                if triggered:
                    return {
                        'action': 'STOP_LOSS',
                        'price': current_price,
                        'stop_price': level.stop_price,
                        'level_name': level.level_name,
                        'loss_percent': abs(current_pnl),
                        'description': level.description,
                        'reason': f"{level.level_name}に到達"
                    }
            
            return {'action': 'NONE'}
            
        except Exception as e:
            logger.error(f"Stop levels check failed: {e}")
            return {'action': 'NONE', 'error': str(e)}
    
    async def _check_time_stop(
        self,
        position_id: str,
        config: ConservativeStopConfig
    ) -> Dict:
        """時間ベース損切りチェック"""
        try:
            position = self.active_positions[position_id]
            entry_time = position['entry_time']
            
            time_held = (datetime.now() - entry_time).total_seconds() / 3600  # 時間単位
            
            if time_held >= config.time_stop_hours:
                return {
                    'action': 'TIME_STOP',
                    'price': 0.0,  # 市場価格
                    'time_held_hours': time_held,
                    'max_time_hours': config.time_stop_hours,
                    'description': f"時間制限超過: {time_held:.1f}時間",
                    'reason': '保有時間制限に到達'
                }
            
            return {'action': 'NONE'}
            
        except Exception as e:
            logger.error(f"Time stop check failed: {e}")
            return {'action': 'NONE', 'error': str(e)}
    
    async def _check_partial_stop(
        self,
        position_id: str,
        current_pnl: float,
        config: ConservativeStopConfig
    ) -> Dict:
        """部分損切りチェック"""
        try:
            # 指定の損失に達したら部分的に損切り
            if current_pnl <= -config.partial_stop_percent:
                position = self.active_positions[position_id]
                
                return {
                    'action': 'PARTIAL_STOP',
                    'price': 0.0,  # 市場価格
                    'percentage': 0.5,  # 50%を損切り
                    'loss_percent': abs(current_pnl),
                    'threshold': config.partial_stop_percent,
                    'description': f"部分損切り: 50% (損失 {abs(current_pnl):.2f}%)",
                    'reason': '部分損切り条件に到達'
                }
            
            return {'action': 'NONE'}
            
        except Exception as e:
            logger.error(f"Partial stop check failed: {e}")
            return {'action': 'NONE', 'error': str(e)}
    
    def get_stop_levels(self, position_id: str) -> List[Dict]:
        """ポジションの損切りレベルを取得"""
        levels = self.active_stops.get(position_id, [])
        result = []
        
        for level in levels:
            if level.is_active:
                result.append({
                    "price": level.stop_price,
                    "name": level.level_name,
                    "trigger_conditions": level.trigger_conditions,
                    "priority": level.priority,
                    "description": level.description
                })
        
        # ブレークイーブン情報を追加
        if position_id in self.breakeven_moved and self.breakeven_moved[position_id]:
            result.append({
                "price": 0,
                "name": "ブレークイーブン",
                "trigger_conditions": ["MOVED"],
                "priority": 0,
                "description": "ストップはブレークイーブンに移動済み"
            })
        
        return result
    
    def cleanup_position(self, position_id: str) -> bool:
        """ポジション情報のクリーンアップ"""
        try:
            if position_id in self.active_stops:
                del self.active_stops[position_id]
            if position_id in self.stop_configs:
                del self.stop_configs[position_id]
            if position_id in self.active_positions:
                del self.active_positions[position_id]
            if position_id in self.breakeven_moved:
                del self.breakeven_moved[position_id]
            
            logger.info(f"Conservative stop cleanup completed: {position_id}")
            return True
            
        except Exception as e:
            logger.error(f"Conservative stop cleanup failed: {e}")
            return False

# グローバルインスタンス
conservative_stop_system = ConservativeStopSystem()