"""配对交易策略。"""

from datetime import datetime
from typing import cast

import numpy as np

from vnpy.trader.utility import BarGenerator
from vnpy.trader.object import TickData, BarData
from vnpy.trader.constant import Direction

from vnpy_portfoliostrategy import StrategyTemplate, StrategyEngine


class PairTradingStrategy(StrategyTemplate):
    """配对交易策略"""

    author: str = "用Python的交易员"

    tick_add: int = 1
    boll_window: int = 20
    boll_dev: int = 2
    fixed_size: int = 1
    leg1_ratio: int = 1
    leg2_ratio: int = 1

    leg1_symbol: str = ""
    leg2_symbol: str = ""
    current_spread: float = 0.0
    boll_mid: float = 0.0
    boll_down: float = 0.0
    boll_up: float = 0.0

    parameters: list[str] = [
        "tick_add",
        "boll_window",
        "boll_dev",
        "fixed_size",
        "leg1_ratio",
        "leg2_ratio",
    ]
    variables: list[str] = [
        "leg1_symbol",
        "leg2_symbol",
        "current_spread",
        "boll_mid",
        "boll_down",
        "boll_up",
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

        self.bgs: dict[str, BarGenerator] = {}
        self.last_tick_time: datetime | None = None

        self.spread_count: int = 0
        self.spread_data: np.ndarray = np.zeros(100)

        # Obtain contract info
        self.leg1_symbol, self.leg2_symbol = vt_symbols

        def on_bar(bar: BarData) -> None:
            """空回调，不处理K线。"""
            pass

        vt_symbol: str
        for vt_symbol in self.vt_symbols:
            self.bgs[vt_symbol] = BarGenerator(on_bar)

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
        if (
            self.last_tick_time
            and self.last_tick_time.minute != tick.datetime.minute
        ):
            bars: dict[str, BarData | None] = {}
            vt_symbol: str
            bg: BarGenerator
            for vt_symbol, bg in self.bgs.items():
                bars[vt_symbol] = bg.generate()
            self.on_bars(cast(dict[str, BarData], bars))

        bg = self.bgs[tick.vt_symbol]
        bg.update_tick(tick)

        self.last_tick_time = tick.datetime

    def on_bars(self, bars: dict[str, BarData]) -> None:
        """K线切片回调"""
        # 获取期权腿K线
        leg1_bar: BarData | None = bars.get(self.leg1_symbol, None)
        leg2_bar: BarData | None = bars.get(self.leg2_symbol, None)

        # 必须两条期权腿行情都存在
        if not leg1_bar or not leg2_bar:
            return

        # 每5分钟运行一次
        if (leg1_bar.datetime.minute + 1) % 5:
            return

        # 计算当前价差
        self.current_spread = leg1_bar.close_price * self.leg1_ratio - leg2_bar.close_price * self.leg2_ratio

        # 更新到价差序列
        self.spread_data[:-1] = self.spread_data[1:]
        self.spread_data[-1] = self.current_spread

        self.spread_count += 1
        if self.spread_count <= self.boll_window:
            return

        # 计算布林带
        buf: np.ndarray = self.spread_data[-self.boll_window:]

        std: float = buf.std()
        self.boll_mid = buf.mean()
        self.boll_up = self.boll_mid + self.boll_dev * std
        self.boll_down = self.boll_mid - self.boll_dev * std

        # 计算目标持仓
        leg1_pos: float = self.get_pos(self.leg1_symbol)

        if not leg1_pos:
            if self.current_spread >= self.boll_up:
                self.set_target(self.leg1_symbol, -self.fixed_size)
                self.set_target(self.leg2_symbol, self.fixed_size)
            elif self.current_spread <= self.boll_down:
                self.set_target(self.leg1_symbol, self.fixed_size)
                self.set_target(self.leg2_symbol, -self.fixed_size)
        elif leg1_pos > 0:
            if self.current_spread >= self.boll_mid:
                self.set_target(self.leg1_symbol, 0)
                self.set_target(self.leg2_symbol, 0)
        else:
            if self.current_spread <= self.boll_mid:
                self.set_target(self.leg1_symbol, 0)
                self.set_target(self.leg2_symbol, 0)

        # 执行调仓交易
        self.rebalance_portfolio(bars)

        # 推送更新事件
        self.put_event()

    def calculate_price(self, vt_symbol: str, direction: Direction, reference: float) -> float:
        """计算调仓委托价格（支持按需重载实现）"""
        pricetick: float = self.get_pricetick(vt_symbol)

        if direction == Direction.LONG:
            price: float = reference + self.tick_add * pricetick
        else:
            price = reference - self.tick_add * pricetick

        return price
