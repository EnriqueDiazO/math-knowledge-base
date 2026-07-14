"""Command construction and owned-child lifecycle for the local runtime."""

# ruff: noqa: D102, D107

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Callable
from collections.abc import Mapping
from pathlib import Path
from typing import IO
from typing import Protocol

from mathmongo.local_runtime.health import loopback_url
from mathmongo.local_runtime.models import RuntimeSettings

DATABASE_ENV_VAR = "MONGODB_DB"
MAX_DIAGNOSTIC_LINES = 40
MAX_LOG_LINE_CHARS = 800

_MONGO_URI = re.compile(r"mongodb(?:\+srv)?://[^\s'\"<>]+", re.IGNORECASE)
_PRIVATE_UNIX_PATH = re.compile(
    r"(?:(?:/home|/root|/Users|/tmp|/var|/run/user|/opt|/usr|/mnt|/media|/srv|/data|"
    r"/workspace|/private|/app|/code)/"
    r"[^\s'\"<>:,;]+)"
)
_PRIVATE_WINDOWS_PATH = re.compile(r"[A-Za-z]:\\[^\s'\"<>]+", re.IGNORECASE)
_LOGICAL_BLOB_PATH = re.compile(
    r"(?i)(?:source_documents/)?blobs/sha256/[0-9a-f]{2}/[0-9a-f]{64}\.pdf"
)
_CREDENTIAL = re.compile(r"(?i)\b(password|passwd|credential|secret|token)(\s*[:=]\s*)[^\s,;]+")


class ProcessLike(Protocol):
    """The subprocess surface used by the supervisor and its unit-test fakes."""

    stdout: IO[str] | None
    pid: int

    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...


def _process_group_exists(process_group: int) -> bool:
    """Probe one private process group without signalling its members."""
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # A group created by this process should remain signalable. Fail closed
        # if the OS unexpectedly reports otherwise so cleanup still escalates.
        return True
    except OSError:
        return False
    return True


def build_advanced_reader_command(
    settings: RuntimeSettings,
    *,
    executable: str | None = None,
) -> list[str]:
    """Build the Reader child command without a shell or a MongoDB URI."""
    return [
        executable or sys.executable,
        "-m",
        "mathmongo.advanced_reader",
        "--host",
        settings.advanced_reader_host,
        "--port",
        str(settings.advanced_reader_port),
        "--database",
        settings.database,
        "--log-level",
        settings.log_level,
    ]


def build_streamlit_command(
    settings: RuntimeSettings,
    app_path: str | Path,
    *,
    executable: str | None = None,
) -> list[str]:
    """Build the Streamlit child command using the active Python interpreter."""
    return [
        executable or sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.address",
        settings.streamlit_host,
        "--server.port",
        str(settings.streamlit_port),
    ]


def build_child_environment(
    settings: RuntimeSettings,
    *,
    base_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return a per-run environment without changing the parent process."""
    environment = dict(os.environ if base_environment is None else base_environment)
    environment.update(
        {
            DATABASE_ENV_VAR: settings.database,
            "MATHMONGO_ADVANCED_READER_ENABLED": "1",
            "MATHMONGO_ADVANCED_READER_HOST": settings.advanced_reader_host,
            "MATHMONGO_ADVANCED_READER_PORT": str(settings.advanced_reader_port),
            "MATHMONGO_ADVANCED_READER_URL": loopback_url(
                settings.advanced_reader_host,
                settings.advanced_reader_port,
            ),
            "MATHMONGO_STREAMLIT_ADDRESS": settings.streamlit_host,
            "MATHMONGO_STREAMLIT_PORT": str(settings.streamlit_port),
            "PYTHONUNBUFFERED": "1",
        }
    )
    return environment


def sanitize_log_line(value: object) -> str:
    """Bound one child log line and redact credentials, URIs, and private paths."""
    line = str(value or "").replace("\x00", "").replace("\r", "").strip()
    line = "".join(char if char == "\t" or ord(char) >= 32 else " " for char in line)
    line = _MONGO_URI.sub("<MongoDB URI omitida>", line)
    line = _PRIVATE_UNIX_PATH.sub("<ruta local omitida>", line)
    line = _PRIVATE_WINDOWS_PATH.sub("<ruta local omitida>", line)
    line = _LOGICAL_BLOB_PATH.sub("<ruta de blob omitida>", line)
    line = _CREDENTIAL.sub(lambda match: f"{match.group(1)}=<omitido>", line)
    if len(line) > MAX_LOG_LINE_CHARS:
        line = f"{line[: MAX_LOG_LINE_CHARS - 1]}…"
    return line


class SafeLineBuffer:
    """Thread-safe bounded tail of already-sanitized diagnostic lines."""

    def __init__(self, maximum: int = MAX_DIAGNOSTIC_LINES) -> None:
        self._lines: deque[str] = deque(maxlen=maximum)
        self._lock = threading.Lock()

    def append(self, line: object) -> str:
        safe = sanitize_log_line(line)
        if safe:
            with self._lock:
                self._lines.append(safe)
        return safe

    def snapshot(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._lines)


class PrefixedLogPump:
    """Drain one merged child stream so a verbose process cannot deadlock."""

    def __init__(
        self,
        *,
        prefix: str,
        stream: IO[str] | None,
        tail: SafeLineBuffer,
        emit: Callable[[str], None],
    ) -> None:
        self._prefix = prefix
        self._stream = stream
        self._tail = tail
        self._emit = emit
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._stream is None:
            return
        self._thread = threading.Thread(
            target=self._run,
            name=f"mathmongo-{self._prefix}-logs",
            daemon=True,
        )
        self._thread.start()

    def _run(self) -> None:
        assert self._stream is not None
        try:
            while chunk := self._stream.readline(MAX_LOG_LINE_CHARS + 1):
                safe = self._tail.append(chunk)
                if safe:
                    self._emit(f"[{self._prefix}] {safe}")
        except (OSError, ValueError):
            return
        finally:
            self._close_stream()

    def _close_stream(self) -> None:
        if self._stream is not None:
            try:
                self._stream.close()
            except (OSError, ValueError):
                pass

    def finish(self, timeout: float = 1.0) -> None:
        if self._thread is None:
            self._close_stream()
            return
        # Joining before closing avoids contending with a blocking TextIO read.
        # The daemon owns and eventually closes its stream if a descendant still
        # has the pipe open, while supervisor shutdown itself stays bounded.
        self._thread.join(timeout=timeout)


class ManagedChild:
    """A process created by this supervisor and therefore safe for it to stop."""

    def __init__(
        self,
        *,
        name: str,
        process: ProcessLike,
        tail: SafeLineBuffer,
        pump: PrefixedLogPump,
        group_signaler: Callable[[int, int], None] | None,
        group_probe: Callable[[int], bool] | None,
        monotonic: Callable[[], float],
        sleep: Callable[[float], None],
    ) -> None:
        self.name = name
        self.process = process
        self.tail = tail
        self.pump = pump
        self._group_signaler = group_signaler
        self._group_probe = group_probe
        self._monotonic = monotonic
        self._sleep = sleep

    @classmethod
    def start(
        cls,
        *,
        name: str,
        prefix: str,
        command: list[str],
        environment: Mapping[str, str],
        emit: Callable[[str], None],
        popen_factory: Callable[..., ProcessLike] = subprocess.Popen,
        group_signaler: Callable[[int, int], None] | None = os.killpg,
        group_probe: Callable[[int], bool] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> ManagedChild:
        """Start one child with merged output and explicit ``shell=False``."""
        process = popen_factory(
            list(command),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=dict(environment),
            shell=False,
            start_new_session=True,
        )
        tail = SafeLineBuffer()
        pump = PrefixedLogPump(prefix=prefix, stream=process.stdout, tail=tail, emit=emit)
        child = cls(
            name=name,
            process=process,
            tail=tail,
            pump=pump,
            group_signaler=group_signaler,
            group_probe=group_probe or _process_group_exists,
            monotonic=monotonic,
            sleep=sleep,
        )
        pump.start()
        return child

    def poll(self) -> int | None:
        return self.process.poll()

    def diagnostics(self) -> tuple[str, ...]:
        return self.tail.snapshot()

    def finish_logs(self) -> None:
        """Close and join the log pump after the child has exited."""
        self.pump.finish()

    def _signal_owned_group(self, signum: int) -> bool:
        pid = getattr(self.process, "pid", None)
        if self._group_signaler is None or not isinstance(pid, int) or pid <= 0:
            return False
        try:
            self._group_signaler(pid, signum)
        except OSError:
            return False
        return True

    def _owned_group_exists(self) -> bool:
        pid = getattr(self.process, "pid", None)
        if self._group_probe is None or not isinstance(pid, int) or pid <= 0:
            return False
        try:
            return bool(self._group_probe(pid))
        except OSError:
            return False

    def _wait_for_owned_group(self, timeout: float) -> bool:
        deadline = self._monotonic() + max(0.0, timeout)
        while self._owned_group_exists():
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                return False
            self._sleep(min(0.05, remaining))
        return True

    def stop(self, *, timeout: float) -> int:
        """Terminate, bounded-wait, and reap only this owned process."""
        returncode = self.process.poll()
        group_signaled = False
        try:
            if returncode is None:
                group_signaled = self._signal_owned_group(signal.SIGTERM)
                if not group_signaled:
                    self.process.terminate()
                try:
                    returncode = self.process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    if not group_signaled or not self._signal_owned_group(signal.SIGKILL):
                        self.process.kill()
                    # SIGKILL has no graceful timeout left to honor. Reap the
                    # child unconditionally so it can never remain a zombie.
                    returncode = self.process.wait()
            else:
                # ``poll`` may already have reaped the session leader while one
                # of its descendants still belongs to our private process group.
                # Signal that owned group as well; ESRCH simply means it is gone.
                group_signaled = self._signal_owned_group(signal.SIGTERM)
                returncode = self.process.wait(timeout=0)
            if group_signaled and not self._wait_for_owned_group(timeout):
                self._signal_owned_group(signal.SIGKILL)
                self._wait_for_owned_group(timeout)
        finally:
            self.pump.finish()
        return int(returncode)


__all__ = [
    "DATABASE_ENV_VAR",
    "MAX_DIAGNOSTIC_LINES",
    "MAX_LOG_LINE_CHARS",
    "ManagedChild",
    "PrefixedLogPump",
    "ProcessLike",
    "SafeLineBuffer",
    "build_advanced_reader_command",
    "build_child_environment",
    "build_streamlit_command",
    "sanitize_log_line",
]
