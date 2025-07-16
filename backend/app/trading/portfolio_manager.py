"""
ポートフォリオマネージャー
複数通貨の同時取引とリスク管理
"""
import asyncio
import logging
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import json
from collections import defaultdict

logger = logging.getLogger(__name__)

@dataclass
class PortfolioPosition:
    """ポートフォリオポジション"""
    symbol: str
    side: str  # 'BUY' or 'SELL'
    entry_price: float
    current_price: float
    quantity: float
    stop_loss: float
    take_profit: List[float]
    entry_time: datetime
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    status: str = 'OPEN'  # 'OPEN', 'PARTIAL', 'CLOSED'

@dataclass
class PortfolioSettings:
    """ポートフォリオ設定"""
    max_concurrent_positions: int = 15  # 本番用：15ポジションまで拡張
    max_position_per_symbol: int = 2  # 本番用：同一通貨で2ポジションまで
    max_portfolio_risk: float = 0.10  # 本番用：10%に拡張（より多くのポジションを保有可能）
    max_single_position_risk: float = 0.008  # 本番用：0.8%に調整（15ポジション時のバランス）
    max_correlation_positions: int = 3  # 本番用：相関通貨を3まで
    rebalance_interval_minutes: int = 60
    
class PortfolioManager:
    """
    ポートフォリオマネージャー
    複数通貨の同時取引とリスク管理を担当
    """
    
    def __init__(self, settings: Optional[PortfolioSettings] = None):
        self.settings = settings or PortfolioSettings()
        self.positions: Dict[str, List[PortfolioPosition]] = defaultdict(list)
        self.active_symbols: Set[str] = set()
        self.total_portfolio_value = 0.0
        self.total_risk_exposure = 0.0
        self.last_rebalance = datetime.now()
        # 統合ポジション管理（position_id -> position info）
        self.all_positions: Dict[str, Dict] = {}
        
        # 通貨グループ（相関の高い通貨）
        self.currency_groups = {
            'BTC_GROUP': ['BTCUSDT', 'BTCPERP'],
            'ETH_GROUP': ['ETHUSDT', 'ETHPERP'],
            'ALT_GROUP': ['BNBUSDT', 'SOLUSDT', 'ADAUSDT', 'AVAXUSDT', 'ATOMUSDT'],
            'MEME_GROUP': ['DOGEUSDT', 'SHIBUSDT'],
            'DEFI_GROUP': ['LINKUSDT', 'UNIUSDT', 'AAVEUSDT'],
            'LAYER1_GROUP': ['DOTUSDT', 'NEARUSDT', 'ALGOUSDT', 'FTMUSDT'],
            'STORAGE_GROUP': ['FILUSDT', 'ICPUSDT'],
            'LEGACY_GROUP': ['LTCUSDT', 'XRPUSDT', 'VETUSDT']
        }
        
    async def can_open_position(
        self,
        symbol: str,
        risk_amount: float,
        position_size: float
    ) -> Dict[str, any]:
        """
        新しいポジションを開けるかチェック
        
        Returns:
        --------
        Dict : {
            'allowed': bool,
            'reason': str,
            'available_risk': float,
            'recommended_size': float
        }
        """
        try:
            # 最大同時ポジション数チェック
            total_positions = sum(len(pos_list) for pos_list in self.positions.values())
            if total_positions >= self.settings.max_concurrent_positions:
                return {
                    'allowed': False,
                    'reason': f'最大同時ポジション数({self.settings.max_concurrent_positions})に達しています',
                    'available_risk': 0,
                    'recommended_size': 0
                }
            
            # シンボルごとの最大ポジション数チェック
            symbol_positions = len(self.positions.get(symbol, []))
            if symbol_positions >= self.settings.max_position_per_symbol:
                return {
                    'allowed': False,
                    'reason': f'{symbol}の最大ポジション数({self.settings.max_position_per_symbol})に達しています',
                    'available_risk': 0,
                    'recommended_size': 0
                }
            
            # ポートフォリオ全体のリスクチェック
            current_risk = self._calculate_portfolio_risk()
            available_risk = (self.settings.max_portfolio_risk * self.total_portfolio_value) - current_risk
            
            if risk_amount > available_risk:
                return {
                    'allowed': False,
                    'reason': f'ポートフォリオリスク上限を超えます（利用可能: ${available_risk:.2f}）',
                    'available_risk': available_risk,
                    'recommended_size': position_size * (available_risk / risk_amount)
                }
            
            # 相関通貨グループのチェック
            group_check = self._check_correlation_limit(symbol)
            if not group_check['allowed']:
                return group_check
            
            return {
                'allowed': True,
                'reason': 'ポジション開設可能',
                'available_risk': available_risk,
                'recommended_size': position_size
            }
            
        except Exception as e:
            logger.error(f"Position check failed: {e}")
            return {
                'allowed': False,
                'reason': f'エラー: {str(e)}',
                'available_risk': 0,
                'recommended_size': 0
            }
    
    def add_position(self, position: PortfolioPosition):
        """ポジションを追加"""
        self.positions[position.symbol].append(position)
        self.active_symbols.add(position.symbol)
        logger.info(f"Position added: {position.symbol} {position.side} {position.quantity} @ {position.entry_price}")
        
    def update_position(
        self,
        symbol: str,
        current_price: float,
        partial_close_qty: Optional[float] = None
    ):
        """ポジションを更新"""
        if symbol not in self.positions:
            return
        
        for position in self.positions[symbol]:
            if position.status == 'OPEN':
                # 未実現損益を更新
                if position.side == 'BUY':
                    position.unrealized_pnl = (current_price - position.entry_price) * position.quantity
                else:
                    position.unrealized_pnl = (position.entry_price - current_price) * position.quantity
                
                position.current_price = current_price
                
                # 部分決済の処理
                if partial_close_qty and partial_close_qty > 0:
                    closed_pnl = position.unrealized_pnl * (partial_close_qty / position.quantity)
                    position.realized_pnl += closed_pnl
                    position.quantity -= partial_close_qty
                    
                    if position.quantity <= 0:
                        position.status = 'CLOSED'
                    else:
                        position.status = 'PARTIAL'
    
    def close_position(self, symbol: str, position_index: int = 0):
        """ポジションをクローズ"""
        if symbol in self.positions and len(self.positions[symbol]) > position_index:
            position = self.positions[symbol][position_index]
            position.status = 'CLOSED'
            position.realized_pnl += position.unrealized_pnl
            position.unrealized_pnl = 0
            
            # クローズされたポジションを削除
            self.positions[symbol].pop(position_index)
            
            # すべてのポジションがクローズされた場合
            if not self.positions[symbol]:
                del self.positions[symbol]
                self.active_symbols.discard(symbol)
            
            logger.info(f"Position closed: {symbol}, PnL: ${position.realized_pnl:.2f}")
    
    def get_portfolio_summary(self) -> Dict:
        """ポートフォリオサマリーを取得"""
        total_unrealized_pnl = 0
        total_realized_pnl = 0
        total_positions = 0
        positions_by_status = {'OPEN': 0, 'PARTIAL': 0, 'CLOSED': 0}
        
        for symbol_positions in self.positions.values():
            for position in symbol_positions:
                total_positions += 1
                total_unrealized_pnl += position.unrealized_pnl
                total_realized_pnl += position.realized_pnl
                positions_by_status[position.status] += 1
        
        # total_portfolio_valueが0の場合はデフォルト値を使用
        portfolio_value = self.total_portfolio_value if self.total_portfolio_value > 0 else 230700  # 6ポジション × 平均38450
        risk_exposure = self._calculate_portfolio_risk()
        risk_utilization = (risk_exposure / (self.settings.max_portfolio_risk * portfolio_value) * 100) if portfolio_value > 0 else 0
        
        return {
            'total_positions': total_positions,
            'active_symbols': len(self.active_symbols),
            'total_unrealized_pnl': round(total_unrealized_pnl, 2),
            'total_realized_pnl': round(total_realized_pnl, 2),
            'total_pnl': round(total_unrealized_pnl + total_realized_pnl, 2),
            'positions_by_status': positions_by_status,
            'risk_exposure': round(risk_exposure, 2),
            'risk_utilization': round(risk_utilization, 2)
        }
    
    def get_symbol_allocation(self) -> Dict[str, Dict]:
        """シンボルごとの配分を取得"""
        allocation = {}
        
        for symbol, positions in self.positions.items():
            total_value = sum(p.quantity * p.current_price for p in positions if p.status != 'CLOSED')
            total_risk = sum(abs(p.entry_price - p.stop_loss) * p.quantity for p in positions if p.status != 'CLOSED')
            
            allocation[symbol] = {
                'position_count': len([p for p in positions if p.status != 'CLOSED']),
                'total_value': round(total_value, 2),
                'total_risk': round(total_risk, 2),
                'percentage_of_portfolio': round(total_value / self.total_portfolio_value * 100, 2) if self.total_portfolio_value > 0 else 0
            }
        
        return allocation
    
    async def rebalance_portfolio(self):
        """ポートフォリオをリバランス"""
        try:
            current_time = datetime.now()
            
            # リバランス間隔チェック
            if (current_time - self.last_rebalance).total_seconds() < self.settings.rebalance_interval_minutes * 60:
                return
            
            logger.info("Starting portfolio rebalance...")
            
            # リスクの高いポジションを特定
            high_risk_positions = []
            for symbol, positions in self.positions.items():
                for i, position in enumerate(positions):
                    if position.status == 'OPEN':
                        position_risk = abs(position.current_price - position.stop_loss) * position.quantity
                        if position_risk > self.settings.max_single_position_risk * self.total_portfolio_value:
                            high_risk_positions.append((symbol, i, position_risk))
            
            # リスクの高い順にソート
            high_risk_positions.sort(key=lambda x: x[2], reverse=True)
            
            # 必要に応じてポジションを削減
            for symbol, index, risk in high_risk_positions:
                if self._calculate_portfolio_risk() <= self.settings.max_portfolio_risk * self.total_portfolio_value:
                    break
                
                # ポジションサイズを削減（50%）
                position = self.positions[symbol][index]
                reduce_qty = position.quantity * 0.5
                self.update_position(symbol, position.current_price, reduce_qty)
                logger.info(f"Reduced position: {symbol} by {reduce_qty} units")
            
            self.last_rebalance = current_time
            logger.info("Portfolio rebalance completed")
            
        except Exception as e:
            logger.error(f"Portfolio rebalance failed: {e}")
    
    def _calculate_portfolio_risk(self) -> float:
        """ポートフォリオ全体のリスクを計算"""
        total_risk = 0
        
        for positions in self.positions.values():
            for position in positions:
                if position.status != 'CLOSED':
                    # ストップロスまでの距離 × 数量
                    position_risk = abs(position.current_price - position.stop_loss) * position.quantity
                    total_risk += position_risk
        
        return total_risk
    
    def _check_correlation_limit(self, symbol: str) -> Dict:
        """相関通貨グループの制限をチェック"""
        # シンボルが属するグループを特定
        symbol_group = None
        for group_name, symbols in self.currency_groups.items():
            if symbol in symbols:
                symbol_group = group_name
                break
        
        if not symbol_group:
            return {'allowed': True, 'reason': '相関グループなし'}
        
        # 同じグループのアクティブポジション数を数える
        group_positions = 0
        for active_symbol in self.active_symbols:
            if active_symbol in self.currency_groups[symbol_group]:
                group_positions += 1
        
        if group_positions >= self.settings.max_correlation_positions:
            return {
                'allowed': False,
                'reason': f'{symbol_group}の最大ポジション数({self.settings.max_correlation_positions})に達しています',
                'available_risk': 0,
                'recommended_size': 0
            }
        
        return {'allowed': True, 'reason': '相関グループ制限内'}
    
    def get_recommended_symbols(self, current_symbols: List[str]) -> List[str]:
        """推奨シンボルを取得（分散投資のため）"""
        recommended = []
        
        # 各グループから最低1つは推奨
        for group_name, symbols in self.currency_groups.items():
            group_has_position = any(s in self.active_symbols for s in symbols)
            
            if not group_has_position:
                # グループ内で取引可能なシンボルを推奨
                for symbol in symbols:
                    if symbol not in self.active_symbols and symbol in current_symbols:
                        recommended.append(symbol)
                        break
        
        return recommended
    
    def get_all_positions(self) -> Dict[str, Dict]:
        """
        全ポジション情報を取得（conservativeモードと統合）
        """
        # キャッシュをクリア
        self.all_positions.clear()
        
        # rapid_profit_systemのポジション
        from ..trading.scalping.rapid_profit_system import rapid_profit_system
        for position_id, pos in rapid_profit_system.active_positions.items():
            self.all_positions[position_id] = {
                **pos,
                'mode': 'scalping'
            }
        
        # conservative_profit_systemのポジション
        from ..trading.conservative.conservative_profit_system import conservative_profit_system
        for position_id, pos in conservative_profit_system.active_positions.items():
            self.all_positions[position_id] = {
                **pos,
                'mode': 'conservative'
            }
        
        return self.all_positions
    
    async def reset_portfolio(self):
        """
        ポートフォリオをリセット（全ポジションをクリア）
        手動取引後の状態不整合を解消するため
        """
        logger.warning("Resetting portfolio manager...")
        
        # ポートフォリオマネージャーの内部状態をクリア
        self.positions.clear()
        self.active_symbols.clear()
        self.all_positions.clear()
        self.total_portfolio_value = 0.0
        self.total_risk_exposure = 0.0
        self.last_rebalance = datetime.now()
        
        # rapid_profit_systemをクリア
        from ..trading.scalping.rapid_profit_system import rapid_profit_system
        rapid_profit_system.active_positions.clear()
        rapid_profit_system.profit_targets.clear()
        
        # aggressive_stop_systemをクリア
        from ..trading.scalping.aggressive_stop_system import aggressive_stop_system
        aggressive_stop_system.active_positions.clear()
        aggressive_stop_system.active_stops.clear()
        
        # conservative_profit_systemをクリア
        from ..trading.conservative.conservative_profit_system import conservative_profit_system
        conservative_profit_system.active_positions.clear()
        conservative_profit_system.profit_targets.clear()
        
        # conservative_stop_systemをクリア
        from ..trading.conservative.conservative_stop_system import conservative_stop_system
        conservative_stop_system.active_positions.clear()
        conservative_stop_system.active_stops.clear()
        
        # trading_mode_managerのポジションをクリア
        from .modes.trading_mode_manager import trading_mode_manager, TradingMode
        trading_mode_manager.active_positions[TradingMode.SCALPING] = []
        trading_mode_manager.active_positions[TradingMode.CONSERVATIVE] = []
        
        logger.info("Portfolio manager reset completed")

# グローバルインスタンス
portfolio_manager = PortfolioManager()