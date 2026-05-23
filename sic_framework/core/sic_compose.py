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
import sys
import time
from pathlib import Path
from typing import Optional


DOCKER_NOT_INSTALLED_MESSAGE = (
    "Docker is not installed or not on PATH. Install Docker Desktop to use "
    "services_compose, or start required services manually."
)

DOCKER_ROOT_MISSING_MESSAGE = (
    "Docker files not found in the installed social-interaction-cloud package. "
    "Reinstall or upgrade the package, set SIC_DOCKER_ROOT manually, or use "
    "pre-built images in your compose file."
)


def _sic_framework_dir() -> Path:
    import sic_framework

    return Path(sic_framework.__file__).resolve().parent


def resolve_docker_root() -> Path:
    """
    Return the directory containing shipped Docker files (``sic_framework/docker/``).

    Uses ``SIC_DOCKER_ROOT`` when set, otherwise derives the path from the installed
    ``sic_framework`` package location.
    """
    override = os.environ.get("SIC_DOCKER_ROOT")
    if override:
        root = Path(override).expanduser().resolve()
    else:
        root = _sic_framework_dir()

    dockerfile = root / "docker" / "sic-base" / "Dockerfile"
    if not dockerfile.is_file():
        legacy = root.parent / "docker" / "sic-base" / "Dockerfile"
        if legacy.is_file():
            return root.parent
        raise RuntimeError(DOCKER_ROOT_MISSING_MESSAGE)
    return root


def resolve_build_context(docker_root: Optional[Path] = None) -> Path:
    """
    Return the Docker build context for service images.

    Source checkouts use the repo root (parent of ``sic_framework/``) so local
    ``COPY`` installs work. PyPI installs use the package directory (PyPI target
    ignores context).
    """
    override = os.environ.get("SIC_BUILD_CONTEXT")
    if override:
        return Path(override).expanduser().resolve()

    docker_root = docker_root or resolve_docker_root()
    repo_root = docker_root.parent
    if (repo_root / "setup.py").is_file():
        return repo_root.resolve()
    return docker_root


def resolve_build_target(docker_root: Optional[Path] = None) -> str:
    """Return ``local`` for source checkouts, ``pypi`` for PyPI-only installs."""
    override = os.environ.get("SIC_BUILD_TARGET")
    if override:
        return override

    docker_root = docker_root or resolve_docker_root()
    repo_root = docker_root.parent
    if (repo_root / "setup.py").is_file():
        return "local"
    return "pypi"


def resolve_sic_version() -> str:
    override = os.environ.get("SIC_VERSION")
    if override:
        return override

    try:
        from importlib.metadata import version

        return version("social-interaction-cloud")
    except Exception:
        pass

    setup_py = _sic_framework_dir().parent / "setup.py"
    if setup_py.is_file():
        for line in setup_py.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("version="):
                return stripped.split("=", 1)[1].strip().strip('"').strip("'").rstrip(",")
    return "2.2.3"


def _compose_env(host_ip: Optional[str] = None) -> dict[str, str]:
    env = os.environ.copy()
    docker_root = resolve_docker_root()
    env["SIC_DOCKER_ROOT"] = str(docker_root)
    env["SIC_BUILD_CONTEXT"] = str(resolve_build_context(docker_root))
    env["SIC_BUILD_TARGET"] = resolve_build_target(docker_root)
    env["SIC_VERSION"] = resolve_sic_version()
    if host_ip is not None:
        env["SIC_HOST_IP"] = host_ip
    return env


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


def compose_project_name(
    compose_path: Path, override: Optional[str] = None
) -> str:
    """
    Return the Docker Compose project name for status messages.

    Uses ``override`` when provided, otherwise the top-level ``name:`` field in
    the compose file, otherwise a name derived from the compose directory.
    """
    if override:
        return override
    for line in compose_path.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("name:"):
            return stripped.split(":", 1)[1].strip().strip("'\"")
    return default_project_name(compose_path)


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


def _compose_file_paths(compose_path: Path) -> list[str]:
    return [str(compose_path)]


def _compose_cmd(
    compose_path: Path, project_name: Optional[str] = None
) -> list[str]:
    cmd = _docker_compose_base_cmd()
    for compose_file in _compose_file_paths(compose_path):
        cmd.extend(["-f", compose_file])
    if project_name:
        cmd.extend(["-p", project_name])
    return cmd


def _notify(message: str) -> None:
    """Print a user-facing status line (compose starts before SIC logging is up)."""
    print(message, file=sys.stderr, flush=True)


def _image_exists(image_ref: str) -> bool:
    ref = image_ref if ":" in image_ref else image_ref + ":latest"
    return (
        subprocess.run(
            ["docker", "image", "inspect", ref],
            capture_output=True,
        ).returncode
        == 0
    )


def _rebuild_requested() -> bool:
    return os.environ.get("SIC_COMPOSE_REBUILD", "").lower() in (
        "1",
        "true",
        "yes",
    )


def _service_image_names(project_name: str) -> list[str]:
    return ["{}-{}".format(project_name, svc) for svc in ("gpt", "datastore")]


def _ensure_images(
    base: list[str],
    env: dict[str, str],
    project_name: str,
) -> bool:
    """
    Build images that are not present locally (or all images when rebuild requested).

    Returns True if any build step ran.
    """
    built = False
    rebuild = _rebuild_requested()

    if rebuild or not _image_exists("sic-base:local"):
        _notify("Building shared sic-base image...")
        _run_compose(
            base + ["--profile", "build", "build", "sic-base"],
            env,
            "build (sic-base)",
        )
        built = True

    missing_services = [
        img
        for img in _service_image_names(project_name)
        if rebuild or not _image_exists(img)
    ]
    if missing_services:
        _notify("Building service images ({})...".format(", ".join(missing_services)))
        _run_compose(base + ["build", "gpt", "datastore"], env, "build")
        built = True

    return built


def _run_compose(cmd: list[str], env: dict[str, str], action: str) -> None:
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            "docker compose {action} failed (exit {code}):\n{out}\n{err}".format(
                action=action,
                code=result.returncode,
                out=(result.stdout or "").strip(),
                err=(result.stderr or "").strip(),
            )
        )


def start(
    compose_path: Path,
    host_ip: str,
    project_name: Optional[str] = None,
    *,
    redis_host: str = "127.0.0.1",
    redis_port: int = 6379,
    startup_timeout_sec: float = 120.0,
) -> None:
    """
    Build and start the compose stack, then wait until Redis is reachable on the host.

    The compose project name comes from the top-level ``name:`` field in the compose
    file unless ``project_name`` is passed to override it.
    """
    env = _compose_env(host_ip)

    display_name = compose_project_name(compose_path, project_name)
    base = _compose_cmd(compose_path, project_name)

    _notify(
        "Starting background services from {} (project: {})...".format(
            compose_path.name, display_name
        )
    )

    built = _ensure_images(base, env, display_name)
    if built:
        _notify(
            "Hold tight — building Docker images can take a few minutes on first run."
        )
    else:
        _notify("Using existing Docker images, starting containers...")

    _run_compose(base + ["up", "-d", "--wait"], env, "up")

    _wait_for_tcp(redis_host, redis_port, timeout_sec=startup_timeout_sec)
    _notify("Background services are ready.")


def stop(compose_path: Path, project_name: Optional[str] = None) -> None:
    """Stop and remove containers for the compose project."""
    if shutil.which("docker") is None:
        return

    cmd = _compose_cmd(compose_path, project_name) + [
        "down",
        "--remove-orphans",
    ]
    subprocess.run(cmd, env=_compose_env(), capture_output=True, text=True)
