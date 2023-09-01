from typing import Callable, Dict

from vnpy.trader.object import BarData, TickData, Interval
from vnpy.trader.utility import BarGenerator


class PortfolioBarGenerator:
    """组合K线生成器"""

    def __init__(
        self,
        on_bar: Callable,
        window: int = 0,
        on_window_bar: Callable = None,
        interval: Interval = Interval.MINUTE
    ) -> None:
        """构造函数"""
        self.on_bar: Callable = on_bar
        self.window: int = window
        self.on_window_bar: Callable = on_window_bar
        self.interval: Interval = interval

        self.bar_generators: Dict[str, BarGenerator] = {}

    def update_tick(self, tick: TickData) -> None:
        """更新行情切片数据"""

        vt_symbol = tick.vt_symbol
        bar_generator: BarGenerator = self.bar_generators.get(vt_symbol, None)
        if not bar_generator:
            bar_generator = BarGenerator(self.on_bar, self.window, self.on_window_bar, self.interval)
            self.bar_generators[vt_symbol] = bar_generator

        bar_generator.update_tick(tick)

    def update_bar(self, bar: BarData) -> None:
        vt_symbol = bar.vt_symbol
        bar_generator: BarGenerator = self.bar_generators.get(vt_symbol, None)
        if not bar_generator:
            bar_generator = BarGenerator(self.on_bar, self.window, self.on_window_bar, self.interval)
            self.bar_generators[vt_symbol] = bar_generator
        bar_generator.update_bar(bar)
