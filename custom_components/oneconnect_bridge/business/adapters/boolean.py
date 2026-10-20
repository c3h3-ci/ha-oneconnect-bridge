"""Generic single-boolean-characteristic Huawei service adapter.

Many Profiles expose a dedicated boolean service per feature where the service
id, the service type and the characteristic name are all the same token, for
example the Haier fridge profile prodId `A0VG`:

| sid                  | st                  | characteristic        |
| -------------------- | ------------------- | --------------------- |
| intelligenceMode     | intelligenceMode    | intelligenceMode      |
| dailyStatus          | dailyStatus         | dailyStatus           |
| travelMode           | travelMode          | travelMode            |
| quickFreezingMode    | quickFreezingMode   | quickFreezingMode     |
| quickRefrigeratingMode | quickRefrigeratingMode | quickRefrigeratingMode |

Rather than duplicating one near-identical adapter per sid, this adapter is
registered once per boolean sid through `register_boolean_adapter`. It maps
`{"<char>": true|false}` onto `turn_on` / `turn_off` for the bound entity and
reports the entity state back with the same characteristic name.

Contract:
  `on_value` / `off_value` override the uploaded JSON values (defaults
  `true` / `false`). Use `{"on_value": 1, "off_value": 0}` for Profiles that
  document an int encoding.

Verified against a real projection (5 A0VG fridge boolean children registered
through OneConnect Bridge 0.1.x, state reporting and on/off commands confirmed).
"""

from __future__ import annotations

from ..models import ServiceRef


class BooleanServiceAdapter:
    """Adapter for a service whose single characteristic is a boolean."""

    def __init__(self, service_id: str) -> None:
        self.service_id = service_id

    # -- validation ------------------------------------------------------

    def validate_service(self, service: ServiceRef) -> None:
        if service.service_id != self.service_id:
            raise ValueError(f"{self.service_id} adapter cannot serve {service.service_id}")
        if not service.service_type:
            raise ValueError(f"{self.service_id} requires a service type")
        unknown = set(dict(service.contract)) - {"on_value", "off_value", "characteristic"}
        if unknown:
            raise ValueError(
                f"{self.service_id} has unsupported contract keys: "
                + ", ".join(sorted(unknown))
            )
        _values(service)

    def validate_entities(self, entity_ids: tuple[str, ...]) -> None:
        if len(entity_ids) != 1:
            raise ValueError(f"{self.service_id} currently requires exactly one HA entity")
        domain, separator, _object_id = entity_ids[0].partition(".")
        if not separator or domain not in {"switch", "light", "fan", "input_boolean"}:
            raise ValueError(
                f"{self.service_id} requires a switch, light, fan or input_boolean entity"
            )

    # -- conversion ------------------------------------------------------

    async def read_state(
        self, hass, service: ServiceRef, entity_ids: tuple[str, ...]
    ) -> dict[str, object]:
        self.validate_service(service)
        self.validate_entities(entity_ids)
        state = hass.states.get(entity_ids[0])
        if state is None or state.state not in {"on", "off"}:
            return {}
        on_value, off_value = _values(service)
        return {_characteristic(service): on_value if state.state == "on" else off_value}

    async def apply_command(
        self,
        hass,
        service: ServiceRef,
        entity_ids: tuple[str, ...],
        payload: dict[str, object],
    ) -> None:
        self.validate_service(service)
        self.validate_entities(entity_ids)
        characteristic = _characteristic(service)
        if characteristic not in payload:
            return
        on_value, off_value = _values(service)
        value = payload[characteristic]
        if value == on_value:
            enabled = True
        elif value == off_value:
            enabled = False
        else:
            return
        domain, _separator, _object_id = entity_ids[0].partition(".")
        await hass.services.async_call(
            domain,
            "turn_on" if enabled else "turn_off",
            {"entity_id": entity_ids[0]},
            blocking=True,
        )


def _characteristic(service: ServiceRef) -> str:
    value = service.contract_value("characteristic", service.service_id)
    if isinstance(value, str) and value:
        return value
    return service.service_id


def _values(service: ServiceRef) -> tuple[object, object]:
    on_value = service.contract_value("on_value", True)
    off_value = service.contract_value("off_value", False)
    if isinstance(on_value, bool) is False and on_value not in (True, 1, "1"):
        on_value = True
    if isinstance(off_value, bool) is False and off_value not in (False, 0, "0"):
        off_value = False
    return on_value, off_value


def register_boolean_adapter(service_id: str, service_type: str | None = None) -> BooleanServiceAdapter:
    """Build one adapter instance for a boolean sid.

    `service_type` exists only so callers can document the expected Profile
    `st`; validation accepts any non-empty type because Huawei reuses the sid
    as the service type for these single-feature services.
    """
    del service_type
    return BooleanServiceAdapter(service_id)
