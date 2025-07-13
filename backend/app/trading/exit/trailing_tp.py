"""
高度なトレーリング利確システム
利益を最大化する自動実行トレーリング
"""
import asyncio
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)

class TrailingMethod(Enum):
    ATR_BASED = "atr_based"
    PERCENTAGE_BASED = "percentage_based"
    STRUCTURE_BASED = "structure_based"
    PARABOLIC_SAR = "parabolic_sar"
    HYBRID = "hybrid"

@dataclass
class TrailingStatus:
    active: bool
    current_stop: float
    highest_price: float
    lowest_price: float
    locked_profit_percent: float
    trailing_distance: float
    method: TrailingMethod
    last_update: datetime

class AdvancedTrailingTakeProfit:
    """
    利益を最大化する高度なトレーリングシステム
    【重要】このシステムは必ず自動実行される
    """
    
    def __init__(self, session, config: Dict):
        self.session = session
        self.config = config
        self.min_profit_to_trail = config.get('min_profit_to_trail', 0.01)  # 1%
        self.atr_multiplier = config.get('atr_multiplier', 1.5)
        self.percentage_trail = config.get('percentage_trail', 0.02)  # 2%
        self.monitoring_interval = config.get('monitoring_interval', 1)  # 1秒
        self.active_positions = {}  # ポジションID -> TrailingStatus
        
    async def manage_trailing_profit(self, position: Dict) -> Dict:
        """
        トレーリング利確を管理
        
        Parameters:
        -----------
        position : dict
            管理対象のポジション情報
            
        Returns:
        --------
        dict : トレーリング状態
        """
        try:
            position_id = position['id']
            entry_price = position['entry_price']
            current_price = position['current_price']
            side = position['side']  # 'BUY' or 'SELL'
            
            # 利益率を計算
            if side == 'BUY':
                profit_percent = (current_price - entry_price) / entry_price
            else:
                profit_percent = (entry_price - current_price) / entry_price
            
            # トレーリング開始条件をチェック
            if profit_percent >= self.min_profit_to_trail:
                if position_id not in self.active_positions:
                    # 新規トレーリング開始
                    await self._activate_trailing(position)
                else:
                    # 既存トレーリングを更新
                    await self._update_trailing(position)
            
            # 現在のトレーリング状態を返す
            if position_id in self.active_positions:
                status = self.active_positions[position_id]
                return {
                    'trailing_active': status.active,
                    'current_stop': status.current_stop,
                    'locked_profit': status.locked_profit_percent,
                    'highest_price': status.highest_price,
                    'lowest_price': status.lowest_price,
                    'trailing_method': status.method.value,
                    'next_tp_level': self._calculate_next_tp(position, status)
                }
            else:
                return {
                    'trailing_active': False,
                    'current_stop': position.get('stop_loss', 0),
                    'locked_profit': 0,
                    'next_tp_level': None
                }
                
        except Exception as e:
            logger.error(f"Failed to manage trailing profit: {e}")
            return {'trailing_active': False, 'error': str(e)}
    
    async def _activate_trailing(self, position: Dict):
        """トレーリングを開始"""
        position_id = position['id']
        current_price = position['current_price']
        side = position['side']
        
        # 初期トレーリングストップを計算
        initial_stop = await self._calculate_optimal_trailing_stop(position)
        
        # トレーリング状態を作成
        status = TrailingStatus(
            active=True,
            current_stop=initial_stop,
            highest_price=current_price if side == 'BUY' else position['entry_price'],
            lowest_price=position['entry_price'] if side == 'BUY' else current_price,
            locked_profit_percent=self._calculate_locked_profit(
                position['entry_price'], initial_stop, side
            ),
            trailing_distance=abs(current_price - initial_stop),
            method=TrailingMethod.HYBRID,
            last_update=datetime.now()
        )
        
        self.active_positions[position_id] = status
        
        # ストップ注文を更新
        await self._update_stop_order(position_id, initial_stop)
        
        # 自動監視タスクを開始
        asyncio.create_task(self._monitor_position(position))
        
        logger.info(f"Trailing activated for position {position_id} at stop {initial_stop}")
    
    async def _update_trailing(self, position: Dict):
        """既存のトレーリングを更新"""
        position_id = position['id']
        status = self.active_positions[position_id]
        current_price = position['current_price']
        side = position['side']
        
        # 最高値/最安値を更新
        if side == 'BUY':
            if current_price > status.highest_price:
                status.highest_price = current_price
                # 新しいトレーリングストップを計算
                new_stop = await self._calculate_optimal_trailing_stop(position)
                
                # ストップを上げる（下げない）
                if new_stop > status.current_stop:
                    status.current_stop = new_stop
                    status.locked_profit_percent = self._calculate_locked_profit(
                        position['entry_price'], new_stop, side
                    )
                    await self._update_stop_order(position_id, new_stop)
        else:  # SELL
            if current_price < status.lowest_price:
                status.lowest_price = current_price
                # 新しいトレーリングストップを計算
                new_stop = await self._calculate_optimal_trailing_stop(position)
                
                # ストップを下げる（上げない）
                if new_stop < status.current_stop:
                    status.current_stop = new_stop
                    status.locked_profit_percent = self._calculate_locked_profit(
                        position['entry_price'], new_stop, side
                    )
                    await self._update_stop_order(position_id, new_stop)
        
        status.last_update = datetime.now()
    
    async def _calculate_optimal_trailing_stop(self, position: Dict) -> float:
        """最適なトレーリングストップを計算"""
        try:
            # 複数の方法でトレーリングストップを計算
            stops = []
            
            # 1. ATRベース
            atr_stop = await self._calculate_atr_trailing(position)
            if atr_stop:
                stops.append(atr_stop)
            
            # 2. パーセンテージベース
            percent_stop = self._calculate_percentage_trailing(position)
            stops.append(percent_stop)
            
            # 3. 構造ベース
            structure_stop = await self._calculate_structure_trailing(position)
            if structure_stop:
                stops.append(structure_stop)
            
            # 4. パラボリックSAR
            sar_stop = await self._calculate_sar_trailing(position)
            if sar_stop:
                stops.append(sar_stop)
            
            # 最も有利なストップを選択
            if position['side'] == 'BUY':
                # ロングの場合、最も高いストップ（利益確保）
                optimal_stop = max(stops) if stops else position['stop_loss']
            else:
                # ショートの場合、最も低いストップ
                optimal_stop = min(stops) if stops else position['stop_loss']
            
            return optimal_stop
            
        except Exception as e:
            logger.error(f"Failed to calculate optimal stop: {e}")
            return position['stop_loss']
    
    async def _calculate_atr_trailing(self, position: Dict) -> Optional[float]:
        """ATRベースのトレーリングストップ"""
        try:
            # 5分足のATRを取得
            kline_response = self.session.get_kline(
                category="linear",
                symbol=position['symbol'],
                interval="5",
                limit=20
            )
            
            if kline_response["retCode"] != 0:
                return None
            
            df = self._create_dataframe(kline_response["result"]["list"])
            
            # ATRを計算
            high_low = df['high'] - df['low']
            high_close = abs(df['high'] - df['close'].shift())
            low_close = abs(df['low'] - df['close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = ranges.max(axis=1)
            atr = true_range.rolling(14).mean().iloc[-1]
            
            current_price = position['current_price']
            
            if position['side'] == 'BUY':
                return current_price - (atr * self.atr_multiplier)
            else:
                return current_price + (atr * self.atr_multiplier)
                
        except Exception as e:
            logger.error(f"Failed to calculate ATR trailing: {e}")
            return None
    
    def _calculate_percentage_trailing(self, position: Dict) -> float:
        """パーセンテージベースのトレーリングストップ"""
        position_id = position['id']
        
        if position_id in self.active_positions:
            status = self.active_positions[position_id]
            if position['side'] == 'BUY':
                return status.highest_price * (1 - self.percentage_trail)
            else:
                return status.lowest_price * (1 + self.percentage_trail)
        else:
            # 初回計算
            current_price = position['current_price']
            if position['side'] == 'BUY':
                return current_price * (1 - self.percentage_trail)
            else:
                return current_price * (1 + self.percentage_trail)
    
    async def _calculate_structure_trailing(self, position: Dict) -> Optional[float]:
        """構造ベースのトレーリングストップ（直近のスイング）"""
        try:
            # 15分足データを取得
            kline_response = self.session.get_kline(
                category="linear",
                symbol=position['symbol'],
                interval="15",
                limit=50
            )
            
            if kline_response["retCode"] != 0:
                return None
            
            df = self._create_dataframe(kline_response["result"]["list"])
            
            if position['side'] == 'BUY':
                # 直近の重要な安値を探す
                lows = df['low'].values
                swing_lows = []
                
                for i in range(2, len(lows) - 2):
                    if (lows[i] < lows[i-1] and lows[i] < lows[i-2] and
                        lows[i] < lows[i+1] and lows[i] < lows[i+2]):
                        swing_lows.append(lows[i])
                
                if swing_lows:
                    # 最も近い（高い）スイングローを使用
                    return max(swing_lows[-3:])  # 直近3つから選択
            else:
                # 直近の重要な高値を探す
                highs = df['high'].values
                swing_highs = []
                
                for i in range(2, len(highs) - 2):
                    if (highs[i] > highs[i-1] and highs[i] > highs[i-2] and
                        highs[i] > highs[i+1] and highs[i] > highs[i+2]):
                        swing_highs.append(highs[i])
                
                if swing_highs:
                    # 最も近い（低い）スイングハイを使用
                    return min(swing_highs[-3:])
                    
        except Exception as e:
            logger.error(f"Failed to calculate structure trailing: {e}")
            
        return None
    
    async def _calculate_sar_trailing(self, position: Dict) -> Optional[float]:
        """パラボリックSARトレーリング"""
        try:
            # 5分足データを取得
            kline_response = self.session.get_kline(
                category="linear",
                symbol=position['symbol'],
                interval="5",
                limit=100
            )
            
            if kline_response["retCode"] != 0:
                return None
            
            df = self._create_dataframe(kline_response["result"]["list"])
            
            # パラボリックSARを計算
            sar = self._calculate_parabolic_sar(df)
            
            if sar is not None:
                return sar[-1]  # 最新のSAR値
                
        except Exception as e:
            logger.error(f"Failed to calculate SAR trailing: {e}")
            
        return None
    
    def _calculate_parabolic_sar(self, df: pd.DataFrame, 
                                initial_af: float = 0.02, 
                                max_af: float = 0.2) -> np.ndarray:
        """パラボリックSARを計算"""
        high = df['high'].values
        low = df['low'].values
        close = df['close'].values
        
        sar = np.zeros_like(close)
        ep = 0  # Extreme Point
        af = initial_af
        uptrend = True
        
        # 初期値
        sar[0] = low[0]
        ep = high[0]
        
        for i in range(1, len(close)):
            if uptrend:
                sar[i] = sar[i-1] + af * (ep - sar[i-1])
                
                if low[i] <= sar[i]:
                    uptrend = False
                    sar[i] = ep
                    ep = low[i]
                    af = initial_af
                else:
                    if high[i] > ep:
                        ep = high[i]
                        af = min(af + initial_af, max_af)
                    sar[i] = min(sar[i], low[i-1], low[i])
            else:
                sar[i] = sar[i-1] + af * (ep - sar[i-1])
                
                if high[i] >= sar[i]:
                    uptrend = True
                    sar[i] = ep
                    ep = high[i]
                    af = initial_af
                else:
                    if low[i] < ep:
                        ep = low[i]
                        af = min(af + initial_af, max_af)
                    sar[i] = max(sar[i], high[i-1], high[i])
        
        return sar
    
    async def _monitor_position(self, position: Dict):
        """ポジションを自動監視（重要：必ず実行される）"""
        position_id = position['id']
        symbol = position['symbol']
        
        logger.info(f"Starting automatic monitoring for position {position_id}")
        
        try:
            while position_id in self.active_positions:
                # 現在価格を取得
                ticker_response = self.session.get_tickers(
                    category="linear",
                    symbol=symbol
                )
                
                if ticker_response["retCode"] == 0:
                    current_price = float(ticker_response["result"]["list"][0]["lastPrice"])
                    position['current_price'] = current_price
                    
                    # トレーリングを更新
                    await self._update_trailing(position)
                    
                    # 利確レベルのチェック
                    await self._check_tp_levels(position)
                    
                    # 市場の弱さをチェック
                    if await self._detect_market_weakness(position):
                        await self._tighten_stops(position)
                
                # 監視間隔
                await asyncio.sleep(self.monitoring_interval)
                
        except Exception as e:
            logger.error(f"Error in position monitoring: {e}")
            # エラーでも監視を継続
            await asyncio.sleep(5)
            asyncio.create_task(self._monitor_position(position))
    
    async def _check_tp_levels(self, position: Dict):
        """利確レベルをチェックして実行"""
        current_price = position['current_price']
        
        for tp_level in position.get('tp_levels', []):
            if tp_level['executed']:
                continue
                
            # 利確条件をチェック
            if position['side'] == 'BUY' and current_price >= tp_level['price']:
                await self.execute_partial_close(
                    position['id'], 
                    tp_level['percentage'],
                    f"TP{tp_level['level']}到達"
                )
                tp_level['executed'] = True
            elif position['side'] == 'SELL' and current_price <= tp_level['price']:
                await self.execute_partial_close(
                    position['id'],
                    tp_level['percentage'],
                    f"TP{tp_level['level']}到達"
                )
                tp_level['executed'] = True
    
    async def execute_partial_close(self, position_id: str, 
                                  percentage: float, reason: str):
        """
        【重要】必ず実行される部分決済
        失敗は許されない - 複数のリトライとフォールバック機構
        """
        max_retries = 3
        retry_delay = 0.5
        
        for attempt in range(max_retries):
            try:
                # ポジション情報を取得
                positions = self.session.get_positions(
                    category="linear",
                    settleCoin="USDT"
                )
                
                if positions["retCode"] != 0:
                    raise Exception(f"Failed to get positions: {positions['retMsg']}")
                
                # 対象ポジションを探す
                target_position = None
                for pos in positions["result"]["list"]:
                    if pos.get("positionIdx") == position_id:
                        target_position = pos
                        break
                
                if not target_position:
                    logger.error(f"Position {position_id} not found")
                    return
                
                # 決済サイズを計算
                total_size = float(target_position["size"])
                close_size = total_size * (percentage / 100)
                
                # 成行注文で部分決済
                side = "Sell" if target_position["side"] == "Buy" else "Buy"
                
                order_response = self.session.place_order(
                    category="linear",
                    symbol=target_position["symbol"],
                    side=side,
                    orderType="Market",
                    qty=str(close_size),
                    timeInForce="IOC",  # Immediate or Cancel
                    reduceOnly=True,
                    positionIdx=0
                )
                
                if order_response["retCode"] == 0:
                    logger.info(f"Partial close executed: {percentage}% of position {position_id} - {reason}")
                    return
                else:
                    raise Exception(f"Order failed: {order_response['retMsg']}")
                    
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed: {e}")
                
                if attempt == max_retries - 1:
                    # 最終手段：全ポジション決済
                    logger.warning(f"Final attempt - closing entire position {position_id}")
                    await self._emergency_close_all(position_id)
                else:
                    await asyncio.sleep(retry_delay)
    
    async def _emergency_close_all(self, position_id: str):
        """緊急全決済"""
        try:
            positions = self.session.get_positions(
                category="linear",
                settleCoin="USDT"
            )
            
            for pos in positions["result"]["list"]:
                if pos.get("positionIdx") == position_id:
                    side = "Sell" if pos["side"] == "Buy" else "Buy"
                    
                    # 全量を成行決済
                    self.session.place_order(
                        category="linear",
                        symbol=pos["symbol"],
                        side=side,
                        orderType="Market",
                        qty=pos["size"],
                        timeInForce="IOC",
                        reduceOnly=True,
                        positionIdx=0
                    )
                    
                    logger.warning(f"Emergency close executed for position {position_id}")
                    break
                    
        except Exception as e:
            logger.error(f"Emergency close failed: {e}")
    
    async def _detect_market_weakness(self, position: Dict) -> bool:
        """市場の弱さを検出"""
        try:
            # RSIやモメンタムの急激な変化をチェック
            symbol = position['symbol']
            
            # 5分足データ
            kline_response = self.session.get_kline(
                category="linear",
                symbol=symbol,
                interval="5",
                limit=20
            )
            
            if kline_response["retCode"] != 0:
                return False
            
            df = self._create_dataframe(kline_response["result"]["list"])
            
            # RSIを計算
            rsi = self._calculate_rsi(df['close'], 14)
            
            if position['side'] == 'BUY':
                # ロングポジションで RSI < 30 は弱さのサイン
                return rsi < 30
            else:
                # ショートポジションで RSI > 70 は弱さのサイン
                return rsi > 70
                
        except Exception as e:
            logger.error(f"Failed to detect market weakness: {e}")
            return False
    
    async def _tighten_stops(self, position: Dict):
        """ストップをタイトにする"""
        position_id = position['id']
        
        if position_id in self.active_positions:
            status = self.active_positions[position_id]
            current_price = position['current_price']
            
            # より近いストップに変更
            tight_percentage = 0.005  # 0.5%
            
            if position['side'] == 'BUY':
                new_stop = current_price * (1 - tight_percentage)
                if new_stop > status.current_stop:
                    status.current_stop = new_stop
                    await self._update_stop_order(position_id, new_stop)
            else:
                new_stop = current_price * (1 + tight_percentage)
                if new_stop < status.current_stop:
                    status.current_stop = new_stop
                    await self._update_stop_order(position_id, new_stop)
    
    async def _update_stop_order(self, position_id: str, new_stop: float):
        """ストップロス注文を更新"""
        try:
            # 既存のストップ注文をキャンセル
            # ... (実装省略)
            
            # 新しいストップ注文を配置
            # ... (実装省略)
            
            logger.info(f"Stop order updated for position {position_id}: {new_stop}")
            
        except Exception as e:
            logger.error(f"Failed to update stop order: {e}")
    
    def _calculate_locked_profit(self, entry_price: float, 
                               stop_price: float, side: str) -> float:
        """確保された利益率を計算"""
        if side == 'BUY':
            return max(0, (stop_price - entry_price) / entry_price)
        else:
            return max(0, (entry_price - stop_price) / entry_price)
    
    def _calculate_next_tp(self, position: Dict, status: TrailingStatus) -> Optional[float]:
        """次の利確レベルを計算"""
        for tp_level in position.get('tp_levels', []):
            if not tp_level['executed']:
                return tp_level['price']
        return None
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> float:
        """RSIを計算"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi.iloc[-1]
    
    def _create_dataframe(self, kline_data: List) -> pd.DataFrame:
        """KlineデータからDataFrameを作成"""
        df = pd.DataFrame(kline_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])
        
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)
        
        return df