"""
Defines constants and objects used in PortfolioStrategy App.
"""

from enum import Enum


APP_NAME: str = "PortfolioStrategy"


class EngineType(Enum):
    LIVE: str = "实盘"
    BACKTESTING: str = "回测"


EVENT_PORTFOLIO_LOG: str = "ePortfolioLog"
EVENT_PORTFOLIO_STRATEGY: str = "ePortfolioStrategy"
