from datetime import datetime

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.database import get_database
from vnpy.trader.object import BarData

import pandas as pd


def load_daily_gc001():
    # 读取CSV文件
    df: pd.DataFrame = pd.read_csv("204001_SSE_daily.csv")
    # 遍历每一行数据并转换为BarData对象
    bars: list[BarData] = []
    for _, row in df.iterrows():
        # 解析日期时间
        dt: datetime = datetime.strptime(row["date"], "%Y-%m-%d")

        # 读取价格数据
        gc_close: float = float(row["GC001_close"])
        gc_avg: float = float(row["GC001_avg"])

        # 创建BarData对象
        bar: BarData = BarData(
            symbol="204001",
            exchange=Exchange.SSE,
            datetime=dt,
            interval=Interval.DAILY,
            volume=0,
            turnover=0,
            open_interest=gc_avg,
            open_price=gc_close,
            high_price=gc_close,
            low_price=gc_close,
            close_price=gc_close,
            gateway_name="CSV"
        )
        bars.append(bar)
    # 将数据保存到数据库
    db = get_database()
    db.save_bar_data(bars)
    print(f"成功导入{len(bars)}条K线数据")


def load_minute_gc001():
    # 读取CSV文件
    df: pd.DataFrame = pd.read_csv("204001_SSE_minute.csv")
    # 遍历每一行数据并转换为BarData对象
    bars: list[BarData] = []
    for _, row in df.iterrows():
        # Convert datetime string to datetime object
        dt: datetime = datetime.strptime(row["datetime"], "%Y-%m-%d %H:%M:%S")

        # 创建BarData对象
        bar: BarData = BarData(
            symbol="204001",
            exchange=Exchange.SSE,
            datetime=dt,
            interval=Interval.MINUTE,
            volume=row["volume"],
            turnover=row["turnover"],
            open_interest=row["open_interest"],
            open_price=row["open"],
            high_price=row["high"],
            low_price=row["low"],
            close_price=row["close"],
            gateway_name="CSV"
        )
        bars.append(bar)
    # 将数据保存到数据库
    db = get_database()
    db.save_bar_data(bars)
    print(f"成功导入{len(bars)}条K线数据")

# load_daily_gc001()
load_minute_gc001()