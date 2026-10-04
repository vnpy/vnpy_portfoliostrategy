from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest

from vnpy.event import Event
from vnpy.trader.constant import Direction, Exchange, Interval, Offset, Product, Status
from vnpy.trader.event import EVENT_ORDER, EVENT_TRADE
from vnpy.trader.object import (
    BarData,
    CancelRequest,
    ContractData,
    OrderData,
    OrderRequest,
    SubscribeRequest,
    TradeData,
)
from vnpy.trader.setting import SETTINGS
from vnpy.trader.utility import TEMP_DIR
from vnpy_portfoliostrategy.base import APP_NAME
from vnpy_portfoliostrategy.engine import StrategyEngine
from vnpy_portfoliostrategy.template import StrategyTemplate


RB_SYMBOL: str = "rb2501"
AG_SYMBOL: str = "ag2506"
RB: str = f"{RB_SYMBOL}.{Exchange.SHFE.value}"
AG: str = f"{AG_SYMBOL}.{Exchange.SHFE.value}"


class FakeGateway:
    def __init__(self) -> None:
        self.gateway_name: str = "FAKE"
        self.order_requests: list[OrderRequest] = []
        self.cancel_requests: list[CancelRequest] = []
        self.subscriptions: list[SubscribeRequest] = []
        self.orders: dict[str, OrderData] = {}
        self._count: int = 0

    def send_order(self, req: OrderRequest) -> str:
        self._count += 1
        orderid: str = str(self._count)
        order: OrderData = req.create_order_data(orderid, self.gateway_name)
        self.orders[order.vt_orderid] = order
        self.order_requests.append(req)
        return order.vt_orderid

    def cancel_order(self, req: CancelRequest) -> None:
        self.cancel_requests.append(req)

    def subscribe(self, req: SubscribeRequest) -> None:
        self.subscriptions.append(req)


class FakeMainEngine:
    def __init__(self, gateway: FakeGateway) -> None:
        self.gateway: FakeGateway = gateway
        self.contracts: dict[str, ContractData] = {}

    def get_contract(self, vt_symbol: str) -> ContractData | None:
        return self.contracts.get(vt_symbol)

    def subscribe(self, req: SubscribeRequest, gateway_name: str) -> None:
        self.gateway.subscribe(req)

    def convert_order_request(
        self,
        req: OrderRequest,
        gateway_name: str,
        lock: bool,
        net: bool = False,
    ) -> list[OrderRequest]:
        return [req]

    def send_order(self, req: OrderRequest, gateway_name: str) -> str:
        return self.gateway.send_order(req)

    def update_order_request(
        self,
        req: OrderRequest,
        vt_orderid: str,
        gateway_name: str,
    ) -> None:
        return None

    def get_order(self, vt_orderid: str) -> OrderData | None:
        return self.gateway.orders.get(vt_orderid)

    def cancel_order(self, req: CancelRequest, gateway_name: str) -> None:
        self.gateway.cancel_order(req)


class FakeEventEngine:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def put(self, event: Event) -> None:
        self.events.append(event)


class TargetStrategy(StrategyTemplate):
    def on_init(self) -> None:
        return

    def on_bars(self, bars: dict[str, BarData]) -> None:
        return


class EngineRig:
    def __init__(
        self,
        engine: StrategyEngine,
        gateway: FakeGateway,
        strategy: TargetStrategy,
    ) -> None:
        self.engine: StrategyEngine = engine
        self.gateway: FakeGateway = gateway
        self.strategy: TargetStrategy = strategy


def make_contract(symbol: str, size: float) -> ContractData:
    return ContractData(
        symbol=symbol,
        exchange=Exchange.SHFE,
        name=symbol,
        product=Product.FUTURES,
        size=size,
        pricetick=1,
        min_volume=1,
        gateway_name="FAKE",
    )


def make_bar(symbol: str, dt: datetime, close_price: float) -> BarData:
    return BarData(
        symbol=symbol,
        exchange=Exchange.SHFE,
        datetime=dt,
        interval=Interval.MINUTE,
        open_price=close_price,
        high_price=close_price,
        low_price=close_price,
        close_price=close_price,
        gateway_name="FAKE",
    )


def sent_orders(gateway: FakeGateway) -> list[OrderData]:
    return list(gateway.orders.values())


def push_trade(rig: EngineRig, order: OrderData) -> None:
    assert order.direction is not None
    trade: TradeData = TradeData(
        symbol=order.symbol,
        exchange=order.exchange,
        orderid=order.orderid,
        tradeid=order.orderid,
        direction=order.direction,
        offset=order.offset,
        price=order.price,
        volume=order.volume,
        datetime=order.datetime,
        gateway_name=order.gateway_name,
    )
    rig.engine.process_trade_event(Event(EVENT_TRADE, trade))


def mark_alltraded(rig: EngineRig, order: OrderData) -> None:
    order.status = Status.ALLTRADED
    order.traded = order.volume
    rig.engine.process_order_event(Event(EVENT_ORDER, order))


def _disconnected_service() -> object:
    return object()


def build_engine() -> EngineRig:
    gateway: FakeGateway = FakeGateway()
    main_engine: FakeMainEngine = FakeMainEngine(gateway)
    for symbol, size in ((RB_SYMBOL, 10), (AG_SYMBOL, 15)):
        contract: ContractData = make_contract(symbol, size)
        main_engine.contracts[contract.vt_symbol] = contract
    events: FakeEventEngine = FakeEventEngine()
    engine: StrategyEngine = StrategyEngine(main_engine, events)  # type: ignore[arg-type]
    engine.classes[TargetStrategy.__name__] = TargetStrategy
    engine.add_strategy(TargetStrategy.__name__, "target", [RB, AG], {})
    strategy: StrategyTemplate = engine.strategies["target"]
    assert isinstance(strategy, TargetStrategy)
    return EngineRig(engine, gateway, strategy)


def test_settings_dir_is_temporary() -> None:
    assert SETTINGS["log.file"] is False
    assert SETTINGS["log.console"] is False
    assert TEMP_DIR.resolve() == Path.cwd().resolve().joinpath(".vntrader")
    assert TEMP_DIR.resolve() != Path.home().resolve().joinpath(".vntrader")


@pytest.fixture
def rig(monkeypatch: pytest.MonkeyPatch) -> Iterator[EngineRig]:
    monkeypatch.setattr("vnpy_portfoliostrategy.engine.get_database", _disconnected_service)
    monkeypatch.setattr("vnpy_portfoliostrategy.engine.get_datafeed", _disconnected_service)
    built: EngineRig = build_engine()
    try:
        yield built
    finally:
        built.engine.init_executor.shutdown(wait=False, cancel_futures=True)


class TestTargetPosition:
    def test_rebalance_order_and_trade_update_position(self, rig: EngineRig) -> None:
        # 持仓 0、目标 2 只买开。成交把数量加进该合约持仓，另一合约不变。
        # 持仓 2、目标 -1 时先卖平 2，再卖开 1。
        strategy: TargetStrategy = rig.strategy
        engine: StrategyEngine = rig.engine
        gateway: FakeGateway = rig.gateway

        engine._init_strategy("target")
        assert strategy.inited is True
        assert strategy.trading is False
        assert {item.symbol for item in gateway.subscriptions} == {RB_SYMBOL, AG_SYMBOL}

        strategy.set_target(RB, 2)
        strategy.rebalance_portfolio({RB: make_bar(RB_SYMBOL, datetime(2024, 1, 2, 9, 0), 3500)})
        assert gateway.order_requests == []

        engine.start_strategy("target")
        assert strategy.trading is True

        strategy.rebalance_portfolio({RB: make_bar(RB_SYMBOL, datetime(2024, 1, 2, 9, 1), 3500)})
        assert len(gateway.order_requests) == 1
        buy_req: OrderRequest = gateway.order_requests[0]
        assert buy_req.symbol == RB_SYMBOL
        assert buy_req.exchange == Exchange.SHFE
        assert buy_req.direction == Direction.LONG
        assert buy_req.offset == Offset.OPEN
        assert buy_req.price == 3500
        assert buy_req.volume == 2
        assert buy_req.reference == f"{APP_NAME}_target"

        buy_order: OrderData = sent_orders(gateway)[0]
        assert buy_order.direction == Direction.LONG
        assert buy_order.volume == 2
        assert buy_order.vt_orderid in strategy.active_orderids
        push_trade(rig, buy_order)
        assert strategy.get_pos(RB) == 2
        assert strategy.get_pos(AG) == 0
        push_trade(rig, buy_order)
        assert strategy.get_pos(RB) == 2
        mark_alltraded(rig, buy_order)
        assert buy_order.vt_orderid not in strategy.active_orderids
        recorded_buy: OrderData | None = strategy.get_order(buy_order.vt_orderid)
        assert recorded_buy is not None
        assert recorded_buy.direction == Direction.LONG
        assert recorded_buy.volume == 2

        strategy.set_target(AG, 1)
        strategy.rebalance_portfolio({AG: make_bar(AG_SYMBOL, datetime(2024, 1, 2, 9, 2), 5800)})
        assert len(gateway.order_requests) == 2
        ag_req: OrderRequest = gateway.order_requests[1]
        assert ag_req.symbol == AG_SYMBOL
        assert ag_req.direction == Direction.LONG
        assert ag_req.offset == Offset.OPEN
        assert ag_req.price == 5800
        assert ag_req.volume == 1
        ag_order: OrderData = sent_orders(gateway)[1]
        push_trade(rig, ag_order)
        mark_alltraded(rig, ag_order)
        assert strategy.get_pos(AG) == 1
        assert strategy.get_pos(RB) == 2

        strategy.set_target(RB, -1)
        strategy.rebalance_portfolio({RB: make_bar(RB_SYMBOL, datetime(2024, 1, 2, 9, 3), 3480)})
        assert len(gateway.order_requests) == 4
        close_req: OrderRequest = gateway.order_requests[2]
        open_req: OrderRequest = gateway.order_requests[3]
        assert close_req.symbol == RB_SYMBOL
        assert close_req.direction == Direction.SHORT
        assert close_req.offset == Offset.CLOSE
        assert close_req.price == 3480
        assert close_req.volume == 2
        assert open_req.symbol == RB_SYMBOL
        assert open_req.direction == Direction.SHORT
        assert open_req.offset == Offset.OPEN
        assert open_req.price == 3480
        assert open_req.volume == 1

        close_order: OrderData = sent_orders(gateway)[2]
        open_order: OrderData = sent_orders(gateway)[3]
        assert close_order.direction == Direction.SHORT
        assert close_order.volume == 2
        assert open_order.direction == Direction.SHORT
        assert open_order.volume == 1
        push_trade(rig, close_order)
        push_trade(rig, open_order)
        assert strategy.get_pos(RB) == -1
        assert strategy.get_pos(AG) == 1
        assert strategy.get_target(RB) == -1
        assert strategy.get_target(AG) == 1
