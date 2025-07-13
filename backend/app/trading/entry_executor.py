"""
エントリー実行エンジン
実際の注文実行と管理
"""
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from pybit.unified_trading import HTTP

logger = logging.getLogger(__name__)

class SmartEntryExecutor:
    """
    スマートエントリー実行エンジン
    """
    
    def __init__(self, client: HTTP, config: Dict[str, Any]):
        self.client = client
        self.config = config
        self.max_slippage = config.get("max_slippage", 0.001)
        self.max_position_size = config.get("max_position_size", 10000)
        self.risk_per_trade = config.get("risk_per_trade", 0.02)
        self.symbol_info_cache = {}
        
    async def execute_entry(
        self,
        symbol: str,
        signal: Any,
        account_balance: float
    ) -> Dict[str, Any]:
        """
        エントリーを実行
        
        Parameters:
        -----------
        symbol : str
            取引シンボル
        signal : EntrySignal
            エントリーシグナル
        account_balance : float
            アカウント残高
            
        Returns:
        --------
        Dict : 実行結果
        """
        try:
            # WAITシグナルは実行しない
            if signal.action.value == "WAIT":
                return {
                    "executed": False,
                    "reason": "WAIT signal - no action taken"
                }
            
            # ポジションサイズを計算
            position_size = self._calculate_position_size(
                account_balance,
                signal.entry_price,
                signal.stop_loss,
                signal.position_size_multiplier,
                symbol
            )
            
            # 注文タイプを決定
            side = "Buy" if signal.action.value == "BUY" else "Sell"
            
            # リミット注文を実行
            order_result = self._place_order(
                symbol=symbol,
                side=side,
                qty=position_size,
                price=signal.entry_price,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit[0] if signal.take_profit else None
            )
            
            if order_result["success"]:
                logger.info(f"Order placed successfully: {symbol} {side} {position_size} @ {signal.entry_price}")
                
                # ストップロスとテイクプロフィット注文を設定
                if signal.stop_loss:
                    self._set_stop_loss(symbol, side, position_size, signal.stop_loss)
                
                if signal.take_profit:
                    for i, tp in enumerate(signal.take_profit):
                        # 分割利確の設定（全体の1/3ずつ）
                        tp_qty = position_size / len(signal.take_profit)
                        self._set_take_profit(symbol, side, tp_qty, tp)
                
                return {
                    "executed": True,
                    "order_id": order_result["order_id"],
                    "entry_price": signal.entry_price,
                    "position_size": position_size,
                    "side": side,
                    "stop_loss": signal.stop_loss,
                    "take_profit": signal.take_profit
                }
            else:
                return {
                    "executed": False,
                    "error": order_result.get("error", "Order placement failed")
                }
                
        except Exception as e:
            logger.error(f"Entry execution failed: {e}")
            return {
                "executed": False,
                "error": str(e)
            }
    
    def _calculate_position_size(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss: float,
        size_multiplier: float,
        symbol: str = None
    ) -> float:
        """ポジションサイズを計算"""
        # リスク金額を計算
        risk_amount = account_balance * self.risk_per_trade
        
        # ストップロスまでの価格差
        stop_loss_distance = abs(entry_price - stop_loss)
        stop_loss_percent = stop_loss_distance / entry_price
        
        # 基本ポジションサイズ
        base_position_value = risk_amount / stop_loss_percent
        
        # サイズ倍率を適用
        position_value = base_position_value * size_multiplier
        
        # 最大ポジションサイズで制限
        position_value = min(position_value, self.max_position_size)
        
        # 数量に変換（USDTベース）
        quantity = position_value / entry_price
        
        # シンボル情報を取得して適切な数量に調整
        return self._adjust_quantity_precision(quantity, symbol)
    
    def _place_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> Dict[str, Any]:
        """注文を実行"""
        try:
            # 注文パラメータ
            order_params = {
                "category": "linear",
                "symbol": symbol,
                "side": side,
                "orderType": "Limit",
                "qty": str(qty),
                "price": str(price),
                "timeInForce": "GTC",  # Good Till Cancel
                "positionIdx": 0,      # ヘッジモードではない
                "reduceOnly": False
            }
            
            # 注文を実行
            response = self.client.place_order(**order_params)
            
            if response["retCode"] == 0:
                return {
                    "success": True,
                    "order_id": response["result"]["orderId"],
                    "response": response
                }
            else:
                return {
                    "success": False,
                    "error": f"Order failed: {response['retMsg']}"
                }
                
        except Exception as e:
            logger.error(f"Order placement error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _set_stop_loss(self, symbol: str, side: str, qty: float, stop_price: float):
        """ストップロス注文を設定"""
        try:
            # ストップロスの方向を決定
            sl_side = "Sell" if side == "Buy" else "Buy"
            
            sl_params = {
                "category": "linear",
                "symbol": symbol,
                "side": sl_side,
                "orderType": "Market",
                "qty": str(qty),
                "triggerPrice": str(stop_price),
                "triggerDirection": 2 if side == "Buy" else 1,  # 2: 下方向, 1: 上方向
                "triggerBy": "LastPrice",
                "timeInForce": "IOC",  # Immediate or Cancel
                "positionIdx": 0,
                "reduceOnly": True
            }
            
            response = self.client.place_order(**sl_params)
            
            if response["retCode"] == 0:
                logger.info(f"Stop loss set at {stop_price}")
            else:
                logger.error(f"Stop loss failed: {response['retMsg']}")
                
        except Exception as e:
            logger.error(f"Stop loss setting error: {e}")
    
    def _set_take_profit(self, symbol: str, side: str, qty: float, tp_price: float):
        """テイクプロフィット注文を設定"""
        try:
            # テイクプロフィットの方向を決定
            tp_side = "Sell" if side == "Buy" else "Buy"
            
            tp_params = {
                "category": "linear",
                "symbol": symbol,
                "side": tp_side,
                "orderType": "Limit",
                "qty": str(qty),
                "price": str(tp_price),
                "timeInForce": "GTC",
                "positionIdx": 0,
                "reduceOnly": True
            }
            
            response = self.client.place_order(**tp_params)
            
            if response["retCode"] == 0:
                logger.info(f"Take profit set at {tp_price}")
            else:
                logger.error(f"Take profit failed: {response['retMsg']}")
                
        except Exception as e:
            logger.error(f"Take profit setting error: {e}")
    
    def _get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        """シンボル情報を取得（キャッシュ付き）"""
        if symbol not in self.symbol_info_cache:
            try:
                response = self.client.get_instruments_info(
                    category="linear",
                    symbol=symbol
                )
                if response["retCode"] == 0 and response["result"]["list"]:
                    symbol_data = response["result"]["list"][0]
                    # lotSizeFilterから情報を取得
                    lot_size_filter = symbol_data.get("lotSizeFilter", {})
                    self.symbol_info_cache[symbol] = {
                        "minOrderQty": lot_size_filter.get("minOrderQty", "0.001"),
                        "qtyStep": lot_size_filter.get("qtyStep", "0.001"),
                        "maxOrderQty": lot_size_filter.get("maxOrderQty", "1000000")
                    }
                    logger.info(f"Symbol info for {symbol}: {self.symbol_info_cache[symbol]}")
            except Exception as e:
                logger.error(f"Failed to get symbol info for {symbol}: {e}")
                return None
        
        return self.symbol_info_cache.get(symbol)
    
    def _adjust_quantity_precision(self, quantity: float, symbol: str) -> float:
        """シンボルの仕様に合わせて数量を調整"""
        logger.info(f"Adjusting quantity for {symbol}: Original quantity = {quantity}")
        
        # シンボル情報を取得
        symbol_info = self._get_symbol_info(symbol)
        
        if symbol_info:
            # 最小取引数量
            min_qty = float(symbol_info.get("minOrderQty", 0.001))
            # 数量の刻み幅
            qty_step = float(symbol_info.get("qtyStep", 0.001))
            
            logger.info(f"{symbol} - Min qty: {min_qty}, Qty step: {qty_step}")
            
            # 最小取引数量以上に調整
            if quantity < min_qty:
                quantity = min_qty
                logger.info(f"Adjusted to minimum quantity: {quantity}")
            
            # 刻み幅に合わせて調整
            if qty_step > 0:
                # 刻み幅の倍数に丸める
                adjusted = round(quantity / qty_step) * qty_step
                
                # 小数点の桁数を計算して最終的な丸めを実行
                if '.' in str(qty_step):
                    decimal_places = len(str(qty_step).split('.')[-1])
                else:
                    decimal_places = 0
                
                quantity = round(adjusted, decimal_places)
                logger.info(f"Adjusted to qty step: {quantity} (decimal places: {decimal_places})")
        else:
            # シンボル情報が取得できない場合のデフォルト処理
            logger.warning(f"Using default precision for {symbol}")
            if symbol in ['BTCUSDT', 'ETHUSDT']:
                # BTC, ETHは小数点以下2桁（0.01刻み）
                quantity = round(quantity, 2)
            elif symbol in ['XRPUSDT', 'DOGEUSDT', 'ADAUSDT', 'MATICUSDT']:
                # これらは整数
                quantity = round(quantity, 0)
            else:
                # その他は小数点以下1桁
                quantity = round(quantity, 1)
        
        logger.info(f"Final adjusted quantity for {symbol}: {quantity}")
        return quantity