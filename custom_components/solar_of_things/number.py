"""Number platform for Solar of Things integration."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfElectricCurrent
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
    """Set up number entities (controls) for each device."""

    data = hass.data[DOMAIN][entry.entry_id]
    api = data["api"]
    station_id: str = data["station_id"]
    device_coordinators = data["device_coordinators"]

    entities: list[NumberEntity] = []

    for device_id, coordinator in device_coordinators.items():
        device_name = (coordinator.device_meta or {}).get("name") or device_id
        settings = (coordinator.data or {}).get("settings") or {}
        candidates: list[type[_BaseNumber]] = [
            SolarOfThingsBatteryChargeLimitNumber,
            SolarOfThingsBatteryDischargeLimitNumber,
            SolarOfThingsGridChargeLimitNumber,
        ]
        for entity_cls in candidates:
            if entity_cls.setting_key_available(settings):
                entities.append(entity_cls(api, coordinator, station_id, device_id, device_name))
            else:
                _LOGGER.debug(
                    "Skipping %s for %s; none of the writable setting keys exist: %s",
                    entity_cls.__name__, device_id, entity_cls._setting_candidates,
                )

    async_add_entities(entities)


class _BaseNumber(CoordinatorEntity, NumberEntity):
    _setting_candidates: tuple[str, ...] = ()

    def __init__(self, api, coordinator, station_id: str, device_id: str, device_name: str) -> None:
        super().__init__(coordinator)
        self._api = api
        self._station_id = station_id
        self._device_id = device_id
        self._device_name = device_name

    @classmethod
    def setting_key_available(cls, settings: dict) -> bool:
        return any(key in settings for key in cls._setting_candidates)

    @property
    def _setting_key(self) -> str | None:
        settings = ((self.coordinator.data or {}).get("settings") or {})
        return next((key for key in self._setting_candidates if key in settings), None)

    def _native_setting_value(self):
        key = self._setting_key
        if not key:
            return None
        setting = ((self.coordinator.data or {}).get("settings") or {}).get(key)
        if isinstance(setting, dict):
            return setting.get("value")
        return setting

    @property
    def available(self) -> bool:
        return super().available and self._setting_key is not None

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": self._device_name,
            "manufacturer": "Siseli",
            "model": (self.coordinator.data.get("device_meta") or {}).get("model") if self.coordinator.data else None,
            "via_device": (DOMAIN, self._station_id),
        }


class SolarOfThingsBatteryChargeLimitNumber(_BaseNumber):
    _setting_candidates = (
        "maximumChargingCurrentSetting",
    )

    def __init__(self, api, coordinator, station_id: str, device_id: str, device_name: str) -> None:
        super().__init__(api, coordinator, station_id, device_id, device_name)
        self._attr_name = f"{device_name} Maximum Charging Current"
        self._attr_unique_id = f"{DOMAIN}_{station_id}_{device_id}_battery_charge_limit"
        self._attr_native_min_value = 0
        self._attr_native_max_value = 200
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        self._attr_mode = NumberMode.SLIDER
        self._attr_icon = "mdi:battery-arrow-up"

    @property
    def native_value(self):
        return self._native_setting_value()

    async def async_set_native_value(self, value: float) -> None:
        key = self._setting_key
        if not key:
            return
        await self.hass.async_add_executor_job(self._api.set_device_setting, self._device_id, key, int(value))
        await self.coordinator.async_request_refresh()


class SolarOfThingsBatteryDischargeLimitNumber(_BaseNumber):
    _setting_candidates = (
        "bmsReturnsToMainsModeSOCSetting",
        "returnToMainsModeSOCSetting",
        "lowPowerSOCSetting",
    )

    def __init__(self, api, coordinator, station_id: str, device_id: str, device_name: str) -> None:
        super().__init__(api, coordinator, station_id, device_id, device_name)
        self._attr_name = f"{device_name} Battery Discharge Limit"
        self._attr_unique_id = f"{DOMAIN}_{station_id}_{device_id}_battery_discharge_limit"
        self._attr_native_min_value = 0
        self._attr_native_max_value = 100
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_mode = NumberMode.SLIDER
        self._attr_icon = "mdi:battery-arrow-down"

    @property
    def native_value(self):
        return self._native_setting_value()

    async def async_set_native_value(self, value: float) -> None:
        key = self._setting_key
        if not key:
            return
        await self.hass.async_add_executor_job(self._api.set_device_setting, self._device_id, key, int(value))
        await self.coordinator.async_request_refresh()


class SolarOfThingsGridChargeLimitNumber(_BaseNumber):
    _setting_candidates = (
        "gridChargeLimit",
        "gridChargeLimitSetting",
        "maxUtilityChargeCurrent",
        "maxUtilityChargeCurrentSetting",
    )

    def __init__(self, api, coordinator, station_id: str, device_id: str, device_name: str) -> None:
        super().__init__(api, coordinator, station_id, device_id, device_name)
        self._attr_name = f"{device_name} Grid Charge Limit"
        self._attr_unique_id = f"{DOMAIN}_{station_id}_{device_id}_grid_charge_limit"
        self._attr_native_min_value = 0
        self._attr_native_max_value = 5000
        self._attr_native_step = 100
        self._attr_native_unit_of_measurement = "W"
        self._attr_mode = NumberMode.SLIDER
        self._attr_device_class = NumberDeviceClass.POWER
        self._attr_icon = "mdi:transmission-tower-import"

    @property
    def native_value(self):
        return self._native_setting_value()

    async def async_set_native_value(self, value: float) -> None:
        key = self._setting_key
        if not key:
            return
        await self.hass.async_add_executor_job(self._api.set_device_setting, self._device_id, key, int(value))
        await self.coordinator.async_request_refresh()
