"""Date/time platform for Solar of Things integration."""
from __future__ import annotations

from datetime import datetime
import logging

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    api = data["api"]
    station_id: str = data["station_id"]
    device_coordinators = data["device_coordinators"]

    entities: list[DateTimeEntity] = []
    for device_id, coordinator in device_coordinators.items():
        settings = (coordinator.data or {}).get("settings") or {}
        if "setSystemTime" not in settings:
            continue
        device_name = (coordinator.device_meta or {}).get("name") or device_id
        entities.append(SolarOfThingsSystemTimeDateTime(api, coordinator, station_id, device_id, device_name))

    async_add_entities(entities)


def _setting_raw_value(coordinator_data: dict | None, key: str):
    settings = ((coordinator_data or {}).get("settings") or {})
    entry = settings.get(key)
    if isinstance(entry, dict):
        return entry.get("value")
    return entry


class SolarOfThingsSystemTimeDateTime(CoordinatorEntity, DateTimeEntity):
    """Set the inverter system time via setSystemTime."""

    _setting_key = "setSystemTime"

    def __init__(self, api, coordinator, station_id: str, device_id: str, device_name: str) -> None:
        super().__init__(coordinator)
        self._api = api
        self._station_id = station_id
        self._device_id = device_id
        self._device_name = device_name
        self._attr_name = f"{device_name} System Time"
        self._attr_unique_id = f"{DOMAIN}_{station_id}_{device_id}_system_time"
        self._attr_icon = "mdi:clock-outline"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": self._device_name,
            "manufacturer": "Siseli",
            "model": (self.coordinator.data.get("device_meta") or {}).get("model") if self.coordinator.data else None,
            "via_device": (DOMAIN, self._station_id),
        }

    @property
    def native_value(self) -> datetime | None:
        raw = _setting_raw_value(self.coordinator.data, self._setting_key)
        if not raw or not isinstance(raw, str):
            return None
        try:
            return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None

    async def async_set_value(self, value: datetime) -> None:
        formatted = value.replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
        await self.hass.async_add_executor_job(
            self._api.set_device_setting, self._device_id, self._setting_key, formatted
        )
        await self.coordinator.async_request_refresh()
