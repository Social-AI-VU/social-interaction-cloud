"""
Docker Compose lifecycle helpers for SICApplication.

Starts and stops per-demo service stacks declared in a docker-compose.yml file.
"""

from __future__ import annotations

import inspect
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Optional


DOCKER_NOT_INSTALLED_MESSAGE = (
    "Docker is not installed or not on PATH. Install Docker Desktop to use "
    "services_compose, or start required services manually."
)


def resolve_compose_path(path: str, caller_file: Optional[str] = None) -> Path:
    """
    Resolve ``path`` relative to the caller's source directory.

    If ``path`` is already absolute, it is returned as-is.
    """
    compose_path = Path(path)
    if compose_path.is_absolute():
        resolved = compose_path.resolve()
    else:
        if not caller_file:
            frame = inspect.currentframe()
            try:
                caller = frame.f_back if frame else None
                caller_file = caller.f_globals.get("__file__") if caller else None
            finally:
                del frame
        if not caller_file:
            raise RuntimeError(
                "Could not resolve services_compose path; pass an absolute path or "
                "call from demo module code."
            )
        base = Path(caller_file).resolve().parent
        resolved = (base / path).resolve()

    if not resolved.is_file():
        raise IOError("Docker Compose file not found: {}".format(resolved))
    return resolved


def default_project_name(compose_path: Path) -> str:
    """Derive a stable compose project name from the compose file location."""
    slug = compose_path.parent.name.replace("_", "-").lower()
    return "sic-{}".format(slug)


def _docker_compose_base_cmd() -> list[str]:
    if shutil.which("docker") is None:
        raise RuntimeError(DOCKER_NOT_INSTALLED_MESSAGE)
    return ["docker", "compose"]


def _wait_for_tcp(host: str, port: int, timeout_sec: float = 60.0) -> None:
    deadline = time.time() + timeout_sec
    last_err = None
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2.0):
                return
        except OSError as exc:
            last_err = exc
            time.sleep(0.4)
    raise RuntimeError(
        "Timed out waiting for {host}:{port} ({err})".format(
            host=host, port=port, err=last_err
        )
    )


def start(
    compose_path: Path,
    project_name: str,
    host_ip: str,
    *,
    redis_host: str = "127.0.0.1",
    redis_port: int = 6379,
    startup_timeout_sec: float = 120.0,
) -> None:
    """
    Build and start the compose stack, then wait until Redis is reachable on the host.
    """
    env = os.environ.copy()
    env["SIC_HOST_IP"] = host_ip

    cmd = _docker_compose_base_cmd() + [
        "-f",
        str(compose_path),
        "-p",
        project_name,
        "up",
        "-d",
        "--build",
        "--wait",
    ]
    result = subprocess.run(
        cmd,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "docker compose up failed (exit {code}):\n{out}\n{err}".format(
                code=result.returncode,
                out=(result.stdout or "").strip(),
                err=(result.stderr or "").strip(),
            )
        )

    _wait_for_tcp(redis_host, redis_port, timeout_sec=startup_timeout_sec)


def stop(compose_path: Path, project_name: str) -> None:
    """Stop and remove containers for the compose project."""
    if shutil.which("docker") is None:
        return

    cmd = _docker_compose_base_cmd() + [
        "-f",
        str(compose_path),
        "-p",
        project_name,
        "down",
        "--remove-orphans",
    ]
    subprocess.run(cmd, capture_output=True, text=True)
