from datetime import datetime
from typing import cast

from vnpy.trader.constant import Direction, Exchange, Interval, Offset, Status
from vnpy.trader.object import BarData, OrderData, TradeData

from vnpy_portfoliostrategy.backtesting import BacktestingEngine
from vnpy_portfoliostrategy.template import StrategyTemplate


RB_SYMBOL: str = "rb2501"
AG_SYMBOL: str = "ag2506"
RB: str = f"{RB_SYMBOL}.{Exchange.SHFE.value}"
AG: str = f"{AG_SYMBOL}.{Exchange.SHFE.value}"


def make_bar(
    symbol: str,
    dt: datetime,
    open_price: float,
    high_price: float,
    low_price: float,
    close_price: float,
) -> BarData:
    return BarData(
        symbol=symbol,
        exchange=Exchange.SHFE,
        datetime=dt,
        interval=Interval.MINUTE,
        volume=1,
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=close_price,
        gateway_name="BACKTESTING",
    )


class TargetOnceStrategy(StrategyTemplate):
    def __init__(
        self,
        strategy_engine: object,
        strategy_name: str,
        vt_symbols: list[str],
        setting: dict,
    ) -> None:
        super().__init__(strategy_engine, strategy_name, vt_symbols, setting)
        self.pos_at_bar: list[tuple[float, float]] = []
        self.trade_count_at_bar: list[int] = []

    def on_init(self) -> None:
        return

    def on_bars(self, bars: dict[str, BarData]) -> None:
        engine: BacktestingEngine = cast(BacktestingEngine, self.strategy_engine)
        self.pos_at_bar.append((self.get_pos(RB), self.get_pos(AG)))
        self.trade_count_at_bar.append(engine.trade_count)
        if self.trading and engine.trade_count == 0 and RB in bars and AG in bars:
            self.set_target(RB, 1)
            self.set_target(AG, -2)
            self.rebalance_portfolio(bars)


class TestPortfolioBacktesting:
    def test_targets_fill_on_next_bar(self) -> None:
        # new_bars 先撮合再回调。第一根只按下单价发单，第二根才成交。
        t1: datetime = datetime(2024, 1, 2, 9, 0)
        t2: datetime = datetime(2024, 1, 2, 9, 1)
        t3: datetime = datetime(2024, 1, 2, 9, 2)
        bars: list[BarData] = [
            make_bar(RB_SYMBOL, t1, 100, 100, 100, 100),
            make_bar(AG_SYMBOL, t1, 200, 200, 200, 200),
            make_bar(RB_SYMBOL, t2, 100, 101, 99, 100),
            make_bar(AG_SYMBOL, t2, 200, 201, 199, 200),
            make_bar(RB_SYMBOL, t3, 100, 100, 100, 100),
            make_bar(AG_SYMBOL, t3, 200, 200, 200, 200),
        ]

        logs: list[str] = []

        def swallow_output(msg: str) -> None:
            logs.append(msg)

        engine: BacktestingEngine = BacktestingEngine()
        engine.output = swallow_output  # type: ignore[method-assign]
        engine.set_parameters(
            vt_symbols=[RB, AG],
            interval=Interval.MINUTE,
            start=datetime(2024, 1, 2),
            rates={RB: 0, AG: 0},
            slippages={RB: 0, AG: 0},
            sizes={RB: 10, AG: 15},
            priceticks={RB: 1, AG: 1},
            capital=1_000_000,
            end=datetime(2024, 1, 2, 15, 0),
        )
        engine.add_strategy(TargetOnceStrategy, {})
        for bar in bars:
            engine.dts.add(bar.datetime)
            engine.history_data[(bar.datetime, bar.vt_symbol)] = bar
        engine.run_backtesting()

        strategy: TargetOnceStrategy = cast(TargetOnceStrategy, engine.strategy)
        assert strategy.pos_at_bar == [(0, 0), (1, -2), (1, -2)], logs
        assert strategy.trade_count_at_bar == [0, 2, 2], logs
        assert strategy.get_pos(RB) == 1
        assert strategy.get_pos(AG) == -2
        assert strategy.get_target(RB) == 1
        assert strategy.get_target(AG) == -2
        assert engine.trade_count == 2
        assert engine.datetime == t3

        orders: list[OrderData] = list(engine.limit_orders.values())
        assert len(orders) == 2
        assert orders[0].vt_symbol == RB
        assert orders[0].direction == Direction.LONG
        assert orders[0].offset == Offset.OPEN
        assert orders[0].volume == 1
        assert orders[0].price == 100
        assert orders[0].status == Status.ALLTRADED
        assert orders[1].vt_symbol == AG
        assert orders[1].direction == Direction.SHORT
        assert orders[1].offset == Offset.OPEN
        assert orders[1].volume == 2
        assert orders[1].price == 200
        assert orders[1].status == Status.ALLTRADED

        trades: list[TradeData] = list(engine.trades.values())
        assert [trade.vt_symbol for trade in trades] == [RB, AG]
        assert trades[0].direction == Direction.LONG
        assert trades[0].offset == Offset.OPEN
        assert trades[0].volume == 1
        assert trades[0].price == 100
        assert trades[0].datetime == t2
        assert trades[1].direction == Direction.SHORT
        assert trades[1].offset == Offset.OPEN
        assert trades[1].volume == 2
        assert trades[1].price == 200
        assert trades[1].datetime == t2
