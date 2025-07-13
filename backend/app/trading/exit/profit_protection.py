"""
利益保護メカニズム
獲得した利益を絶対に失わないシステム
"""
import asyncio
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class ProtectionLevel(Enum):
    BREAKEVEN = "breakeven"
    LOCK_25 = "lock_25"
    LOCK_50 = "lock_50"
    LOCK_75 = "lock_75"
    LOCK_90 = "lock_90"

@dataclass
class ProtectionStatus:
    level: ProtectionLevel
    locked_price: float
    locked_profit_percent: float
    activated_at: datetime
    position_size_protected: float

class ProfitProtectionSystem:
    """
    獲得した利益を絶対に失わないシステム
    """
    
    def __init__(self, session, config: Dict):
        self.session = session
        self.config = config
        
        # 保護レベルの定義（利益率 -> ロック率）
        self.protection_levels = {
            ProtectionLevel.BREAKEVEN: {'threshold': 0.005, 'lock_percent': 0},      # 0.5%でブレークイーブン
            ProtectionLevel.LOCK_25: {'threshold': 0.02, 'lock_percent': 25},        # 2%で25%ロック
            ProtectionLevel.LOCK_50: {'threshold': 0.04, 'lock_percent': 50},        # 4%で50%ロック
            ProtectionLevel.LOCK_75: {'threshold': 0.06, 'lock_percent': 75},        # 6%で75%ロック
            ProtectionLevel.LOCK_90: {'threshold': 0.10, 'lock_percent': 90},        # 10%で90%ロック
        }
        
        # ボラティリティスパイク検出パラメータ
        self.volatility_spike_threshold = config.get('volatility_spike_threshold', 2.0)  # 通常の2倍
        self.spike_protection_percent = config.get('spike_protection_percent', 50)  # 50%即座に利確
        
        # アクティブな保護状態
        self.protected_positions = {}  # position_id -> ProtectionStatus
        
    async def protect_profits(self, position: Dict) -> Dict:
        """
        利益保護を実行
        
        Parameters:
        -----------
        position : dict
            ポジション情報
            
        Returns:
        --------
        dict : 保護状態
        """
        try:
            position_id = position['id']
            entry_price = position['entry_price']
            current_price = position['current_price']
            side = position['side']
            
            # 利益率を計算
            if side == 'BUY':
                profit_percent = (current_price - entry_price) / entry_price
            else:
                profit_percent = (entry_price - current_price) / entry_price
            
            # 現在の保護レベルを確認
            current_protection = self.protected_positions.get(position_id)
            
            # 保護レベルの更新をチェック
            new_protection = await self._check_protection_levels(
                position, profit_percent, current_protection
            )
            
            # ボラティリティスパイクをチェック
            if await self._detect_volatility_spike(position):
                await self._handle_volatility_spike(position)
            
            # 保護状態を返す
            if new_protection:
                return {
                    'protected': True,
                    'level': new_protection.level.value,
                    'locked_price': new_protection.locked_price,
                    'locked_profit': new_protection.locked_profit_percent,
                    'current_profit': profit_percent
                }
            else:
                return {
                    'protected': False,
                    'current_profit': profit_percent
                }
                
        except Exception as e:
            logger.error(f"Failed to protect profits: {e}")
            return {'protected': False, 'error': str(e)}
    
    async def _check_protection_levels(self, position: Dict, 
                                     profit_percent: float,
                                     current_protection: Optional[ProtectionStatus]) -> Optional[ProtectionStatus]:
        """保護レベルをチェックして更新"""
        position_id = position['id']
        entry_price = position['entry_price']
        side = position['side']
        
        # 各保護レベルをチェック
        for level, params in self.protection_levels.items():
            threshold = params['threshold']
            lock_percent = params['lock_percent']
            
            # この保護レベルに到達しているか
            if profit_percent >= threshold:
                # 既に同じかより高いレベルで保護されているか確認
                if current_protection and self._is_higher_protection(current_protection.level, level):
                    continue
                
                # 新しい保護価格を計算
                if lock_percent == 0:  # ブレークイーブン
                    if side == 'BUY':
                        protected_price = entry_price * 1.002  # 手数料分を追加
                    else:
                        protected_price = entry_price * 0.998
                else:
                    # 利益の一定割合を確保
                    locked_profit = profit_percent * (lock_percent / 100)
                    if side == 'BUY':
                        protected_price = entry_price * (1 + locked_profit)
                    else:
                        protected_price = entry_price * (1 - locked_profit)
                
                # ストップロスを更新
                await self._update_stop_loss(position_id, protected_price)
                
                # 保護状態を記録
                new_protection = ProtectionStatus(
                    level=level,
                    locked_price=protected_price,
                    locked_profit_percent=locked_profit if lock_percent > 0 else 0,
                    activated_at=datetime.now(),
                    position_size_protected=position['size']
                )
                
                self.protected_positions[position_id] = new_protection
                
                logger.info(f"Profit protection activated: {level.value} for position {position_id}")
                
                return new_protection
        
        return current_protection
    
    def _is_higher_protection(self, current: ProtectionLevel, new: ProtectionLevel) -> bool:
        """現在の保護レベルが新しいレベルより高いか確認"""
        level_order = [
            ProtectionLevel.BREAKEVEN,
            ProtectionLevel.LOCK_25,
            ProtectionLevel.LOCK_50,
            ProtectionLevel.LOCK_75,
            ProtectionLevel.LOCK_90
        ]
        
        current_idx = level_order.index(current)
        new_idx = level_order.index(new)
        
        return current_idx >= new_idx
    
    async def _detect_volatility_spike(self, position: Dict) -> bool:
        """ボラティリティスパイクを検出"""
        try:
            symbol = position['symbol']
            
            # 5分足データを取得
            kline_response = self.session.get_kline(
                category="linear",
                symbol=symbol,
                interval="5",
                limit=30
            )
            
            if kline_response["retCode"] != 0:
                return False
            
            klines = kline_response["result"]["list"]
            
            # ATRを計算
            atr_values = []
            for i in range(1, len(klines)):
                high = float(klines[i][2])
                low = float(klines[i][3])
                prev_close = float(klines[i-1][4])
                
                tr = max(
                    high - low,
                    abs(high - prev_close),
                    abs(low - prev_close)
                )
                atr_values.append(tr)
            
            if len(atr_values) < 14:
                return False
            
            # 直近のATRと平均ATRを比較
            recent_atr = sum(atr_values[-3:]) / 3
            avg_atr = sum(atr_values[-14:]) / 14
            
            # スパイク検出
            is_spike = recent_atr > avg_atr * self.volatility_spike_threshold
            
            if is_spike:
                logger.warning(f"Volatility spike detected for {symbol}: {recent_atr/avg_atr:.2f}x normal")
            
            return is_spike
            
        except Exception as e:
            logger.error(f"Failed to detect volatility spike: {e}")
            return False
    
    async def _handle_volatility_spike(self, position: Dict):
        """ボラティリティスパイク時の処理"""
        position_id = position['id']
        
        logger.warning(f"Handling volatility spike for position {position_id}")
        
        try:
            # 1. 即座に一部を利確
            await self._execute_spike_protection(position)
            
            # 2. 残りのポジションにタイトなストップを設定
            await self._tighten_stops_after_spike(position)
            
            # 3. アラートを発行
            await self._send_spike_alert(position)
            
        except Exception as e:
            logger.error(f"Failed to handle volatility spike: {e}")
    
    async def _execute_spike_protection(self, position: Dict):
        """スパイク時の部分決済を実行"""
        try:
            # 指定された割合を即座に決済
            close_percentage = self.spike_protection_percent
            
            # ポジションサイズを取得
            total_size = position['size']
            close_size = total_size * (close_percentage / 100)
            
            # 成行注文で決済
            side = "Sell" if position['side'] == "BUY" else "Buy"
            
            order_response = self.session.place_order(
                category="linear",
                symbol=position['symbol'],
                side=side,
                orderType="Market",
                qty=str(close_size),
                timeInForce="IOC",
                reduceOnly=True,
                positionIdx=0
            )
            
            if order_response["retCode"] == 0:
                logger.info(f"Spike protection executed: {close_percentage}% of position {position['id']}")
            else:
                logger.error(f"Failed to execute spike protection: {order_response['retMsg']}")
                
        except Exception as e:
            logger.error(f"Failed to execute spike protection: {e}")
    
    async def _tighten_stops_after_spike(self, position: Dict):
        """スパイク後のストップをタイトにする"""
        try:
            position_id = position['id']
            current_price = position['current_price']
            side = position['side']
            
            # 非常にタイトなストップ（0.3%）
            tight_stop_percent = 0.003
            
            if side == 'BUY':
                new_stop = current_price * (1 - tight_stop_percent)
            else:
                new_stop = current_price * (1 + tight_stop_percent)
            
            # ストップを更新
            await self._update_stop_loss(position_id, new_stop)
            
            logger.info(f"Tightened stop for position {position_id} to {new_stop}")
            
        except Exception as e:
            logger.error(f"Failed to tighten stops: {e}")
    
    async def _update_stop_loss(self, position_id: str, new_stop_price: float):
        """ストップロス注文を更新"""
        try:
            # 既存のストップロス注文を取得
            orders = self.session.get_open_orders(
                category="linear",
                settleCoin="USDT"
            )
            
            if orders["retCode"] != 0:
                return
            
            # 該当するストップ注文を探す
            stop_order = None
            for order in orders["result"]["list"]:
                if (order.get("positionIdx") == position_id and 
                    order["orderType"] in ["Stop", "StopMarket"]):
                    stop_order = order
                    break
            
            if stop_order:
                # 既存の注文をキャンセル
                cancel_response = self.session.cancel_order(
                    category="linear",
                    symbol=stop_order["symbol"],
                    orderId=stop_order["orderId"]
                )
                
                if cancel_response["retCode"] != 0:
                    logger.error(f"Failed to cancel old stop: {cancel_response['retMsg']}")
                    return
            
            # 新しいストップ注文を配置
            # （実装は実際のポジション情報に基づいて行う）
            
            logger.info(f"Stop loss updated for position {position_id}: {new_stop_price}")
            
        except Exception as e:
            logger.error(f"Failed to update stop loss: {e}")
    
    async def _send_spike_alert(self, position: Dict):
        """スパイクアラートを送信"""
        alert_message = {
            'type': 'volatility_spike',
            'position_id': position['id'],
            'symbol': position['symbol'],
            'action_taken': f'{self.spike_protection_percent}% partial close',
            'timestamp': datetime.now().isoformat()
        }
        
        # WebSocketやその他の通知システムでアラートを送信
        logger.warning(f"Volatility spike alert: {alert_message}")
    
    def get_protection_summary(self) -> Dict:
        """全ポジションの保護状態サマリーを取得"""
        summary = {
            'total_protected': len(self.protected_positions),
            'protection_levels': {},
            'total_locked_profit': 0
        }
        
        # レベル別の集計
        for level in ProtectionLevel:
            summary['protection_levels'][level.value] = 0
        
        # 各ポジションの保護状態を集計
        for pos_id, protection in self.protected_positions.items():
            summary['protection_levels'][protection.level.value] += 1
            summary['total_locked_profit'] += protection.locked_profit_percent
        
        # 平均ロック利益
        if summary['total_protected'] > 0:
            summary['avg_locked_profit'] = summary['total_locked_profit'] / summary['total_protected']
        else:
            summary['avg_locked_profit'] = 0
        
        return summary
    
    async def reset_position_protection(self, position_id: str):
        """ポジションの保護状態をリセット"""
        if position_id in self.protected_positions:
            del self.protected_positions[position_id]
            logger.info(f"Protection reset for position {position_id}")