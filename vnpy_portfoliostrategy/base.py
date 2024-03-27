from enum import Enum
from .locale import _

APP_NAME = "PortfolioStrategy"


class EngineType(Enum):
    LIVE = _("实盘")
    BACKTESTING = _("回测")


EVENT_PORTFOLIO_LOG = "ePortfolioLog"
EVENT_PORTFOLIO_STRATEGY = "ePortfolioStrategy"
