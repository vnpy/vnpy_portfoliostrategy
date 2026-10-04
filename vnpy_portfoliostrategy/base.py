"""组合策略常量。"""

from enum import Enum
from .locale import _

APP_NAME: str = "PortfolioStrategy"


class EngineType(Enum):
    """引擎类型，区分实盘和回测。"""
    LIVE = _("实盘")
    BACKTESTING = _("回测")


EVENT_PORTFOLIO_LOG: str = "ePortfolioLog"
EVENT_PORTFOLIO_STRATEGY: str = "ePortfolioStrategy"
