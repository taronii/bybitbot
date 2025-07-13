"""
スマートマネー分析
機関投資家の動きを追跡
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging
from datetime import datetime, timedelta
import asyncio

logger = logging.getLogger(__name__)

class SmartMoneyDirection(Enum):
    BUYING = "BUYING"
    SELLING = "SELLING"
    NEUTRAL = "NEUTRAL"

@dataclass
class VolumeNode:
    price: float
    volume: float
    percentage: float

@dataclass
class OrderFlowData:
    buy_volume: float
    sell_volume: float
    delta: float
    cumulative_delta: float
    imbalance: float

class SmartMoneyAnalyzer:
    """
    機関投資家の動きを追跡
    """
    
    def __init__(self, session):
        self.session = session
        self.volume_spike_threshold = 3.0  # 平均の3倍
        self.large_order_threshold = 100000  # $100,000
        
    async def detect_smart_money(self, symbol: str) -> Dict:
        """
        スマートマネーの動きを検出
        
        Parameters:
        -----------
        symbol : str
            取引シンボル（例: "BTCUSDT"）
            
        Returns:
        --------
        Dict : スマートマネー分析結果
        """
        try:
            # 並列で各種分析を実行
            tasks = [
                self._analyze_large_orders(symbol),
                self._analyze_order_flow(symbol),
                self._analyze_volume_profile(symbol),
                self._check_exchange_premium(symbol)
            ]
            
            results = await asyncio.gather(*tasks)
            
            large_order_analysis = results[0]
            order_flow_analysis = results[1]
            volume_profile = results[2]
            exchange_premium = results[3]
            
            # スマートマネーの方向を判定
            direction = self._determine_smart_money_direction(
                large_order_analysis, 
                order_flow_analysis
            )
            
            return {
                'smart_money_direction': direction,
                'volume_profile': volume_profile,
                'order_flow_imbalance': order_flow_analysis['imbalance'],
                'exchange_premium': exchange_premium,
                'large_orders': large_order_analysis,
                'order_flow': order_flow_analysis,
                'confidence': self._calculate_confidence(
                    large_order_analysis, 
                    order_flow_analysis
                )
            }
            
        except Exception as e:
            logger.error(f"Failed to detect smart money: {e}")
            return self._get_default_analysis()
    
    async def _analyze_large_orders(self, symbol: str) -> Dict:
        """大口注文を検出"""
        try:
            # 最近の取引データを取得
            trades_response = self.session.get_public_trading_records(
                category="linear",
                symbol=symbol,
                limit=1000
            )
            
            if trades_response["retCode"] != 0:
                logger.error(f"Failed to fetch trades: {trades_response['retMsg']}")
                return {}
            
            trades = trades_response["result"]["list"]
            
            # DataFrameに変換
            df = pd.DataFrame(trades)
            df['value'] = pd.to_numeric(df['price']) * pd.to_numeric(df['size'])
            df['time'] = pd.to_datetime(df['time'], unit='ms')
            
            # 大口注文を検出
            large_orders = df[df['value'] > self.large_order_threshold]
            
            # 出来高分析
            volume_ma = df['size'].rolling(window=100).mean().iloc[-1]
            recent_volume = df['size'].iloc[-20:].sum()
            volume_spike = recent_volume > (volume_ma * 20 * self.volume_spike_threshold)
            
            # アキュムレーション/ディストリビューションの検出
            # 価格が横ばいなのに出来高が多い
            price_std = df['price'].iloc[-20:].std() / df['price'].iloc[-20:].mean()
            accumulation = volume_spike and price_std < 0.001
            
            # ウィック分析（大口の指値注文による反発）
            # ここでは簡易的に実装
            wicks = self._analyze_wicks(symbol)
            
            return {
                'large_orders_count': len(large_orders),
                'large_orders_value': large_orders['value'].sum() if len(large_orders) > 0 else 0,
                'volume_spike': volume_spike,
                'accumulation_detected': accumulation,
                'rejection_wicks': wicks,
                'buy_pressure': len(large_orders[large_orders['side'] == 'Buy']),
                'sell_pressure': len(large_orders[large_orders['side'] == 'Sell'])
            }
            
        except Exception as e:
            logger.error(f"Error analyzing large orders: {e}")
            return {}
    
    async def _analyze_order_flow(self, symbol: str) -> Dict:
        """オーダーフロー分析"""
        try:
            # 最近の取引データからデルタを計算
            trades_response = self.session.get_public_trading_records(
                category="linear",
                symbol=symbol,
                limit=500
            )
            
            if trades_response["retCode"] != 0:
                return {'imbalance': 0.0}
            
            trades = trades_response["result"]["list"]
            
            buy_volume = sum(float(t['size']) for t in trades if t['side'] == 'Buy')
            sell_volume = sum(float(t['size']) for t in trades if t['side'] == 'Sell')
            
            # デルタとインバランス計算
            delta = buy_volume - sell_volume
            total_volume = buy_volume + sell_volume
            imbalance = delta / total_volume if total_volume > 0 else 0
            
            # CVD（累積ボリュームデルタ）の計算
            cvd = 0
            cvd_history = []
            for trade in sorted(trades, key=lambda x: x['time']):
                if trade['side'] == 'Buy':
                    cvd += float(trade['size'])
                else:
                    cvd -= float(trade['size'])
                cvd_history.append(cvd)
            
            # CVDのトレンド（上昇/下降）
            cvd_trend = 1 if len(cvd_history) > 1 and cvd_history[-1] > cvd_history[0] else -1
            
            return {
                'buy_volume': buy_volume,
                'sell_volume': sell_volume,
                'delta': delta,
                'cumulative_delta': cvd,
                'imbalance': imbalance,
                'cvd_trend': cvd_trend,
                'buy_ratio': buy_volume / total_volume if total_volume > 0 else 0.5
            }
            
        except Exception as e:
            logger.error(f"Error analyzing order flow: {e}")
            return {'imbalance': 0.0}
    
    async def _analyze_volume_profile(self, symbol: str) -> Dict:
        """ボリュームプロファイル分析"""
        try:
            # 1時間足のデータを取得
            kline_response = self.session.get_kline(
                category="linear",
                symbol=symbol,
                interval="60",
                limit=24
            )
            
            if kline_response["retCode"] != 0:
                return {}
            
            candles = kline_response["result"]["list"]
            
            # 価格帯別の出来高を集計
            volume_by_price = {}
            for candle in candles:
                price = float(candle[4])  # close
                volume = float(candle[5])
                
                # 価格を丸める（0.1%単位）
                price_level = round(price / 100) * 100
                
                if price_level in volume_by_price:
                    volume_by_price[price_level] += volume
                else:
                    volume_by_price[price_level] = volume
            
            # POC（Point of Control）を特定
            if volume_by_price:
                poc = max(volume_by_price, key=volume_by_price.get)
                total_volume = sum(volume_by_price.values())
                
                # 高出来高ノードを特定
                high_volume_nodes = []
                for price, volume in volume_by_price.items():
                    percentage = (volume / total_volume) * 100
                    if percentage > 10:  # 全体の10%以上
                        high_volume_nodes.append(VolumeNode(
                            price=price,
                            volume=volume,
                            percentage=percentage
                        ))
                
                return {
                    'poc': poc,
                    'high_volume_nodes': sorted(high_volume_nodes, key=lambda x: x.volume, reverse=True),
                    'volume_distribution': volume_by_price
                }
            
            return {}
            
        except Exception as e:
            logger.error(f"Error analyzing volume profile: {e}")
            return {}
    
    async def _check_exchange_premium(self, symbol: str) -> Dict:
        """取引所間の価格差をチェック"""
        try:
            # 現在のBybit価格
            ticker_response = self.session.get_tickers(
                category="linear",
                symbol=symbol
            )
            
            if ticker_response["retCode"] != 0:
                return {}
            
            bybit_price = float(ticker_response["result"]["list"][0]["lastPrice"])
            
            # 他の取引所の価格は実際のAPIが必要なため、ここでは仮実装
            # 実際の実装では、Binance、Coinbase等のAPIを使用
            
            # 仮の価格差
            premium_data = {
                'bybit': bybit_price,
                'premium_percentage': 0.0,  # 実際は他取引所との比較
                'leading_exchange': 'BYBIT',
                'arbitrage_opportunity': False
            }
            
            return premium_data
            
        except Exception as e:
            logger.error(f"Error checking exchange premium: {e}")
            return {}
    
    def _analyze_wicks(self, symbol: str) -> List[Dict]:
        """ウィック分析（簡易版）"""
        # 実際の実装では、ローソク足データから長いウィックを検出
        return []
    
    def _determine_smart_money_direction(self, large_orders: Dict, order_flow: Dict) -> SmartMoneyDirection:
        """スマートマネーの方向を判定"""
        if not large_orders or not order_flow:
            return SmartMoneyDirection.NEUTRAL
        
        # 大口の買い圧力と売り圧力を比較
        buy_pressure = large_orders.get('buy_pressure', 0)
        sell_pressure = large_orders.get('sell_pressure', 0)
        
        # オーダーフローのインバランス
        imbalance = order_flow.get('imbalance', 0)
        
        # 総合判定
        if buy_pressure > sell_pressure * 1.5 and imbalance > 0.2:
            return SmartMoneyDirection.BUYING
        elif sell_pressure > buy_pressure * 1.5 and imbalance < -0.2:
            return SmartMoneyDirection.SELLING
        
        return SmartMoneyDirection.NEUTRAL
    
    def _calculate_confidence(self, large_orders: Dict, order_flow: Dict) -> float:
        """信頼度を計算"""
        confidence_factors = []
        
        # 大口注文の明確さ
        if large_orders.get('large_orders_count', 0) > 5:
            confidence_factors.append(0.9)
        elif large_orders.get('large_orders_count', 0) > 2:
            confidence_factors.append(0.7)
        else:
            confidence_factors.append(0.4)
        
        # オーダーフローの偏り
        imbalance = abs(order_flow.get('imbalance', 0))
        confidence_factors.append(min(1.0, imbalance * 2))
        
        # アキュムレーションの検出
        if large_orders.get('accumulation_detected', False):
            confidence_factors.append(0.8)
        
        return sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.5
    
    def _get_default_analysis(self) -> Dict:
        """デフォルトの分析結果"""
        return {
            'smart_money_direction': SmartMoneyDirection.NEUTRAL,
            'volume_profile': {},
            'order_flow_imbalance': 0.0,
            'exchange_premium': {},
            'large_orders': {},
            'order_flow': {'imbalance': 0.0},
            'confidence': 0.0
        }