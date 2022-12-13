from typing import List, Dict
from datetime import datetime

from vnpy.trader.utility import BarGenerator, extract_vt_symbol
from vnpy.trader.object import TickData, BarData
from vnpy.trader.constant import Direction

from vnpy_portfoliostrategy import StrategyTemplate, StrategyEngine


class PcpArbitrageStrategy(StrategyTemplate):
    """期权平价套利策略"""

    author = "用Python的交易员"

    entry_level = 20
    price_add = 5
    fixed_size = 1

    strike_price = 0
    futures_price = 0
    synthetic_price = 0
    current_spread = 0
    futures_pos = 0
    call_pos = 0
    put_pos = 0

    parameters = [
        "entry_level",
        "price_add",
        "fixed_size"
    ]
    variables = [
        "strike_price",
        "futures_price",
        "synthetic_price",
        "current_spread",
        "futures_pos",
        "call_pos",
        "put_pos",
    ]

    def __init__(
        self,
        strategy_engine: StrategyEngine,
        strategy_name: str,
        vt_symbols: List[str],
        setting: dict
    ):
        """"""
        super().__init__(strategy_engine, strategy_name, vt_symbols, setting)

        self.bgs: Dict[str, BarGenerator] = {}
        self.last_tick_time: datetime = None

        # Obtain contract info
        for vt_symbol in self.vt_symbols:
            symbol, exchange = extract_vt_symbol(vt_symbol)

            if "C" in symbol:
                self.call_symbol = vt_symbol
                _, strike_str = symbol.split("-C-")     # For CFFEX/DCE options
                self.strike_price = int(strike_str)
            elif "P" in symbol:
                self.put_symbol = vt_symbol
            else:
                self.futures_symbol = vt_symbol

            def on_bar(bar: BarData):
                """"""
                pass

            self.bgs[vt_symbol] = BarGenerator(on_bar)

    def on_init(self):
        """
        Callback when strategy is inited.
        """
        self.write_log("策略初始化")

        self.load_bars(1)

    def on_start(self):
        """
        Callback when strategy is started.
        """
        self.write_log("策略启动")

    def on_stop(self):
        """
        Callback when strategy is stopped.
        """
        self.write_log("策略停止")

    def on_tick(self, tick: TickData):
        """
        Callback of new tick data update.
        """
        if (
            self.last_tick_time
            and self.last_tick_time.minute != tick.datetime.minute
        ):
            bars = {}
            for vt_symbol, bg in self.bgs.items():
                bars[vt_symbol] = bg.generate()
            self.on_bars(bars)

        bg: BarGenerator = self.bgs[tick.vt_symbol]
        bg.update_tick(tick)

        self.last_tick_time = tick.datetime

    def on_bars(self, bars: Dict[str, BarData]):
        """"""
        self.cancel_all()

        # Calcualate spread data
        call_bar = bars[self.call_symbol]
        put_bar = bars[self.put_symbol]
        futures_bar = bars[self.futures_symbol]

        self.futures_price = futures_bar.close_price
        self.synthetic_price = (
            call_bar.close_price - put_bar.close_price + self.strike_price
        )
        self.current_spread = self.synthetic_price - self.futures_price

        # Get current position
        self.call_pos = self.get_pos(self.call_symbol)
        self.put_pos = self.get_pos(self.put_symbol)
        self.futures_pos = self.get_pos(self.futures_symbol)

        # Calculate target position
        if not self.futures_pos:
            if self.current_spread > self.entry_level:
                self.set_target(self.call_symbol, -self.fixed_size)
                self.set_target(self.put_symbol, self.fixed_size)
                self.set_target(self.futures_symbol, self.fixed_size)
            elif self.current_spread < -self.entry_level:
                self.set_target(self.call_symbol, self.fixed_size)
                self.set_target(self.put_symbol, -self.fixed_size)
                self.set_target(self.futures_symbol, -self.fixed_size)
        elif self.futures_pos > 0:
            if self.current_spread <= 0:
                self.set_target(self.call_symbol, 0)
                self.set_target(self.put_symbol, 0)
                self.set_target(self.futures_symbol, 0)
        else:
            if self.current_spread >= 0:
                self.set_target(self.call_symbol, 0)
                self.set_target(self.put_symbol, 0)
                self.set_target(self.futures_symbol, 0)

        self.execute_target_orders()

        self.put_event()

    def calculate_target_price(self, vt_symbol: str, direction: Direction, reference: float) -> float:
        """计算目标交易的委托价格"""
        if direction == Direction.LONG:
            price: float = reference + self.price_add
        else:
            price: float = reference - self.price_add

        return price
