from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import ap01_install_firmware
from ap01_custom_ota import choose_fds_device


class InstallFirmwareTests(unittest.TestCase):
    def make_firmware(self, root: Path) -> Path:
        path = root / "screen-realtime.bin"
        path.write_bytes(b"BFNP" + bytes(60))
        return path

    def test_explicit_fds_identity_does_not_require_device_listing(self) -> None:
        cloud = Mock()
        selected = choose_fds_device(
            cloud,
            did="gateway-did",
            model="lumi.gateway.example",
        )
        self.assertEqual(
            selected,
            {"did": "gateway-did", "model": "lumi.gateway.example"},
        )
        cloud.devices.assert_not_called()

    def test_upload_only_writes_transferable_url(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            firmware = self.make_firmware(root)
            output = root / "ota-url.txt"
            with (
                patch.object(ap01_install_firmware, "MiCloud", return_value=Mock()),
                patch.object(
                    ap01_install_firmware,
                    "upload_to_xiaomi",
                    return_value="https://iot-ota-cdn.io.mi.com/object?signature=test",
                ),
                patch.object(ap01_install_firmware, "deliver") as deliver,
                patch(
                    "sys.argv",
                    [
                        "ap01_install_firmware.py",
                        str(firmware),
                        "--upload-only",
                        "--url-output",
                        str(output),
                    ],
                ),
            ):
                self.assertEqual(ap01_install_firmware.main(), 0)
            self.assertEqual(
                output.read_text(encoding="utf-8").strip(),
                "https://iot-ota-cdn.io.mi.com/object?signature=test",
            )
            deliver.assert_not_called()

    def test_download_only_can_reuse_signed_url(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            firmware = self.make_firmware(root)
            cloud = Mock()
            url = "https://iot-ota-cdn.io.mi.com/object?signature=test"
            with (
                patch.object(ap01_install_firmware, "MiCloud", return_value=cloud),
                patch.object(ap01_install_firmware, "probe_ota_url") as probe,
                patch.object(ap01_install_firmware, "upload_to_xiaomi") as upload,
                patch.object(ap01_install_firmware, "deliver") as deliver,
                patch(
                    "sys.argv",
                    [
                        "ap01_install_firmware.py",
                        str(firmware),
                        "--download-only",
                        "--ota-url",
                        url,
                    ],
                ),
            ):
                self.assertEqual(ap01_install_firmware.main(), 0)
            probe.assert_called_once_with(url)
            upload.assert_not_called()
            deliver.assert_called_once_with(
                cloud,
                firmware,
                url,
                360,
                download_only=True,
            )

    def test_download_only_can_read_signed_url_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            firmware = self.make_firmware(root)
            url = "https://iot-ota-cdn.io.mi.com/object?signature=test"
            url_file = root / "ota-url.txt"
            url_file.write_text(url + "\n", encoding="utf-8")
            cloud = Mock()
            with (
                patch.object(ap01_install_firmware, "MiCloud", return_value=cloud),
                patch.object(ap01_install_firmware, "probe_ota_url") as probe,
                patch.object(ap01_install_firmware, "upload_to_xiaomi") as upload,
                patch.object(ap01_install_firmware, "deliver") as deliver,
                patch(
                    "sys.argv",
                    [
                        "ap01_install_firmware.py",
                        str(firmware),
                        "--download-only",
                        "--ota-url-file",
                        str(url_file),
                    ],
                ),
            ):
                self.assertEqual(ap01_install_firmware.main(), 0)
            probe.assert_called_once_with(url)
            upload.assert_not_called()
            deliver.assert_called_once_with(
                cloud,
                firmware,
                url,
                360,
                download_only=True,
            )


if __name__ == "__main__":
    unittest.main()
