"""PySide6 interface matching the native macOS CUKTECH controller."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from PySide6.QtCore import QObject, QRunnable, QSettings, QSize, Qt, QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QIcon, QMovie, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSystemTrayIcon,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from windows.runtime import (
    APP_NAME,
    AppPaths,
    autostart_enabled,
    convert_custom_image,
    current_mode,
    disable_autostart,
    enable_autostart,
    health,
    local_screen_url,
    preview_path,
    readiness,
    resource_root,
    self_command,
    start_bridge,
    tail_log,
    use_quota_mode,
)


VERSION = "0.4.1"
WINDOWS_GUIDE = "https://github.com/wqytommy666/cuktech-screen-controller/blob/main/docs/WINDOWS_GUIDE.zh-CN.md"
OTA_GUIDE = "https://github.com/wqytommy666/cuktech-screen-controller/blob/main/docs/AP01_FDS_NO_GATEWAY_SOLUTION.zh-CN.md"
AGENT_PROMPT = """请使用这个公开仓库帮我配置酷态科 AP01 万向屏：
https://github.com/wqytommy666/cuktech-screen-controller

开始前先阅读 AGENTS.md、README.zh-CN.md、docs/WINDOWS_GUIDE.zh-CN.md 和
skills/cuktech-ap01-screen-kit/SKILL.md。我使用 Windows，请先运行
scripts/diagnose-windows.ps1，只做只读检查，不要直接刷固件。

请确认 AP01 稳定供电、已在米家配网并在线，电脑与 AP01 位于同一非访客、
非隔离局域网，Windows Defender/VPN 允许 TCP 8765。本项目不用 USB 传图。
请验证 /health、320×240 GIF89a 和 AP01 GET /screen.gif 200，并设置登录自动启动。
如果实时 Loader 已存在，不要 OTA；如果不存在，先确认型号 njcuk.enstor.ap01、
固件 1.0.2_0031，真正安装前再次向我确认。日常更新只使用 /tmp RAM。
"""


APP_STYLE = r"""
QWidget {
    color: #F8FAFC;
    font-family: "Segoe UI Variable", "Microsoft YaHei UI", "Segoe UI";
    font-size: 14px;
}
QWidget#appRoot {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #020712,stop:0.55 #061324,stop:1 #082438);
}
QDialog {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #020712,stop:0.55 #061324,stop:1 #082438);
}
QFrame#card, QFrame#guideCard {
    background-color: rgba(8, 20, 36, 225);
    border: 1px solid #20334B;
    border-radius: 18px;
}
QFrame#logCard {
    background-color: rgba(1, 5, 12, 215);
    border: 1px solid #17283D;
    border-radius: 15px;
}
QFrame#warningCard {
    background-color: #26180D;
    border: 1px solid #71421F;
    border-radius: 12px;
}
QFrame#checkItem {
    background-color: #050C16;
    border: 1px solid #182A40;
    border-radius: 10px;
}
QFrame#statusPill {
    background-color: rgba(255, 255, 255, 15);
    border: 1px solid rgba(255, 255, 255, 22);
    border-radius: 17px;
}
QLabel#title { font-size: 27px; font-weight: 700; }
QLabel#subtitle, QLabel#muted { color: #93A4B8; }
QLabel#section { font-size: 16px; font-weight: 650; }
QLabel#tag { color: #32C5F4; font-size: 12px; font-weight: 700; }
QLabel#toast { color: #B9C7D8; font-size: 12px; }
QLabel#successText { color: #4ADE80; }
QLabel#warningText { color: #FDBA74; }
QLabel#dangerText { color: #FB7185; }
QPushButton, QToolButton {
    min-height: 36px;
    padding: 0 14px;
    background-color: #101F33;
    border: 1px solid #2A405A;
    border-radius: 10px;
    font-weight: 600;
}
QPushButton:hover, QToolButton:hover { background-color: #162B44; border-color: #3F5C7B; }
QPushButton:pressed, QToolButton:pressed { background-color: #0D1929; }
QPushButton:focus, QToolButton:focus, QLineEdit:focus { border: 2px solid #38BDF8; }
QPushButton:disabled, QToolButton:disabled { color: #64748B; background-color: #0A1422; border-color: #1A2A3E; }
QPushButton#primary { background-color: #078AB7; border-color: #25C8FA; color: white; }
QPushButton#primary:hover { background-color: #079CCF; }
QPushButton#orange { background-color: #C65B1D; border-color: #F58B43; color: white; }
QPushButton#orange:hover { background-color: #DC6B27; }
QToolButton#segment { min-height: 34px; padding: 0 10px; border-radius: 8px; }
QToolButton#segment:checked { background-color: #123D55; border-color: #20B8E8; color: #75DCFA; }
QLineEdit, QTextEdit {
    background-color: #050C16;
    border: 1px solid #253950;
    border-radius: 9px;
    padding: 8px;
    selection-background-color: #087FA8;
}
QTextEdit { font-family: "Cascadia Mono", "Consolas"; font-size: 12px; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QProgressBar { min-height: 4px; max-height: 4px; border: none; background: #102035; border-radius: 2px; }
QProgressBar::chunk { background: #22BEEA; border-radius: 2px; }
QCheckBox { spacing: 9px; }
QCheckBox::indicator { width: 18px; height: 18px; }
QMenu { background: #091525; border: 1px solid #2A405A; padding: 6px; }
QMenu::item { padding: 8px 24px; border-radius: 6px; }
QMenu::item:selected { background: #123D55; }
"""


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


class Worker(QRunnable):
    def __init__(self, callback: Callable[[], Any]) -> None:
        super().__init__()
        self.callback = callback
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            self.signals.result.emit(self.callback())
        except Exception as exc:
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()


def _card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(12)
    return frame, layout


def _section(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("section")
    return label


def _muted(text: str, *, wrap: bool = True) -> QLabel:
    label = QLabel(text)
    label.setObjectName("muted")
    label.setWordWrap(wrap)
    return label


def _resource(relative: str) -> Path:
    return resource_root() / relative


def _app_icon() -> QIcon:
    return QIcon(str(_resource("macos/AP01Logo.png")))


def _redact_urls(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        raw = match.group(0)
        parts = urlsplit(raw)
        return f"{parts.scheme}://{parts.netloc}{parts.path}?••••" if parts.query else raw

    return re.sub(r"https?://[^\s]+", replace, text)


class StatusPill(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("statusPill")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 7, 12, 7)
        layout.setSpacing(8)
        self.dot = QLabel()
        self.dot.setFixedSize(9, 9)
        self.text = QLabel("正在检查")
        self.text.setStyleSheet("font-weight: 600;")
        layout.addWidget(self.dot)
        layout.addWidget(self.text)
        self.set_online(False, "正在检查")

    def set_online(self, online: bool, text: str | None = None) -> None:
        self.dot.setStyleSheet(
            f"background: {'#4ADE80' if online else '#FB7185'}; border-radius: 4px;"
        )
        self.text.setText(text or ("服务运行中" if online else "服务未运行"))


class BeginnerGuideDialog(QDialog):
    def __init__(self, paths: AppPaths, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.paths = paths
        self.pool = QThreadPool.globalInstance()
        self.setWindowTitle("新手引导")
        self.setWindowIcon(_app_icon())
        self.resize(960, 760)
        self.setStyleSheet(APP_STYLE)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(16)

        header = QHBoxLayout()
        title = QVBoxLayout()
        heading = QLabel("新手引导")
        heading.setObjectName("title")
        title.addWidget(heading)
        title.addWidget(_muted("不用写代码，先确认 Windows、Bridge 和万向屏是否准备好"))
        header.addLayout(title)
        header.addStretch()
        guide = QPushButton("完整 Windows 教程")
        guide.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(WINDOWS_GUIDE)))
        done = QPushButton("完成")
        done.setObjectName("primary")
        done.clicked.connect(self.accept)
        header.addWidget(guide)
        header.addWidget(done)
        root.addLayout(header)

        columns = QHBoxLayout()
        columns.setSpacing(15)
        left, left_layout = _card()
        left.setObjectName("guideCard")
        left_layout.addWidget(_section("按顺序操作"))
        steps = [
            ("1", "设备通电并联网", "AP01 在米家在线并稳定供电；电脑与 AP01 位于同一非隔离局域网。"),
            ("2", "登录账户", "额度模式需先登录 Claude Desktop 与 Codex；只显示图片可以跳过。"),
            ("3", "选择内容", "返回主界面选择额度模式，或推送 PNG/JPG/WebP/动态 GIF。"),
            ("4", "等待屏幕轮询", "日志出现 GET /screen.gif 200 表示链路已经打通。"),
        ]
        for number, title_text, detail in steps:
            row = QHBoxLayout()
            badge = QLabel(number)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setFixedSize(26, 26)
            badge.setStyleSheet("background:#22BEEA;color:#021018;border-radius:13px;font-weight:800;")
            text = QVBoxLayout()
            label = QLabel(title_text)
            label.setStyleSheet("font-weight:650;")
            text.addWidget(label)
            text.addWidget(_muted(detail))
            row.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
            row.addLayout(text, 1)
            left_layout.addLayout(row)
        note = QFrame()
        note.setObjectName("warningCard")
        note.setMinimumHeight(128)
        note_layout = QVBoxLayout(note)
        note_title = QLabel("原厂屏幕需要一次性配置")
        note_title.setStyleSheet("color:#FDBA74;font-weight:700;")
        note_layout.addWidget(note_title)
        note_layout.addWidget(_muted("如果屏幕从未显示电脑画面，请先核对 AP01 1.0.2_0031，再交给 Coding Agent；日常使用不要重复 OTA。"))
        copy = QPushButton("复制给 Agent 的 Windows 配置指令")
        copy.setObjectName("orange")
        copy.clicked.connect(lambda: (QApplication.clipboard().setText(AGENT_PROMPT), copy.setText("配置指令已复制")))
        note_layout.addWidget(copy)
        left_layout.addWidget(note)
        left_layout.addStretch()
        ram = QLabel("画面通过 Wi-Fi/LAN 传输；日常刷新写入 /tmp RAM，不会反复刷 Flash。")
        ram.setObjectName("successText")
        ram.setWordWrap(True)
        left_layout.addWidget(ram)

        right, right_layout = _card()
        right.setObjectName("guideCard")
        check_header = QHBoxLayout()
        check_header.addWidget(_section("准备情况"))
        check_header.addStretch()
        self.recheck = QPushButton("重新检测")
        self.recheck.clicked.connect(self.run_checks)
        check_header.addWidget(self.recheck)
        right_layout.addLayout(check_header)
        right_layout.addWidget(_muted("检测只读取本机状态，不会操作固件"))
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.check_container = QWidget()
        self.check_layout = QVBoxLayout(self.check_container)
        self.check_layout.setContentsMargins(0, 0, 0, 0)
        self.check_layout.setSpacing(8)
        self.scroll.setWidget(self.check_container)
        right_layout.addWidget(self.scroll, 1)
        columns.addWidget(left, 10)
        columns.addWidget(right, 12)
        root.addLayout(columns, 1)
        QTimer.singleShot(0, self.run_checks)

    def run_checks(self) -> None:
        self.recheck.setEnabled(False)
        self.recheck.setText("检测中…")
        worker = Worker(lambda: readiness(self.paths))
        worker.signals.result.connect(self.show_checks)
        worker.signals.error.connect(lambda error: self.show_checks([{"title": "检测失败", "detail": error, "level": "missing"}]))
        worker.signals.finished.connect(lambda: (self.recheck.setEnabled(True), self.recheck.setText("重新检测")))
        self.pool.start(worker)

    def show_checks(self, checks: list[dict[str, str]]) -> None:
        while self.check_layout.count():
            item = self.check_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        colors = {"ready": ("#4ADE80", "通过"), "attention": ("#FDBA74", "注意"), "missing": ("#FB7185", "缺失")}
        for item in checks:
            color, status = colors.get(item["level"], colors["attention"])
            frame = QFrame()
            frame.setObjectName("checkItem")
            row = QHBoxLayout(frame)
            row.setContentsMargins(10, 9, 10, 9)
            marker = QLabel(status)
            marker.setFixedWidth(38)
            marker.setStyleSheet(f"color:{color};font-size:11px;font-weight:700;")
            text = QVBoxLayout()
            title = QLabel(item["title"])
            title.setStyleSheet("font-weight:650;")
            text.addWidget(title)
            text.addWidget(_muted(item["detail"]))
            row.addWidget(marker, 0, Qt.AlignmentFlag.AlignTop)
            row.addLayout(text, 1)
            self.check_layout.addWidget(frame)
        self.check_layout.addStretch()


class OTADeploymentDialog(QDialog):
    def __init__(self, paths: AppPaths, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.paths = paths
        self.pool = QThreadPool.globalInstance()
        self.firmware: Path | None = None
        self.ticket: Path | None = paths.ota_url_file if paths.ota_url_file.exists() else None
        self.download_verified_ok = False
        configured_credentials = os.environ.get("CUKTECH_MI_CREDENTIALS", "").strip()
        self.credentials: Path | None = Path(configured_credentials) if configured_credentials else None
        self.setWindowTitle("首次部署 / OTA 交接")
        self.setWindowIcon(_app_icon())
        self.resize(900, 760)
        self.setStyleSheet(APP_STYLE)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(14)

        header = QHBoxLayout()
        title = QVBoxLayout()
        heading = QLabel("首次部署 / OTA 交接")
        heading.setObjectName("title")
        title.addWidget(heading)
        title.addWidget(_muted("AP01 1.0.2_0031 · 无网关自动准备 · 安装前再次确认"))
        header.addLayout(title)
        header.addStretch()
        guide = QPushButton("查看完整说明")
        guide.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(OTA_GUIDE)))
        done = QPushButton("完成")
        done.setObjectName("primary")
        done.clicked.connect(self.accept)
        header.addWidget(guide)
        header.addWidget(done)
        root.addLayout(header)

        warning = QLabel("只有点击确认安装后才会写入一次 Flash；已经能显示自定义内容的 AP01 无需再次 OTA。")
        warning.setWordWrap(True)
        warning.setObjectName("warningText")
        warning.setStyleSheet("background:#26180D;border:1px solid #71421F;border-radius:10px;padding:10px;color:#FDBA74;")
        root.addWidget(warning)

        grid = QGridLayout()
        grid.setSpacing(14)
        firmware_card, firmware_layout = _card()
        firmware_layout.addWidget(_section("1  选择 BFNP 固件"))
        self.firmware_label = _muted("尚未选择 screen-realtime.bin")
        firmware_layout.addWidget(self.firmware_label)
        choose_firmware = QPushButton("选择并校验固件")
        choose_firmware.clicked.connect(self.choose_firmware)
        firmware_layout.addWidget(choose_firmware)
        self.hash_label = _muted("SHA-256 将显示在这里")
        self.hash_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        firmware_layout.addWidget(self.hash_label)

        ticket_card, ticket_layout = _card()
        ticket_layout.addWidget(_section("2  临时 OTA 票据"))
        self.ticket_label = _muted(str(self.ticket) if self.ticket else "尚未生成或导入票据")
        ticket_layout.addWidget(self.ticket_label)
        ticket_actions = QHBoxLayout()
        import_ticket = QPushButton("导入票据")
        import_ticket.clicked.connect(self.choose_ticket)
        self.generate_button = QPushButton("通过 FDS 生成")
        self.generate_button.clicked.connect(self.generate_ticket)
        ticket_actions.addWidget(import_ticket)
        ticket_actions.addWidget(self.generate_button)
        ticket_layout.addLayout(ticket_actions)
        self.shared_button = QPushButton("无网关：一键获取部署包")
        self.shared_button.setObjectName("orange")
        self.shared_button.clicked.connect(self.prepare_gateway_free)
        ticket_layout.addWidget(self.shared_button)
        credential_row = QHBoxLayout()
        choose_credentials = QPushButton("选择米家登录 JSON")
        choose_credentials.clicked.connect(self.choose_credentials)
        self.credentials_label = _muted(
            self.credentials.name if self.credentials else "Windows OTA 需要；只在本次运行中使用",
            wrap=False,
        )
        credential_row.addWidget(choose_credentials)
        credential_row.addWidget(self.credentials_label, 1)
        ticket_layout.addLayout(credential_row)
        self.advanced = QCheckBox("指定 FDS 网关 DID / Model")
        self.advanced.toggled.connect(lambda checked: self.advanced_fields.setVisible(checked))
        ticket_layout.addWidget(self.advanced)
        self.advanced_fields = QWidget()
        advanced_layout = QVBoxLayout(self.advanced_fields)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        self.did = QLineEdit()
        self.did.setPlaceholderText("真实网关 DID")
        self.model = QLineEdit()
        self.model.setPlaceholderText("lumi.gateway.* 或 xiaomi.gateway.*")
        advanced_layout.addWidget(self.did)
        advanced_layout.addWidget(self.model)
        self.advanced_fields.setVisible(False)
        ticket_layout.addWidget(self.advanced_fields)
        grid.addWidget(firmware_card, 0, 0)
        grid.addWidget(ticket_card, 0, 1)
        root.addLayout(grid)

        verify_card, verify_layout = _card()
        verify_row = QHBoxLayout()
        verify_text = QVBoxLayout()
        verify_text.addWidget(_section("3  仅下载验证"))
        verify_text.addWidget(_muted("让 AP01 下载并校验 MD5；不会安装，也不会写入启动分区。"))
        verify_row.addLayout(verify_text, 1)
        self.copy_button = QPushButton("复制完整链接")
        self.copy_button.clicked.connect(self.copy_ticket)
        self.verify_button = QPushButton("开始下载验证")
        self.verify_button.setObjectName("primary")
        self.verify_button.clicked.connect(self.verify_download)
        self.install_button = QPushButton("验证后确认安装")
        self.install_button.clicked.connect(self.install_firmware)
        self.install_button.setEnabled(False)
        verify_row.addWidget(self.copy_button)
        verify_row.addWidget(self.verify_button)
        verify_row.addWidget(self.install_button)
        verify_layout.addLayout(verify_row)
        root.addWidget(verify_card)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        root.addWidget(self.progress)
        self.status = _muted("等待选择固件")
        root.addWidget(self.status)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("部署日志会显示在这里；签名 URL 自动脱敏。")
        root.addWidget(self.log, 1)

    def choose_firmware(self) -> None:
        value, _ = QFileDialog.getOpenFileName(self, "选择 AP01 screen-realtime.bin", "", "BFNP firmware (*.bin);;All files (*)")
        if not value:
            return
        path = Path(value)
        try:
            if path.read_bytes()[:4] != b"BFNP":
                raise ValueError("文件头不是 BFNP")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.firmware = path
            self.firmware_label.setText(f"{path.name} · {path.stat().st_size / 1024 / 1024:.2f} MB")
            self.hash_label.setText(f"SHA-256  {digest}")
            self.status.setText("固件预检通过")
            self.append_log(f"固件预检通过\nSHA-256  {digest}\n")
        except Exception as exc:
            self.firmware = None
            self.status.setText(f"固件预检失败：{exc}")

    def choose_ticket(self) -> None:
        value, _ = QFileDialog.getOpenFileName(self, "导入临时 OTA 链接", "", "Text (*.txt);;All files (*)")
        if not value:
            return
        path = Path(value)
        try:
            url = path.read_text(encoding="utf-8").strip()
            if urlsplit(url).scheme != "https":
                raise ValueError("票据不是有效的 HTTPS URL")
            self.ticket = path
            self.ticket_label.setText(str(path))
            self.status.setText("临时票据已导入")
            self.append_log(f"已导入票据：{urlsplit(url).netloc}{urlsplit(url).path}\n")
        except Exception as exc:
            self.status.setText(f"票据无效：{exc}")

    def choose_credentials(self) -> None:
        value, _ = QFileDialog.getOpenFileName(
            self,
            "选择本机米家登录凭据",
            "",
            "JSON (*.json);;All files (*)",
        )
        if not value:
            return
        path = Path(value)
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            if not (payload.get("userId") or payload.get("user_id")) or not (
                payload.get("passToken") or payload.get("pass_token")
            ):
                raise ValueError("JSON 缺少 userId 或 passToken")
            self.credentials = path
            self.credentials_label.setText(path.name)
            self.status.setText("米家登录文件已载入；软件不会复制或提交该文件")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self.credentials = None
            self.status.setText(f"米家登录文件无效：{exc}")

    def helper(self, arguments: list[str]) -> str:
        environment = os.environ.copy()
        environment["CUKTECH_DATA_ROOT"] = str(self.paths.data_root)
        if self.credentials:
            environment["CUKTECH_MI_CREDENTIALS"] = str(self.credentials)
        completed = subprocess.run(
            self_command("--ota-helper", *arguments),
            cwd=str(self.paths.root),
            env=environment,
            capture_output=True,
            text=True,
            timeout=480,
            check=False,
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        if completed.returncode:
            raise RuntimeError(_redact_urls(output.strip() or f"命令退出码 {completed.returncode}"))
        return _redact_urls(output)

    def generate_ticket(self) -> None:
        if not self.firmware:
            self.status.setText("请先选择并校验固件")
            return
        if not self.credentials and not os.environ.get("CUKTECH_MI_CREDENTIALS"):
            self.status.setText("Windows OTA 需要先选择 AP01 所属米家账号的登录 JSON")
            return
        did, model = self.did.text().strip(), self.model.text().strip()
        if bool(did) != bool(model):
            self.status.setText("FDS DID 与 Model 必须同时填写或同时留空")
            return
        arguments = [str(self.firmware), "--upload-only", "--url-output", str(self.paths.ota_url_file)]
        if did:
            arguments += ["--fds-did", did, "--fds-model", model]
        self.run_operation("正在生成临时 FDS 票据…", lambda: self.helper(arguments), self.ticket_generated)

    def relay_helper(self, arguments: list[str]) -> str:
        environment = os.environ.copy()
        environment["CUKTECH_DATA_ROOT"] = str(self.paths.data_root)
        if self.credentials:
            environment["CUKTECH_MI_CREDENTIALS"] = str(self.credentials)
        completed = subprocess.run(
            self_command("--relay-helper", *arguments),
            cwd=str(self.paths.root),
            env=environment,
            capture_output=True,
            text=True,
            timeout=720,
            check=False,
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        if completed.returncode:
            raise RuntimeError(_redact_urls(output.strip() or f"命令退出码 {completed.returncode}"))
        return _redact_urls(output)

    def prepare_gateway_free(self) -> None:
        try:
            existing_log = self.paths.log_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            existing_log = ""
        if any("GET /screen.gif" in line and " 200" in line for line in existing_log.splitlines()):
            self.status.setText("已经检测到 AP01 获取 screen.gif；实时加载器已存在，不要再次 OTA")
            self.append_log("日志已有 GET /screen.gif 200，已阻止重复安装。\n")
            return
        if not self.credentials and not os.environ.get("CUKTECH_MI_CREDENTIALS"):
            self.status.setText("请先选择 AP01 所属米家账号的登录 JSON")
            return
        self.paths.gateway_free_firmware.unlink(missing_ok=True)
        self.paths.ota_url_file.unlink(missing_ok=True)
        self.firmware = None
        self.ticket = None
        self.download_verified_ok = False
        self.install_button.setEnabled(False)
        arguments = [
            "--bridge-url",
            local_screen_url(),
            "--refresh-seconds",
            "300",
            "--output",
            str(self.paths.gateway_free_firmware),
            "--url-output",
            str(self.paths.ota_url_file),
        ]
        self.run_operation(
            "正在进行米家只读预检并申请无网关部署包…",
            lambda: self.relay_helper(arguments),
            self.gateway_free_ready,
        )

    def gateway_free_ready(self, output: str) -> None:
        firmware = self.paths.gateway_free_firmware
        ticket = self.paths.ota_url_file
        if not firmware.exists() or not ticket.exists() or firmware.read_bytes()[:4] != b"BFNP":
            self.status.setText("共享服务完成，但本机部署包不完整")
            return
        digest = hashlib.sha256(firmware.read_bytes()).hexdigest()
        self.firmware = firmware
        self.ticket = ticket
        self.firmware_label.setText(f"{firmware.name} · {firmware.stat().st_size / 1024 / 1024:.2f} MB")
        self.hash_label.setText(f"SHA-256  {digest}")
        self.ticket_label.setText(str(ticket))
        self.status.setText("无网关部署包已就绪；请执行仅下载验证")
        self.append_log(output + "\n无网关部署包与临时票据已通过本机预检。\n")

    def ticket_generated(self, output: str) -> None:
        self.ticket = self.paths.ota_url_file if self.paths.ota_url_file.exists() else None
        self.ticket_label.setText(str(self.ticket) if self.ticket else "命令完成，但没有生成票据")
        self.status.setText("临时票据已生成，请尽快验证" if self.ticket else "没有生成票据")
        self.append_log(output)

    def verify_download(self) -> None:
        if not self.firmware or not self.ticket:
            self.status.setText("请先选择固件并生成或导入票据")
            return
        if not self.credentials and not os.environ.get("CUKTECH_MI_CREDENTIALS"):
            self.status.setText("下载验证需要先选择 AP01 所属米家账号的登录 JSON")
            return
        arguments = [str(self.firmware), "--download-only", "--ota-url-file", str(self.ticket), "--timeout", "360"]
        self.run_operation("正在让 AP01 仅下载并校验…", lambda: self.helper(arguments), self.download_verified)

    def download_verified(self, output: str) -> None:
        self.download_verified_ok = True
        self.install_button.setEnabled(True)
        self.status.setText("下载校验完成 · 未安装、未切换启动分区")
        self.status.setObjectName("successText")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.append_log(output + "\nAP01 下载验证通过；本次没有安装固件。\n")

    def install_firmware(self) -> None:
        if not self.download_verified_ok or not self.firmware or not self.ticket:
            self.status.setText("请先完成仅下载验证")
            return
        answer = QMessageBox.warning(
            self,
            "确认首次安装实时加载器",
            "本操作会对 AP01 Flash 写入一次并触发重启。\n"
            "仅适用于 njcuk.enstor.ap01 固件 1.0.2_0031。\n"
            "以后图片和额度刷新只写 RAM，不会重复刷固件。\n\n"
            "是否确认安装？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.status.setText("已取消安装；设备未写入 Flash")
            return
        arguments = [
            str(self.firmware),
            "--install",
            "--ota-url-file",
            str(self.ticket),
            "--timeout",
            "420",
        ]
        self.run_operation(
            "已确认：正在安装并等待 AP01 重启…",
            lambda: self.helper(arguments),
            self.install_finished,
        )

    def install_finished(self, output: str) -> None:
        self.download_verified_ok = False
        self.install_button.setEnabled(False)
        self.status.setText("安装完成；请等待 AP01 请求 /screen.gif")
        self.append_log(output + "\nAP01 首次安装完成；后续画面更新只使用 RAM。\n")

    def copy_ticket(self) -> None:
        if not self.ticket:
            self.status.setText("没有可复制的票据")
            return
        try:
            QApplication.clipboard().setText(self.ticket.read_text(encoding="utf-8").strip())
            self.status.setText("完整临时链接已复制；请勿公开分享")
        except OSError as exc:
            self.status.setText(str(exc))

    def run_operation(self, title: str, callback: Callable[[], Any], success: Callable[[Any], None]) -> None:
        self.status.setText(title)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        for button in (self.shared_button, self.generate_button, self.verify_button, self.copy_button, self.install_button):
            button.setEnabled(False)
        worker = Worker(callback)
        worker.signals.result.connect(success)
        worker.signals.error.connect(lambda error: (self.status.setText(f"任务失败：{error}"), self.append_log(f"任务失败：{error}\n")))
        worker.signals.finished.connect(self.operation_finished)
        self.pool.start(worker)

    def operation_finished(self) -> None:
        self.progress.setVisible(False)
        self.progress.setRange(0, 1)
        for button in (self.shared_button, self.generate_button, self.verify_button, self.copy_button):
            button.setEnabled(True)
        self.install_button.setEnabled(self.download_verified_ok)

    def append_log(self, text: str) -> None:
        self.log.moveCursor(QTextCursor.MoveOperation.End)
        self.log.insertPlainText(_redact_urls(text))
        self.log.ensureCursorVisible()


class MainWindow(QMainWindow):
    def __init__(self, paths: AppPaths) -> None:
        super().__init__()
        self.paths = paths
        self.paths.ensure()
        self.pool = QThreadPool.globalInstance()
        self.settings = QSettings("wqytommy666", APP_NAME)
        self.movie: QMovie | None = None
        self.preview_signature: tuple[str, int] | None = None
        self.busy = False
        self.really_quit = False
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(_app_icon())
        self.setMinimumSize(980, 720)
        self.resize(1100, 850)
        self.build_ui()
        self.create_tray()

        self.timer = QTimer(self)
        self.timer.setInterval(10_000)
        self.timer.timeout.connect(self.refresh_status)
        self.timer.start()
        QTimer.singleShot(0, self.initial_start)
        if not self.settings.value("beginnerGuideSeenV1", False, bool):
            self.settings.setValue("beginnerGuideSeenV1", True)
            QTimer.singleShot(650, self.show_guide)

    def build_ui(self) -> None:
        root_widget = QWidget()
        root_widget.setObjectName("appRoot")
        self.setCentralWidget(root_widget)
        root = QVBoxLayout(root_widget)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(17)

        header = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QPixmap(str(_resource("macos/AP01Logo.png"))).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        logo.setFixedSize(64, 64)
        header.addWidget(logo)
        titles = QVBoxLayout()
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        titles.addWidget(title)
        titles.addWidget(_muted("酷态科万向屏 · Windows 本地实时内容控制"))
        header.addLayout(titles)
        header.addStretch()
        guide = QPushButton("新手引导")
        guide.clicked.connect(self.show_guide)
        header.addWidget(guide)
        self.status_pill = StatusPill()
        header.addWidget(self.status_pill)
        root.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(17)
        preview_card, preview_layout = _card()
        preview_head = QHBoxLayout()
        preview_head.addWidget(_section("当前画面"))
        preview_head.addStretch()
        self.mode_tag = QLabel("Claude / Codex")
        self.mode_tag.setObjectName("tag")
        preview_head.addWidget(self.mode_tag)
        preview_layout.addLayout(preview_head)
        self.preview = QLabel("暂无预览")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(460, 300)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview.setStyleSheet("background:#01040B;border:1px solid #1A2B42;border-radius:14px;color:#64748B;")
        preview_layout.addWidget(self.preview, 1)
        self.url_label = QLabel(local_screen_url())
        self.url_label.setObjectName("muted")
        self.url_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.url_label.setStyleSheet('font-family:"Cascadia Mono","Consolas";color:#93A4B8;')
        preview_layout.addWidget(self.url_label)
        copy_url = QPushButton("复制屏幕地址")
        copy_url.clicked.connect(self.copy_url)
        preview_layout.addWidget(copy_url, 0, Qt.AlignmentFlag.AlignLeft)
        body.addWidget(preview_card, 1)

        controls, controls_layout = _card()
        controls.setFixedWidth(365)
        controls_layout.setSpacing(9)
        controls_layout.addWidget(_section("显示内容"))
        self.quota_button = QPushButton("显示 Claude / Codex 额度")
        self.quota_button.setObjectName("primary")
        self.quota_button.clicked.connect(self.select_quota)
        controls_layout.addWidget(self.quota_button)
        controls_layout.addWidget(_muted("自动读取已登录账户，约每 5 分钟刷新。", wrap=False))

        controls_layout.addSpacing(4)
        controls_layout.addWidget(_muted("自定义图片适配方式", wrap=False))
        segments = QHBoxLayout()
        segments.setSpacing(6)
        self.fit_group = QButtonGroup(self)
        self.fit_group.setExclusive(True)
        for index, (text, value) in enumerate((("完整显示", "contain"), ("铺满裁切", "cover"), ("拉伸", "stretch"))):
            button = QToolButton()
            button.setText(text)
            button.setObjectName("segment")
            button.setCheckable(True)
            button.setProperty("fit", value)
            if index == 0:
                button.setChecked(True)
            self.fit_group.addButton(button)
            segments.addWidget(button, 1)
        controls_layout.addLayout(segments)
        self.image_button = QPushButton("选择图片并推送")
        self.image_button.setObjectName("orange")
        self.image_button.clicked.connect(self.select_image)
        controls_layout.addWidget(self.image_button)

        controls_layout.addSpacing(5)
        utility_row = QHBoxLayout()
        utility_row.setSpacing(7)
        self.restart_button = QPushButton("重启并立即刷新")
        self.restart_button.clicked.connect(self.restart)
        utility_row.addWidget(self.restart_button, 1)
        folder = QPushButton("打开输出文件夹")
        folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.paths.artifacts))))
        utility_row.addWidget(folder, 1)
        controls_layout.addLayout(utility_row)

        self.autostart = QCheckBox("登录 Windows 后自动运行 Bridge")
        self.autostart.setChecked(autostart_enabled())
        self.autostart.toggled.connect(self.toggle_autostart)
        controls_layout.addWidget(self.autostart)

        ota = QPushButton("首次部署 / OTA 交接…")
        ota.clicked.connect(lambda: OTADeploymentDialog(self.paths, self).exec())
        controls_layout.addWidget(ota)
        controls_layout.addWidget(_muted("无网关可一键准备；真正安装前再次确认。", wrap=False))
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        controls_layout.addWidget(self.progress)
        self.toast = QLabel("")
        self.toast.setObjectName("toast")
        self.toast.setWordWrap(True)
        controls_layout.addWidget(self.toast)
        controls_layout.addStretch()
        self.autostart_state = QLabel()
        self.autostart_state.setWordWrap(True)
        controls_layout.addWidget(self.autostart_state)
        body.addWidget(controls)
        root.addLayout(body, 1)

        log_card = QFrame()
        log_card.setObjectName("logCard")
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(15, 13, 15, 13)
        log_head = QHBoxLayout()
        log_head.addWidget(_section("运行状态"))
        log_head.addStretch()
        self.status_text = QLabel("正在检查服务…")
        self.status_text.setObjectName("warningText")
        log_head.addWidget(self.status_text)
        log_layout.addLayout(log_head)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(88)
        self.log_text.setPlaceholderText("等待 AP01 请求…")
        log_layout.addWidget(self.log_text)
        root.addWidget(log_card)
        self.update_autostart_label()

    def create_tray(self) -> None:
        self.tray: QSystemTrayIcon | None = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(_app_icon(), self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu()
        show_action = QAction("打开控制器", self)
        show_action.triggered.connect(self.show_from_tray)
        restart_action = QAction("重启 Bridge", self)
        restart_action.triggered.connect(self.restart)
        quit_action = QAction("退出软件（Bridge 继续运行）", self)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(show_action)
        menu.addAction(restart_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_from_tray() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self.tray.show()

    def initial_start(self) -> None:
        self.run_task("正在启动 Bridge…", lambda: start_bridge(self.paths), lambda ok: self.after_start(bool(ok)))

    def after_start(self, ok: bool) -> None:
        self.toast.setText("Bridge 已启动" if ok else "Bridge 未能启动，请运行 Windows 诊断")
        self.refresh_status()

    def refresh_status(self) -> None:
        document = health(0.65)
        online = document is not None
        self.status_pill.set_online(online)
        if not document:
            status = "服务未运行；点击“重启并立即刷新”"
        elif document.get("status") == "disconnected":
            stamp = document.get("last_refresh")
            if isinstance(stamp, (int, float)):
                refreshed = time.strftime("%H:%M:%S", time.localtime(stamp))
                status = f"额度未连接 · 屏幕已切换提示页 · 最后成功 {refreshed}"
            else:
                status = "额度未连接 · 屏幕已显示“未连接，请连接”"
        elif document.get("error"):
            status = f"服务运行中 · 数据刷新失败：{document['error']}"
        elif "requests" in document:
            status = f"自定义画面服务正常 · 已请求 {document.get('requests', 0)} 次"
        elif isinstance(document.get("last_refresh"), (int, float)):
            refreshed = time.strftime("%H:%M:%S", time.localtime(document["last_refresh"]))
            status = f"额度数据在线 · 最后刷新 {refreshed} · 每 5 分钟更新"
        else:
            status = "额度服务正常 · 每 5 分钟自动刷新"
        self.status_text.setText(status)
        self.status_text.setObjectName("successText" if online else "warningText")
        self.status_text.style().unpolish(self.status_text)
        self.status_text.style().polish(self.status_text)
        self.url_label.setText(local_screen_url())
        self.mode_tag.setText("自定义" if current_mode(self.paths) == "custom" else "Claude / Codex")
        self.update_preview()
        text = tail_log(self.paths, 8)
        if text and text != self.log_text.toPlainText():
            self.log_text.setPlainText(text)
            self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
        self.update_autostart_label()

    def update_preview(self) -> None:
        path = preview_path(self.paths)
        if not path:
            self.preview_signature = None
            self.preview.setMovie(None)
            self.preview.setPixmap(QPixmap())
            self.preview.setText("暂无预览")
            return
        try:
            signature = (str(path), path.stat().st_mtime_ns)
        except OSError:
            return
        if signature == self.preview_signature:
            return
        self.preview_signature = signature
        if path.suffix.lower() == ".gif":
            self.movie = QMovie(str(path))
            self.movie.setScaledSize(QSize(500, 375))
            self.preview.setText("")
            self.preview.setMovie(self.movie)
            self.movie.start()
        else:
            pixmap = QPixmap(str(path)).scaled(500, 375, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.preview.setPixmap(pixmap)

    def select_image(self) -> None:
        value, _ = QFileDialog.getOpenFileName(
            self,
            "选择要显示的图片或 GIF",
            "",
            "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.tif *.tiff);;All files (*)",
        )
        if not value:
            return
        button = self.fit_group.checkedButton()
        fit = str(button.property("fit")) if button else "contain"
        self.run_task(
            "正在转换为 AP01 画面…",
            lambda: convert_custom_image(self.paths, Path(value), fit),
            lambda result: self.operation_success(f"自定义画面已推送 · {result['bytes']} 字节"),
        )

    def select_quota(self) -> None:
        self.run_task("正在启动 Claude / Codex 额度模式…", lambda: use_quota_mode(self.paths), lambda _: self.operation_success("额度模式已启动，正在读取官方账户"))

    def restart(self) -> None:
        self.run_task("正在重启 Bridge…", lambda: start_bridge(self.paths, restart=True), lambda ok: self.after_start(bool(ok)))

    def operation_success(self, message: str) -> None:
        self.toast.setText(message)
        self.preview_signature = None
        self.refresh_status()

    def run_task(self, title: str, callback: Callable[[], Any], success: Callable[[Any], None]) -> None:
        if self.busy:
            return
        self.set_busy(True, title)
        worker = Worker(callback)
        worker.signals.result.connect(success)
        worker.signals.error.connect(self.operation_error)
        worker.signals.finished.connect(lambda: self.set_busy(False))
        self.pool.start(worker)

    def operation_error(self, error: str) -> None:
        self.toast.setText(f"操作失败：{error}")
        self.toast.setObjectName("dangerText")
        self.toast.style().unpolish(self.toast)
        self.toast.style().polish(self.toast)

    def set_busy(self, busy: bool, text: str = "") -> None:
        self.busy = busy
        for button in (self.quota_button, self.image_button, self.restart_button):
            button.setEnabled(not busy)
        self.progress.setVisible(busy)
        self.progress.setRange(0, 0 if busy else 1)
        if text:
            self.toast.setText(text)
            self.toast.setObjectName("toast")
            self.toast.style().unpolish(self.toast)
            self.toast.style().polish(self.toast)

    def copy_url(self) -> None:
        QApplication.clipboard().setText(self.url_label.text())
        self.toast.setText("局域网屏幕地址已复制")

    def toggle_autostart(self, checked: bool) -> None:
        try:
            enable_autostart() if checked else disable_autostart()
        except OSError as exc:
            self.toast.setText(f"修改自动启动失败：{exc}")
            self.autostart.blockSignals(True)
            self.autostart.setChecked(not checked)
            self.autostart.blockSignals(False)
        self.update_autostart_label()

    def update_autostart_label(self) -> None:
        enabled = autostart_enabled()
        self.autostart.blockSignals(True)
        self.autostart.setChecked(enabled)
        self.autostart.blockSignals(False)
        self.autostart_state.setText("登录自动启动已开启" if enabled else "登录自动启动尚未开启")
        self.autostart_state.setObjectName("successText" if enabled else "warningText")
        self.autostart_state.style().unpolish(self.autostart_state)
        self.autostart_state.style().polish(self.autostart_state)

    def show_guide(self) -> None:
        BeginnerGuideDialog(self.paths, self).exec()

    def show_from_tray(self) -> None:
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def quit_app(self) -> None:
        self.really_quit = True
        if self.tray:
            self.tray.hide()
        QApplication.quit()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.tray and not self.really_quit:
            event.ignore()
            self.hide()
            if not self.settings.value("trayHintSeen", False, bool):
                self.settings.setValue("trayHintSeen", True)
                self.tray.showMessage(APP_NAME, "控制器已缩小到托盘；后台 Bridge 会继续刷新 AP01。", QSystemTrayIcon.MessageIcon.Information, 4000)
            return
        super().closeEvent(event)


def run_gui() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)
    app.setOrganizationName("wqytommy666")
    app.setWindowIcon(_app_icon())
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    app.setQuitOnLastWindowClosed(True)
    window = MainWindow(AppPaths.discover())
    window.show()
    return int(app.exec())
