"""Huawei ``temperature`` measurement service adapter."""

from __future__ import annotations

import math

from ..models import ServiceRef


_DOMAINS = {"climate", "sensor", "number", "input_number"}


class TemperatureServiceAdapter:
    service_id = "temperature"

    def validate_service(self, service: ServiceRef) -> None:
        if service.service_type != "temperature":
            raise ValueError("temperature requires st: temperature")
        unknown = set(dict(service.contract)) - {"factor", "min", "max", "step", "characteristic"}
        if unknown:
            raise ValueError(
                "temperature has unsupported contract keys: "
                f"{', '.join(sorted(unknown))}"
            )
        _measurement_contract(service)

    def validate_entities(self, entity_ids: tuple[str, ...]) -> None:
        if len(entity_ids) != 1:
            raise ValueError("temperature currently requires exactly one HA entity")
        domain, separator, _object_id = entity_ids[0].partition(".")
        if not separator or domain not in _DOMAINS:
            raise ValueError(
                "temperature requires a climate, sensor, number or input_number entity"
            )

    async def read_state(
        self, hass, service: ServiceRef, entity_ids: tuple[str, ...]
    ) -> dict[str, object]:
        self.validate_service(service)
        self.validate_entities(entity_ids)
        state = hass.states.get(entity_ids[0])
        if state is None or state.state in {"unknown", "unavailable"}:
            return {}
        domain = entity_ids[0].partition(".")[0]
        factor = _factor(service)
        if domain != "climate":
            # A plain sensor/number carries the set-point in its own state.
            raw = _as_number(state.attributes.get("value", state.state))
            if raw is None:
                return {}
            minimum, maximum, step = _limits(service)
            degrees = raw
            if minimum is not None:
                degrees = max(minimum, degrees)
            if maximum is not None:
                degrees = min(maximum, degrees)
            if step:
                degrees = round(degrees / step) * step
            value = _quantize(degrees * factor, None, None, None)
            return {_characteristic(service): value} if value is not None else {}
        minimum, maximum, step = _limits(service)
        result: dict[str, object] = {}
        char = _characteristic(service)
        pairs = (("target", "temperature"), ("current", "current_temperature"))
        for field, attribute in pairs:
            raw = state.attributes.get(attribute)
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                continue
            # min/max/step are Profile ranges in whole degrees: quantize in the
            # degree domain first, then scale onto the wire.
            degrees = raw
            if minimum is not None:
                degrees = max(minimum, degrees)
            if maximum is not None:
                degrees = min(maximum, degrees)
            if step:
                degrees = round(degrees / step) * step
            value = _quantize(degrees * factor, None, None, None)
            if value is not None:
                # A Profile may name the writable characteristic differently
                # (for example the A0VG fridge exposes `refrigerator.target`).
                result[char if field == "target" else field] = value
        return result

    async def apply_command(
        self,
        hass,
        service: ServiceRef,
        entity_ids: tuple[str, ...],
        payload: dict[str, object],
    ) -> None:
        self.validate_service(service)
        self.validate_entities(entity_ids)
        factor = _factor(service)
        minimum, maximum, step = _limits(service)
        char = _characteristic(service)
        target = payload.get(char, payload.get("target"))
        if isinstance(target, bool) or not isinstance(target, (int, float)):
            return
        _field, target_field, scale = _measurement_contract(service)
        if target_field is None:
            return
        target = _command_number(payload.get(target_field))
        if target is None:
            return
        domain = entity_ids[0].partition(".")[0]
        if domain == "climate":
            await hass.services.async_call(
                "climate",
                "set_temperature",
                {"entity_id": entity_ids[0], "temperature": value},
                blocking=True,
            )
            return
        if domain in {"number", "input_number"}:
            await hass.services.async_call(
                domain,
                "set_value",
                {"entity_id": entity_ids[0], "value": value},
                blocking=True,
            )


def _measurement_contract(
    service: ServiceRef,
) -> tuple[str | None, str | None, float]:
    """Map HA Celsius to the Huawei field using ``scale`` in both directions."""


def _characteristic(service: ServiceRef) -> str:
    """Profile characteristic name carrying the set-point (default `target`)."""
    value = service.contract_value("characteristic", "target")
    if isinstance(value, str) and value:
        return value
    return "target"


def _as_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _factor(service: ServiceRef) -> float:
    value = service.contract_value("factor", 10)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value == 0:
        return 10.0
    return float(value)


def _limits(service: ServiceRef) -> tuple[float | None, float | None, float]:
    minimum = _number(service.contract_value("min"))
    maximum = _number(service.contract_value("max"))
    step = _number(service.contract_value("step")) or 1.0
    return minimum, maximum, float(step)


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        try:
            value = float(value)
        except (OverflowError, TypeError, ValueError):
            return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _command_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _wire_number(value: float) -> int | float:
    return int(value) if value.is_integer() else value


ADAPTER = TemperatureServiceAdapter()
