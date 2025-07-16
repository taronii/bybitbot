"""
ポジション同期サービス
Bybitの実際のポジションとローカルのポジション情報を同期
"""
import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime
from ..services.bybit_client import get_bybit_client
from ..trading.modes.trading_mode_manager import trading_mode_manager, TradingMode
from ..trading.scalping.rapid_profit_system import rapid_profit_system, RapidProfitTarget
from ..trading.scalping.aggressive_stop_system import aggressive_stop_system

logger = logging.getLogger(__name__)

class PositionSyncService:
    """ポジション同期サービス"""
    
    def __init__(self):
        self.sync_interval = 10  # 10秒ごとに同期
        self.is_running = False
        self._sync_task = None
        
    async def start_sync(self):
        """同期を開始"""
        if self.is_running:
            logger.warning("Position sync is already running")
            return
            
        self.is_running = True
        self._sync_task = asyncio.create_task(self._sync_loop())
        logger.info("Position sync started")
        
    async def stop_sync(self):
        """同期を停止"""
        self.is_running = False
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
        logger.info("Position sync stopped")
        
    async def _sync_loop(self):
        """同期ループ"""
        while self.is_running:
            try:
                await self.sync_positions()
                await asyncio.sleep(self.sync_interval)
            except Exception as e:
                logger.error(f"Error in position sync loop: {e}")
                await asyncio.sleep(self.sync_interval)
                
    async def sync_positions(self):
        """ポジションを同期"""
        client = get_bybit_client()
        if not client:
            logger.warning("Bybit client not initialized")
            return
            
        try:
            # Bybitから実際のポジションを取得
            bybit_positions = await client.get_positions()
            
            # ローカルのポジション情報を取得
            local_positions = self._get_local_positions()
            
            # Bybitポジションをシンボルでインデックス化
            bybit_positions_dict = {pos['symbol']: pos for pos in bybit_positions}
            
            # ローカルポジションを確認・更新
            for position_id, local_pos in list(local_positions.items()):
                symbol = local_pos.get('symbol')
                
                if symbol in bybit_positions_dict:
                    # Bybitにポジションが存在する場合、情報を更新
                    bybit_pos = bybit_positions_dict[symbol]
                    await self._update_position_info(position_id, local_pos, bybit_pos)
                else:
                    # Bybitにポジションが存在しない場合、クリーンアップ
                    logger.info(f"Position {position_id} ({symbol}) not found in Bybit, cleaning up")
                    await self._cleanup_position(position_id)
                    
            # Bybitにあるがローカルにないポジションを検出
            local_symbols = {pos.get('symbol') for pos in local_positions.values()}
            for symbol, bybit_pos in bybit_positions_dict.items():
                if symbol not in local_symbols:
                    logger.info(f"New position found in Bybit: {symbol}, registering locally")
                    # 新しいポジションとして登録
                    await self._register_external_position(symbol, bybit_pos)
                    
        except Exception as e:
            logger.error(f"Error syncing positions: {e}")
            
    def _get_local_positions(self) -> Dict[str, Dict]:
        """ローカルのポジション情報を取得"""
        positions = {}
        
        # rapid_profit_systemのポジション
        for position_id, pos in rapid_profit_system.active_positions.items():
            positions[position_id] = pos
            
        # conservative_profit_systemのポジション
        from ..trading.conservative.conservative_profit_system import conservative_profit_system
        for position_id, pos in conservative_profit_system.active_positions.items():
            positions[position_id] = pos
            
        return positions
        
    async def _update_position_info(self, position_id: str, local_pos: Dict, bybit_pos: Dict):
        """ポジション情報を更新"""
        try:
            # サイズの確認
            bybit_size = float(bybit_pos.get('size', 0))
            local_size = float(local_pos.get('position_size', 0))
            
            # サイズが変更されている場合（部分決済など）
            if abs(bybit_size - local_size) > 0.0001:
                logger.info(f"Position size changed for {position_id}: {local_size} -> {bybit_size}")
                
                # rapid_profit_systemのポジションサイズを更新
                if position_id in rapid_profit_system.active_positions:
                    rapid_profit_system.active_positions[position_id]['position_size'] = bybit_size
                    rapid_profit_system.active_positions[position_id]['remaining_size'] = bybit_size
                    
                # conservative_profit_systemのポジションサイズを更新
                from ..trading.conservative.conservative_profit_system import conservative_profit_system
                if position_id in conservative_profit_system.active_positions:
                    conservative_profit_system.active_positions[position_id]['position_size'] = bybit_size
                    conservative_profit_system.active_positions[position_id]['remaining_size'] = bybit_size
                    
            # 平均価格の更新
            bybit_avg_price = float(bybit_pos.get('avgPrice', 0))
            if bybit_avg_price > 0 and abs(bybit_avg_price - local_pos.get('entry_price', 0)) > 0.01:
                logger.info(f"Entry price updated for {position_id}: {local_pos.get('entry_price')} -> {bybit_avg_price}")
                if position_id in rapid_profit_system.active_positions:
                    rapid_profit_system.active_positions[position_id]['entry_price'] = bybit_avg_price
                    
            # 未実現損益の更新
            unrealized_pnl = float(bybit_pos.get('unrealisedPnl', 0))
            mark_price = float(bybit_pos.get('markPrice', 0))
            
            if mark_price > 0 and position_id in rapid_profit_system.active_positions:
                direction = local_pos.get('direction', 'BUY')
                entry_price = rapid_profit_system.active_positions[position_id]['entry_price']
                
                if direction == 'BUY':
                    profit_percent = ((mark_price - entry_price) / entry_price) * 100
                else:
                    profit_percent = ((entry_price - mark_price) / entry_price) * 100
                    
                rapid_profit_system.active_positions[position_id]['current_profit'] = profit_percent
                rapid_profit_system.active_positions[position_id]['unrealized_pnl'] = unrealized_pnl
                
        except Exception as e:
            logger.error(f"Error updating position info: {e}")
            
    async def _cleanup_position(self, position_id: str):
        """ポジションをクリーンアップ"""
        try:
            # rapid_profit_systemからクリーンアップ
            rapid_profit_system.cleanup_position(position_id)
            
            # aggressive_stop_systemからクリーンアップ
            aggressive_stop_system.cleanup_position(position_id)
            
            # conservative_profit_systemからクリーンアップ
            from ..trading.conservative.conservative_profit_system import conservative_profit_system
            from ..trading.conservative.conservative_stop_system import conservative_stop_system
            conservative_profit_system.cleanup_position(position_id)
            conservative_stop_system.cleanup_position(position_id)
            
            # trading_mode_managerから削除
            for mode in [TradingMode.SCALPING, TradingMode.CONSERVATIVE]:
                if position_id in trading_mode_manager.active_positions.get(mode, []):
                    trading_mode_manager.active_positions[mode].remove(position_id)
                    
            logger.info(f"Position {position_id} cleaned up successfully")
            
        except Exception as e:
            logger.error(f"Error cleaning up position {position_id}: {e}")
            
    async def force_sync(self):
        """強制的に同期を実行"""
        logger.info("Forcing position sync")
        await self.sync_positions()
        
    async def cleanup_all_positions(self):
        """すべてのポジションをクリーンアップ"""
        logger.info("Cleaning up all positions")
        
        # すべてのローカルポジションを取得
        local_positions = self._get_local_positions()
        
        # 各ポジションをクリーンアップ
        for position_id in list(local_positions.keys()):
            await self._cleanup_position(position_id)
            
        # trading_mode_managerのポジションもクリア
        trading_mode_manager.active_positions[TradingMode.SCALPING] = []
        trading_mode_manager.active_positions[TradingMode.CONSERVATIVE] = []
        
        logger.info("All positions cleaned up")
        
    async def _register_external_position(self, symbol: str, bybit_pos: Dict):
        """
        Bybitで検出された外部ポジションをローカルシステムに登録
        
        Parameters:
        -----------
        symbol : str
            シンボル（例: 'BTCUSDT'）
        bybit_pos : Dict
            Bybitのポジション情報
        """
        try:
            # ポジション情報を抽出
            side = bybit_pos.get('side', 'Buy')  # Buy or Sell
            direction = 'BUY' if side == 'Buy' else 'SELL'
            size = float(bybit_pos.get('size', 0))
            avg_price = float(bybit_pos.get('avgPrice', 0))
            mark_price = float(bybit_pos.get('markPrice', 0))
            unrealized_pnl = float(bybit_pos.get('unrealisedPnl', 0))
            
            if size <= 0 or avg_price <= 0:
                logger.warning(f"Invalid position data for {symbol}: size={size}, price={avg_price}")
                return
                
            # ポジションIDを生成（外部ポジション用のプレフィックス付き）
            position_id = f"external_{symbol}_{datetime.now().timestamp()}"
            
            # 現在の利益率を計算
            if direction == 'BUY':
                profit_percent = ((mark_price - avg_price) / avg_price) * 100
            else:
                profit_percent = ((avg_price - mark_price) / avg_price) * 100
                
            # rapid_profit_systemに登録
            rapid_profit_system.active_positions[position_id] = {
                'symbol': symbol,
                'entry_price': avg_price,
                'position_size': size,
                'direction': direction,
                'entry_time': datetime.now(),  # 実際のエントリー時刻は不明なので現在時刻
                'expected_duration': 10,  # デフォルト10分
                'confidence': 0.5,  # 外部ポジションなので中程度の信頼度
                'current_profit': profit_percent,
                'max_profit': max(0, profit_percent),
                'profit_locked': 0.0,
                'remaining_size': size,
                'unrealized_pnl': unrealized_pnl,
                'is_external': True  # 外部ポジションフラグ
            }
            
            # 基本的な利確・損切りレベルを設定
            if direction == 'BUY':
                tp1 = avg_price * 1.002  # 0.2%
                tp2 = avg_price * 1.003  # 0.3%
                tp3 = avg_price * 1.005  # 0.5%
                sl = avg_price * 0.998   # -0.2%
            else:
                tp1 = avg_price * 0.998  # 0.2%
                tp2 = avg_price * 0.997  # 0.3%
                tp3 = avg_price * 0.995  # 0.5%
                sl = avg_price * 1.002   # -0.2%
                
            # 利確ターゲットを設定
            rapid_profit_system.profit_targets[position_id] = [
                RapidProfitTarget(
                    target_price=tp1,
                    percentage=0.5,
                    priority=1,
                    trigger_type='PRICE',
                    conditions={}
                ),
                RapidProfitTarget(
                    target_price=tp2,
                    percentage=0.3,
                    priority=2,
                    trigger_type='PRICE',
                    conditions={}
                ),
                RapidProfitTarget(
                    target_price=tp3,
                    percentage=0.2,
                    priority=3,
                    trigger_type='PRICE',
                    conditions={}
                )
            ]
            
            # aggressive_stop_systemに登録
            aggressive_stop_system.active_positions[position_id] = {
                'symbol': symbol,
                'entry_price': avg_price,
                'direction': direction,
                'position_size': size,
                'confidence': 0.5,
                'expected_duration': 10
            }
            
            # 損切りレベルを設定（StopLossLevelクラスを使用）
            from ..trading.scalping.aggressive_stop_system import StopLossLevel
            
            aggressive_stop_system.active_stops[position_id] = [
                StopLossLevel(
                    stop_price=sl,
                    level_name='初期ストップ',
                    trigger_conditions=['PRICE'],
                    priority=1,
                    is_active=True
                )
            ]
            
            # trading_mode_managerに登録（スキャルピングモードとして）
            position_info = {
                'symbol': symbol,
                'direction': direction,
                'entry_price': avg_price,
                'quantity': size,
                'position_id': position_id,
                'signal_confidence': 0.5,
                'expected_duration': 10,
                'mode': 'scalping',
                'is_external': True
            }
            
            # スキャルピングモードのポジションリストに追加
            if position_id not in [p.get('position_id') for p in trading_mode_manager.active_positions.get(TradingMode.SCALPING, [])]:
                trading_mode_manager.active_positions[TradingMode.SCALPING].append(position_info)
                
            logger.info(f"External position registered: {position_id} - {symbol} {direction} {size} @ {avg_price}")
            
        except Exception as e:
            logger.error(f"Error registering external position {symbol}: {e}")

# グローバルインスタンス
position_sync_service = PositionSyncService()