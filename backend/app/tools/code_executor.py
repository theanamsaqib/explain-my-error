"""execute_python tool: run Python code in an isolated process and report what happened.

SECURITY NOTE: this is a development / college-project sandbox, NOT a production-grade one.
The default "subprocess" backend gives you: a separate process, a stripped environment (no API
keys), a wall-clock timeout, CPU / memory / file-size limits (POSIX only), a capped output size,
stdin closed, stdlib-only imports, and a best-effort block on network calls from Python.
It cannot stop determined malicious code (for example it can still read files the backend user
can read). Use EXECUTION_BACKEND=docker for real isolation (--network none, memory/pids limits,
read-only filesystem).
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Protocol

from app.config import Settings
from app.models.schemas import ExecutionResult

log = logging.getLogger("explain_my_error")

# Runs inside the child process. Applies resource limits, optionally blocks sockets, then
# executes main.py. Frames of this wrapper are removed from tracebacks so the error text
# looks exactly like a normal `python main.py` run.
_RUNNER = r'''
import sys


def _apply_limits(cpu, mem, fsize):
    try:
        import resource
    except ImportError:  # Windows
        return
    for name, value in (
        ("RLIMIT_CPU", cpu),
        ("RLIMIT_AS", mem),
        ("RLIMIT_FSIZE", fsize),
        ("RLIMIT_NOFILE", 64),
        ("RLIMIT_CORE", 0),
    ):
        try:
            resource.setrlimit(getattr(resource, name), (value, value))
        except (ValueError, OSError, AttributeError):
            pass


def _block_network():
    import socket

    def blocked(*args, **kwargs):
        raise OSError("Network access is disabled in this sandbox")

    for attr in ("connect", "connect_ex", "sendto"):
        setattr(socket.socket, attr, blocked)
    for attr in ("getaddrinfo", "gethostbyname", "create_connection"):
        setattr(socket, attr, blocked)


cpu_s, mem_bytes, fsize_bytes, block_net = (int(a) for a in sys.argv[1:5])
_apply_limits(cpu_s, mem_bytes, fsize_bytes)
if block_net:
    _block_network()

import traceback

with open("main.py", encoding="utf-8") as fh:
    source = fh.read()

sys.argv = ["main.py"]
namespace = {"__name__": "__main__", "__file__": "main.py"}
try:
    exec(compile(source, "main.py", "exec"), namespace)
except SystemExit:
    raise
except BaseException as exc:
    tb = exc.__traceback__
    while tb is not None and tb.tb_frame.f_code.co_filename == __file__:
        tb = tb.tb_next  # drop this wrapper's own frames
    sys.stdout.flush()
    traceback.print_exception(type(exc), exc, tb)
    sys.stderr.flush()
    sys.exit(1)
'''


class Executor(Protocol):
    async def run(self, code: str) -> ExecutionResult: ...


def _read_capped(path: Path, limit: int) -> tuple[str, bool]:
    size = path.stat().st_size if path.exists() else 0
    if size == 0:
        return "", False
    with open(path, "rb") as fh:
        data = fh.read(limit)
    text = data.decode("utf-8", errors="replace")
    truncated = size > limit
    if truncated:
        text += f"\n... [output truncated at {limit} bytes]"
    return text, truncated


class _BaseExecutor:
    """Shared process handling: temp dir, output files, timeout and output-size watchdog."""

    def __init__(self, settings: Settings) -> None:
        self.timeout = settings.execution_timeout
        self.max_output = settings.max_output_size
        self.memory_mb = settings.execution_memory_mb
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_executions)

    async def run(self, code: str) -> ExecutionResult:
        async with self._semaphore:
            return await asyncio.to_thread(self._run_blocking, code)

    # -- hooks ------------------------------------------------------------------------
    def _command(self, workdir: Path, container_name: str) -> list[str]:
        raise NotImplementedError

    def _env(self, workdir: Path) -> dict[str, str]:
        raise NotImplementedError

    def _kill(self, proc: subprocess.Popen, container_name: str) -> None:
        raise NotImplementedError

    def _wall_limit(self) -> float:
        return self.timeout

    def _infrastructure_failure(self, exit_code: int | None, stderr: str) -> str:
        """Return a message if the sandbox itself (not the user's code) failed. '' otherwise."""
        return ""

    # -- implementation ---------------------------------------------------------------
    def _run_blocking(self, code: str) -> ExecutionResult:
        workdir = Path(tempfile.mkdtemp(prefix="eme_run_"))
        container_name = f"eme-{uuid.uuid4().hex[:12]}"
        started = time.monotonic()
        try:
            (workdir / "main.py").write_text(code, encoding="utf-8")
            (workdir / "runner.py").write_text(_RUNNER, encoding="utf-8")
            out_path, err_path = workdir / "stdout.txt", workdir / "stderr.txt"

            timed_out = False
            output_flood = False
            try:
                with open(out_path, "wb") as out_f, open(err_path, "wb") as err_f:
                    proc = subprocess.Popen(
                        self._command(workdir, container_name),
                        cwd=workdir,
                        env=self._env(workdir),
                        stdin=subprocess.DEVNULL,
                        stdout=out_f,
                        stderr=err_f,
                        **_popen_isolation_kwargs(),
                    )
                    deadline = started + self._wall_limit()
                    while True:
                        try:
                            proc.wait(timeout=0.05)
                            break
                        except subprocess.TimeoutExpired:
                            pass
                        if time.monotonic() > deadline:
                            timed_out = True
                            self._kill(proc, container_name)
                            break
                        if (
                            out_path.stat().st_size > self.max_output * 4
                            or err_path.stat().st_size > self.max_output * 4
                        ):
                            output_flood = True
                            self._kill(proc, container_name)
                            break
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
            except (OSError, ValueError) as exc:
                return ExecutionResult(
                    success=False,
                    stderr=f"Sandbox could not start: {exc}",
                    exit_code=None,
                    note="The code could not be executed because the sandbox failed to start.",
                )

            flood_size = self.max_output * 4
            if not timed_out and (
                out_path.stat().st_size >= flood_size or err_path.stat().st_size >= flood_size
            ):
                output_flood = True  # the file-size rlimit stopped it before our watchdog did
            stdout, out_trunc = _read_capped(out_path, self.max_output)
            stderr, err_trunc = _read_capped(err_path, self.max_output)
            if output_flood and "File too large" in stderr:
                stderr = ""  # junk produced by the wrapper once its own stdout was cut off
            truncated = out_trunc or err_trunc or output_flood
            exit_code = proc.returncode
            success = exit_code == 0 and not timed_out and not output_flood

            note = ""
            if timed_out:
                note = (
                    f"Execution timed out after {self.timeout:g}s "
                    "(possible infinite loop or very slow code)."
                )
            elif output_flood:
                note = "Execution was stopped because it produced far too much output."
            elif success and not stdout.strip() and not stderr.strip():
                note = "Program finished successfully but printed nothing."

            # The sandbox itself failed to start (e.g. Docker image missing). That is OUR problem,
            # not a bug in the user's code, so never hand the infrastructure error to the agent.
            infra = self._infrastructure_failure(exit_code, stderr)
            if infra:
                return ExecutionResult(
                    success=False, stdout="", stderr="", exit_code=exit_code,
                    duration_ms=int((time.monotonic() - started) * 1000), note=infra,
                )

            return ExecutionResult(
                success=success,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                timed_out=timed_out,
                output_truncated=truncated,
                duration_ms=int((time.monotonic() - started) * 1000),
                note=note,
            )
        finally:
            shutil.rmtree(workdir, ignore_errors=True)


def _popen_isolation_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


class SubprocessExecutor(_BaseExecutor):
    """Runs code with the current Python interpreter in a restricted child process."""

    def _command(self, workdir: Path, container_name: str) -> list[str]:
        cpu = int(self.timeout) + 2
        mem = self.memory_mb * 1024 * 1024
        fsize = self.max_output * 4 + 1024
        # -I isolated mode, -S no site-packages (stdlib only), -B no .pyc files
        return [sys.executable, "-I", "-S", "-B", "runner.py", str(cpu), str(mem), str(fsize), "1"]

    def _env(self, workdir: Path) -> dict[str, str]:
        # Deliberately NOT inheriting os.environ: no API keys or other secrets reach the child.
        env = {
            "PATH": "/usr/bin:/bin" if os.name != "nt" else os.environ.get("PATH", ""),
            "HOME": str(workdir),
            "TMPDIR": str(workdir),
            "LANG": "C.UTF-8",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        if os.name == "nt":
            for key in ("SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP"):
                if key in os.environ:
                    env[key] = os.environ[key]
        return env

    def _kill(self, proc: subprocess.Popen, container_name: str) -> None:
        try:
            if os.name == "nt":
                proc.kill()
            else:
                import signal

                os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass


class DockerExecutor(_BaseExecutor):
    """Runs code in a throw-away container with no network, limited memory and a read-only FS."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.image = settings.docker_image

    def _wall_limit(self) -> float:
        return self.timeout + 3.0  # container start-up overhead

    def _command(self, workdir: Path, container_name: str) -> list[str]:
        mem = f"{self.memory_mb}m"
        return [
            "docker", "run", "--rm", "--name", container_name,
            "--network", "none",
            "--memory", mem, "--memory-swap", mem,
            "--cpus", "1", "--pids-limit", "64",
            "--read-only", "--tmpfs", "/tmp:rw,size=16m",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "-v", f"{workdir}:/work:ro", "-w", "/work",
            "-e", "PYTHONDONTWRITEBYTECODE=1",
            self.image,
            "python", "-I", "-B", "runner.py",
            str(int(self.timeout) + 2), str(self.memory_mb * 1024 * 1024),
            str(self.max_output * 4 + 1024), "0",
        ]

    def _env(self, workdir: Path) -> dict[str, str]:
        env = {"PATH": os.environ.get("PATH", "")}
        for key in ("DOCKER_HOST", "DOCKER_CONTEXT", "HOME", "USERPROFILE", "SYSTEMROOT"):
            if key in os.environ:
                env[key] = os.environ[key]
        return env

    def _infrastructure_failure(self, exit_code: int | None, stderr: str) -> str:
        # 125 = the docker CLI itself failed (image missing, daemon gone, bad flag).
        low = stderr.lower()
        docker_said = any(
            s in low
            for s in ("unable to find image", "failed to resolve reference", "pull access denied",
                      "cannot connect to the docker daemon", "error response from daemon")
        )
        if exit_code == 125 or (docker_said and not exit_code == 0):
            return (
                f"The Docker sandbox could not start (image '{self.image}' may be missing or the "
                "daemon is unreachable). Pull the image, or set EXECUTION_BACKEND=subprocess."
            )
        return ""

    def _kill(self, proc: subprocess.Popen, container_name: str) -> None:
        try:
            subprocess.run(
                ["docker", "kill", container_name],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            pass
        try:
            proc.kill()
        except OSError:
            pass


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(
            ["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def docker_image_present(image: str) -> bool:
    try:
        return subprocess.run(
            ["docker", "image", "inspect", image],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def build_executor(settings: Settings) -> Executor:
    """Pick the sandbox. Docker is used only if it genuinely works; otherwise we say why."""
    if settings.execution_backend == "docker":
        if not docker_available():
            log.warning("EXECUTION_BACKEND=docker but the Docker daemon is unreachable; using the subprocess sandbox.")
        elif not docker_image_present(settings.docker_image):
            log.warning(
                "EXECUTION_BACKEND=docker but image '%s' is not available locally "
                "(run: docker pull %s); using the subprocess sandbox.",
                settings.docker_image, settings.docker_image,
            )
        else:
            return DockerExecutor(settings)
    return SubprocessExecutor(settings)


def compare_output(actual: str, expected: str | None) -> bool | None:
    """True/False if an expected output was given, otherwise None."""
    if expected is None or not expected.strip():
        return None
    norm = lambda s: "\n".join(line.rstrip() for line in s.strip().splitlines())
    return norm(actual) == norm(expected)
