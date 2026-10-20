"""Explicit registry of trusted Huawei service adapters.

Combines the upstream adapter set (switch, brightness, cct, colour, mode,
temperature, motorization, opener, status, action, ...) with the real-device
adapters added on the bench: clothesHanger, enum-backed action/status and
leftTime countdowns.
"""

from __future__ import annotations

from .action import ADAPTER as ACTION
from .alarm import ADAPTER as ALARM
from .air_detector import ADAPTER as AIR_DETECTOR
from .api import ServiceAdapter
from .boolean import register_boolean_adapter
from .brightness import ADAPTER as BRIGHTNESS
from .cct import ADAPTER as CCT
from .cleaner_robot import ADAPTER as CLEANER_ROBOT
from .clothes_hanger import ADAPTER as CLOTHES_HANGER
from .colour import ADAPTER as COLOUR
from .enum_service import register_enum_adapter
from .fan import ADAPTER as FAN
from .gas_sensor import ADAPTER as GAS_SENSOR
from .hcho import ADAPTER as HCHO
from .humidity import ADAPTER as HUMIDITY
from .left_time import register_left_time_adapter
from .mode import ADAPTER as MODE
from .motor import ADAPTER as MOTOR
from .open_level import ADAPTER as OPEN_LEVEL
from .opener import ADAPTER as OPENER
from .status import ADAPTER as STATUS
from .switch import ADAPTER as SWITCH
from .temperature import ADAPTER as TEMPERATURE


def _build_adapters() -> dict[str, ServiceAdapter]:
    adapters: dict[str, ServiceAdapter] = {}
    for adapter in (
        SWITCH,
        BRIGHTNESS,
        CCT,
        COLOUR,
        TEMPERATURE,
        HUMIDITY,
        AIR_DETECTOR,
        MOTOR,
        OPEN_LEVEL,
        OPENER,
        HCHO,
        ALARM,
        GAS_SENSOR,
        MODE,
        FAN,
        CLEANER_ROBOT,
        STATUS,
        ACTION,
        CLOTHES_HANGER,
    ):
        adapters[adapter.service_id] = adapter
    for _service_id in ("switch1", "switch2", "switch3"):
        adapters[_service_id] = SWITCH
    adapters["leftAction"] = ACTION
    for _service_id in _BOOLEAN_SERVICE_IDS:
        adapters[_service_id] = register_boolean_adapter(_service_id)
    # `status` is method R on the real Profiles; `action` is method RW.
    adapters["action"] = register_enum_adapter("action", writable=True)
    adapters["status"] = register_enum_adapter("status", writable=False)
    for _service_id in _LEFT_TIME_SERVICE_IDS:
        adapters[_service_id] = register_left_time_adapter(_service_id)
    return adapters


_SERVICE_ADAPTERS: dict[str, ServiceAdapter] = _build_adapters()


def get_service_adapter(service_id: str) -> ServiceAdapter:
    try:
        return _SERVICE_ADAPTERS[service_id]
    except KeyError as error:
        raise ValueError(f"unknown Huawei service: {service_id}") from error
