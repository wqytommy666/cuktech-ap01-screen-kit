#!/usr/bin/env python3
"""Minimal Xiaomi cloud client for researching the CUKTECH AP01 display.

Credentials are refreshed from the local Mi Home app's preferences at runtime.
They are never written into this repository or printed by this program.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import plistlib
import random
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


MODEL = "njcuk.enstor.ap01"
DEFAULT_PREFS = Path.home() / (
    "Library/Group Containers/group.com.xiaomi.mihome/Library/Preferences/"
    "group.com.xiaomi.mihome.plist"
)


class MiCloud:
    def __init__(self, prefs: Path = DEFAULT_PREFS) -> None:
        with prefs.open("rb") as stream:
            account = plistlib.load(stream)["GroupShareAccountInfo"]
        self.user_id = str(account["userId"])
        self.pass_token = account["passToken"]
        self.device_id = "B4C9D5BF5C4B6925"
        self.ssecurity = ""
        self.service_token = ""
        self._refresh_session()

    def _refresh_session(self) -> None:
        session = requests.Session()
        session.headers["User-Agent"] = "APP/com.xiaomi.mihome APPV/9.1.200"
        session.cookies.update(
            {
                "userId": self.user_id,
                "passToken": self.pass_token,
                "deviceId": self.device_id,
            }
        )
        response = session.get(
            "https://account.xiaomi.com/pass/serviceLogin",
            params={"sid": "xiaomiio", "_json": "true"},
            timeout=20,
        )
        response.raise_for_status()
        auth = json.loads(response.text.replace("&&&START&&&", ""))
        if auth.get("code") != 0 or not auth.get("location"):
            raise RuntimeError(f"Xiaomi account refresh failed: code={auth.get('code')}")
        self.ssecurity = auth["ssecurity"]
        response = session.get(auth["location"], timeout=20)
        response.raise_for_status()
        self.service_token = (
            response.cookies.get("serviceToken")
            or session.cookies.get("serviceToken")
            or ""
        )
        if not self.service_token:
            raise RuntimeError("Xiaomi account refresh returned no service token")

    @staticmethod
    def _nonce() -> str:
        first = (random.getrandbits(64) - 2**63).to_bytes(8, "big", signed=True)
        minute = int(time.time() / 60)
        second = minute.to_bytes((minute.bit_length() + 7) // 8, "big")
        return base64.b64encode(first + second).decode()

    def _signed_nonce(self, nonce: str) -> str:
        raw = base64.b64decode(self.ssecurity) + base64.b64decode(nonce)
        return base64.b64encode(hashlib.sha256(raw).digest()).decode()

    @staticmethod
    def _rc4(key: str, payload: str, *, decrypt: bool = False) -> str:
        secret = base64.b64decode(key)
        state = list(range(256))
        j = 0
        for i in range(256):
            j = (j + state[i] + secret[i % len(secret)]) & 0xFF
            state[i], state[j] = state[j], state[i]

        i = j = 0

        def next_byte() -> int:
            nonlocal i, j
            i = (i + 1) & 0xFF
            j = (j + state[i]) & 0xFF
            state[i], state[j] = state[j], state[i]
            return state[(state[i] + state[j]) & 0xFF]

        # Xiaomi's RC4 transport drops the first 1024 keystream bytes.
        for _ in range(1024):
            next_byte()
        source = base64.b64decode(payload) if decrypt else payload.encode()
        result = bytes(value ^ next_byte() for value in source)
        if decrypt:
            return result.decode()
        return base64.b64encode(result).decode()

    @staticmethod
    def _signature(method: str, url: str, params: dict[str, str], key: str) -> str:
        path = urlparse(url).path
        if path.startswith("/app/"):
            path = path[4:]
        parts = [method.upper(), path]
        parts.extend(f"{name}={value}" for name, value in params.items())
        parts.append(key)
        digest = hashlib.sha1("&".join(parts).encode()).digest()
        return base64.b64encode(digest).decode()

    def request(self, path: str, data: Any) -> dict[str, Any]:
        url = "https://api.io.mi.com/app/" + path.lstrip("/")
        nonce = self._nonce()
        signed_nonce = self._signed_nonce(nonce)
        params = {
            "data": json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        }
        params["rc4_hash__"] = self._signature("POST", url, params, signed_nonce)
        encrypted = {
            name: self._rc4(signed_nonce, value) for name, value in params.items()
        }
        encrypted.update(
            {
                "signature": self._signature("POST", url, encrypted, signed_nonce),
                "ssecurity": self.ssecurity,
                "_nonce": nonce,
            }
        )
        headers = {
            "User-Agent": (
                "Android-7.1.1-1.0.0-ONEPLUS A3010-136-ABCDEF1234567 "
                "APP/xiaomi.smarthome APPV/62830"
            ),
            "Accept-Encoding": "identity",
            "MIOT-ENCRYPT-ALGORITHM": "ENCRYPT-RC4",
        }
        cookies = {
            "userId": self.user_id,
            "yetAnotherServiceToken": self.service_token,
            "serviceToken": self.service_token,
            "locale": "zh_CN",
            "timezone": "GMT+08:00",
            "channel": "MI_APP_STORE",
        }
        response = requests.post(
            url, data=encrypted, headers=headers, cookies=cookies, timeout=30
        )
        response.raise_for_status()
        decoded = self._rc4(signed_nonce, response.text, decrypt=True)
        return json.loads(decoded)

    def devices(self) -> list[dict[str, Any]]:
        result = self.request(
            "home/device_list",
            {
                "getVirtualModel": True,
                "getHuamiDevices": 1,
                "get_split_device": False,
                "support_smart_home": True,
            },
        )
        return result.get("result", {}).get("list", [])

    def ap01(self) -> dict[str, Any]:
        for device in self.devices():
            if device.get("model") == MODEL:
                return device
        raise RuntimeError(f"{MODEL} was not found in this Xiaomi account")

    def properties(self, did: str) -> list[dict[str, Any]]:
        queries = [
            {"did": did, "siid": 1, "piid": piid} for piid in range(1, 6)
        ]
        queries += [
            {"did": did, "siid": 3, "piid": piid} for piid in range(1, 9)
        ]
        response = self.request("miotspec/prop/get", {"params": queries})
        return response.get("result", [])

    def rpc(self, did: str, method: str, params: Any = None) -> dict[str, Any]:
        """Send a MiIO RPC through Xiaomi Cloud instead of the local LAN."""
        payload = {
            "id": random.randint(1_000_000, 9_999_999),
            "method": method,
            "params": [] if params is None else params,
        }
        return self.request(f"home/rpc/{did}", payload)

    def plugin_info(self) -> dict[str, Any]:
        plugins = [{"model": MODEL}]
        payload = {
            "latest_req": {
                "api_version": 10058,
                "app_platform": "Android",
                "region": "CN",
                "plugins": plugins,
                "package_type": "",
            },
            "backup_req": {
                "plugins": plugins,
                "api_level": 111,
                "app_platform": "Android",
            },
        }
        return self.request("v2/plugin/fetch_plugin", payload)

    def firmware_info(self) -> dict[str, Any]:
        response = self.request("home/latest_version", {"model": MODEL})
        result = response.get("result") or {}
        if not result.get("url") or not result.get("md5"):
            raise RuntimeError("Xiaomi OTA service returned no firmware artifact")
        return result

    def download_firmware(self, output_dir: Path) -> Path:
        info = self.firmware_info()
        version = str(info["version"])
        target = output_dir / f"ap01-{version}.bin"
        output_dir.mkdir(parents=True, exist_ok=True)
        response = requests.get(info["url"], timeout=120)
        response.raise_for_status()
        digest = hashlib.md5(response.content).hexdigest()
        if digest.lower() != str(info["md5"]).lower():
            raise RuntimeError(f"OTA MD5 mismatch: expected {info['md5']}, got {digest}")
        target.write_bytes(response.content)
        return target


def safe_device(device: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "did",
        "name",
        "model",
        "localip",
        "mac",
        "ssid",
        "isOnline",
        "pid",
        "desc",
        "fw_version",
    ]
    return {key: device.get(key) for key in keys}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command", choices=["device", "props", "plugin", "firmware", "download"]
    )
    args = parser.parse_args()
    cloud = MiCloud()
    device = cloud.ap01()
    if args.command == "device":
        result: Any = safe_device(device)
    elif args.command == "props":
        result = cloud.properties(str(device["did"]))
    elif args.command == "plugin":
        result = cloud.plugin_info()
    elif args.command == "firmware":
        info = cloud.firmware_info()
        result = {
            key: info.get(key)
            for key in ["version", "md5", "changeLog", "upload_time", "time_out"]
        }
    else:
        target = cloud.download_firmware(Path(__file__).parent / "artifacts")
        result = {"downloaded": str(target), "bytes": target.stat().st_size}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
