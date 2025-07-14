"""
アグレッシブ損切りシステム
スキャルピング専用の高速損切りと緊急保護機能
"""
import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class AggressiveStopConfig:
    """アグレッシブ損切り設定"""
    initial_stop_distance: float  # 初期ストップ距離（%）
    max_loss_percent: float  # 最大損失（%）
    time_stop_seconds: int  # 時間ストップ（秒）
    momentum_stop_threshold: float  # モメンタムストップ閾値
    volume_stop_multiplier: float  # ボリュームストップ倍率
    emergency_stop_percent: float  # 緊急ストップ（%）

@dataclass
class StopLossLevel:
    """損切りレベル"""
    level_name: str
    stop_price: float
    trigger_conditions: List[str]
    priority: int  # 1が最高優先度
    is_active: bool = True

@dataclass
class RiskMetrics:
    """リスク指標"""
    current_drawdown: float
    max_drawdown: float
    momentum_deterioration: float
    volume_decline: float
    time_exposure: int  # 秒
    market_stress_level: float

class AggressiveStopSystem:
    """
    アグレッシブ損切りシステム
    スキャルピング専用の高速損切りと緊急保護機能
    """
    
    def __init__(self):
        # 基本設定
        self.default_config = AggressiveStopConfig(
            initial_stop_distance=0.15,  # 0.15%
            max_loss_percent=0.25,       # 0.25%
            time_stop_seconds=300,       # 5分
            momentum_stop_threshold=0.3,
            volume_stop_multiplier=0.5,
            emergency_stop_percent=0.4   # 0.4%
        )
        
        # アクティブストップ管理
        self.active_stops: Dict[str, List[StopLossLevel]] = {}
        self.risk_metrics: Dict[str, RiskMetrics] = {}
        self.stop_configs: Dict[str, AggressiveStopConfig] = {}
        
        # 緊急停止フラグ
        self.emergency_mode: Dict[str, bool] = {}
        
    async def setup_aggressive_stops(
        self,
        position_id: str,
        entry_price: float,
        direction: str,
        position_size: float,
        confidence: float,
        expected_duration: int
    ) -> Dict:
        """
        アグレッシブ損切りの設定
        
        Parameters:
        -----------
        position_id : str
            ポジションID
        entry_price : float
            エントリー価格
        direction : str
            方向 ('BUY' or 'SELL')
        position_size : float
            ポジションサイズ
        confidence : float
            シグナル信頼度
        expected_duration : int
            予想保有時間（分）
            
        Returns:
        --------
        Dict : 設定結果
        """
        try:
            # 信頼度と期間に基づく設定調整
            config = await self._create_custom_config(confidence, expected_duration)
            self.stop_configs[position_id] = config
            
            # 多層ストップロスレベルの作成
            stop_levels = await self._create_stop_levels(
                entry_price, direction, config, confidence
            )
            self.active_stops[position_id] = stop_levels
            
            # リスク指標の初期化
            self.risk_metrics[position_id] = RiskMetrics(
                current_drawdown=0.0,
                max_drawdown=0.0,
                momentum_deterioration=0.0,
                volume_decline=0.0,
                time_exposure=0,
                market_stress_level=0.0
            )
            
            # 緊急モード初期化
            self.emergency_mode[position_id] = False
            
            logger.info(f"Aggressive stops setup completed for {position_id}")
            
            return {
                'success': True,
                'position_id': position_id,
                'stop_levels': len(stop_levels),
                'config': {
                    'initial_stop': config.initial_stop_distance,
                    'max_loss': config.max_loss_percent,
                    'time_stop': config.time_stop_seconds,
                    'emergency_stop': config.emergency_stop_percent
                }
            }
            
        except Exception as e:
            logger.error(f"Aggressive stops setup failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def check_stop_conditions(
        self,
        position_id: str,
        current_price: float,
        entry_price: float,
        direction: str,
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
        entry_price : float
            エントリー価格
        direction : str
            方向
        market_data : Dict
            市場データ（ボリューム、モメンタムなど）
            
        Returns:
        --------
        Dict : 損切りアクション
        """
        if position_id not in self.active_stops:
            return {'action': 'NONE', 'reason': 'No stops configured'}
        
        try:
            # リスク指標の更新
            await self._update_risk_metrics(
                position_id, current_price, entry_price, direction, market_data
            )
            
            # 緊急停止チェック
            emergency_action = await self._check_emergency_stop(
                position_id, current_price, entry_price, direction
            )
            if emergency_action['action'] != 'NONE':
                return emergency_action
            
            # 通常損切りレベルのチェック
            normal_action = await self._check_normal_stops(
                position_id, current_price, entry_price, direction, market_data
            )
            if normal_action['action'] != 'NONE':
                return normal_action
            
            # 時間ベース損切りチェック
            time_action = await self._check_time_stop(position_id)
            if time_action['action'] != 'NONE':
                return time_action
            
            # モメンタム劣化チェック
            momentum_action = await self._check_momentum_stop(
                position_id, market_data
            )
            if momentum_action['action'] != 'NONE':
                return momentum_action
            
            # ボリューム低下チェック
            volume_action = await self._check_volume_stop(
                position_id, market_data
            )
            
            return volume_action
            
        except Exception as e:
            logger.error(f"Stop conditions check failed: {e}")
            return {'action': 'NONE', 'error': str(e)}
    
    async def _create_custom_config(
        self,
        confidence: float,
        expected_duration: int
    ) -> AggressiveStopConfig:
        """カスタム設定の作成"""
        try:
            # 信頼度に基づく調整
            confidence_factor = confidence  # 0.5-1.0
            
            # 高信頼度ほどタイトなストップ
            initial_stop = self.default_config.initial_stop_distance * (2.0 - confidence_factor)
            max_loss = self.default_config.max_loss_percent * (2.0 - confidence_factor)
            
            # 期間に基づく調整
            if expected_duration <= 2:  # 2分以下
                time_multiplier = 0.6  # より短時間で損切り
            elif expected_duration <= 5:  # 5分以下
                time_multiplier = 1.0
            else:
                time_multiplier = 1.5  # より長時間許容
            
            time_stop = int(self.default_config.time_stop_seconds * time_multiplier)
            
            # 緊急ストップは常にタイト
            emergency_stop = max_loss * 1.6
            
            return AggressiveStopConfig(
                initial_stop_distance=initial_stop,
                max_loss_percent=max_loss,
                time_stop_seconds=time_stop,
                momentum_stop_threshold=self.default_config.momentum_stop_threshold,
                volume_stop_multiplier=self.default_config.volume_stop_multiplier,
                emergency_stop_percent=emergency_stop
            )
            
        except Exception as e:
            logger.error(f"Custom config creation failed: {e}")
            return self.default_config
    
    async def _create_stop_levels(
        self,
        entry_price: float,
        direction: str,
        config: AggressiveStopConfig,
        confidence: float
    ) -> List[StopLossLevel]:
        """多層ストップロスレベルの作成"""
        levels = []
        
        try:
            # レベル1: 初期ストップ（価格ベース）
            if direction == 'BUY':
                initial_stop_price = entry_price * (1 - config.initial_stop_distance / 100)
                max_loss_price = entry_price * (1 - config.max_loss_percent / 100)
                emergency_price = entry_price * (1 - config.emergency_stop_percent / 100)
            else:
                initial_stop_price = entry_price * (1 + config.initial_stop_distance / 100)
                max_loss_price = entry_price * (1 + config.max_loss_percent / 100)
                emergency_price = entry_price * (1 + config.emergency_stop_percent / 100)
            
            levels.append(StopLossLevel(
                level_name='初期ストップ',
                stop_price=initial_stop_price,
                trigger_conditions=['PRICE'],
                priority=3
            ))
            
            # レベル2: 最大損失ストップ
            levels.append(StopLossLevel(
                level_name='最大損失ストップ',
                stop_price=max_loss_price,
                trigger_conditions=['PRICE', 'DRAWDOWN'],
                priority=2
            ))
            
            # レベル3: 緊急ストップ
            levels.append(StopLossLevel(
                level_name='緊急ストップ',
                stop_price=emergency_price,
                trigger_conditions=['PRICE', 'EMERGENCY'],
                priority=1
            ))
            
            # レベル4: 時間ストップ（価格無関係）
            levels.append(StopLossLevel(
                level_name='時間ストップ',
                stop_price=0.0,  # 市場価格
                trigger_conditions=['TIME'],
                priority=4
            ))
            
            # レベル5: モメンタムストップ
            levels.append(StopLossLevel(
                level_name='モメンタムストップ',
                stop_price=0.0,  # 市場価格
                trigger_conditions=['MOMENTUM'],
                priority=5
            ))
            
            return levels
            
        except Exception as e:
            logger.error(f"Stop levels creation failed: {e}")
            return []
    
    async def _update_risk_metrics(
        self,
        position_id: str,
        current_price: float,
        entry_price: float,
        direction: str,
        market_data: Dict
    ) -> None:
        """リスク指標の更新"""
        try:
            metrics = self.risk_metrics[position_id]
            
            # 現在のドローダウン計算
            if direction == 'BUY':
                current_drawdown = ((entry_price - current_price) / entry_price) * 100
            else:
                current_drawdown = ((current_price - entry_price) / entry_price) * 100
            
            current_drawdown = max(0, current_drawdown)  # 負の値は0
            
            metrics.current_drawdown = current_drawdown
            metrics.max_drawdown = max(metrics.max_drawdown, current_drawdown)
            
            # モメンタム劣化
            momentum = market_data.get('momentum', 0.5)
            baseline_momentum = 0.5
            metrics.momentum_deterioration = max(0, baseline_momentum - momentum)
            
            # ボリューム低下
            current_volume = market_data.get('volume', 1.0)
            baseline_volume = market_data.get('baseline_volume', 1.0)
            metrics.volume_decline = max(0, 1.0 - (current_volume / baseline_volume))
            
            # 時間露出
            if not hasattr(self, '_position_start_times'):
                self._position_start_times = {}
            
            if position_id not in self._position_start_times:
                self._position_start_times[position_id] = datetime.now()
            
            time_diff = datetime.now() - self._position_start_times[position_id]
            metrics.time_exposure = int(time_diff.total_seconds())
            
            # 市場ストレスレベル
            volatility = market_data.get('volatility', 0.01)
            spread = market_data.get('spread_percent', 0.01)
            metrics.market_stress_level = min(1.0, (volatility * 50) + (spread * 100))
            
        except Exception as e:
            logger.error(f"Risk metrics update failed: {e}")
    
    async def _check_emergency_stop(
        self,
        position_id: str,
        current_price: float,
        entry_price: float,
        direction: str
    ) -> Dict:
        """緊急停止チェック"""
        try:
            config = self.stop_configs[position_id]
            metrics = self.risk_metrics[position_id]
            
            # 緊急トリガー条件
            emergency_triggers = []
            
            # 1. 急激な価格変動
            if direction == 'BUY':
                price_drop = ((entry_price - current_price) / entry_price) * 100
                if price_drop > config.emergency_stop_percent:
                    emergency_triggers.append(f'急激な価格下落 ({price_drop:.2f}%)')
            else:
                price_rise = ((current_price - entry_price) / entry_price) * 100
                if price_rise > config.emergency_stop_percent:
                    emergency_triggers.append(f'急激な価格上昇 ({price_rise:.2f}%)')
            
            # 2. 市場ストレス
            if metrics.market_stress_level > 0.8:
                emergency_triggers.append(f'市場ストレス ({metrics.market_stress_level:.2f})')
            
            # 3. 極端なドローダウン
            if metrics.current_drawdown > config.max_loss_percent * 1.5:
                emergency_triggers.append(f'極端ドローダウン ({metrics.current_drawdown:.2f}%)')
            
            if emergency_triggers:
                self.emergency_mode[position_id] = True
                logger.warning(f"Emergency stop triggered for {position_id}: {emergency_triggers}")
                
                return {
                    'action': 'EMERGENCY_CLOSE',
                    'price': current_price,
                    'reason': '; '.join(emergency_triggers),
                    'loss_percent': metrics.current_drawdown,
                    'stop_type': 'EMERGENCY'
                }
            
            return {'action': 'NONE', 'reason': 'No emergency conditions'}
            
        except Exception as e:
            logger.error(f"Emergency stop check failed: {e}")
            return {'action': 'NONE', 'error': str(e)}
    
    async def _check_normal_stops(
        self,
        position_id: str,
        current_price: float,
        entry_price: float,
        direction: str,
        market_data: Dict
    ) -> Dict:
        """通常損切りレベルのチェック"""
        try:
            stop_levels = self.active_stops[position_id]
            metrics = self.risk_metrics[position_id]
            
            # 優先度順にチェック
            for level in sorted(stop_levels, key=lambda x: x.priority):
                if not level.is_active or level.stop_price == 0.0:
                    continue
                
                triggered = False
                
                if 'PRICE' in level.trigger_conditions:
                    if direction == 'BUY':
                        triggered = current_price <= level.stop_price
                    else:
                        triggered = current_price >= level.stop_price
                
                if 'DRAWDOWN' in level.trigger_conditions:
                    config = self.stop_configs[position_id]
                    triggered = triggered or metrics.current_drawdown >= config.max_loss_percent
                
                if triggered:
                    level.is_active = False  # このレベルを無効化
                    
                    logger.info(f"Normal stop triggered: {position_id}, {level.level_name}")
                    
                    return {
                        'action': 'STOP_LOSS',
                        'price': current_price,
                        'stop_price': level.stop_price,
                        'level_name': level.level_name,
                        'loss_percent': metrics.current_drawdown,
                        'stop_type': 'NORMAL'
                    }
            
            return {'action': 'NONE', 'reason': 'No normal stops triggered'}
            
        except Exception as e:
            logger.error(f"Normal stops check failed: {e}")
            return {'action': 'NONE', 'error': str(e)}
    
    async def _check_time_stop(self, position_id: str) -> Dict:
        """時間ベース損切りチェック"""
        try:
            config = self.stop_configs[position_id]
            metrics = self.risk_metrics[position_id]
            
            if metrics.time_exposure > config.time_stop_seconds:
                # 利益が出ていない場合のみ時間ストップ
                if metrics.current_drawdown > 0:
                    logger.info(f"Time stop triggered: {position_id}, {metrics.time_exposure}s")
                    
                    return {
                        'action': 'TIME_STOP',
                        'price': 0.0,  # 市場価格
                        'time_exposed': metrics.time_exposure,
                        'loss_percent': metrics.current_drawdown,
                        'reason': f'時間制限超過 ({metrics.time_exposure}秒)',
                        'stop_type': 'TIME'
                    }
            
            return {'action': 'NONE', 'reason': 'Time stop not triggered'}
            
        except Exception as e:
            logger.error(f"Time stop check failed: {e}")
            return {'action': 'NONE', 'error': str(e)}
    
    async def _check_momentum_stop(
        self,
        position_id: str,
        market_data: Dict
    ) -> Dict:
        """モメンタムベース損切りチェック"""
        try:
            config = self.stop_configs[position_id]
            metrics = self.risk_metrics[position_id]
            
            # モメンタム劣化が閾値を超えた場合
            if metrics.momentum_deterioration > config.momentum_stop_threshold:
                # ドローダウンがある場合のみ
                if metrics.current_drawdown > config.initial_stop_distance * 0.5:
                    logger.info(f"Momentum stop triggered: {position_id}")
                    
                    return {
                        'action': 'MOMENTUM_STOP',
                        'price': 0.0,  # 市場価格
                        'momentum_deterioration': metrics.momentum_deterioration,
                        'loss_percent': metrics.current_drawdown,
                        'reason': 'モメンタム劣化',
                        'stop_type': 'MOMENTUM'
                    }
            
            return {'action': 'NONE', 'reason': 'Momentum stop not triggered'}
            
        except Exception as e:
            logger.error(f"Momentum stop check failed: {e}")
            return {'action': 'NONE', 'error': str(e)}
    
    async def _check_volume_stop(
        self,
        position_id: str,
        market_data: Dict
    ) -> Dict:
        """ボリュームベース損切りチェック"""
        try:
            config = self.stop_configs[position_id]
            metrics = self.risk_metrics[position_id]
            
            # ボリューム大幅低下 + ドローダウン
            if (metrics.volume_decline > config.volume_stop_multiplier and 
                metrics.current_drawdown > config.initial_stop_distance * 0.3):
                
                logger.info(f"Volume stop triggered: {position_id}")
                
                return {
                    'action': 'VOLUME_STOP',
                    'price': 0.0,  # 市場価格
                    'volume_decline': metrics.volume_decline,
                    'loss_percent': metrics.current_drawdown,
                    'reason': 'ボリューム低下',
                    'stop_type': 'VOLUME'
                }
            
            return {'action': 'NONE', 'reason': 'Volume stop not triggered'}
            
        except Exception as e:
            logger.error(f"Volume stop check failed: {e}")
            return {'action': 'NONE', 'error': str(e)}
    
    def cleanup_position(self, position_id: str) -> bool:
        """ポジション情報のクリーンアップ"""
        try:
            if position_id in self.active_stops:
                del self.active_stops[position_id]
            if position_id in self.risk_metrics:
                del self.risk_metrics[position_id]
            if position_id in self.stop_configs:
                del self.stop_configs[position_id]
            if position_id in self.emergency_mode:
                del self.emergency_mode[position_id]
            if hasattr(self, '_position_start_times') and position_id in self._position_start_times:
                del self._position_start_times[position_id]
            
            logger.info(f"Aggressive stop cleanup completed: {position_id}")
            return True
            
        except Exception as e:
            logger.error(f"Aggressive stop cleanup failed: {e}")
            return False
    
    def get_position_risk(self, position_id: str) -> Optional[Dict]:
        """ポジションリスク情報の取得"""
        if position_id not in self.risk_metrics:
            return None
        
        metrics = self.risk_metrics[position_id]
        config = self.stop_configs.get(position_id, self.default_config)
        
        return {
            'current_drawdown': metrics.current_drawdown,
            'max_drawdown': metrics.max_drawdown,
            'time_exposure': metrics.time_exposure,
            'max_time': config.time_stop_seconds,
            'emergency_mode': self.emergency_mode.get(position_id, False),
            'market_stress': metrics.market_stress_level,
            'momentum_deterioration': metrics.momentum_deterioration,
            'volume_decline': metrics.volume_decline
        }
    
    def get_stop_levels(self, position_id: str) -> List[Dict]:
        """ポジションの損切りレベルを取得"""
        levels = self.stop_levels.get(position_id, [])
        result = []
        
        for level in levels:
            if level.is_active:
                result.append({
                    "price": level.stop_price,
                    "name": level.level_name,
                    "trigger_conditions": level.trigger_conditions,
                    "priority": level.priority,
                    "description": f"{level.level_name}: {level.stop_price:.2f}"
                })
        
        # 設定からの追加情報
        if position_id in self.stop_configs:
            config = self.stop_configs[position_id]
            position = self.active_positions.get(position_id, {})
            entry_price = position.get('entry_price', 0)
            
            if entry_price > 0:
                # 初期ストップ
                if position.get('direction') == 'BUY':
                    initial_stop = entry_price * (1 - config.initial_stop_distance / 100)
                else:
                    initial_stop = entry_price * (1 + config.initial_stop_distance / 100)
                
                result.append({
                    "price": initial_stop,
                    "name": "初期ストップ",
                    "trigger_conditions": ["価格"],
                    "priority": 1,
                    "description": f"初期ストップ: {initial_stop:.2f} (-{config.initial_stop_distance:.1f}%)"
                })
                
                # 緊急ストップ
                if position.get('direction') == 'BUY':
                    emergency_stop = entry_price * (1 - config.emergency_stop_percent / 100)
                else:
                    emergency_stop = entry_price * (1 + config.emergency_stop_percent / 100)
                
                result.append({
                    "price": emergency_stop,
                    "name": "緊急ストップ",
                    "trigger_conditions": ["緊急事態"],
                    "priority": 0,
                    "description": f"緊急ストップ: {emergency_stop:.2f} (-{config.emergency_stop_percent:.1f}%)"
                })
        
        return sorted(result, key=lambda x: x['priority'])

# グローバルインスタンス
aggressive_stop_system = AggressiveStopSystem()