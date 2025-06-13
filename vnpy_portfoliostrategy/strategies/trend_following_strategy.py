from datetime import datetime

from vnpy.trader.utility import ArrayManager
from vnpy.trader.object import TickData, BarData
from vnpy.trader.constant import Direction

from vnpy_portfoliostrategy import StrategyTemplate, StrategyEngine
from vnpy_portfoliostrategy.utility import PortfolioBarGenerator


class TrendFollowingStrategy(StrategyTemplate):
    """ATR-RSI趋势跟踪策略"""

    author = "用Python的交易员"

    atr_window = 22
    atr_ma_window = 10
    rsi_window = 5
    rsi_entry = 16
    trailing_percent = 0.8
    fixed_size = 1
    price_add = 5

    rsi_buy = 0
    rsi_sell = 0

    parameters = [
        "price_add",
        "atr_window",
        "atr_ma_window",
        "rsi_window",
        "rsi_entry",
        "trailing_percent",
        "fixed_size"
    ]
    variables = [
        "rsi_buy",
        "rsi_sell"
    ]

    def __init__(
        self,
        strategy_engine: StrategyEngine,
        strategy_name: str,
        vt_symbols: list[str],
        setting: dict
    ) -> None:
        """构造函数"""
        super().__init__(strategy_engine, strategy_name, vt_symbols, setting)

        self.rsi_data: dict[str, float] = {}
        self.atr_data: dict[str, float] = {}
        self.atr_ma: dict[str, float] = {}
        self.intra_trade_high: dict[str, float] = {}
        self.intra_trade_low: dict[str, float] = {}

        self.last_tick_time: datetime | None = None

        # 创建每个合约的ArrayManager
        self.ams: dict[str, ArrayManager] = {}
        for vt_symbol in self.vt_symbols:
            self.ams[vt_symbol] = ArrayManager()

        self.pbg = PortfolioBarGenerator(self.on_bars)

    def on_init(self) -> None:
        """策略初始化回调"""
        self.write_log("策略初始化")

        self.rsi_buy = 50 + self.rsi_entry
        self.rsi_sell = 50 - self.rsi_entry

        self.load_bars(10)

    def on_start(self) -> None:
        """策略启动回调"""
        self.write_log("策略启动")

    def on_stop(self) -> None:
        """策略停止回调"""
        self.write_log("策略停止")

    def on_tick(self, tick: TickData) -> None:
        """行情推送回调"""
        self.pbg.update_tick(tick)

    def on_bars(self, bars: dict[str, BarData]) -> None:
        """K线切片回调"""
        # 更新K线计算RSI数值
        for vt_symbol, bar in bars.items():
            am: ArrayManager = self.ams[vt_symbol]
            am.update_bar(bar)

        for vt_symbol, bar in bars.items():
            am = self.ams[vt_symbol]
            if not am.inited:
                return

            atr_array = am.atr(self.atr_window, array=True)
            self.atr_data[vt_symbol] = atr_array[-1]
            self.atr_ma[vt_symbol] = atr_array[-self.atr_ma_window:].mean()
            self.rsi_data[vt_symbol] = am.rsi(self.rsi_window)

            current_pos = self.get_pos(vt_symbol)
            if current_pos == 0:
                self.intra_trade_high[vt_symbol] = bar.high_price
                self.intra_trade_low[vt_symbol] = bar.low_price

                if self.atr_data[vt_symbol] > self.atr_ma[vt_symbol]:
                    if self.rsi_data[vt_symbol] > self.rsi_buy:
                        self.set_target(vt_symbol, self.fixed_size)
                    elif self.rsi_data[vt_symbol] < self.rsi_sell:
                        self.set_target(vt_symbol, -self.fixed_size)
                    else:
                        self.set_target(vt_symbol, 0)

            elif current_pos > 0:
                self.intra_trade_high[vt_symbol] = max(self.intra_trade_high[vt_symbol], bar.high_price)
                self.intra_trade_low[vt_symbol] = bar.low_price

                long_stop = self.intra_trade_high[vt_symbol] * (1 - self.trailing_percent / 100)

                if bar.close_price <= long_stop:
                    self.set_target(vt_symbol, 0)

            elif current_pos < 0:
                self.intra_trade_low[vt_symbol] = min(self.intra_trade_low[vt_symbol], bar.low_price)
                self.intra_trade_high[vt_symbol] = bar.high_price

                short_stop = self.intra_trade_low[vt_symbol] * (1 + self.trailing_percent / 100)

                if bar.close_price >= short_stop:
                    self.set_target(vt_symbol, 0)

        self.rebalance_portfolio(bars)

        self.put_event()

    def calculate_price(self, vt_symbol: str, direction: Direction, reference: float) -> float:
        """计算调仓委托价格（支持按需重载实现）"""
        if direction == Direction.LONG:
            price: float = reference + self.price_add
        else:
            price = reference - self.price_add

        return price
