#!/usr/bin/env python3
"""Standalone Solar of Things / DatouBoss telemetry dumper.

This script intentionally does not import Home Assistant.  It can either read a
captured DatouBoss JSON response from disk or log in to the Siseli cloud API and
print every measured field returned by the device endpoint.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

try:
    from Crypto.Cipher import AES
except ImportError:  # pragma: no cover
    AES = None

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]


API_BASE_URL = "https://solar.siseli.com"
API_AUTH_BASE_URL = "https://solar.siseli.com"
API_LOGIN = "/apis/login/account"
API_REFRESH_TOKEN = "/apis/login/refresh/access/token"
API_DEVICE_LIST = "/apis/device/list"
API_TIME_SERIES = "/apis/deviceState/simple/attribute/keys/history/v1"

IOT_APP_ID = "rBrTRfAPXz"
IOT_APP_SECRET_ENC = "I4D0KRr2339z3pQ/at91V9BpFAOe54DaTafwSm6suIQ="
DEFAULT_TZ = "Asia/Manila"
TOKEN_REFRESH_LEAD_SECONDS = 300


class AuthenticationError(Exception):
    """Raised when login credentials are rejected by the upstream API."""


class TokenExpiredError(Exception):
    """Raised when no available token refresh strategy works."""


@dataclass(frozen=True)
class Measurement:
    key: str
    value: Any
    unit: str = ""
    name: str = ""
    display: str = ""
    source: str = ""


def decrypt_app_secret(app_id: str, encrypted_b64: str) -> str:
    if AES is None:
        raise RuntimeError("Missing dependency: install pycryptodome")

    md5_hex = hashlib.md5(app_id.encode("utf-8")).hexdigest()
    key = md5_hex[:16].encode("ascii")
    iv = md5_hex[16:].encode("ascii")
    ciphertext = base64.b64decode(encrypted_b64)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    plaintext = cipher.decrypt(ciphertext).rstrip(b"\x00")
    return plaintext.decode("utf-8")


def make_signed_headers(body: bytes) -> dict[str, str]:
    secret = decrypt_app_secret(IOT_APP_ID, IOT_APP_SECRET_ENC)
    nonce = os.urandom(16).hex()
    body_hash = hashlib.sha256(body).hexdigest()
    sign_headers = {
        "IOT-Open-AppID": IOT_APP_ID,
        "IOT-Open-Body-Hash": body_hash,
        "IOT-Open-Nonce": nonce,
    }
    qs = "&".join(f"{key}={sign_headers[key]}" for key in sorted(sign_headers))
    b64_qs = base64.b64encode(qs.encode("utf-8")).decode("ascii")
    digest = hmac.new(secret.encode("utf-8"), b64_qs.encode("utf-8"), hashlib.sha256).digest()

    return {
        "Accept": "application/json",
        "Content-Type": "application/json; charset=utf-8",
        "Origin": "https://solar.siseli.com",
        "Referer": "https://solar.siseli.com/",
        "IOT-Open-AppID": IOT_APP_ID,
        "IOT-Open-Nonce": nonce,
        "IOT-Open-Body-Hash": body_hash,
        "IOT-Open-Sign": hashlib.md5(digest).hexdigest(),
    }


def parse_expiry(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class SolarOfThingsClient:
    def __init__(
        self,
        *,
        user_id: str | None = None,
        password: str | None = None,
        iot_token: str | None = None,
        refresh_token: str | None = None,
        access_token_expires: str | None = None,
        refresh_token_expires: str | None = None,
        time_zone: str = DEFAULT_TZ,
    ) -> None:
        self.user_id = user_id
        self.password = password
        self.time_zone = time_zone
        self.access_token = iot_token or ""
        self.refresh_token = refresh_token or ""
        self.access_expires = parse_expiry(access_token_expires)
        self.refresh_expires = parse_expiry(refresh_token_expires)
        self.lock = threading.Lock()

        if user_id and password:
            self.auth_mode = "password"
        elif iot_token and refresh_token:
            self.auth_mode = "token_pair"
        elif iot_token:
            self.auth_mode = "legacy"
        else:
            raise ValueError("Provide user/password or an IOT token.")

        self.session = requests.Session()
        self.apply_headers()

    def apply_headers(self) -> None:
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json; charset=utf-8",
                "IOT-Token": self.access_token,
                "IOT-Time-Zone": self.time_zone,
                "Origin": "https://solar.siseli.com",
                "Referer": "https://solar.siseli.com/",
                "User-Agent": "SolarOfThingsStandalone/0.1",
            }
        )

    def login(self) -> None:
        if self.auth_mode != "password":
            return

        password_md5 = hashlib.md5((self.password or "").encode("utf-8")).hexdigest()
        payload = {"account": self.user_id, "password": password_md5}
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        resp = requests.post(
            f"{API_AUTH_BASE_URL}{API_LOGIN}",
            data=body,
            headers=make_signed_headers(body),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") not in (0, None, "0"):
            raise AuthenticationError(data.get("message") or data.get("msg") or str(data))
        self.store_tokens(data.get("data") or data)

    def store_tokens(self, payload: dict[str, Any]) -> None:
        access = payload.get("accessToken") or payload.get("iotToken") or payload.get("token")
        if not access:
            raise AuthenticationError(f"Response did not contain an access token: {list(payload)}")
        self.access_token = access
        self.refresh_token = payload.get("refreshToken") or self.refresh_token
        self.access_expires = parse_expiry(
            payload.get("accessTokenWillExpiredAt") or payload.get("accessTokenExpiredAt")
        )
        self.refresh_expires = parse_expiry(
            payload.get("refreshTokenWillExpiredAt") or payload.get("refreshTokenExpiredAt")
        )
        self.apply_headers()

    def token_needs_refresh(self) -> bool:
        if not self.access_token:
            return True
        if self.access_expires is None:
            return bool(self.refresh_token)
        return datetime.now(timezone.utc) >= (
            self.access_expires - timedelta(seconds=TOKEN_REFRESH_LEAD_SECONDS)
        )

    def refresh_access_token(self) -> None:
        if not self.refresh_token:
            raise TokenExpiredError("No refresh token available.")

        resp = requests.post(
            f"{API_AUTH_BASE_URL}{API_REFRESH_TOKEN}",
            json={"refreshToken": self.refresh_token},
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json; charset=utf-8",
                "Origin": "https://solar.siseli.com",
                "Referer": "https://solar.siseli.com/",
            },
            timeout=30,
        )
        if resp.status_code in (401, 403):
            raise TokenExpiredError("Refresh token rejected.")
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") not in (0, None, "0"):
            raise TokenExpiredError(data.get("message") or str(data))
        self.store_tokens(data.get("data") or data)

    def ensure_token(self) -> None:
        if not self.token_needs_refresh():
            return
        with self.lock:
            if not self.token_needs_refresh():
                return
            if self.refresh_token:
                try:
                    self.refresh_access_token()
                    return
                except Exception:
                    pass
            if self.auth_mode == "password":
                self.login()
                return
            raise TokenExpiredError("Access token expired and could not be refreshed.")

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.ensure_token()
        resp = self.session.post(f"{API_BASE_URL}{path}", json=payload, timeout=30)
        if resp.status_code == 401:
            self.access_expires = None
            self.ensure_token()
            resp = self.session.post(f"{API_BASE_URL}{path}", json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def list_devices(self, station_id: str) -> list[dict[str, Any]]:
        devices: list[dict[str, Any]] = []
        page = 1
        total: int | None = None
        while True:
            data = self.post(API_DEVICE_LIST, {"page": page, "count": 50, "stationId": station_id})
            if data.get("code") not in (0, None):
                raise RuntimeError(f"Device list failed: {data}")
            payload = data.get("data") or {}
            total = payload.get("total", total)
            batch = payload.get("list") or []
            if not isinstance(batch, list) or not batch:
                break
            devices.extend(batch)
            if total is not None and len(devices) >= int(total):
                break
            page += 1
        return devices

    def fetch_raw_measurements(self, device_id: str, hours: int = 1) -> dict[str, Any]:
        now = current_time(self.time_zone)
        start = now - timedelta(hours=hours)
        return self.post(
            API_TIME_SERIES,
            {
                "deviceId": device_id,
                "count": 2000,
                "page": 1,
                "fromTime": format_time(start, self.time_zone),
                "toTime": format_time(now, self.time_zone),
                "orderByTimeAsc": True,
            },
        )


def current_time(time_zone: str) -> datetime:
    if ZoneInfo:
        try:
            return datetime.now(tz=ZoneInfo(time_zone))
        except Exception:
            pass
    return datetime.now()


def format_time(value: datetime, time_zone: str) -> str:
    if ZoneInfo:
        try:
            value = value.astimezone(ZoneInfo(time_zone))
        except Exception:
            pass
    return value.replace(microsecond=0).isoformat()


def extract_measurements(response: dict[str, Any]) -> list[Measurement]:
    data = response.get("data") or {}
    payload = data.get("payload") or {}
    fields = payload.get("fields") or data.get("fields") or response.get("fields") or {}
    if not isinstance(fields, dict):
        return []

    measurements: list[Measurement] = []
    for key in sorted(fields):
        raw = fields[key]
        if isinstance(raw, dict):
            measurements.append(
                Measurement(
                    key=key,
                    value=raw.get("value"),
                    unit=str(raw.get("unit") or ""),
                    name=str(raw.get("nameDisplay") or ""),
                    display=str(raw.get("valueDisplay") or ""),
                    source="field",
                )
            )
        elif isinstance(raw, list):
            if not raw:
                continue
            measurements.append(Measurement(key=key, value=raw[-1], source="history"))
        else:
            measurements.append(Measurement(key=key, value=raw, source="raw"))
    return measurements


def print_measurements(measurements: list[Measurement], *, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps([m.__dict__ for m in measurements], ensure_ascii=False, indent=2))
        return

    if not measurements:
        print("No measurements found.")
        return

    key_width = max(len(m.key) for m in measurements)
    value_width = max(len(str(m.value)) for m in measurements)
    for item in measurements:
        value = str(item.value).rjust(value_width)
        unit = f" {item.unit}" if item.unit else ""
        name = f"  {item.name}" if item.name else ""
        display = f" ({item.display})" if item.display and item.display != str(item.value) else ""
        print(f"{item.key.ljust(key_width)}  {value}{unit}{display}{name}")


def build_client(args: argparse.Namespace) -> SolarOfThingsClient:
    user = args.user or os.getenv("SOT_USER")
    password = args.password or os.getenv("SOT_PASSWORD")
    token = args.token or os.getenv("SOT_TOKEN")
    refresh = args.refresh_token or os.getenv("SOT_REFRESH_TOKEN")
    access_exp = args.access_token_expires or os.getenv("SOT_ACCESS_TOKEN_EXPIRES")
    refresh_exp = args.refresh_token_expires or os.getenv("SOT_REFRESH_TOKEN_EXPIRES")

    return SolarOfThingsClient(
        user_id=user,
        password=password,
        iot_token=token,
        refresh_token=refresh,
        access_token_expires=access_exp,
        refresh_token_expires=refresh_exp,
        time_zone=args.time_zone,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="List all Solar of Things / DatouBoss measured fields without Home Assistant."
    )
    parser.add_argument("--from-file", type=Path, help="Read a captured JSON response instead of calling the API.")
    parser.add_argument("--station-id", default=os.getenv("SOT_STATION_ID"))
    parser.add_argument("--device-id", default=os.getenv("SOT_DEVICE_ID"))
    parser.add_argument("--user", default=os.getenv("SOT_USER"))
    parser.add_argument("--password", default=os.getenv("SOT_PASSWORD"))
    parser.add_argument("--token", default=os.getenv("SOT_TOKEN"))
    parser.add_argument("--refresh-token", default=os.getenv("SOT_REFRESH_TOKEN"))
    parser.add_argument("--access-token-expires", default=os.getenv("SOT_ACCESS_TOKEN_EXPIRES"))
    parser.add_argument("--refresh-token-expires", default=os.getenv("SOT_REFRESH_TOKEN_EXPIRES"))
    parser.add_argument("--time-zone", default=os.getenv("SOT_TIME_ZONE", DEFAULT_TZ))
    parser.add_argument("--hours", type=int, default=1)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--list-devices", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.from_file:
        response = json.loads(args.from_file.read_text())
        print_measurements(extract_measurements(response), as_json=args.json)
        return 0

    client = build_client(args)
    if client.auth_mode == "password":
        client.login()

    if args.list_devices:
        if not args.station_id:
            raise SystemExit("--station-id or SOT_STATION_ID is required for --list-devices")
        devices = client.list_devices(args.station_id)
        print(json.dumps(devices, ensure_ascii=False, indent=2))
        return 0

    if not args.device_id:
        raise SystemExit("--device-id or SOT_DEVICE_ID is required")

    response = client.fetch_raw_measurements(args.device_id, hours=args.hours)
    print_measurements(extract_measurements(response), as_json=args.json)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as err:
        print(f"error: {err}", file=sys.stderr)
        raise SystemExit(1)
