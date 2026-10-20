from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


_BUSINESS_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "oneconnect_bridge"
    / "business"
)
_INTEGRATION_PATH = _BUSINESS_PATH.parent
_integration_package = ModuleType("custom_components.oneconnect_bridge")
_integration_package.__path__ = [str(_INTEGRATION_PATH)]
sys.modules.setdefault("custom_components.oneconnect_bridge", _integration_package)
_business_package = ModuleType("custom_components.oneconnect_bridge.business")
_business_package.__path__ = [str(_BUSINESS_PATH)]
sys.modules.setdefault("custom_components.oneconnect_bridge.business", _business_package)

from custom_components.oneconnect_bridge.business.adapters import get_service_adapter
from custom_components.oneconnect_bridge.business.models import ServiceRef


class _FakeServices:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object], bool]] = []

    async def async_call(
        self,
        domain: str,
        service: str,
        data: dict[str, object],
        *,
        blocking: bool,
    ) -> None:
        self.calls.append((domain, service, data, blocking))


class _FakeHass:
    def __init__(self, states: dict[str, object]) -> None:
        self.services = _FakeServices()
        self.states = SimpleNamespace(get=states.get)


def _state(value: str, **attributes: object) -> SimpleNamespace:
    return SimpleNamespace(state=value, attributes=attributes)


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------
# boolean single-feature services (A0VG fridge)
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "service_id",
    ["intelligenceMode", "dailyStatus", "travelMode", "quickFreezingMode", "quickRefrigeratingMode"],
)
def test_boolean_adapters_report_and_apply(service_id: str) -> None:
    adapter = get_service_adapter(service_id)
    hass = _FakeHass({"switch.fridge": _state("on")})
    service = ServiceRef(service_id, service_id)

    assert _run(adapter.read_state(hass, service, ("switch.fridge",))) == {
        service_id: True
    }

    hass = _FakeHass({"switch.fridge": _state("off")})
    assert _run(adapter.read_state(hass, service, ("switch.fridge",))) == {
        service_id: False
    }

    hass = _FakeHass({"switch.fridge": _state("off")})
    _run(adapter.apply_command(hass, service, ("switch.fridge",), {service_id: True}))
    _run(adapter.apply_command(hass, service, ("switch.fridge",), {service_id: False}))
    assert [call[1] for call in hass.services.calls] == ["turn_on", "turn_off"]


def test_boolean_adapter_supports_an_int_encoding() -> None:
    adapter = get_service_adapter("quickFreezingMode")
    hass = _FakeHass({"switch.fridge": _state("on")})
    service = ServiceRef(
        "quickFreezingMode", "quickFreezingMode", (("on_value", 1), ("off_value", 0))
    )

    assert _run(adapter.read_state(hass, service, ("switch.fridge",))) == {
        "quickFreezingMode": 1
    }
    _run(adapter.apply_command(hass, service, ("switch.fridge",), {"quickFreezingMode": 1}))
    assert hass.services.calls[0][1] == "turn_on"


def test_boolean_adapter_supports_a_renamed_characteristic() -> None:
    adapter = get_service_adapter("dailyStatus")
    hass = _FakeHass({"switch.fridge": _state("on")})
    service = ServiceRef("dailyStatus", "dailyStatus", (("characteristic", "on"),))

    assert _run(adapter.read_state(hass, service, ("switch.fridge",))) == {"on": True}


def test_boolean_adapter_rejects_unsupported_domains_and_contracts() -> None:
    adapter = get_service_adapter("travelMode")
    with pytest.raises(ValueError):
        adapter.validate_entities(("sensor.temperature",))
    with pytest.raises(ValueError):
        adapter.validate_service(ServiceRef("travelMode", "travelMode", (("factor", 2),)))


def test_boolean_adapter_ignores_unavailable_entities() -> None:
    adapter = get_service_adapter("travelMode")
    hass = _FakeHass({"switch.fridge": _state("unavailable")})
    service = ServiceRef("travelMode", "travelMode")

    assert _run(adapter.read_state(hass, service, ("switch.fridge",))) == {}


# --------------------------------------------------------------------------
# clothesHanger (Hotata airer, 174P)
# --------------------------------------------------------------------------

def test_clothes_hanger_action_maps_raise_lower_pause() -> None:
    adapter = get_service_adapter("clothesHanger")
    hass = _FakeHass({"cover.airer": _state("open")})
    service = ServiceRef("clothesHanger", "clothesHanger", (("field", "action"),))

    assert _run(adapter.read_state(hass, service, ("cover.airer",))) == {"action": 1}

    hass = _FakeHass({"cover.airer": _state("closed")})
    assert _run(adapter.read_state(hass, service, ("cover.airer",))) == {"action": 0}

    hass = _FakeHass({"cover.airer": _state("open")})
    for enum_value, expected in ((1, "open_cover"), (0, "close_cover"), (2, "stop_cover")):
        _run(adapter.apply_command(hass, service, ("cover.airer",), {"action": enum_value}))
        assert hass.services.calls[-1][1] == expected


def test_clothes_hanger_lighting_and_disinfect_fields() -> None:
    adapter = get_service_adapter("clothesHanger")
    hass = _FakeHass(
        {"light.airer": _state("on"), "switch.airer_disinfect": _state("off")}
    )
    lighting = ServiceRef("clothesHanger", "clothesHanger", (("field", "lighting"),))
    disinfect = ServiceRef("clothesHanger", "clothesHanger", (("field", "disinfect"),))

    assert _run(adapter.read_state(hass, lighting, ("light.airer",))) == {"lighting": True}
    assert _run(adapter.read_state(hass, disinfect, ("switch.airer_disinfect",))) == {
        "disinfect": False
    }

    hass = _FakeHass(
        {"light.airer": _state("off"), "switch.airer_disinfect": _state("off")}
    )
    _run(adapter.apply_command(hass, lighting, ("light.airer",), {"lighting": True}))
    _run(adapter.apply_command(hass, disinfect, ("switch.airer_disinfect",), {"disinfect": True}))
    assert [call[:2] for call in hass.services.calls] == [
        ("light", "turn_on"),
        ("switch", "turn_on"),
    ]


def test_clothes_hanger_rejects_a_field_entity_mismatch() -> None:
    adapter = get_service_adapter("clothesHanger")
    service = ServiceRef("clothesHanger", "clothesHanger", (("field", "action"),))
    # validate_entities only knows the domain set, so the field/domain pairing is
    # enforced where the contract is available.
    adapter.validate_entities(("cover.airer",))
    with pytest.raises(ValueError):
        adapter.validate_entities(("climate.airer",))
    hass = _FakeHass({"switch.airer": _state("on")})
    with pytest.raises(ValueError):
        _run(adapter.read_state(hass, service, ("switch.airer",)))


def test_clothes_hanger_rejects_unknown_fields_and_contracts() -> None:
    adapter = get_service_adapter("clothesHanger")
    with pytest.raises(ValueError):
        adapter.validate_service(ServiceRef("switch", "clothesHanger"))
    with pytest.raises(ValueError):
        adapter.validate_service(
            ServiceRef("clothesHanger", "clothesHanger", (("field", "nope"),))
        )
    with pytest.raises(ValueError):
        adapter.validate_service(
            ServiceRef("clothesHanger", "clothesHanger", (("factor", 2),))
        )


# --------------------------------------------------------------------------
# enum services with per-product tables (action / status)
# --------------------------------------------------------------------------

def test_enum_action_requires_a_mapping_and_maps_both_ways() -> None:
    adapter = get_service_adapter("action")
    # A2GT dishwasher: 0 enable, 1 stop.
    service = ServiceRef(
        "action", "action", (("mapping", {"0": "on", "1": "off"}),)
    )
    hass = _FakeHass({"switch.dishwasher": _state("on")})

    assert _run(adapter.read_state(hass, service, ("switch.dishwasher",))) == {
        "action": 0
    }

    hass = _FakeHass({"switch.dishwasher": _state("off")})
    assert _run(adapter.read_state(hass, service, ("switch.dishwasher",))) == {
        "action": 1
    }

    hass = _FakeHass({"switch.dishwasher": _state("off")})
    _run(adapter.apply_command(hass, service, ("switch.dishwasher",), {"action": 0}))
    assert hass.services.calls[0][:2] == ("switch", "turn_on")


def test_enum_action_supports_cover_products() -> None:
    adapter = get_service_adapter("action")
    # 2QXU projection screen: 0 open, 1 close, 2 pause.
    service = ServiceRef(
        "action",
        "action",
        (("mapping", {"0": "open", "1": "close", "2": "stop"}), ("service", "noop")),
    )
    hass = _FakeHass({"cover.screen": _state("open")})

    assert _run(adapter.read_state(hass, service, ("cover.screen",))) == {"action": 0}


def test_enum_status_is_read_only_by_contract() -> None:
    adapter = get_service_adapter("status")
    # A2GQ dryer: 1 idle, 3 running, 5 finished.
    service = ServiceRef(
        "status",
        "status",
        (("mapping", {"1": "idle", "3": "running", "5": "finished"}),),
    )
    hass = _FakeHass({"sensor.dryer": _state("running")})

    assert _run(adapter.read_state(hass, service, ("sensor.dryer",))) == {"status": 3}

    # The shared action adapter is writable, so a read-only projection must use
    # the dedicated status adapter and must never call an HA service.
    hass = _FakeHass({"sensor.dryer": _state("running")})
    _run(adapter.apply_command(hass, service, ("sensor.dryer",), {"status": 3}))
    assert hass.services.calls == []


def test_enum_adapters_reject_an_empty_or_unknown_mapping() -> None:
    adapter = get_service_adapter("action")
    with pytest.raises(ValueError):
        adapter.validate_service(ServiceRef("action", "action"))
    with pytest.raises(ValueError):
        adapter.validate_service(ServiceRef("action", "action", (("mapping", {}),)))
    with pytest.raises(ValueError):
        adapter.validate_service(ServiceRef("action", "action", (("factor", 2),)))


def test_enum_adapters_drop_unknown_ha_states() -> None:
    adapter = get_service_adapter("status")
    service = ServiceRef("status", "status", (("mapping", {"1": "idle"}),))
    hass = _FakeHass({"sensor.dryer": _state("exploded")})

    assert _run(adapter.read_state(hass, service, ("sensor.dryer",))) == {}


# --------------------------------------------------------------------------
# leftTime / lefttime1 (A2GQ dryer, A2GT dishwasher)
# --------------------------------------------------------------------------

def test_left_time_reports_clamped_minutes() -> None:
    adapter = get_service_adapter("leftTime")
    hass = _FakeHass({"sensor.dryer": _state("idle", remaining_time=42)})
    # A2GQ: sid=leftTime, st=time, characteristic=time (adapter default).
    service = ServiceRef("time", "leftTime")

    assert _run(adapter.read_state(hass, service, ("sensor.dryer",))) == {"time": 42}

    hass = _FakeHass({"sensor.dryer": _state("idle", remaining_time=9999)})
    assert _run(adapter.read_state(hass, service, ("sensor.dryer",))) == {"time": 1440}


def test_left_time_supports_the_dishwasher_characteristic_name() -> None:
    adapter = get_service_adapter("lefttime1")
    hass = _FakeHass({"sensor.dishwasher": _state("idle", remaining_time=30)})
    # A2GT: sid=lefttime1, st=lefttime1, characteristic=lefttime (adapter default).
    service = ServiceRef("lefttime1", "lefttime1")

    assert _run(adapter.read_state(hass, service, ("sensor.dishwasher",))) == {
        "lefttime": 30
    }


def test_left_time_falls_back_to_the_entity_state() -> None:
    adapter = get_service_adapter("leftTime")
    hass = _FakeHass({"sensor.dryer": _state("55")})
    service = ServiceRef("time", "leftTime")

    assert _run(adapter.read_state(hass, service, ("sensor.dryer",))) == {"time": 55}


def test_left_time_rejects_unsupported_contracts() -> None:
    adapter = get_service_adapter("leftTime")
    with pytest.raises(ValueError):
        adapter.validate_service(ServiceRef("leftTime", "leftTime", (("factor", 2),)))


def test_left_time_ignores_unavailable_entities() -> None:
    adapter = get_service_adapter("leftTime")
    hass = _FakeHass({"sensor.dryer": _state("unavailable")})
    service = ServiceRef("leftTime", "leftTime")

    assert _run(adapter.read_state(hass, service, ("sensor.dryer",))) == {}


# --------------------------------------------------------------------------
# registry completeness
# --------------------------------------------------------------------------

def test_registry_exposes_every_real_device_adapter() -> None:
    expected = {
        "switch",
        "switch1",
        "brightness",
        "cct",
        "colour",
        "mode",
        "temperature",
        "motorization",
        "clothesHanger",
        "intelligenceMode",
        "dailyStatus",
        "travelMode",
        "quickFreezingMode",
        "quickRefrigeratingMode",
        "action",
        "status",
        "leftTime",
        "lefttime1",
    }
    for service_id in expected:
        assert get_service_adapter(service_id).service_id == service_id


# --------------------------------------------------------------------------
# read-only numeric services (A0VG fridge temperatures)
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "service_id,minimum",
    [
        ("refrigeratorTemperatureC", -38),
        ("freezerTemperatureC", -23),
        ("vtRoomTemperature", -38),
    ],
)
def test_readonly_number_reports_clamped_degrees(service_id: str, minimum: int) -> None:
    adapter = get_service_adapter(service_id)
    hass = _FakeHass({"sensor.fridge": _state("5")})
    service = ServiceRef(service_id, service_id)

    assert _run(adapter.read_state(hass, service, ("sensor.fridge",))) == {
        service_id: 5
    }

    hass = _FakeHass({"sensor.fridge": _state("-100")})
    assert _run(adapter.read_state(hass, service, ("sensor.fridge",))) == {
        service_id: minimum
    }


def test_readonly_number_supports_a_scale_factor() -> None:
    adapter = get_service_adapter("refrigeratorTemperatureC")
    hass = _FakeHass({"sensor.fridge": _state("5.0")})
    service = ServiceRef(
        "refrigeratorTemperatureC",
        "refrigeratorTemperatureC",
        (("factor", 10), ("min", -380), ("max", 500)),
    )

    assert _run(adapter.read_state(hass, service, ("sensor.fridge",))) == {
        "refrigeratorTemperatureC": 50
    }


def test_readonly_number_never_calls_ha_services() -> None:
    adapter = get_service_adapter("freezerTemperatureC")
    hass = _FakeHass({"sensor.fridge": _state("-18")})
    service = ServiceRef("freezerTemperatureC", "freezerTemperatureC")

    _run(adapter.apply_command(hass, service, ("sensor.fridge",), {"freezerTemperatureC": -18}))

    assert hass.services.calls == []


def test_readonly_number_rejects_writable_domains_and_contracts() -> None:
    adapter = get_service_adapter("vtRoomTemperature")
    with pytest.raises(ValueError):
        adapter.validate_entities(("switch.fridge",))
    with pytest.raises(ValueError):
        adapter.validate_service(
            ServiceRef("vtRoomTemperature", "vtRoomTemperature", (("factor", 0),))
        )
    with pytest.raises(ValueError):
        adapter.validate_service(
            ServiceRef("vtRoomTemperature", "vtRoomTemperature", (("mapping", {}),))
        )


def test_readonly_number_ignores_unavailable_entities() -> None:
    adapter = get_service_adapter("vtRoomTemperature")
    hass = _FakeHass({"sensor.fridge": _state("unavailable")})
    service = ServiceRef("vtRoomTemperature", "vtRoomTemperature")

    assert _run(adapter.read_state(hass, service, ("sensor.fridge",))) == {}
