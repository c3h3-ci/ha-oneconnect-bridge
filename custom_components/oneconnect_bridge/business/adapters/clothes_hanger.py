"""Huawei `clothesHanger` service adapter for the Hotata airer.

The `clothesHanger` service bundles four usable characteristics plus two
remaining-time counters. Default contract source: prodId `174P`
(好太太定制晾衣机), Profile
https://smarthome-drcn.dbankcdn.com/device/guide/174P/174P.json

| characteristic | type | method | meaning                          |
| -------------- | ---- | ------ | -------------------------------- |
| action         | int  | RW     | 0 升 / 1 降 / 2 暂停              |
| lighting       | bool | RW     | 1 照明开 / 0 照明关               |
| disinfect      | bool | RW     | 1 杀菌开 / 0 杀菌关               |
| status         | int  | RW     | 0 其他 / 1 最高 / 2 最低          |
| lightingTime   | int  | RW     | 30..180 分钟                     |
| disinfectTime  | int  | R      | 0..30 分钟                       |

The two `*Left` counters are read-only Profile internals and are not mapped.

This adapter binds **one HA entity per service**. The typical projection binds
three sibling services (a `cover` for `action`, a `light` for `lighting` and a
`switch` for `disinfect`) by declaring the same `clothesHanger` service three
times with different `field` contract values.

Contract:
  `field` selects which characteristic this binding drives:
  `action` (default) / `lighting` / `disinfect` / `status`.
  `entities` must match the field: `cover` for action, `light` for lighting,
  `switch`/`input_boolean` for disinfect and status.

Verified against a real projection (1 Hotata airer registered through
OneConnect Bridge 0.1.x; lighting and disinfect on/off plus raise/lower/pause
all confirmed in both directions).
"""

from __future__ import annotations

from ..models import ServiceRef


_ACTION_SERVICES = {0: "close_cover", 1: "open_cover", 2: "stop_cover"}
_FIELDS = {"action", "lighting", "disinfect", "status"}
_ALLOWED_DOMAINS = {"cover", "light", "switch", "input_boolean", "sensor"}
_FIELD_DOMAINS = {
    "action": {"cover"},
    "lighting": {"light", "switch", "input_boolean"},
    "disinfect": {"switch", "input_boolean", "light"},
    "status": {"sensor", "switch", "input_boolean"},
}


class ClothesHangerServiceAdapter:
    service_id = "clothesHanger"

    def validate_service(self, service: ServiceRef) -> None:
        if service.service_type != "clothesHanger":
            raise ValueError("clothesHanger requires st: clothesHanger")
        unknown = set(dict(service.contract)) - {"field"}
        if unknown:
            raise ValueError(
                "clothesHanger has unsupported contract keys: "
                + ", ".join(sorted(unknown))
            )
        _field(service)

    def validate_entities(self, entity_ids: tuple[str, ...]) -> None:
        if len(entity_ids) != 1:
            raise ValueError("clothesHanger currently requires exactly one HA entity")
        domain, separator, _object_id = entity_ids[0].partition(".")
        if not separator or domain not in _ALLOWED_DOMAINS:
            raise ValueError(
                "clothesHanger requires one of " + ", ".join(sorted(_ALLOWED_DOMAINS))
            )

    async def read_state(
        self, hass, service: ServiceRef, entity_ids: tuple[str, ...]
    ) -> dict[str, object]:
        self.validate_service(service)
        self.validate_entities(entity_ids)
        field = _field(service)
        _check_domain(entity_ids[0], field)
        state = hass.states.get(entity_ids[0])
        if state is None or state.state in {"unknown", "unavailable"}:
            return {}
        if field == "action":
            mapping = {"open": 1, "opening": 1, "closed": 0, "closing": 0}
            value = mapping.get(state.state)
            return {"action": value} if value is not None else {}
        if field == "lighting" or field == "disinfect":
            return {field: state.state == "on"}
        # status: report the HA state verbatim when it is numeric, else drop it.
        try:
            return {"status": int(state.state)}
        except (TypeError, ValueError):
            return {}

    async def apply_command(
        self,
        hass,
        service: ServiceRef,
        entity_ids: tuple[str, ...],
        payload: dict[str, object],
    ) -> None:
        self.validate_service(service)
        self.validate_entities(entity_ids)
        field = _field(service)
        domain = entity_ids[0].partition(".")[0]
        _check_domain(entity_ids[0], field)
        if field not in payload:
            return
        value = payload[field]
        if field == "action":
            if isinstance(value, bool) or not isinstance(value, int):
                return
            service_name = _ACTION_SERVICES.get(value)
            if service_name is None:
                return
            await hass.services.async_call(
                "cover", service_name, {"entity_id": entity_ids[0]}, blocking=True
            )
            return
        if not isinstance(value, bool):
            return
        await hass.services.async_call(
            domain,
            "turn_on" if value else "turn_off",
            {"entity_id": entity_ids[0]},
            blocking=True,
        )


ADAPTER = ClothesHangerServiceAdapter()


def _check_domain(entity_id: str, field: str) -> None:
    domain = entity_id.partition(".")[0]
    if domain not in _FIELD_DOMAINS[field]:
        raise ValueError(
            f"clothesHanger {field} requires one of "
            + ", ".join(sorted(_FIELD_DOMAINS[field]))
        )


def _field(service: ServiceRef) -> str:
    value = service.contract_value("field", "action")
    if not isinstance(value, str) or value not in _FIELDS:
        raise ValueError(
            f"clothesHanger contract field must be one of {', '.join(sorted(_FIELDS))}"
        )
    return value
