from collections.abc import Iterator
from copy import deepcopy
from dataclasses import replace
import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from vnpy.event import Event
from vnpy.trader.constant import Direction, Exchange, Interval, Offset, Product, Status
from vnpy.trader.datafeed import BaseDatafeed
from vnpy.trader.engine import LogEngine
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
from vnpy.trader.ui import QtCore, QtWidgets
from vnpy_portfoliostrategy.base import APP_NAME, EVENT_PORTFOLIO_LOG, EVENT_PORTFOLIO_STRATEGY
from vnpy_portfoliostrategy.engine import StrategyEngine
from vnpy_portfoliostrategy.template import StrategyTemplate
from vnpy_portfoliostrategy.ui.widget import PortfolioStrategyManager, StrategyManager


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


@pytest.mark.parametrize("error", [RuntimeError, ValueError, TypeError])
def test_init_error_does_not_restore_or_subscribe(rig: EngineRig, monkeypatch: pytest.MonkeyPatch, error: type[Exception]) -> None:
    saved = {"pos_data": {RB: 7}, "target_data": {RB: 9}}
    rig.engine.strategy_data["target"] = deepcopy(saved)

    def fail() -> None:
        raise error("initialization failed")

    monkeypatch.setattr(rig.strategy, "on_init", fail)
    rig.engine._init_strategy("target")

    assert (rig.strategy.inited, rig.strategy.trading) == (False, False)
    assert rig.strategy.get_pos(RB) == 0
    assert rig.gateway.subscriptions == []
    assert rig.engine.strategy_data["target"] == saved
    events = [event.data for event in rig.engine.event_engine.events if event.type == EVENT_PORTFOLIO_STRATEGY]
    assert events[-1]["variables"]["inited"] is False
    assert events[-1]["variables"]["trading"] is False
    logs = [event.data.msg for event in rig.engine.event_engine.events if event.type == EVENT_PORTFOLIO_LOG]
    assert any("initialization failed" in message for message in logs)
    assert not any("初始化完成" in message for message in logs)


@pytest.mark.parametrize("error", [RuntimeError, ValueError, TypeError])
def test_start_error_keeps_orders_disabled(rig: EngineRig, monkeypatch: pytest.MonkeyPatch, error: type[Exception]) -> None:
    rig.engine._init_strategy("target")

    def fail() -> None:
        raise error("startup failed")

    monkeypatch.setattr(rig.strategy, "on_start", fail)
    rig.engine.start_strategy("target")

    assert (rig.strategy.inited, rig.strategy.trading) == (False, False)
    assert rig.strategy.buy(RB, 3500, 1) == []
    assert rig.gateway.order_requests == []
    states = [event.data["variables"] for event in rig.engine.event_engine.events if event.type == EVENT_PORTFOLIO_STRATEGY]
    assert not any(not state["inited"] and state["trading"] for state in states)


@pytest.mark.parametrize("result", [None, False, 0])
def test_normal_callbacks_keep_their_return_and_ordering(rig: EngineRig, monkeypatch: pytest.MonkeyPatch, result: object) -> None:
    calls: list[str] = []

    def initialize() -> object:
        calls.append("init")
        return result

    def start() -> object:
        calls.append("start")
        assert (rig.strategy.inited, rig.strategy.trading) == (True, False)
        assert rig.strategy.buy(RB, 3500, 1) == []
        return result

    monkeypatch.setattr(rig.strategy, "on_init", initialize)
    monkeypatch.setattr(rig.strategy, "on_start", start)
    assert rig.engine._init_strategy("target") is None
    assert rig.engine.start_strategy("target") is None
    assert calls == ["init", "start"]
    assert (rig.strategy.inited, rig.strategy.trading) == (True, True)
    assert len(rig.strategy.buy(RB, 3500, 1)) == 1


def fail_start(rig: EngineRig, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail() -> None:
        raise RuntimeError("startup failed")

    monkeypatch.setattr(rig.strategy, "on_start", fail)
    rig.engine.start_strategy("target")


def test_failed_restart_keeps_cancellation_persistence_and_routes(rig: EngineRig, monkeypatch: pytest.MonkeyPatch) -> None:
    stop_calls: list[str] = []
    monkeypatch.setattr(rig.strategy, "on_stop", lambda: stop_calls.append("stop"))
    rig.engine._init_strategy("target")
    rig.engine.start_strategy("target")
    orderid = rig.strategy.buy(RB, 3500, 2)[0]
    rig.engine.stop_strategy("target")
    fail_start(rig, monkeypatch)
    assert rig.engine.remove_strategy("target") is False
    assert rig.engine.orderid_strategy_map[orderid] is rig.strategy

    order = rig.gateway.orders[orderid]
    rig.engine.process_trade_event(Event(EVENT_TRADE, TradeData(
        symbol=order.symbol, exchange=order.exchange, orderid=order.orderid,
        tradeid="late", direction=Direction.LONG, offset=Offset.OPEN,
        price=order.price, volume=1, gateway_name=order.gateway_name,
    )))
    event_count = len(rig.engine.event_engine.events)
    rig.engine.stop_strategy("target")
    assert len(rig.engine.event_engine.events) == event_count + 1
    assert len(rig.gateway.cancel_requests) == 2
    assert stop_calls == ["stop"]
    stored = json.loads(TEMP_DIR.joinpath(rig.engine.data_filename).read_text(encoding="utf-8"))
    assert stored["target"]["pos_data"][RB] == 1
    assert orderid in rig.strategy.active_orderids
    assert rig.engine.remove_strategy("target") is False

    rig.engine.process_order_event(Event(EVENT_ORDER, replace(order, status=Status.CANCELLED, traded=1)))
    assert orderid not in rig.strategy.active_orderids
    assert rig.engine.remove_strategy("target") is True


def test_successful_reinitialization_has_no_extra_stop_side_effects(rig: EngineRig, monkeypatch: pytest.MonkeyPatch) -> None:
    rig.engine._init_strategy("target")
    fail_start(rig, monkeypatch)
    rig.engine._init_strategy("target")
    assert (rig.strategy.inited, rig.strategy.trading) == (True, False)
    before = len(rig.engine.event_engine.events)
    saved: list[str] = []
    monkeypatch.setattr(rig.engine, "sync_strategy_data", lambda strategy: saved.append(strategy.strategy_name))
    rig.engine.stop_strategy("target")
    assert len(rig.engine.event_engine.events) == before
    assert saved == []
    assert rig.gateway.cancel_requests == []


def test_reinitialization_keeps_existing_saved_variable_restore_semantics(rig: EngineRig, monkeypatch: pytest.MonkeyPatch) -> None:
    rig.engine.strategy_data["target"] = json.loads(json.dumps({"pos_data": {RB: 7}, "target_data": {RB: 9}}))
    rig.engine._init_strategy("target")
    assert rig.strategy.get_pos(RB) == 7
    fail_start(rig, monkeypatch)
    rig.strategy.pos_data[RB] = 8
    rig.strategy.target_data[RB] = 10
    rig.engine._init_strategy("target")
    assert rig.strategy.get_pos(RB) == 7
    assert rig.strategy.get_target(RB) == 9


def test_failed_reinitialization_keeps_pending_cleanup(rig: EngineRig, monkeypatch: pytest.MonkeyPatch) -> None:
    rig.engine._init_strategy("target")
    rig.engine.start_strategy("target")
    orderid = rig.strategy.buy(RB, 3500, 1)[0]
    rig.engine.stop_strategy("target")
    fail_start(rig, monkeypatch)

    def fail() -> None:
        raise RuntimeError("retry initialization failed")

    monkeypatch.setattr(rig.strategy, "on_init", fail)
    rig.engine._init_strategy("target")
    assert (rig.strategy.inited, rig.strategy.trading) == (False, False)
    rig.engine.stop_strategy("target")
    assert len(rig.gateway.cancel_requests) == 2
    assert rig.engine.orderid_strategy_map[orderid] is rig.strategy


def test_first_init_failure_does_not_overwrite_saved_positions(rig: EngineRig, monkeypatch: pytest.MonkeyPatch) -> None:
    saved = {"target": {"pos_data": {RB: 7}, "target_data": {RB: 9}}}
    path = TEMP_DIR.joinpath(rig.engine.data_filename)
    path.write_text(json.dumps(saved), encoding="utf-8")
    rig.engine.strategy_data = deepcopy(saved)

    def fail() -> None:
        raise RuntimeError("initialization failed")

    monkeypatch.setattr(rig.strategy, "on_init", fail)
    rig.engine._init_strategy("target")
    rig.engine.stop_strategy("target")
    assert json.loads(path.read_text(encoding="utf-8")) == saved


def test_nested_init_error_cannot_be_reported_as_success(rig: EngineRig, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail() -> None:
        raise RuntimeError("nested initialization error")

    def initialize() -> None:
        rig.engine.call_strategy_func(rig.strategy, fail)

    monkeypatch.setattr(rig.strategy, "on_init", initialize)
    rig.engine._init_strategy("target")
    assert (rig.strategy.inited, rig.strategy.trading) == (False, False)
    assert rig.gateway.subscriptions == []


def test_saved_state_flags_do_not_enable_trading(rig: EngineRig) -> None:
    rig.engine.strategy_data["target"] = {"inited": True, "trading": True, "pos_data": {RB: 7}}
    rig.engine._init_strategy("target")
    assert (rig.strategy.inited, rig.strategy.trading) == (True, False)
    assert rig.strategy.get_pos(RB) == 7


@pytest.mark.parametrize("method", ["start_strategy", "stop_strategy", "remove_strategy", "_init_strategy"])
def test_unknown_strategy_still_raises_key_error(rig: EngineRig, method: str) -> None:
    with pytest.raises(KeyError):
        getattr(rig.engine, method)("missing")


@pytest.mark.parametrize("params", [None, False, 0, "value"])
def test_callback_helper_keeps_none_and_argument_rules(rig: EngineRig, params: object) -> None:
    calls: list[tuple] = []
    assert rig.engine.call_strategy_func(rig.strategy, lambda *args: calls.append(args), params) is None
    assert calls == ([(params,)] if params else [()])


@pytest.fixture(scope="module")
def strategy_qt_app() -> Iterator[QtWidgets.QApplication]:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app
    app.processEvents()


@pytest.fixture
def strategy_widget(rig: EngineRig, strategy_qt_app: QtWidgets.QApplication) -> Iterator[StrategyManager]:
    widget = StrategyManager(None, rig.engine, rig.strategy.get_data())  # type: ignore[arg-type]
    try:
        yield widget
    finally:
        widget.close()
        widget.deleteLater()
        strategy_qt_app.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        strategy_qt_app.processEvents()


def update_widget_from_latest_event(rig: EngineRig, widget: StrategyManager) -> None:
    events = [event for event in rig.engine.event_engine.events if event.type == EVENT_PORTFOLIO_STRATEGY]
    widget.update_data(events[-1].data)


def test_widget_allows_manual_recovery_after_start_error(rig: EngineRig, strategy_widget: StrategyManager, monkeypatch: pytest.MonkeyPatch) -> None:
    rig.engine._init_strategy("target")
    update_widget_from_latest_event(rig, strategy_widget)
    fail_start(rig, monkeypatch)
    update_widget_from_latest_event(rig, strategy_widget)
    assert strategy_widget.init_button.isEnabled()
    assert not strategy_widget.start_button.isEnabled()
    assert not strategy_widget.stop_button.isEnabled()
    strategy_widget.init_button.click()
    rig.engine.init_executor.submit(lambda: None).result(timeout=4)
    update_widget_from_latest_event(rig, strategy_widget)
    assert not strategy_widget.init_button.isEnabled()
    assert strategy_widget.start_button.isEnabled()


def test_widget_keeps_cleanup_available_until_cancel_ack(rig: EngineRig, strategy_widget: StrategyManager, monkeypatch: pytest.MonkeyPatch) -> None:
    rig.engine._init_strategy("target")
    rig.engine.start_strategy("target")
    orderid = rig.strategy.buy(RB, 3500, 1)[0]
    rig.engine.stop_strategy("target")
    fail_start(rig, monkeypatch)
    update_widget_from_latest_event(rig, strategy_widget)
    assert strategy_widget.stop_button.isEnabled()
    assert not strategy_widget.remove_button.isEnabled()
    strategy_widget.stop_button.click()
    assert len(rig.gateway.cancel_requests) == 2
    assert not strategy_widget.remove_button.isEnabled()
    order = rig.gateway.orders[orderid]
    rig.engine.process_order_event(Event(EVENT_ORDER, replace(order, status=Status.CANCELLED)))
    update_widget_from_latest_event(rig, strategy_widget)
    assert not strategy_widget.stop_button.isEnabled()
    assert strategy_widget.remove_button.isEnabled()


def test_normal_stop_cancel_ack_refreshes_widget(rig: EngineRig, strategy_widget: StrategyManager) -> None:
    rig.engine._init_strategy("target")
    rig.engine.start_strategy("target")
    orderid = rig.strategy.buy(RB, 3500, 1)[0]
    rig.engine.stop_strategy("target")
    update_widget_from_latest_event(rig, strategy_widget)
    assert strategy_widget.stop_button.isEnabled()
    assert not strategy_widget.remove_button.isEnabled()
    order = rig.gateway.orders[orderid]
    rig.engine.process_order_event(Event(EVENT_ORDER, replace(order, status=Status.CANCELLED)))
    update_widget_from_latest_event(rig, strategy_widget)
    assert not strategy_widget.stop_button.isEnabled()
    assert strategy_widget.remove_button.isEnabled()


@pytest.mark.parametrize("running", [False, True])
def test_new_widget_uses_the_current_strategy_state(rig: EngineRig, strategy_qt_app: QtWidgets.QApplication, running: bool) -> None:
    rig.engine._init_strategy("target")
    if running:
        rig.engine.start_strategy("target")
    widget = StrategyManager(None, rig.engine, rig.strategy.get_data())  # type: ignore[arg-type]
    try:
        assert not widget.init_button.isEnabled()
        assert widget.start_button.isEnabled() is not running
        assert widget.stop_button.isEnabled() is running
        assert widget.remove_button.isEnabled() is not running
    finally:
        widget.close()
        widget.deleteLater()
        strategy_qt_app.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        strategy_qt_app.processEvents()


def test_first_init_can_be_retried_without_losing_saved_positions(rig: EngineRig, monkeypatch: pytest.MonkeyPatch) -> None:
    rig.engine.strategy_data["target"] = {"pos_data": {RB: 7}}

    def fail() -> None:
        raise RuntimeError("first initialization failed")

    monkeypatch.setattr(rig.strategy, "on_init", fail)
    rig.engine._init_strategy("target")
    assert not rig.strategy.inited
    monkeypatch.setattr(rig.strategy, "on_init", lambda: None)
    rig.engine._init_strategy("target")
    assert (rig.strategy.inited, rig.strategy.trading) == (True, False)
    assert rig.strategy.get_pos(RB) == 7
    rig.engine.start_strategy("target")
    assert rig.strategy.trading


def test_late_error_from_removed_instance_does_not_block_reused_name(rig: EngineRig, monkeypatch: pytest.MonkeyPatch) -> None:
    rig.engine._init_strategy("target")
    fail_start(rig, monkeypatch)
    old = rig.strategy
    assert rig.engine.remove_strategy("target")
    rig.engine.add_strategy(TargetStrategy.__name__, "target", [RB, AG], {})
    new = rig.engine.strategies["target"]
    rig.engine._init_strategy("target")

    def fail() -> None:
        raise RuntimeError("late error on removed instance")

    rig.engine.call_strategy_func(old, fail)
    rig.engine.start_strategy("target")
    assert new is not old
    assert (new.inited, new.trading) == (True, True)


def test_custom_strategy_does_not_need_to_be_hashable(rig: EngineRig, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(TargetStrategy, "__hash__", None)
    with pytest.raises(TypeError):
        hash(rig.strategy)
    rig.engine._init_strategy("target")
    rig.engine.start_strategy("target")
    assert (rig.strategy.inited, rig.strategy.trading) == (True, True)


def test_stopping_fresh_ready_strategy_still_has_no_side_effects(rig: EngineRig, monkeypatch: pytest.MonkeyPatch) -> None:
    rig.engine._init_strategy("target")
    saved: list[str] = []
    monkeypatch.setattr(rig.engine, "sync_strategy_data", lambda strategy: saved.append(strategy.strategy_name))
    before = len(rig.engine.event_engine.events)
    rig.engine.stop_strategy("target")
    assert saved == []
    assert len(rig.engine.event_engine.events) == before
    assert rig.gateway.cancel_requests == []


@pytest.mark.parametrize("error", [SystemExit, KeyboardInterrupt])
def test_base_exceptions_still_propagate(rig: EngineRig, monkeypatch: pytest.MonkeyPatch, error: type[BaseException]) -> None:
    rig.engine._init_strategy("target")

    def fail() -> None:
        raise error("exit")

    monkeypatch.setattr(rig.strategy, "on_start", fail)
    with pytest.raises(error):
        rig.engine.start_strategy("target")


@pytest.fixture
def strategy_window(rig: EngineRig, strategy_qt_app: QtWidgets.QApplication, monkeypatch: pytest.MonkeyPatch) -> Iterator[PortfolioStrategyManager]:
    monkeypatch.setattr(rig.engine.event_engine, "register", lambda *args: None, raising=False)
    log_engine = LogEngine(rig.engine.main_engine, rig.engine.event_engine)  # type: ignore[arg-type]
    monkeypatch.setattr(rig.engine.main_engine, "get_engine", lambda name: log_engine if name == "log" else rig.engine, raising=False)
    monkeypatch.setattr(rig.engine, "datafeed", BaseDatafeed())
    window = PortfolioStrategyManager(rig.engine.main_engine, rig.engine.event_engine)
    try:
        yield window
    finally:
        window.close()
        window.deleteLater()
        strategy_qt_app.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        strategy_qt_app.processEvents()


def latest_strategy_event(rig: EngineRig) -> Event:
    events = [event for event in rig.engine.event_engine.events if event.type == EVENT_PORTFOLIO_STRATEGY]
    return Event(EVENT_PORTFOLIO_STRATEGY, deepcopy(events[-1].data))


def test_buffered_failure_event_cannot_undo_successful_reinitialization(rig: EngineRig, strategy_window: PortfolioStrategyManager, monkeypatch: pytest.MonkeyPatch) -> None:
    rig.engine._init_strategy("target")
    fail_start(rig, monkeypatch)
    buffered = latest_strategy_event(rig)
    rig.engine._init_strategy("target")
    strategy_window.process_strategy_event(buffered)
    widget = strategy_window.managers["target"]
    assert widget._data["variables"]["inited"] is True
    assert widget.start_button.isEnabled()
    assert not widget.init_button.isEnabled()


def test_buffered_old_instance_event_uses_replacement_state(rig: EngineRig, strategy_window: PortfolioStrategyManager, monkeypatch: pytest.MonkeyPatch) -> None:
    rig.engine._init_strategy("target")
    fail_start(rig, monkeypatch)
    buffered = latest_strategy_event(rig)
    rig.engine.stop_strategy("target")
    assert rig.engine.remove_strategy("target")
    rig.engine.add_strategy(TargetStrategy.__name__, "target", [RB, AG], {})
    new = rig.engine.strategies["target"]
    rig.engine._init_strategy("target")
    new.pos_data[RB] = 8
    strategy_window.process_strategy_event(buffered)
    widget = strategy_window.managers["target"]
    assert widget._data["variables"]["pos_data"][RB] == 8
    assert widget._data["variables"]["inited"] is True


def test_removed_instance_event_does_not_recreate_widget(rig: EngineRig, strategy_window: PortfolioStrategyManager) -> None:
    buffered = latest_strategy_event(rig)
    assert rig.engine.remove_strategy("target")
    strategy_window.process_strategy_event(buffered)
    assert "target" not in strategy_window.managers


def test_replaced_instance_start_error_does_not_poison_new_strategy(rig: EngineRig, monkeypatch: pytest.MonkeyPatch) -> None:
    rig.engine._init_strategy("target")

    def replace_then_fail() -> None:
        assert rig.engine.remove_strategy("target")
        rig.engine.add_strategy(TargetStrategy.__name__, "target", [RB, AG], {})
        rig.engine._init_strategy("target")
        raise RuntimeError("old instance failed after replacement")

    monkeypatch.setattr(rig.strategy, "on_start", replace_then_fail)
    rig.engine.start_strategy("target")
    new = rig.engine.strategies["target"]
    assert new is not rig.strategy
    rig.engine.start_strategy("target")
    assert (new.inited, new.trading) == (True, True)


def test_removed_instance_cannot_be_started_by_old_completion(rig: EngineRig, monkeypatch: pytest.MonkeyPatch) -> None:
    rig.engine._init_strategy("target")

    def replace_then_return() -> None:
        assert rig.engine.remove_strategy("target")
        rig.engine.add_strategy(TargetStrategy.__name__, "target", [RB, AG], {})
        rig.engine._init_strategy("target")

    monkeypatch.setattr(rig.strategy, "on_start", replace_then_return)
    rig.engine.start_strategy("target")
    new = rig.engine.strategies["target"]
    assert new is not rig.strategy
    assert rig.strategy.trading is False
    assert (new.inited, new.trading) == (True, False)



@pytest.mark.parametrize("reset_during_init", [False, True])
def test_public_reinitialization_restores_saved_variables(
    rig: EngineRig, monkeypatch: pytest.MonkeyPatch, reset_during_init: bool
) -> None:
    rig.strategy.variables.append("recovery_counter")
    rig.strategy.recovery_counter = 0
    rig.engine.strategy_data["target"] = {
        "pos_data": {RB: 7}, "target_data": {RB: 9}, "recovery_counter": 5
    }

    def initialize() -> None:
        if reset_during_init:
            rig.strategy.pos_data.clear()
            rig.strategy.recovery_counter = 0

    monkeypatch.setattr(rig.strategy, "on_init", initialize)
    rig.engine.init_strategy("target")
    rig.engine.init_executor.submit(lambda: None).result(timeout=4)
    assert rig.strategy.get_pos(RB) == 7
    assert rig.strategy.recovery_counter == 5
    fail_start(rig, monkeypatch)
    rig.engine.init_strategy("target")
    rig.engine.init_executor.submit(lambda: None).result(timeout=4)
    assert rig.strategy.get_pos(RB) == 7
    assert rig.strategy.recovery_counter == 5



def test_failed_public_reinitialization_does_not_overwrite_saved_variables(
    rig: EngineRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved = {"target": {"pos_data": {RB: 7}, "target_data": {RB: 9}, "recovery_counter": 5}}
    path = TEMP_DIR.joinpath(rig.engine.data_filename)
    path.write_text(json.dumps(saved), encoding="utf-8")
    rig.engine.strategy_data = deepcopy(saved)
    rig.strategy.variables.append("recovery_counter")
    rig.strategy.recovery_counter = 0
    rig.engine.init_strategy("target")
    rig.engine.init_executor.submit(lambda: None).result(timeout=4)
    assert rig.strategy.get_pos(RB) == 7
    fail_start(rig, monkeypatch)

    def fail_initialization() -> None:
        rig.strategy.pos_data.clear()
        rig.strategy.recovery_counter = 0
        raise RuntimeError("reinitialization failed after resetting defaults")

    monkeypatch.setattr(rig.strategy, "on_init", fail_initialization)
    rig.engine.init_strategy("target")
    rig.engine.init_executor.submit(lambda: None).result(timeout=4)
    rig.engine.close()
    assert json.loads(path.read_text(encoding="utf-8")) == saved
