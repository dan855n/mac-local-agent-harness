from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import time
from pathlib import Path

from .base import ToolContext, register
from ..safety import resolve_user_path

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None

def _require_serial() -> str | None:
    return None if serial is not None else "pyserial is not installed. Reinstall the project dependencies."

@register("list_serial_ports", "List attached serial devices with USB identifiers when available.", group="hardware")
def list_serial_ports(ctx: ToolContext) -> str:
    if list_ports is None:
        return _require_serial() or ""
    ports = list(list_ports.comports())
    return "\n".join(f"{p.device} | {p.description} | {p.hwid}" for p in ports) or "No serial ports detected."

@register("read_serial", "Read output from a serial device without transmitting data.", {"port": {"type": "string"}, "baudrate": {"type": "integer"}, "seconds": {"type": "number"}}, ["port"], group="hardware")
def read_serial(ctx: ToolContext, port: str, baudrate: int = 115200, seconds: float = 3.0) -> str:
    if serial is None:
        return _require_serial() or ""
    seconds = max(0.2, min(float(seconds), 20.0))
    baudrate = max(1200, min(int(baudrate), 3_000_000))
    try:
        chunks = []
        with serial.Serial(port, baudrate=baudrate, timeout=0.25) as device:
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                data = device.read(device.in_waiting or 1)
                if data:
                    chunks.append(data)
        return b"".join(chunks).decode("utf-8", errors="replace")[:12000] or "No serial output received."
    except Exception as exc:
        return f"Serial read failed: {exc}"

@register("capture_esp32_boot", "Reset an ESP32-S3 through the serial control lines and capture boot output. This reboots the board; approval required.", {"port": {"type": "string"}, "baudrate": {"type": "integer"}, "seconds": {"type": "number"}}, ["port"], risk="device", group="hardware")
def capture_esp32_boot(ctx: ToolContext, port: str, baudrate: int = 115200, seconds: float = 5.0) -> str:
    if serial is None:
        return _require_serial() or ""
    seconds = max(1.0, min(float(seconds), 12.0))
    try:
        with serial.Serial(port, baudrate=max(1200, min(int(baudrate), 3_000_000)), timeout=0.3) as device:
            device.reset_input_buffer()
            device.setDTR(False)
            device.setRTS(True)
            time.sleep(0.1)
            device.setRTS(False)
            deadline = time.monotonic() + seconds
            chunks = []
            while time.monotonic() < deadline:
                data = device.read(device.in_waiting or 1)
                if data:
                    chunks.append(data)
        return b"".join(chunks).decode("utf-8", errors="replace")[:16000] or "Reset sent; no boot logs received."
    except Exception as exc:
        return f"ESP32 boot capture failed: {exc}"

@register("send_serial", "Transmit one line to a serial device and capture its response. Requires approval because this changes device state.", {"port": {"type": "string"}, "command": {"type": "string"}, "baudrate": {"type": "integer"}, "seconds": {"type": "number"}}, ["port", "command"], risk="device", group="hardware")
def send_serial(ctx: ToolContext, port: str, command: str, baudrate: int = 115200, seconds: float = 2.0) -> str:
    if serial is None:
        return _require_serial() or ""
    if len(command) > 2000 or "\x00" in command:
        return "Error: Command must be under 2000 characters and contain no NUL bytes."
    seconds = max(0.2, min(float(seconds), 15.0))
    try:
        with serial.Serial(port, baudrate=max(1200, min(int(baudrate), 3_000_000)), timeout=0.25) as device:
            device.reset_input_buffer()
            device.write((command + "\r\n").encode("utf-8"))
            device.flush()
            deadline = time.monotonic() + seconds
            chunks = []
            while time.monotonic() < deadline:
                data = device.read(device.in_waiting or 1)
                if data:
                    chunks.append(data)
        return b"".join(chunks).decode("utf-8", errors="replace")[:12000] or "Command sent; no response received."
    except Exception as exc:
        return f"Serial command failed: {exc}"

@register("adb_diagnostic", "Run one allowlisted read-only Android diagnostic through ADB.", {"diagnostic": {"type": "string", "enum": ["battery", "model", "android_version", "sdk", "screen", "density", "ip", "storage"]}}, ["diagnostic"], group="hardware")
def adb_diagnostic(ctx: ToolContext, diagnostic: str) -> str:
    args = {
        "battery": ["dumpsys", "battery"], "model": ["getprop", "ro.product.model"],
        "android_version": ["getprop", "ro.build.version.release"], "sdk": ["getprop", "ro.build.version.sdk"],
        "screen": ["wm", "size"], "density": ["wm", "density"], "ip": ["ip", "addr"], "storage": ["df", "-h"],
    }.get(diagnostic)
    if not args:
        return "Unsupported diagnostic."
    try:
        result = subprocess.run(["adb", "-d", "shell", *args], capture_output=True, text=True, timeout=15)
        return (result.stdout or result.stderr).strip()[:8000]
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"ADB diagnostic failed: {exc}"

@register("deploy_circuitpython", "Write a complete code.py to a mounted CircuitPython volume. Approval required because the board will reload the code.", {"code": {"type": "string"}, "volume": {"type": "string"}}, ["code"], risk="device", group="hardware")
def deploy_circuitpython(ctx: ToolContext, code: str, volume: str = "/Volumes/CIRCUITPY") -> str:
    target_dir = Path(volume).expanduser().resolve()
    if not target_dir.is_dir() or target_dir.name.upper() != "CIRCUITPY":
        return f"Error: Expected a mounted CIRCUITPY volume, got {target_dir}"
    if len(code.encode("utf-8")) > 1_000_000:
        return "Error: CircuitPython file is limited to 1 MB."
    target = target_dir / "code.py"
    try:
        if target.exists():
            backup = target.with_name("code.py.backup")
            shutil.copy2(target, backup)
        target.write_text(code, encoding="utf-8")
        return f"Wrote {len(code)} characters to {target}; board may auto-reload."
    except OSError as exc:
        return f"CircuitPython deployment failed: {exc}"

@register("flash_esp32_app", "Flash one compiled ESP32-S3 application image at the standard app offset 0x10000. This overwrites firmware; approval required.", {"binary_path": {"type": "string"}, "port": {"type": "string"}, "baudrate": {"type": "integer"}}, ["binary_path", "port"], risk="device", group="hardware")
def flash_esp32_app(ctx: ToolContext, binary_path: str, port: str, baudrate: int = 460800) -> str:
    binary = resolve_user_path(binary_path, ctx.settings.resolved_roots(), ctx.settings.allow_sensitive_paths)
    if not binary.is_file() or binary.suffix.lower() != ".bin":
        return "Error: Provide an existing .bin file inside an allowed path."
    if not shutil.which("python3"):
        return "python3 is unavailable."
    checksum = hashlib.sha256()
    with binary.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(chunk)
    digest = checksum.hexdigest()
    baudrate = max(9600, min(int(baudrate), 921600))
    cmd = ["python3", "-m", "esptool", "--chip", "esp32s3", "--port", port, "--baud", str(baudrate), "write-flash", "0x10000", str(binary)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        output = f"SHA-256: {digest}\nExit code: {result.returncode}\n{result.stdout[-6000:]}\n{result.stderr[-3000:]}"
        return output
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"Flash operation failed: {exc}"
