"""
パフォーマンストラッキングシステム
スキャルピング専用の詳細パフォーマンス分析と最適化提案
"""
import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict, deque
import numpy as np
import json

logger = logging.getLogger(__name__)

@dataclass
class TradeRecord:
    """取引記録"""
    trade_id: str
    symbol: str
    direction: str  # 'BUY' or 'SELL'
    entry_price: float
    exit_price: float
    quantity: float
    entry_time: datetime
    exit_time: datetime
    profit_loss: float  # USDT
    profit_percent: float
    fees: float
    slippage: float
    holding_duration: int  # 秒
    entry_signal_confidence: float
    exit_reason: str
    strategy_used: str
    market_conditions: Dict

@dataclass
class PerformanceMetrics:
    """パフォーマンス指標"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_profit_loss: float = 0.0
    total_fees: float = 0.0
    net_profit: float = 0.0
    avg_profit_per_trade: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    current_drawdown: float = 0.0
    avg_holding_time: float = 0.0  # 秒
    trades_per_hour: float = 0.0
    return_on_capital: float = 0.0

@dataclass
class RiskMetrics:
    """リスク指標"""
    value_at_risk_95: float = 0.0  # 95% VaR
    conditional_var: float = 0.0  # CVaR
    max_consecutive_losses: int = 0
    current_consecutive_losses: int = 0
    volatility: float = 0.0
    beta: float = 0.0
    correlation_with_market: float = 0.0
    tail_ratio: float = 0.0

@dataclass
class OptimizationSuggestion:
    """最適化提案"""
    category: str  # 'ENTRY', 'EXIT', 'RISK', 'TIMING'
    priority: str  # 'HIGH', 'MEDIUM', 'LOW'
    description: str
    expected_improvement: float  # %
    confidence: float  # 0.0-1.0
    implementation_difficulty: str  # 'EASY', 'MEDIUM', 'HARD'

class PerformanceTracker:
    """
    パフォーマンストラッキングシステム
    スキャルピング専用の詳細パフォーマンス分析と最適化提案
    """
    
    def __init__(self):
        # 取引記録
        self.trade_history: List[TradeRecord] = []
        self.daily_records: Dict[str, List[TradeRecord]] = defaultdict(list)
        
        # パフォーマンス指標
        self.performance_metrics = PerformanceMetrics()
        self.risk_metrics = RiskMetrics()
        
        # リアルタイム追跡
        self.realtime_pnl: deque = deque(maxlen=1440)  # 24時間分（分単位）
        self.equity_curve: deque = deque(maxlen=10080)  # 1週間分（分単位）
        self.drawdown_history: deque = deque(maxlen=1440)
        
        # 戦略別パフォーマンス
        self.strategy_performance: Dict[str, PerformanceMetrics] = {}
        
        # 最適化提案
        self.optimization_suggestions: List[OptimizationSuggestion] = []
        
        # 設定
        self.initial_capital = 10000.0  # USDT
        self.current_capital = self.initial_capital
        self.high_water_mark = self.initial_capital
        
    async def record_trade(
        self,
        trade_id: str,
        symbol: str,
        direction: str,
        entry_price: float,
        exit_price: float,
        quantity: float,
        entry_time: datetime,
        exit_time: datetime,
        fees: float,
        slippage: float,
        entry_signal_confidence: float,
        exit_reason: str,
        strategy_used: str,
        market_conditions: Dict
    ) -> Dict:
        """
        取引記録の追加
        
        Returns:
        --------
        Dict : 記録結果と即座パフォーマンス更新
        """
        try:
            # 損益計算
            if direction == 'BUY':
                profit_loss = (exit_price - entry_price) * quantity - fees
            else:
                profit_loss = (entry_price - exit_price) * quantity - fees
            
            profit_percent = (profit_loss / (entry_price * quantity)) * 100
            holding_duration = int((exit_time - entry_time).total_seconds())
            
            # 取引記録作成
            trade_record = TradeRecord(
                trade_id=trade_id,
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                exit_price=exit_price,
                quantity=quantity,
                entry_time=entry_time,
                exit_time=exit_time,
                profit_loss=profit_loss,
                profit_percent=profit_percent,
                fees=fees,
                slippage=slippage,
                holding_duration=holding_duration,
                entry_signal_confidence=entry_signal_confidence,
                exit_reason=exit_reason,
                strategy_used=strategy_used,
                market_conditions=market_conditions
            )
            
            # 記録追加
            self.trade_history.append(trade_record)
            
            # 日別記録
            date_key = exit_time.strftime('%Y-%m-%d')
            self.daily_records[date_key].append(trade_record)
            
            # 資本更新
            self.current_capital += profit_loss
            
            # リアルタイム追跡更新
            await self._update_realtime_tracking(trade_record)
            
            # パフォーマンス指標更新
            await self._update_performance_metrics()
            
            # 戦略別パフォーマンス更新
            await self._update_strategy_performance(trade_record)
            
            # 最適化提案生成
            await self._generate_optimization_suggestions()
            
            logger.info(f"Trade recorded: {trade_id}, P/L: {profit_loss:.2f} USDT")
            
            return {
                'success': True,
                'trade_id': trade_id,
                'profit_loss': profit_loss,
                'profit_percent': profit_percent,
                'current_capital': self.current_capital,
                'total_trades': len(self.trade_history)
            }
            
        except Exception as e:
            logger.error(f"Trade recording failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _update_realtime_tracking(self, trade_record: TradeRecord):
        """リアルタイム追跡更新"""
        try:
            # PnL追跡
            self.realtime_pnl.append({
                'timestamp': trade_record.exit_time,
                'pnl': trade_record.profit_loss,
                'cumulative_pnl': self.current_capital - self.initial_capital
            })
            
            # エクイティカーブ
            self.equity_curve.append({
                'timestamp': trade_record.exit_time,
                'equity': self.current_capital
            })
            
            # ドローダウン計算
            if self.current_capital > self.high_water_mark:
                self.high_water_mark = self.current_capital
            
            current_drawdown = ((self.high_water_mark - self.current_capital) / self.high_water_mark) * 100
            
            self.drawdown_history.append({
                'timestamp': trade_record.exit_time,
                'drawdown': current_drawdown
            })
            
        except Exception as e:
            logger.error(f"Realtime tracking update failed: {e}")
    
    async def _update_performance_metrics(self):
        """パフォーマンス指標更新"""
        try:
            if not self.trade_history:
                return
            
            metrics = self.performance_metrics
            
            # 基本統計
            metrics.total_trades = len(self.trade_history)
            
            winning_trades = [t for t in self.trade_history if t.profit_loss > 0]
            losing_trades = [t for t in self.trade_history if t.profit_loss < 0]
            
            metrics.winning_trades = len(winning_trades)
            metrics.losing_trades = len(losing_trades)
            metrics.win_rate = (metrics.winning_trades / metrics.total_trades) * 100 if metrics.total_trades > 0 else 0
            
            # 損益統計
            metrics.total_profit_loss = sum(t.profit_loss for t in self.trade_history)
            metrics.total_fees = sum(t.fees for t in self.trade_history)
            metrics.net_profit = metrics.total_profit_loss
            metrics.avg_profit_per_trade = metrics.net_profit / metrics.total_trades if metrics.total_trades > 0 else 0
            
            # 勝敗分析
            if winning_trades:
                metrics.avg_win = sum(t.profit_loss for t in winning_trades) / len(winning_trades)
            if losing_trades:
                metrics.avg_loss = sum(t.profit_loss for t in losing_trades) / len(losing_trades)
            
            # プロフィットファクター
            gross_profit = sum(t.profit_loss for t in winning_trades) if winning_trades else 0
            gross_loss = abs(sum(t.profit_loss for t in losing_trades)) if losing_trades else 1
            metrics.profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
            
            # 時間分析
            if self.trade_history:
                avg_holding_seconds = sum(t.holding_duration for t in self.trade_history) / len(self.trade_history)
                metrics.avg_holding_time = avg_holding_seconds
                
                # 時間あたり取引数
                if len(self.trade_history) >= 2:
                    time_span = (self.trade_history[-1].exit_time - self.trade_history[0].exit_time).total_seconds() / 3600
                    metrics.trades_per_hour = len(self.trade_history) / time_span if time_span > 0 else 0
            
            # ドローダウン
            if self.drawdown_history:
                metrics.max_drawdown = max(d['drawdown'] for d in self.drawdown_history)
                metrics.current_drawdown = self.drawdown_history[-1]['drawdown'] if self.drawdown_history else 0
            
            # リターン
            metrics.return_on_capital = ((self.current_capital - self.initial_capital) / self.initial_capital) * 100
            
            # シャープレシオ
            if len(self.trade_history) >= 10:
                returns = [t.profit_percent for t in self.trade_history]
                if np.std(returns) > 0:
                    metrics.sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252)  # 年率化
            
        except Exception as e:
            logger.error(f"Performance metrics update failed: {e}")
    
    async def _update_strategy_performance(self, trade_record: TradeRecord):
        """戦略別パフォーマンス更新"""
        try:
            strategy = trade_record.strategy_used
            
            if strategy not in self.strategy_performance:
                self.strategy_performance[strategy] = PerformanceMetrics()
            
            # 戦略別取引記録取得
            strategy_trades = [t for t in self.trade_history if t.strategy_used == strategy]
            
            if strategy_trades:
                metrics = self.strategy_performance[strategy]
                
                # 基本統計更新
                metrics.total_trades = len(strategy_trades)
                winning_trades = [t for t in strategy_trades if t.profit_loss > 0]
                metrics.winning_trades = len(winning_trades)
                metrics.losing_trades = metrics.total_trades - metrics.winning_trades
                metrics.win_rate = (metrics.winning_trades / metrics.total_trades) * 100
                
                # 損益更新
                metrics.total_profit_loss = sum(t.profit_loss for t in strategy_trades)
                metrics.avg_profit_per_trade = metrics.total_profit_loss / metrics.total_trades
                
                if winning_trades:
                    metrics.avg_win = sum(t.profit_loss for t in winning_trades) / len(winning_trades)
                
                losing_trades = [t for t in strategy_trades if t.profit_loss < 0]
                if losing_trades:
                    metrics.avg_loss = sum(t.profit_loss for t in losing_trades) / len(losing_trades)
            
        except Exception as e:
            logger.error(f"Strategy performance update failed: {e}")
    
    async def _generate_optimization_suggestions(self):
        """最適化提案生成"""
        try:
            suggestions = []
            
            if len(self.trade_history) < 10:
                return  # データ不足
            
            # 勝率分析
            if self.performance_metrics.win_rate < 60:
                suggestions.append(OptimizationSuggestion(
                    category='ENTRY',
                    priority='HIGH',
                    description='エントリーシグナルの信頼度閾値を上げることを検討してください',
                    expected_improvement=10.0,
                    confidence=0.8,
                    implementation_difficulty='EASY'
                ))
            
            # 保有時間分析
            if self.performance_metrics.avg_holding_time > 600:  # 10分超
                suggestions.append(OptimizationSuggestion(
                    category='EXIT',
                    priority='MEDIUM',
                    description='利確目標を下げて保有時間を短縮することを検討してください',
                    expected_improvement=5.0,
                    confidence=0.6,
                    implementation_difficulty='MEDIUM'
                ))
            
            # ドローダウン分析
            if self.performance_metrics.max_drawdown > 10:
                suggestions.append(OptimizationSuggestion(
                    category='RISK',
                    priority='HIGH',
                    description='ポジションサイズを減らしてリスクを軽減してください',
                    expected_improvement=15.0,
                    confidence=0.9,
                    implementation_difficulty='EASY'
                ))
            
            # 戦略別分析
            best_strategy = None
            best_performance = -float('inf')
            
            for strategy, metrics in self.strategy_performance.items():
                if metrics.total_trades >= 5 and metrics.avg_profit_per_trade > best_performance:
                    best_performance = metrics.avg_profit_per_trade
                    best_strategy = strategy
            
            if best_strategy and len(self.strategy_performance) > 1:
                suggestions.append(OptimizationSuggestion(
                    category='TIMING',
                    priority='MEDIUM',
                    description=f'{best_strategy}戦略の使用頻度を上げることを検討してください',
                    expected_improvement=8.0,
                    confidence=0.7,
                    implementation_difficulty='MEDIUM'
                ))
            
            # 時間帯分析
            hourly_performance = defaultdict(list)
            for trade in self.trade_history:
                hour = trade.exit_time.hour
                hourly_performance[hour].append(trade.profit_loss)
            
            if len(hourly_performance) >= 4:
                best_hours = sorted(
                    hourly_performance.items(),
                    key=lambda x: sum(x[1]) / len(x[1]),
                    reverse=True
                )[:3]
                
                if best_hours:
                    best_hour_range = f"{best_hours[0][0]}-{(best_hours[0][0] + 2) % 24}時"
                    suggestions.append(OptimizationSuggestion(
                        category='TIMING',
                        priority='LOW',
                        description=f'{best_hour_range}の取引に集中することを検討してください',
                        expected_improvement=3.0,
                        confidence=0.5,
                        implementation_difficulty='EASY'
                    ))
            
            # 提案を優先度でソート
            self.optimization_suggestions = sorted(
                suggestions,
                key=lambda x: {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}[x.priority],
                reverse=True
            )
            
        except Exception as e:
            logger.error(f"Optimization suggestions generation failed: {e}")
    
    def get_performance_summary(self) -> Dict:
        """パフォーマンスサマリー取得"""
        try:
            return {
                'overview': {
                    'total_trades': self.performance_metrics.total_trades,
                    'win_rate': round(self.performance_metrics.win_rate, 2),
                    'total_profit_loss': round(self.performance_metrics.total_profit_loss, 2),
                    'net_profit': round(self.performance_metrics.net_profit, 2),
                    'return_on_capital': round(self.performance_metrics.return_on_capital, 2),
                    'current_capital': round(self.current_capital, 2)
                },
                'risk_metrics': {
                    'max_drawdown': round(self.performance_metrics.max_drawdown, 2),
                    'current_drawdown': round(self.performance_metrics.current_drawdown, 2),
                    'sharpe_ratio': round(self.performance_metrics.sharpe_ratio, 2),
                    'profit_factor': round(self.performance_metrics.profit_factor, 2)
                },
                'trading_stats': {
                    'avg_profit_per_trade': round(self.performance_metrics.avg_profit_per_trade, 2),
                    'avg_win': round(self.performance_metrics.avg_win, 2),
                    'avg_loss': round(self.performance_metrics.avg_loss, 2),
                    'avg_holding_time_minutes': round(self.performance_metrics.avg_holding_time / 60, 1),
                    'trades_per_hour': round(self.performance_metrics.trades_per_hour, 2)
                },
                'strategy_breakdown': {
                    strategy: {
                        'trades': metrics.total_trades,
                        'win_rate': round(metrics.win_rate, 2),
                        'avg_profit': round(metrics.avg_profit_per_trade, 2)
                    }
                    for strategy, metrics in self.strategy_performance.items()
                }
            }
            
        except Exception as e:
            logger.error(f"Performance summary generation failed: {e}")
            return {'error': str(e)}
    
    def get_optimization_suggestions(self) -> List[Dict]:
        """最適化提案取得"""
        try:
            return [
                {
                    'category': suggestion.category,
                    'priority': suggestion.priority,
                    'description': suggestion.description,
                    'expected_improvement': suggestion.expected_improvement,
                    'confidence': suggestion.confidence,
                    'difficulty': suggestion.implementation_difficulty
                }
                for suggestion in self.optimization_suggestions
            ]
            
        except Exception as e:
            logger.error(f"Optimization suggestions retrieval failed: {e}")
            return []
    
    def get_equity_curve_data(self, period_hours: int = 24) -> List[Dict]:
        """エクイティカーブデータ取得"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=period_hours)
            
            return [
                {
                    'timestamp': point['timestamp'].isoformat(),
                    'equity': point['equity']
                }
                for point in self.equity_curve
                if point['timestamp'] >= cutoff_time
            ]
            
        except Exception as e:
            logger.error(f"Equity curve data retrieval failed: {e}")
            return []
    
    def get_trade_history(self, limit: int = 100) -> List[Dict]:
        """取引履歴取得"""
        try:
            recent_trades = self.trade_history[-limit:] if len(self.trade_history) > limit else self.trade_history
            
            return [
                {
                    'trade_id': trade.trade_id,
                    'symbol': trade.symbol,
                    'direction': trade.direction,
                    'entry_price': trade.entry_price,
                    'exit_price': trade.exit_price,
                    'quantity': trade.quantity,
                    'profit_loss': round(trade.profit_loss, 2),
                    'profit_percent': round(trade.profit_percent, 2),
                    'holding_duration_minutes': round(trade.holding_duration / 60, 1),
                    'exit_reason': trade.exit_reason,
                    'strategy': trade.strategy_used,
                    'entry_time': trade.entry_time.isoformat(),
                    'exit_time': trade.exit_time.isoformat()
                }
                for trade in recent_trades
            ]
            
        except Exception as e:
            logger.error(f"Trade history retrieval failed: {e}")
            return []

# グローバルインスタンス
performance_tracker = PerformanceTracker()