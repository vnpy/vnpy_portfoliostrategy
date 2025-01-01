from vnpy.trader.object import TickData, BarData

from vnpy_portfoliostrategy import StrategyTemplate


class RepoStrategy(StrategyTemplate):
    """逆回购DEMO策略"""

    author = "用Python的交易员"

    repo_symbol: str = "204001.SSE"
    repo_volume: float = 1_000_000

    parameters = []
    variables = []

    def on_init(self) -> None:
        """策略初始化回调"""
        self.write_log("策略初始化")

        self.load_bars(1)

    def on_start(self) -> None:
        """策略启动回调"""
        self.write_log("策略启动")

    def on_stop(self) -> None:
        """策略停止回调"""
        self.write_log("策略停止")

    def on_tick(self, tick: TickData) -> None:
        """行情推送回调"""
        pass

    def on_bars(self, bars: dict[str, BarData]) -> None:
        """K线切片回调"""
        # 撤销之前未成交的委托
        self.cancel_all()

        # 获取K线
        bar: BarData = bars[self.repo_symbol]

        # 检查可用资金
        available_capital: float = self.get_available_capital()

        # 如果足够则卖出逆回购
        if available_capital >= self.repo_volume:
            # 固定以1的回购利率卖出，为了尽可能保证每天成交
            self.sell(
                self.repo_symbol,
                1,
                self.repo_volume
            )
