"""
トレーディングモード管理システム
通常モードとスキャルピングモードの切り替えと管理
"""
import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)

class TradingMode(Enum):
    CONSERVATIVE = "conservative"  # 慎重モード（1日1-3回）
    SCALPING = "scalping"         # スキャルピングモード（1日20-50回）

@dataclass
class ModeConfig:
    """モード設定"""
    name: str
    enabled: bool
    max_positions: int
    position_size_percent: float  # 口座残高に対する割合
    min_interval_seconds: int     # 最小取引間隔
    max_daily_trades: int        # 1日の最大取引数
    risk_level: float            # リスクレベル（0.0-1.0）

class TradingModeManager:
    """
    トレーディングモード管理システム
    複数モードの同時稼働をサポート
    """
    
    def __init__(self):
        self.modes: Dict[TradingMode, ModeConfig] = {
            TradingMode.CONSERVATIVE: ModeConfig(
                name="慎重モード",
                enabled=True,
                max_positions=5,              # 3→5に増加
                position_size_percent=0.03,  # 5%→3%に調整（リスク分散）
                min_interval_seconds=1800,   # 1時間→30分に短縮
                max_daily_trades=10,         # 5→10に増加
                risk_level=0.3
            ),
            TradingMode.SCALPING: ModeConfig(
                name="スキャルピングモード", 
                enabled=True,  # デフォルトを有効に変更
                max_positions=30,  # 15→30に増加
                position_size_percent=0.05,  # 2%→5%に引き上げ
                min_interval_seconds=60,     # 1分
                max_daily_trades=100,  # 50→100に増加（ポジション数増加に対応）
                risk_level=0.7
            )
        }
        
        self.active_positions: Dict[TradingMode, List[Dict]] = {
            TradingMode.CONSERVATIVE: [],
            TradingMode.SCALPING: []
        }
        
        self.daily_trades: Dict[TradingMode, int] = {
            TradingMode.CONSERVATIVE: 0,
            TradingMode.SCALPING: 0
        }
        
        self.last_trade_time: Dict[TradingMode, Optional[datetime]] = {
            TradingMode.CONSERVATIVE: None,
            TradingMode.SCALPING: None
        }
        
        # 日次リセット用
        self.last_reset_date = datetime.now().date()
    
    def toggle_mode(self, mode: TradingMode, enabled: bool) -> Dict:
        """
        モードのON/OFF切り替え
        
        Parameters:
        -----------
        mode : TradingMode
            切り替えるモード
        enabled : bool
            有効/無効フラグ
            
        Returns:
        --------
        Dict : 切り替え結果
        """
        try:
            old_status = self.modes[mode].enabled
            self.modes[mode].enabled = enabled
            
            status_text = "起動" if enabled else "停止"
            emoji = "🚀" if enabled else "🛑"
            
            logger.info(f"{emoji} {self.modes[mode].name}{status_text}")
            
            return {
                "success": True,
                "mode": mode.value,
                "mode_name": self.modes[mode].name,
                "old_status": old_status,
                "new_status": enabled,
                "message": f"{self.modes[mode].name}を{status_text}しました"
            }
            
        except Exception as e:
            logger.error(f"Mode toggle failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def is_mode_active(self, mode: TradingMode) -> bool:
        """モードがアクティブかどうか確認"""
        return self.modes[mode].enabled
    
    def get_active_modes(self) -> List[TradingMode]:
        """アクティブなモードのリストを取得"""
        return [mode for mode, config in self.modes.items() if config.enabled]
    
    def can_open_position(self, mode: TradingMode) -> Dict:
        """
        新規ポジションを開けるかどうかチェック
        
        Returns:
        --------
        Dict : チェック結果
        """
        try:
            self._reset_daily_counters()
            
            config = self.modes[mode]
            logger.info(f"=== can_open_position check for {mode.value} ===")
            logger.info(f"Config enabled: {config.enabled}")
            logger.info(f"Mode name: {config.name}")
            logger.info(f"All modes status: {[(m.value, self.modes[m].enabled) for m in TradingMode]}")
            
            # モードが無効
            if not config.enabled:
                logger.warning(f"Mode {mode.value} is disabled!")
                return {
                    "can_open": False,
                    "reason": f"{config.name}が無効です"
                }
            
            # 最大ポジション数チェック
            current_positions = len(self.active_positions[mode])
            logger.info(f"Position check for {mode.value}: current={current_positions}, max={config.max_positions}, positions={[p.get('symbol', 'Unknown') for p in self.active_positions[mode]]}")
            
            if current_positions >= config.max_positions:
                return {
                    "can_open": False,
                    "reason": f"最大ポジション数({config.max_positions})に達しています"
                }
            
            # 日次取引上限チェック
            if self.daily_trades[mode] >= config.max_daily_trades:
                return {
                    "can_open": False,
                    "reason": f"1日の取引上限({config.max_daily_trades})に達しています"
                }
            
            # 最小間隔チェック
            if self.last_trade_time[mode]:
                time_since_last = (datetime.now() - self.last_trade_time[mode]).total_seconds()
                if time_since_last < config.min_interval_seconds:
                    remaining = config.min_interval_seconds - time_since_last
                    return {
                        "can_open": False,
                        "reason": f"取引間隔不足（あと{remaining:.0f}秒待機必要）"
                    }
            
            return {
                "can_open": True,
                "reason": "新規ポジション開始可能",
                "available_slots": config.max_positions - current_positions,
                "remaining_daily_trades": config.max_daily_trades - self.daily_trades[mode]
            }
            
        except Exception as e:
            logger.error(f"Position check failed: {e}")
            return {
                "can_open": False,
                "reason": f"チェックエラー: {str(e)}"
            }
    
    def get_position_size(self, mode: TradingMode, account_balance: float) -> float:
        """
        モードに応じたポジションサイズを計算
        
        Parameters:
        -----------
        mode : TradingMode
            取引モード
        account_balance : float
            口座残高
            
        Returns:
        --------
        float : ポジションサイズ（USDT）
        """
        try:
            config = self.modes[mode]
            base_size = account_balance * config.position_size_percent
            
            # アクティブなポジション数に応じて調整
            active_count = len(self.active_positions[mode])
            if active_count > 0:
                # 既存ポジションがあるときは少し小さく
                adjustment_factor = 1.0 - (active_count * 0.1)
                base_size *= max(adjustment_factor, 0.5)  # 最小50%
            
            return base_size
            
        except Exception as e:
            logger.error(f"Position size calculation failed: {e}")
            return account_balance * 0.01  # デフォルト1%
    
    def register_position(self, mode: TradingMode, position: Dict) -> bool:
        """
        新規ポジションを登録
        
        Parameters:
        -----------
        mode : TradingMode
            取引モード
        position : Dict
            ポジション情報
            
        Returns:
        --------
        bool : 登録成功フラグ
        """
        try:
            self._reset_daily_counters()
            
            # ポジションに追加情報を付与
            position.update({
                "mode": mode.value,
                "entry_time": datetime.now(),
                "position_id": f"{mode.value}_{datetime.now().timestamp()}"
            })
            
            self.active_positions[mode].append(position)
            self.daily_trades[mode] += 1
            self.last_trade_time[mode] = datetime.now()
            
            logger.info(f"Position registered: {mode.value} - {position.get('symbol', 'Unknown')}")
            
            return True
            
        except Exception as e:
            logger.error(f"Position registration failed: {e}")
            return False
    
    def close_position(self, mode: TradingMode, position_id: str) -> bool:
        """
        ポジションをクローズ
        
        Parameters:
        -----------
        mode : TradingMode
            取引モード
        position_id : str
            ポジションID
            
        Returns:
        --------
        bool : クローズ成功フラグ
        """
        try:
            positions = self.active_positions[mode]
            for i, position in enumerate(positions):
                if position.get("position_id") == position_id:
                    closed_position = positions.pop(i)
                    logger.info(f"Position closed: {mode.value} - {position_id}")
                    return True
            
            logger.warning(f"Position not found: {position_id}")
            return False
            
        except Exception as e:
            logger.error(f"Position close failed: {e}")
            return False
    
    def get_status(self) -> Dict:
        """
        全モードの状態を取得
        
        Returns:
        --------
        Dict : ステータス情報
        """
        try:
            self._reset_daily_counters()
            
            status = {
                "timestamp": datetime.now().isoformat(),
                "modes": {}
            }
            
            for mode, config in self.modes.items():
                active_positions = len(self.active_positions[mode])
                
                status["modes"][mode.value] = {
                    "name": config.name,
                    "enabled": config.enabled,
                    "active_positions": active_positions,
                    "max_positions": config.max_positions,
                    "daily_trades": self.daily_trades[mode],
                    "max_daily_trades": config.max_daily_trades,
                    "position_size_percent": config.position_size_percent,
                    "min_interval_seconds": config.min_interval_seconds,
                    "risk_level": config.risk_level,
                    "last_trade": self.last_trade_time[mode].isoformat() if self.last_trade_time[mode] else None,
                    "can_open_new": self.can_open_position(mode)["can_open"]
                }
            
            return status
            
        except Exception as e:
            logger.error(f"Status retrieval failed: {e}")
            return {"error": str(e)}
    
    def update_mode_config(self, mode: TradingMode, config_updates: Dict) -> Dict:
        """
        モード設定を更新
        
        Parameters:
        -----------
        mode : TradingMode
            更新するモード
        config_updates : Dict
            更新する設定項目
            
        Returns:
        --------
        Dict : 更新結果
        """
        try:
            config = self.modes[mode]
            old_config = {
                "max_positions": config.max_positions,
                "position_size_percent": config.position_size_percent,
                "min_interval_seconds": config.min_interval_seconds,
                "max_daily_trades": config.max_daily_trades,
                "risk_level": config.risk_level
            }
            
            # 設定を更新
            for key, value in config_updates.items():
                if hasattr(config, key):
                    setattr(config, key, value)
                    logger.info(f"Updated {mode.value}.{key}: {value}")
            
            return {
                "success": True,
                "mode": mode.value,
                "old_config": old_config,
                "new_config": {
                    "max_positions": config.max_positions,
                    "position_size_percent": config.position_size_percent,
                    "min_interval_seconds": config.min_interval_seconds,
                    "max_daily_trades": config.max_daily_trades,
                    "risk_level": config.risk_level
                }
            }
            
        except Exception as e:
            logger.error(f"Config update failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _reset_daily_counters(self):
        """日次カウンタをリセット（日付が変わった場合）"""
        current_date = datetime.now().date()
        if current_date != self.last_reset_date:
            self.daily_trades = {mode: 0 for mode in TradingMode}
            self.last_reset_date = current_date
            logger.info("Daily trading counters reset")
    
    async def cleanup_expired_positions(self):
        """
        期限切れポジションのクリーンアップ
        （定期実行用）
        """
        try:
            current_time = datetime.now()
            
            for mode in TradingMode:
                positions = self.active_positions[mode]
                expired_positions = []
                
                for position in positions:
                    entry_time = position.get("entry_time")
                    if entry_time:
                        hold_duration = (current_time - entry_time).total_seconds()
                        
                        # スキャルピングモードは20分、通常モードは24時間で強制クリーンアップ
                        max_hold_time = 1200 if mode == TradingMode.SCALPING else 86400
                        
                        if hold_duration > max_hold_time:
                            expired_positions.append(position)
                
                # 期限切れポジションを削除
                for expired in expired_positions:
                    if expired in positions:
                        positions.remove(expired)
                        logger.warning(f"Expired position cleaned up: {expired.get('position_id')}")
                
                # ポジション数のログ出力
                if len(positions) > 0:
                    logger.info(f"Active positions for {mode.value}: {len(positions)} - {[p.get('symbol', 'Unknown') for p in positions]}")
                        
        except Exception as e:
            logger.error(f"Position cleanup failed: {e}")

# グローバルインスタンス
trading_mode_manager = TradingModeManager()