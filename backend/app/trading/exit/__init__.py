# Exit module initialization
from .dynamic_tp import DynamicTakeProfitCalculator
from .trailing_tp import AdvancedTrailingTakeProfit
from .profit_protection import ProfitProtectionSystem
from .market_adaptive_tp import MarketAdaptiveTakeProfit
from .guaranteed_execution import GuaranteedExecutionSystem

__all__ = [
    'DynamicTakeProfitCalculator',
    'AdvancedTrailingTakeProfit',
    'ProfitProtectionSystem',
    'MarketAdaptiveTakeProfit',
    'GuaranteedExecutionSystem'
]