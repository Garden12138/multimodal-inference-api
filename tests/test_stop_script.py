import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PID_FILE = ROOT / "data" / "inference.pid"
STOP = ["bash", str(ROOT / "scripts" / "stop.sh")]


def _unused_pid() -> int:
    candidate = 200_000
    while candidate < 500_000:
        try:
            os.kill(candidate, 0)
        except ProcessLookupError:
            return candidate
        except PermissionError:
            pass
        candidate += 1
    raise AssertionError("could not find an unused pid")


def _restore(original: str | None) -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    if original is None:
        PID_FILE.unlink(missing_ok=True)
    else:
        PID_FILE.write_text(original)


def test_stop_refuses_a_reused_or_foreign_pid():
    original = PID_FILE.read_text(encoding="utf-8") if PID_FILE.exists() else None
    process = subprocess.Popen(["sleep", "30"])
    try:
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(f"{process.pid}\n", encoding="utf-8")
        result = subprocess.run(STOP, cwd=ROOT, capture_output=True, text=True, check=False)
        assert result.returncode != 0
        assert "Refusing" in result.stderr
        assert process.poll() is None
        assert PID_FILE.read_text(encoding="utf-8").strip() == str(process.pid)
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            process.wait(timeout=5)
        _restore(original)


def test_stop_removes_a_dead_pid_without_signaling_anyone():
    original = PID_FILE.read_text(encoding="utf-8") if PID_FILE.exists() else None
    try:
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(f"{_unused_pid()}\n", encoding="utf-8")
        result = subprocess.run(STOP, cwd=ROOT, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
        assert not PID_FILE.exists()
    finally:
        _restore(original)


def test_stop_rejects_a_malformed_pid_file():
    original = PID_FILE.read_text(encoding="utf-8") if PID_FILE.exists() else None
    try:
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text("not-a-pid\n", encoding="utf-8")
        result = subprocess.run(STOP, cwd=ROOT, capture_output=True, text=True, check=False)
        assert result.returncode != 0
        assert PID_FILE.exists()
    finally:
        _restore(original)


def test_stop_signals_only_this_checkout(tmp_path):
    if (ROOT / ".env").exists():
        # The launcher would also read that file. This test starts the runtime directly.
        pass
    original = PID_FILE.read_text(encoding="utf-8") if PID_FILE.exists() else None
    env = os.environ.copy()
    env.update(
        {
            "INFERENCE_API_KEY": "k" * 40,
            "INFERENCE_HOST": "127.0.0.1",
            "INFERENCE_PORT": "18190",
            "INFERENCE_ALLOWED_CIDRS": "127.0.0.1/32,::1/128",
            "INFERENCE_PUBLIC_BASE_URL": "http://127.0.0.1:18190",
            "VIDEO_ALLOW_RESOLUTION_FALLBACK": "0",
            "INFERENCE_DATABASE_PATH": str(tmp_path / "inference.db"),
            "INFERENCE_DATA_DIR": str(tmp_path / "data"),
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "inference.runtime"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                with urllib.request.urlopen("http://127.0.0.1:18190/healthz", timeout=0.5) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.2)
        else:
            raise AssertionError("runtime did not become healthy")
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(f"{process.pid}\n", encoding="utf-8")
        result = subprocess.run(STOP, cwd=ROOT, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
        process.wait(timeout=5)
        assert not PID_FILE.exists()
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            process.wait(timeout=5)
        _restore(original)
