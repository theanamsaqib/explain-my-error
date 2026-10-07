"""DockerExecutor: command construction, backend selection and infrastructure-failure detection.

These are unit tests. They do not start a container: the sandboxed CI/dev environment this was
built in has no access to a container registry. The subprocess sandbox (the default) IS covered
end-to-end in test_executor.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.tools.code_executor import DockerExecutor, SubprocessExecutor, build_executor


@pytest.fixture
def docker_settings(settings: Settings) -> Settings:
    return Settings(**{**settings.__dict__, "execution_backend": "docker", "execution_timeout": 4.0})


def test_docker_command_is_locked_down(docker_settings):
    ex = DockerExecutor(docker_settings)
    cmd = " ".join(ex._command(Path("/tmp/work"), "eme-test"))

    assert "--network none" in cmd  # no internet from executed code
    assert "--read-only" in cmd
    assert "--cap-drop ALL" in cmd
    assert "--security-opt no-new-privileges" in cmd
    assert "--pids-limit 64" in cmd
    assert "--memory 512m" in cmd and "--memory-swap 512m" in cmd
    assert "--rm" in cmd and "--name eme-test" in cmd
    assert "-v /tmp/work:/work:ro" in cmd  # the work dir is mounted read-only
    assert cmd.endswith("runner.py 6 536870912 41024 0")  # cpu, mem, fsize, block_net=0 (no net anyway)
    assert docker_settings.docker_image in cmd


def test_docker_env_does_not_leak_secrets(docker_settings, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    env = DockerExecutor(docker_settings)._env(Path("/tmp/work"))
    assert "OPENAI_API_KEY" not in env


def test_docker_wall_limit_allows_for_container_startup(docker_settings):
    ex = DockerExecutor(docker_settings)
    assert ex._wall_limit() > ex.timeout


@pytest.mark.parametrize(
    "exit_code,stderr",
    [
        (125, 'Unable to find image "python:3.12-slim" locally'),
        (125, 'failed to resolve reference "docker.io/library/python:3.12-slim"'),
        (1, "Cannot connect to the Docker daemon at unix:///var/run/docker.sock"),
    ],
)
def test_docker_infrastructure_failures_are_recognised(docker_settings, exit_code, stderr):
    msg = DockerExecutor(docker_settings)._infrastructure_failure(exit_code, stderr)
    assert "Docker sandbox could not start" in msg
    assert "EXECUTION_BACKEND=subprocess" in msg  # tells the user how to carry on


def test_real_python_errors_are_not_mistaken_for_infrastructure_failures(docker_settings):
    ex = DockerExecutor(docker_settings)
    assert ex._infrastructure_failure(1, "IndexError: list index out of range") == ""
    assert ex._infrastructure_failure(0, "") == ""


def test_subprocess_executor_never_reports_infrastructure_failures(settings):
    assert SubprocessExecutor(settings)._infrastructure_failure(125, "anything") == ""


def test_backend_selection_falls_back_when_docker_cannot_be_used(docker_settings, monkeypatch, caplog):
    import app.tools.code_executor as mod

    monkeypatch.setattr(mod, "docker_available", lambda: False)
    assert isinstance(build_executor(docker_settings), SubprocessExecutor)

    monkeypatch.setattr(mod, "docker_available", lambda: True)
    monkeypatch.setattr(mod, "docker_image_present", lambda image: False)
    with caplog.at_level("WARNING"):
        assert isinstance(build_executor(docker_settings), SubprocessExecutor)
    assert "docker pull" in caplog.text  # the log says exactly how to fix it

    monkeypatch.setattr(mod, "docker_image_present", lambda image: True)
    assert isinstance(build_executor(docker_settings), DockerExecutor)


def test_default_backend_is_subprocess(settings):
    assert isinstance(build_executor(settings), SubprocessExecutor)
