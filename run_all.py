import os
import sys
import time
import signal
import webbrowser
import subprocess
from pathlib import Path
from typing import Optional

import requests


ROOT = Path(__file__).parent.resolve()
MODELS_DIR = ROOT / "models"


def latest_model_tar() -> Optional[Path]:
    """Return latest .tar.gz in models/ by modified time."""
    candidates = sorted(MODELS_DIR.glob("*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def ensure_model() -> Path:
    """Ensure a usable model exists and prefer production.tar.gz synchronized with latest.

    - If no models exist, train one.
    - If production.tar.gz exists but is older than latest model, update production from latest.
    - Return production.tar.gz if present; otherwise return the latest model.
    """
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    prod = MODELS_DIR / "production.tar.gz"
    latest = latest_model_tar()

    if latest is None:
        print("[orchestrator] No model found. Training a model...")
        subprocess.run([sys.executable, "-m", "rasa", "train"], cwd=ROOT, check=True)
        latest = latest_model_tar()
        if latest is None:
            raise RuntimeError("Model training completed but no model file was found in models/.")

    # Sync production with latest if missing or outdated
    try:
        if (not prod.exists()) or (latest.stat().st_mtime > prod.stat().st_mtime):
            prod.write_bytes(latest.read_bytes())
    except Exception:
        # If copying fails, fall back to latest
        pass

    return prod if prod.exists() else latest


def wait_for_url(url: str, timeout_sec: int = 30) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=3)
            if r.ok:
                return True
        except Exception:
            pass
        time.sleep(0.8)
    return False


def is_url_ok(url: str, timeout_sec: float = 3.0) -> bool:
    try:
        r = requests.get(url, timeout=timeout_sec)
        return bool(r.ok)
    except Exception:
        return False


def start_actions_server(port: int = 5055) -> subprocess.Popen:
    print(f"[orchestrator] Starting actions server on port {port}...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "rasa", "run", "actions", "-p", str(port)],
        cwd=ROOT,
    )
    ok = wait_for_url(f"http://localhost:{port}/health", timeout_sec=40)
    if ok:
        print("[orchestrator] Actions server is healthy.")
    else:
        print("[orchestrator] Warning: actions server health check timed out.")
    return proc


def start_core_server(model_path: Path, port: int = 5006) -> subprocess.Popen:
    print(f"[orchestrator] Starting core server on port {port} with model {model_path.name}...")
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "rasa", "run",
            "--enable-api", "-p", str(port), "--cors", "*",
            "--connector", "rest", "-m", str(model_path),
        ],
        cwd=ROOT,
    )
    ok = wait_for_url(f"http://localhost:{port}/status", timeout_sec=60)
    if ok:
        print("[orchestrator] Core server is reachable.")
    else:
        print("[orchestrator] Warning: core server status check timed out.")
    return proc


def port_free(port: int) -> bool:
    try:
        requests.get(f"http://localhost:{port}/", timeout=1)
        return False
    except Exception:
        return True


def start_streamlit(port: int = 8501) -> subprocess.Popen:
    chosen_port = port if port_free(port) else (port + 1)
    print(f"[orchestrator] Launching Streamlit UI on port {chosen_port}...")
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", "streamlit_app.py",
            "--server.port", str(chosen_port),
            "--server.headless", "true",
            "--browser.gatherUsageStats", "false",
        ],
        cwd=ROOT,
    )
    # Give Streamlit a moment to initialize
    time.sleep(2.5)
    webbrowser.open(f"http://localhost:{chosen_port}/")
    return proc


def main():
    try:
        model_path = ensure_model()
        actions_proc = start_actions_server(port=5055)
        core_proc = start_core_server(model_path, port=5006)
        ui_proc = start_streamlit(port=8501)

        print("\n[orchestrator] All services started.")
        print("[orchestrator] UI: http://localhost:8501/ (or :8502 if 8501 was busy)")
        print("[orchestrator] Core: http://localhost:5006/status")
        print("[orchestrator] Actions: http://localhost:5055/health\n")

        # Keep the orchestrator running until user interrupts
        unhealthy_streak = 0
        while True:
            time.sleep(8.0)
            # Periodic health checks: if core becomes unreachable, restart it
            if not is_url_ok("http://localhost:5006/status", timeout_sec=2.0):
                unhealthy_streak += 1
                if unhealthy_streak >= 3:
                    print("[orchestrator] Core status unreachable. Attempting restart...")
                    try:
                        if core_proc and core_proc.poll() is None:
                            core_proc.terminate()
                            try:
                                core_proc.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                core_proc.kill()
                    except Exception:
                        pass
                    core_proc = start_core_server(model_path, port=5006)
                    unhealthy_streak = 0
            else:
                unhealthy_streak = 0

    except KeyboardInterrupt:
        print("\n[orchestrator] Shutting down...")
    finally:
        # Terminate child processes gracefully
        for proc in [locals().get("ui_proc"), locals().get("core_proc"), locals().get("actions_proc")]:
            if proc and isinstance(proc, subprocess.Popen):
                try:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                except Exception:
                    pass
        print("[orchestrator] Done.")


if __name__ == "__main__":
    main()