from datetime import datetime
from zoneinfo import ZoneInfo

from vnpy.trader.constant import Exchange
from vnpy.trader.object import BarData, TickData

from vnpy_portfoliostrategy.utility import PortfolioBarGenerator


SHANGHAI: ZoneInfo = ZoneInfo("Asia/Shanghai")
GATEWAY: str = "TEST"


def at(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    second: int = 0,
    microsecond: int = 0,
) -> datetime:
    return datetime(year, month, day, hour, minute, second, microsecond, tzinfo=SHANGHAI)


def quote(symbol: str, dt: datetime, last_price: float, volume: float, turnover: float) -> TickData:
    return TickData(
        gateway_name=GATEWAY,
        symbol=symbol,
        exchange=Exchange.SHFE,
        datetime=dt,
        last_price=last_price,
        volume=volume,
        turnover=turnover,
    )


class MinuteRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, tuple]] = []

    def on_bars(self, bars: dict[str, BarData]) -> None:
        snapshot: dict[str, tuple] = {}
        vt_symbol: str
        item: BarData
        for vt_symbol, item in bars.items():
            snapshot[vt_symbol] = (
                item.datetime,
                item.open_price,
                item.high_price,
                item.low_price,
                item.close_price,
                item.volume,
                item.turnover,
            )
        self.calls.append(snapshot)


def test_tick_flush_separates_1500_from_2100() -> None:
    recorder: MinuteRecorder = MinuteRecorder()
    generator: PortfolioBarGenerator = PortfolioBarGenerator(recorder.on_bars)
    generator.update_tick(quote("rb", at(2026, 10, 5, 15, 0, 0, 500000), 100, 10, 100))
    generator.update_tick(quote("rb", at(2026, 10, 5, 15, 0, 20), 108, 16, 160))
    assert recorder.calls == []

    generator.update_tick(quote("rb", at(2026, 10, 5, 21, 0, 0, 500000), 200, 50, 500))

    assert recorder.calls == [
        {"rb.SHFE": (at(2026, 10, 5, 15, 0), 100, 108, 100, 108, 6, 60)}
    ]


def test_tick_flush_separates_1130_from_1330() -> None:
    recorder: MinuteRecorder = MinuteRecorder()
    generator: PortfolioBarGenerator = PortfolioBarGenerator(recorder.on_bars)
    generator.update_tick(quote("rb", at(2026, 10, 5, 11, 30, 0, 500000), 100, 10, 100))
    generator.update_tick(quote("rb", at(2026, 10, 5, 11, 30, 20), 106, 15, 150))
    generator.update_tick(quote("rb", at(2026, 10, 5, 13, 30, 0, 500000), 180, 40, 400))

    assert recorder.calls == [
        {"rb.SHFE": (at(2026, 10, 5, 11, 30), 100, 106, 100, 106, 5, 50)}
    ]


def test_tick_flush_separates_same_minute_next_day() -> None:
    recorder: MinuteRecorder = MinuteRecorder()
    generator: PortfolioBarGenerator = PortfolioBarGenerator(recorder.on_bars)
    generator.update_tick(quote("rb", at(2026, 10, 5, 14, 59, 30), 100, 10, 100))
    generator.update_tick(quote("rb", at(2026, 10, 5, 14, 59, 40), 104, 14, 140))
    generator.update_tick(quote("rb", at(2026, 10, 6, 14, 59, 30), 180, 30, 300))

    assert recorder.calls == [
        {"rb.SHFE": (at(2026, 10, 5, 14, 59), 100, 104, 100, 104, 4, 40)}
    ]
