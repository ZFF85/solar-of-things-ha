# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.4.0] - 2026-05-30

### Added
- **HACS-compliant directory structure** — all integration files now live under
  `custom_components/solar_of_things/` as required by HACS. Installing via HACS
  or manual copy now works without any path adjustments.
- **Brand asset** — `brand/icon.png` added so the integration displays an icon
  in the HACS store and HA Integrations page.
- **Sensor translation keys** — all 14 sensors now use `translation_key` +
  `has_entity_name = True`, enabling future multi-language support and aligning
  with HA quality-scale best practices.

### Fixed
- **Missing API methods crash** — `number.py` called `api.set_battery_charge_limit()`,
  `api.set_battery_discharge_limit()`, and `api.set_grid_charge_limit()` which did not
  exist in `api.py`. Interacting with any number slider raised an `AttributeError`.
  All three methods are now implemented.
- **Select entity state mismatch** — `strings.json` defined state keys
  (`self_use`, `time_of_use`, `backup`, `grid_tie`, `off_grid`) that did not match
  the actual API option strings (`Utility First (USO)`, `Solar First (SUB)`, etc.).
  State translations now match the real API values exactly.
- **Device registry duplicates** — sensors used `(DOMAIN, station_id, device_id)`
  as the device identifier while switches, selects, and numbers used the same tuple
  but in a different evaluation path. All device-level entities now use
  `(DOMAIN, device_id)` and station-level entities use `(DOMAIN, station_id)`,
  eliminating duplicate device entries in the device registry.
- **Re-auth crash on HA 2024.x** — `async_step_reauth` declared `entry_data` as
  a required argument; HA 2024+ calls it with no argument. Made the parameter
  optional (`entry_data: dict | None = None`).

### Changed
- `manifest.json`: added `integration_type: hub` (required since HA 2023.6),
  set `homeassistant: "2023.6.0"` minimum version, updated `codeowners`.
- `hacs.json`: updated `homeassistant` minimum to `2023.6.0`, removed legacy
  `zip_release` / `filename` / `domains` fields incompatible with the new layout.
- `strings.json` / `translations/en.json`: corrected select state keys; added
  full sensor translation entries (previously absent).
- `.gitignore`: added `graphify-out/` to exclude local knowledge-graph cache.

---

## [2.3.3] - 2026-03-07

### Fixed
- **404 Not Found on device settings** — replaced incorrect settings endpoints with
  the correct remote-config API endpoints discovered from the live portal JS bundle:
  - **Read**: `POST /apis/remote/device/configs/cache/get?deviceId=<id>`
  - **Write**: `POST /apis/remote/device/config/write?deviceId=<id>`
- `select.py` — Operating Mode and Battery Priority selects now use real API keys
  (`outputSourcePrioritySetting`, `chargerSourcePrioritySetting`) with correct
  integer value mappings (USO/SUB/SBU, CSO/SNU/OSO).
- `switch.py` — all three switches map to correct API setting keys.

---

## [2.3.2] - 2026-03-07

### Fixed
- `fetch_settings` AttributeError — added class-level alias so both `get_device_settings`
  and `fetch_settings` work.
- Five missing control helper methods on `SolarOfThingsAPI` added
  (`set_operating_mode`, `set_battery_priority`, `set_grid_charging`,
  `set_grid_feed_in`, `set_backup_mode`).

---

## [2.3.1] - 2026-03-07

### Fixed
- Correct production AppID `rBrTRfAPXz` targeting `https://solar.siseli.com`.
  Previous release used the test AppID, causing "account error" for all real users.
- Password now MD5-hashed before transmission, matching portal behaviour.

---

## [2.3.0] - 2026-03-07

### Changed
- Authentication now uses **User ID / Account** instead of email address.

### Fixed
- Fully working IOT Open Platform request signing (AES-128-CBC + HMAC-SHA256 + MD5).
- Correct API base URLs and login path.

---

## [2.2.0] - 2026-03-06

### Added
- Email + Password authentication with automatic token refresh.
- HA re-auth flow on token expiry.
- `on_token_refreshed` callback persists tokens to config entry.
- Legacy IOT-token mode preserved.

---

## [2.1.1] - 2026-03-05

### Added
- PR template for HACS default submission.

### Changed
- `hacs.json` and `manifest.json` metadata updates.

---

## [2.1.0] - 2026-02-26

### Added
- Auto-discover all device IDs under a station via `POST /apis/device/list`.
- Optional `device_id` in config flow (blank = auto-discover all devices).

---

## [2.0.0] - 2024-02-10

### Added
- Full system control: number sliders, select dropdowns, switches.
- Settings API integration.

---

## [1.0.0] - 2024-02-10

### Added
- Initial release — monitoring sensors, config flow, multi-station support,
  Energy Dashboard compatibility.
