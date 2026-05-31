# Installation Guide

## Requirements

- Home Assistant **2023.6** or newer
- Active account at [solar.siseli.com](https://solar.siseli.com)
- Network access from HA to `https://solar.siseli.com`

---

## Method 1: HACS (Recommended)

1. **Install HACS** if not already installed → [hacs.xyz](https://hacs.xyz)

2. Open **HACS → Integrations** in the HA sidebar.

3. Click **⋮** (top-right) → **Custom repositories**.

4. Add:
   ```
   https://github.com/Conexo-Casa/solar-of-things-ha
   ```
   Category: **Integration** → **Add**.

5. Search **Solar of Things** → **Download**.

6. **Restart Home Assistant.**

7. Go to **Settings → Devices & Services → + Add Integration** → search **Solar of Things**.

---

## Method 2: Manual

1. Download the latest release ZIP from:
   **[github.com/Conexo-Casa/solar-of-things-ha/releases/latest](https://github.com/Conexo-Casa/solar-of-things-ha/releases/latest)**

2. Extract and copy the `solar_of_things` folder to your HA config directory:
   ```
   /config/custom_components/solar_of_things/
   ```

   The final structure must be:
   ```
   /config/custom_components/solar_of_things/
   ├── __init__.py
   ├── api.py
   ├── config_flow.py
   ├── const.py
   ├── manifest.json
   ├── number.py
   ├── select.py
   ├── sensor.py
   ├── strings.json
   ├── switch.py
   └── translations/
       └── en.json
   ```

3. **Restart Home Assistant.**

4. Go to **Settings → Devices & Services → + Add Integration** → search **Solar of Things**.

---

## Verifying Installation

After restarting, go to **Settings → System → Logs**. If you see a line like:

```
Setting up custom_components.solar_of_things
```

with no errors, the component loaded correctly.

---

## Upgrading

### Via HACS
1. HACS → Integrations → find Solar of Things → **Update**.
2. Restart Home Assistant.

### Manual
1. Download the new release ZIP.
2. Replace the contents of `/config/custom_components/solar_of_things/`.
3. Restart Home Assistant.

> **Note:** When upgrading from v2.3.x or earlier, the config entry will be
> automatically migrated. No re-authentication is needed if you already use
> User ID + Password auth.

---

## Uninstalling

1. **Settings → Devices & Services → Solar of Things → Delete**.
2. Remove `/config/custom_components/solar_of_things/` from your HA filesystem.
3. Restart Home Assistant.
