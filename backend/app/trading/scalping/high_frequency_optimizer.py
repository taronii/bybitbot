"""
高頻度取引最適化システム
レイテンシ最適化、実行効率化、リソース管理
"""
import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Deque
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import deque
import time
import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class ExecutionMetrics:
    """実行指標"""
    order_latency: float  # 注文レイテンシ（ms）
    fill_rate: float  # 約定率
    slippage: float  # スリッページ（%）
    execution_time: float  # 実行時間（ms）
    network_latency: float  # ネットワークレイテンシ（ms）
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class OptimizationConfig:
    """最適化設定"""
    max_concurrent_orders: int = 10
    order_batch_size: int = 5
    latency_threshold_ms: float = 50.0
    max_slippage_percent: float = 0.05
    retry_attempts: int = 3
    circuit_breaker_threshold: int = 5  # 連続失敗数
    cooldown_seconds: int = 30

@dataclass
class ResourceMonitor:
    """リソース監視"""
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    network_usage: float = 0.0
    active_connections: int = 0
    queue_size: int = 0
    last_update: datetime = field(default_factory=datetime.now)

class HighFrequencyOptimizer:
    """
    高頻度取引最適化システム
    レイテンシ最適化、実行効率化、リソース管理
    """
    
    def __init__(self):
        self.config = OptimizationConfig()
        
        # パフォーマンス追跡
        self.execution_history: Deque[ExecutionMetrics] = deque(maxlen=1000)
        self.latency_samples: Deque[float] = deque(maxlen=100)
        self.throughput_samples: Deque[int] = deque(maxlen=60)  # 1分間のサンプル
        
        # 実行キュー
        self.order_queue: asyncio.Queue = asyncio.Queue()
        self.priority_queue: asyncio.Queue = asyncio.Queue()
        
        # 状態管理
        self.circuit_breaker_active = False
        self.circuit_breaker_until = None
        self.consecutive_failures = 0
        self.active_orders: Dict[str, Dict] = {}
        
        # リソース監視
        self.resource_monitor = ResourceMonitor()
        
        # パフォーマンス統計
        self.performance_stats = {
            'total_orders': 0,
            'successful_orders': 0,
            'failed_orders': 0,
            'avg_latency': 0.0,
            'avg_slippage': 0.0,
            'throughput_per_minute': 0.0
        }
        
        # 最適化フラグ
        self.optimization_enabled = True
        
    async def optimize_order_execution(
        self,
        order_request: Dict,
        priority: str = 'normal'
    ) -> Dict:
        """
        注文実行の最適化
        
        Parameters:
        -----------
        order_request : Dict
            注文リクエスト
        priority : str
            優先度 ('high', 'normal', 'low')
            
        Returns:
        --------
        Dict : 実行結果
        """
        try:
            # サーキットブレーカーチェック
            if await self._check_circuit_breaker():
                return {
                    'success': False,
                    'error': 'Circuit breaker active',
                    'retry_after': self.circuit_breaker_until
                }
            
            # レイテンシチェック
            if not await self._check_latency_conditions():
                return {
                    'success': False,
                    'error': 'High latency detected',
                    'current_latency': self._get_current_latency()
                }
            
            # リソースチェック
            if not await self._check_resource_availability():
                return {
                    'success': False,
                    'error': 'Insufficient resources',
                    'resource_status': self.resource_monitor
                }
            
            # 実行開始時間記録
            start_time = time.time()
            
            # 優先度に基づくキューイング
            execution_result = await self._execute_optimized_order(
                order_request, priority, start_time
            )
            
            # メトリクス記録
            await self._record_execution_metrics(execution_result, start_time)
            
            # 統計更新
            await self._update_performance_stats(execution_result)
            
            return execution_result
            
        except Exception as e:
            logger.error(f"Order execution optimization failed: {e}")
            await self._handle_execution_failure(str(e))
            return {'success': False, 'error': str(e)}
    
    async def _execute_optimized_order(
        self,
        order_request: Dict,
        priority: str,
        start_time: float
    ) -> Dict:
        """最適化された注文実行"""
        try:
            order_id = order_request.get('order_id', f"order_{int(time.time() * 1000)}")
            
            # 注文前準備
            optimized_request = await self._optimize_order_params(order_request)
            
            # 実行戦略選択
            execution_strategy = await self._select_execution_strategy(
                optimized_request, priority
            )
            
            # 注文実行
            if execution_strategy == 'immediate':
                result = await self._execute_immediate_order(optimized_request)
            elif execution_strategy == 'batched':
                result = await self._execute_batched_order(optimized_request)
            elif execution_strategy == 'iceberg':
                result = await self._execute_iceberg_order(optimized_request)
            else:
                result = await self._execute_standard_order(optimized_request)
            
            # 実行時間計算
            execution_time = (time.time() - start_time) * 1000  # ms
            
            result.update({
                'order_id': order_id,
                'execution_time_ms': execution_time,
                'strategy_used': execution_strategy,
                'optimization_applied': True
            })
            
            return result
            
        except Exception as e:
            logger.error(f"Optimized order execution failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'order_id': order_request.get('order_id', 'unknown')
            }
    
    async def _optimize_order_params(self, order_request: Dict) -> Dict:
        """注文パラメータの最適化"""
        try:
            optimized = order_request.copy()
            
            # 価格最適化
            if 'price' in optimized:
                # 現在の板情報に基づく価格調整
                optimized_price = await self._optimize_order_price(
                    optimized['price'], 
                    optimized.get('side', 'BUY'),
                    optimized.get('symbol', 'BTCUSDT')
                )
                optimized['price'] = optimized_price
            
            # サイズ最適化
            if 'quantity' in optimized:
                optimized_quantity = await self._optimize_order_size(
                    optimized['quantity'],
                    optimized.get('symbol', 'BTCUSDT')
                )
                optimized['quantity'] = optimized_quantity
            
            # タイムアウト設定
            optimized['timeout'] = self._calculate_optimal_timeout(optimized)
            
            return optimized
            
        except Exception as e:
            logger.error(f"Order params optimization failed: {e}")
            return order_request
    
    async def _optimize_order_price(
        self, 
        price: float, 
        side: str, 
        symbol: str
    ) -> float:
        """注文価格の最適化"""
        try:
            # スプレッド分析
            spread_info = await self._analyze_spread(symbol)
            
            if spread_info['spread_percent'] > 0.05:  # 0.05%超
                # スプレッドが広い場合は中間価格に近づける
                mid_price = spread_info['mid_price']
                if side == 'BUY':
                    # ビッド価格に近づける
                    optimized_price = min(price, mid_price * 0.9995)  # 0.05%内側
                else:
                    # アスク価格に近づける
                    optimized_price = max(price, mid_price * 1.0005)  # 0.05%外側
                
                return optimized_price
            
            return price
            
        except Exception as e:
            logger.error(f"Price optimization failed: {e}")
            return price
    
    async def _optimize_order_size(self, quantity: float, symbol: str) -> float:
        """注文サイズの最適化"""
        try:
            # 流動性分析
            liquidity_info = await self._analyze_liquidity(symbol)
            
            # 最小取引単位チェック
            min_quantity = liquidity_info.get('min_quantity', 0.001)
            if quantity < min_quantity:
                return min_quantity
            
            # 最大推奨サイズチェック（流動性の10%以下）
            max_recommended = liquidity_info.get('available_liquidity', quantity) * 0.1
            if quantity > max_recommended:
                return max_recommended
            
            return quantity
            
        except Exception as e:
            logger.error(f"Size optimization failed: {e}")
            return quantity
    
    async def _select_execution_strategy(
        self, 
        order_request: Dict, 
        priority: str
    ) -> str:
        """実行戦略の選択"""
        try:
            order_size = order_request.get('quantity', 0)
            symbol = order_request.get('symbol', 'BTCUSDT')
            
            # 緊急度判定
            if priority == 'high':
                return 'immediate'
            
            # サイズ判定
            liquidity_info = await self._analyze_liquidity(symbol)
            available_liquidity = liquidity_info.get('available_liquidity', float('inf'))
            
            if order_size > available_liquidity * 0.2:  # 20%超
                return 'iceberg'  # 分割実行
            elif order_size > available_liquidity * 0.1:  # 10%超
                return 'batched'  # バッチ実行
            else:
                return 'standard'  # 標準実行
            
        except Exception as e:
            logger.error(f"Strategy selection failed: {e}")
            return 'standard'
    
    async def _execute_immediate_order(self, order_request: Dict) -> Dict:
        """即座実行"""
        try:
            # 最高優先度で実行
            result = await self._send_order_request(order_request, timeout=1.0)
            
            return {
                'success': result.get('success', False),
                'order_id': result.get('order_id'),
                'filled_quantity': result.get('filled_quantity', 0),
                'avg_price': result.get('avg_price', 0),
                'strategy': 'immediate'
            }
            
        except Exception as e:
            logger.error(f"Immediate execution failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _execute_batched_order(self, order_request: Dict) -> Dict:
        """バッチ実行"""
        try:
            # バッチキューに追加
            await self.order_queue.put(order_request)
            
            # バッチ処理を待機
            batch_result = await self._process_order_batch()
            
            return {
                'success': batch_result.get('success', False),
                'batch_id': batch_result.get('batch_id'),
                'orders_processed': batch_result.get('orders_processed', 0),
                'strategy': 'batched'
            }
            
        except Exception as e:
            logger.error(f"Batched execution failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _execute_iceberg_order(self, order_request: Dict) -> Dict:
        """アイスバーグ実行（分割実行）"""
        try:
            total_quantity = order_request['quantity']
            chunk_size = total_quantity / 5  # 5分割
            
            filled_quantity = 0
            total_cost = 0
            
            for i in range(5):
                chunk_request = order_request.copy()
                chunk_request['quantity'] = min(chunk_size, total_quantity - filled_quantity)
                
                chunk_result = await self._send_order_request(chunk_request, timeout=2.0)
                
                if chunk_result.get('success'):
                    filled_qty = chunk_result.get('filled_quantity', 0)
                    filled_quantity += filled_qty
                    total_cost += filled_qty * chunk_result.get('avg_price', 0)
                    
                    # 小休止
                    await asyncio.sleep(0.1)
                else:
                    break
            
            avg_price = total_cost / filled_quantity if filled_quantity > 0 else 0
            
            return {
                'success': filled_quantity > 0,
                'filled_quantity': filled_quantity,
                'avg_price': avg_price,
                'chunks_executed': i + 1,
                'strategy': 'iceberg'
            }
            
        except Exception as e:
            logger.error(f"Iceberg execution failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _execute_standard_order(self, order_request: Dict) -> Dict:
        """標準実行"""
        try:
            result = await self._send_order_request(order_request, timeout=5.0)
            
            return {
                'success': result.get('success', False),
                'order_id': result.get('order_id'),
                'filled_quantity': result.get('filled_quantity', 0),
                'avg_price': result.get('avg_price', 0),
                'strategy': 'standard'
            }
            
        except Exception as e:
            logger.error(f"Standard execution failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _send_order_request(
        self, 
        order_request: Dict, 
        timeout: float = 5.0
    ) -> Dict:
        """注文リクエスト送信（モック実装）"""
        try:
            # ネットワークレイテンシシミュレーション
            network_delay = np.random.uniform(0.01, 0.05)  # 10-50ms
            await asyncio.sleep(network_delay)
            
            # 成功率シミュレーション（95%）
            success = np.random.random() < 0.95
            
            if success:
                return {
                    'success': True,
                    'order_id': f"order_{int(time.time() * 1000)}",
                    'filled_quantity': order_request.get('quantity', 0),
                    'avg_price': order_request.get('price', 0),
                    'network_latency': network_delay * 1000  # ms
                }
            else:
                return {
                    'success': False,
                    'error': 'Order rejected by exchange',
                    'network_latency': network_delay * 1000
                }
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def _process_order_batch(self) -> Dict:
        """注文バッチ処理"""
        try:
            batch_orders = []
            
            # バッチサイズまで注文を収集（最大1秒待機）
            timeout = time.time() + 1.0
            while len(batch_orders) < self.config.order_batch_size and time.time() < timeout:
                try:
                    order = await asyncio.wait_for(self.order_queue.get(), timeout=0.1)
                    batch_orders.append(order)
                except asyncio.TimeoutError:
                    break
            
            if not batch_orders:
                return {'success': False, 'error': 'No orders in batch'}
            
            # バッチ実行
            batch_id = f"batch_{int(time.time() * 1000)}"
            processed_count = 0
            
            for order in batch_orders:
                result = await self._send_order_request(order, timeout=1.0)
                if result.get('success'):
                    processed_count += 1
            
            return {
                'success': processed_count > 0,
                'batch_id': batch_id,
                'orders_processed': processed_count,
                'total_orders': len(batch_orders)
            }
            
        except Exception as e:
            logger.error(f"Batch processing failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _analyze_spread(self, symbol: str) -> Dict:
        """スプレッド分析（モック実装）"""
        try:
            # モックデータ
            bid_price = 50000.0
            ask_price = 50010.0
            mid_price = (bid_price + ask_price) / 2
            spread_percent = ((ask_price - bid_price) / mid_price) * 100
            
            return {
                'bid_price': bid_price,
                'ask_price': ask_price,
                'mid_price': mid_price,
                'spread_percent': spread_percent
            }
            
        except Exception as e:
            logger.error(f"Spread analysis failed: {e}")
            return {
                'bid_price': 0,
                'ask_price': 0,
                'mid_price': 0,
                'spread_percent': 0.1
            }
    
    async def _analyze_liquidity(self, symbol: str) -> Dict:
        """流動性分析（モック実装）"""
        try:
            return {
                'available_liquidity': 100.0,  # BTC
                'min_quantity': 0.001,
                'depth_score': 0.85
            }
            
        except Exception as e:
            logger.error(f"Liquidity analysis failed: {e}")
            return {
                'available_liquidity': 1.0,
                'min_quantity': 0.001,
                'depth_score': 0.5
            }
    
    def _calculate_optimal_timeout(self, order_request: Dict) -> float:
        """最適タイムアウト計算"""
        try:
            base_timeout = 5.0  # 5秒
            
            # サイズに基づく調整
            quantity = order_request.get('quantity', 0)
            if quantity > 10:
                base_timeout *= 1.5
            elif quantity > 1:
                base_timeout *= 1.2
            
            # 現在のレイテンシに基づく調整
            current_latency = self._get_current_latency()
            if current_latency > 100:  # 100ms超
                base_timeout *= 1.5
            
            return min(base_timeout, 30.0)  # 最大30秒
            
        except Exception as e:
            logger.error(f"Timeout calculation failed: {e}")
            return 5.0
    
    async def _check_circuit_breaker(self) -> bool:
        """サーキットブレーカーチェック"""
        if self.circuit_breaker_active:
            if datetime.now() > self.circuit_breaker_until:
                self.circuit_breaker_active = False
                self.consecutive_failures = 0
                logger.info("Circuit breaker reset")
                return False
            return True
        return False
    
    async def _check_latency_conditions(self) -> bool:
        """レイテンシ条件チェック"""
        current_latency = self._get_current_latency()
        return current_latency < self.config.latency_threshold_ms
    
    async def _check_resource_availability(self) -> bool:
        """リソース可用性チェック"""
        await self._update_resource_monitor()
        
        return (
            self.resource_monitor.cpu_usage < 0.9 and
            self.resource_monitor.memory_usage < 0.9 and
            self.resource_monitor.queue_size < 100
        )
    
    def _get_current_latency(self) -> float:
        """現在のレイテンシ取得"""
        if self.latency_samples:
            return sum(self.latency_samples) / len(self.latency_samples)
        return 0.0
    
    async def _update_resource_monitor(self):
        """リソース監視更新"""
        try:
            # モック実装
            self.resource_monitor.cpu_usage = np.random.uniform(0.3, 0.7)
            self.resource_monitor.memory_usage = np.random.uniform(0.4, 0.8)
            self.resource_monitor.network_usage = np.random.uniform(0.2, 0.6)
            self.resource_monitor.active_connections = len(self.active_orders)
            self.resource_monitor.queue_size = self.order_queue.qsize()
            self.resource_monitor.last_update = datetime.now()
            
        except Exception as e:
            logger.error(f"Resource monitor update failed: {e}")
    
    async def _record_execution_metrics(self, result: Dict, start_time: float):
        """実行メトリクスの記録"""
        try:
            execution_time = (time.time() - start_time) * 1000  # ms
            
            metrics = ExecutionMetrics(
                order_latency=execution_time,
                fill_rate=1.0 if result.get('success') else 0.0,
                slippage=result.get('slippage_percent', 0.0),
                execution_time=execution_time,
                network_latency=result.get('network_latency', 0.0)
            )
            
            self.execution_history.append(metrics)
            self.latency_samples.append(execution_time)
            
        except Exception as e:
            logger.error(f"Metrics recording failed: {e}")
    
    async def _update_performance_stats(self, result: Dict):
        """パフォーマンス統計更新"""
        try:
            self.performance_stats['total_orders'] += 1
            
            if result.get('success'):
                self.performance_stats['successful_orders'] += 1
                self.consecutive_failures = 0
            else:
                self.performance_stats['failed_orders'] += 1
                await self._handle_execution_failure(result.get('error', 'Unknown error'))
            
            # 平均値更新
            if self.execution_history:
                self.performance_stats['avg_latency'] = sum(
                    m.order_latency for m in self.execution_history
                ) / len(self.execution_history)
                
                self.performance_stats['avg_slippage'] = sum(
                    m.slippage for m in self.execution_history
                ) / len(self.execution_history)
            
        except Exception as e:
            logger.error(f"Performance stats update failed: {e}")
    
    async def _handle_execution_failure(self, error: str):
        """実行失敗処理"""
        try:
            self.consecutive_failures += 1
            
            # サーキットブレーカー発動
            if self.consecutive_failures >= self.config.circuit_breaker_threshold:
                self.circuit_breaker_active = True
                self.circuit_breaker_until = datetime.now() + timedelta(
                    seconds=self.config.cooldown_seconds
                )
                logger.warning(f"Circuit breaker activated for {self.config.cooldown_seconds}s")
            
        except Exception as e:
            logger.error(f"Failure handling failed: {e}")
    
    def get_performance_report(self) -> Dict:
        """パフォーマンスレポート取得"""
        try:
            success_rate = 0
            if self.performance_stats['total_orders'] > 0:
                success_rate = (
                    self.performance_stats['successful_orders'] / 
                    self.performance_stats['total_orders']
                ) * 100
            
            return {
                'total_orders': self.performance_stats['total_orders'],
                'success_rate': success_rate,
                'avg_latency_ms': self.performance_stats['avg_latency'],
                'avg_slippage_percent': self.performance_stats['avg_slippage'],
                'current_latency_ms': self._get_current_latency(),
                'circuit_breaker_active': self.circuit_breaker_active,
                'consecutive_failures': self.consecutive_failures,
                'resource_status': {
                    'cpu_usage': self.resource_monitor.cpu_usage,
                    'memory_usage': self.resource_monitor.memory_usage,
                    'queue_size': self.resource_monitor.queue_size
                }
            }
            
        except Exception as e:
            logger.error(f"Performance report generation failed: {e}")
            return {'error': str(e)}

# グローバルインスタンス
hf_optimizer = HighFrequencyOptimizer()