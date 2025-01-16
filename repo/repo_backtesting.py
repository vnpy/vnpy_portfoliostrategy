from datetime import datetime

from vnpy_portfoliostrategy import BacktestingEngine
from vnpy.trader.constant import Interval

from repo_strategy import RepoStrategy


def backtest_daily():
    engine = BacktestingEngine()
    engine.set_parameters(
        vt_symbols=["204001.SSE"],
        interval=Interval.DAILY,
        start=datetime(2017, 8, 24),
        end=datetime(2024, 12, 5),
        rates={"204001.SSE": 0},
        slippages={"204001.SSE": 0},
        sizes={"204001.SSE": 0},
        priceticks={"204001.SSE": 0.001},
        capital=1_000_000,
    )
    setting = {}
    engine.add_strategy(RepoStrategy, setting)
    engine.load_data()
    engine.run_backtesting()
    df = engine.calculate_result()
    engine.calculate_statistics()
    engine.show_chart()
    for repo_position in engine.repo_position_data:
        print(repo_position)


def backtest_minute():
    engine = BacktestingEngine()
    engine.set_parameters(
        vt_symbols=["204001.SSE"],
        interval=Interval.MINUTE,
        start=datetime(2019, 5, 15),
        end=datetime(2025, 1, 9),
        rates={"204001.SSE": 0},
        slippages={"204001.SSE": 0},
        sizes={"204001.SSE": 0},
        priceticks={"204001.SSE": 0.001},
        capital=1_000_000,
    )
    setting = {}
    engine.add_strategy(RepoStrategy, setting)
    engine.load_data()
    engine.run_backtesting()
    df = engine.calculate_result()
    engine.calculate_statistics()
    engine.show_chart()
    # for repo_position in engine.repo_position_data:
    #     print(repo_position)

# backtest_daily()
backtest_minute()