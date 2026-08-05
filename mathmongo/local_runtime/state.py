"""Private, verifiable ownership state for one local MathMongo runtime.

The state file is deliberately not a PID file.  Every PID is paired with the
kernel start tick, command line, working directory, and the canonical checkout
path so a recycled PID can never be treated as an owned service.
"""

# ruff: noqa: D102, D107

from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from enum import Enum
from pathlib import Path
from typing import Any

from mathmongo.local_runtime.health import probe_advanced_reader
from mathmongo.local_runtime.health import probe_streamlit
from mathmongo.local_runtime.models import RuntimeSettings
from mathmongo.paths import get_runtime_dir
from mathmongo.paths import validate_mutable_path

RUNTIME_STATE_VERSION = 1
RUNTIME_STATE_FILENAME = "local-runtime-v1.json"


class RuntimeStateKind(str, Enum):
    """Safe classification of the local ports and ownership metadata."""

    STOPPED = "stopped"
    OWNED = "owned"
    STALE = "stale"
    FOREIGN = "foreign"
    ORPHAN = "orphan"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class ProcessIdentity:
    """A process identity which remains invalid if its PID is recycled."""

    pid: int
    start_ticks: int
    command: tuple[str, ...]
    cwd: str

    def as_dict(self) -> dict[str, object]:
        return {
            "pid": self.pid,
            "start_ticks": self.start_ticks,
            "command": list(self.command),
            "cwd": self.cwd,
        }


@dataclass(frozen=True)
class RuntimeObservation:
    """Read-only state used by status, start, stop, and restart."""

    kind: RuntimeStateKind
    message: str
    record: dict[str, Any] | None = None
    streamlit: ProcessIdentity | None = None
    advanced_reader: ProcessIdentity | None = None
    supervisor: ProcessIdentity | None = None


def repository_root() -> Path:
    """Return the canonical repository/package root without creating files."""
    return Path(__file__).resolve().parents[2]


def _process_start_ticks(pid: int) -> int | None:
    try:
        value = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        # The second field may contain spaces inside parentheses.  Start time is
        # field 22, i.e. index 19 after the final closing parenthesis.
        fields = value.rsplit(") ", maxsplit=1)[1].split()
        start_ticks = int(fields[19])
    except (IndexError, ValueError):
        return None
    return start_ticks if start_ticks > 0 else None


def inspect_process(pid: int) -> ProcessIdentity | None:
    """Inspect a current-user process without exposing its environment."""
    if not isinstance(pid, int) or pid <= 0:
        return None
    process_dir = Path(f"/proc/{pid}")
    try:
        if process_dir.stat().st_uid != os.getuid():
            return None
        command = tuple(
            part.decode("utf-8", errors="replace")
            for part in (process_dir / "cmdline").read_bytes().split(b"\0")
            if part
        )
        cwd = os.readlink(process_dir / "cwd")
    except OSError:
        return None
    start_ticks = _process_start_ticks(pid)
    if not command or start_ticks is None or not Path(cwd).is_absolute():
        return None
    return ProcessIdentity(pid=pid, start_ticks=start_ticks, command=command, cwd=cwd)


def _listening_socket_inodes(port: int) -> set[str]:
    inodes: set[str] = set()
    port_hex = f"{port:04X}"
    for path in (Path("/proc/net/tcp"), Path("/proc/net/tcp6")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) < 10 or fields[3] != "0A":
                continue
            local_address = fields[1]
            if local_address.rsplit(":", maxsplit=1)[-1].upper() == port_hex:
                inodes.add(fields[9])
    return inodes


def listening_pids(port: int) -> tuple[int, ...]:
    """Return current-user listeners for a TCP port using Linux procfs only."""
    inodes = _listening_socket_inodes(port)
    if not inodes:
        return ()
    pids: list[int] = []
    for candidate in Path("/proc").iterdir():
        if not candidate.name.isdigit():
            continue
        try:
            if candidate.stat().st_uid != os.getuid():
                continue
            for descriptor in (candidate / "fd").iterdir():
                try:
                    target = os.readlink(descriptor)
                except OSError:
                    continue
                if target.startswith("socket:[") and target[8:-1] in inodes:
                    pids.append(int(candidate.name))
                    break
        except OSError:
            continue
    return tuple(sorted(set(pids)))


def _argument_value(command: tuple[str, ...], option: str) -> str | None:
    try:
        return command[command.index(option) + 1]
    except (IndexError, ValueError):
        return None


def _command_has(command: tuple[str, ...], *expected: str) -> bool:
    return all(value in command for value in expected)


def _cwd_matches(identity: ProcessIdentity, repository: Path) -> bool:
    try:
        return Path(identity.cwd).resolve() == repository
    except OSError:
        return False


def _matches_streamlit(
    identity: ProcessIdentity,
    settings: RuntimeSettings,
    repository: Path,
) -> bool:
    app_path = str((repository / "editor" / "editor_streamlit.py").resolve())
    return (
        _cwd_matches(identity, repository)
        and _command_has(identity.command, "-m", "streamlit", "run", app_path)
        and _argument_value(identity.command, "--server.port") == str(settings.streamlit_port)
        and _argument_value(identity.command, "--server.address") == settings.streamlit_host
    )


def _matches_reader(
    identity: ProcessIdentity,
    settings: RuntimeSettings,
    repository: Path,
) -> bool:
    return (
        _cwd_matches(identity, repository)
        and _command_has(identity.command, "-m", "mathmongo.advanced_reader")
        and _argument_value(identity.command, "--port") == str(settings.advanced_reader_port)
        and _argument_value(identity.command, "--host") == settings.advanced_reader_host
        and _argument_value(identity.command, "--database") == settings.database
    )


def _matches_supervisor(
    identity: ProcessIdentity,
    repository: Path,
) -> bool:
    return _cwd_matches(identity, repository) and _command_has(
        identity.command,
        "-m",
        "mathmongo.local_runtime",
    )


def _same_identity(identity: ProcessIdentity | None, raw: object) -> bool:
    if identity is None or not isinstance(raw, dict):
        return False
    command = raw.get("command")
    return (
        raw.get("pid") == identity.pid
        and raw.get("start_ticks") == identity.start_ticks
        and isinstance(command, list)
        and tuple(command) == identity.command
        and raw.get("cwd") == identity.cwd
    )


class RuntimeStateStore:
    """Read and write the private state file without trusting it blindly."""

    def __init__(self, environment: Mapping[str, str] | None = None) -> None:
        self.environment = dict(os.environ if environment is None else environment)
        self.directory = get_runtime_dir(self.environment)
        self.path = self.directory / RUNTIME_STATE_FILENAME

    def _safe_path(self) -> Path:
        return validate_mutable_path(self.path, allowed_root=self.directory)

    def load(self) -> dict[str, Any] | None:
        """Return a bounded valid JSON mapping, without creating XDG paths."""
        try:
            metadata = self.path.lstat()
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) & 0o077
                or metadata.st_size > 32_768
            ):
                return None
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def write(self, record: Mapping[str, object]) -> None:
        """Atomically write private metadata only after services are healthy."""
        directory = validate_mutable_path(self.directory)
        path = self._safe_path()
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)
        temporary = directory / f".{RUNTIME_STATE_FILENAME}.{os.getpid()}.{secrets.token_hex(8)}"
        temporary = validate_mutable_path(temporary, allowed_root=directory)
        payload = json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            path.chmod(0o600)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def clear(self, *, runtime_id: str | None = None) -> bool:
        """Remove only our regular state file, optionally for one runtime id."""
        record = self.load()
        if record is None or (runtime_id is not None and record.get("runtime_id") != runtime_id):
            return False
        try:
            self._safe_path().unlink(missing_ok=True)
            return True
        except OSError:
            return False


def build_runtime_record(
    *,
    settings: RuntimeSettings,
    supervisor: ProcessIdentity,
    streamlit: ProcessIdentity,
    advanced_reader: ProcessIdentity,
    repository: Path | None = None,
) -> dict[str, object]:
    """Build versioned metadata with a random non-secret runtime identifier."""
    root = (repository or repository_root()).resolve()
    runtime_id = secrets.token_urlsafe(18)
    fingerprint_input = {
        "repository": str(root),
        "supervisor": supervisor.as_dict(),
        "streamlit": streamlit.as_dict(),
        "advanced_reader": advanced_reader.as_dict(),
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_input, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "format_version": RUNTIME_STATE_VERSION,
        "runtime_id": runtime_id,
        "fingerprint": fingerprint,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "repository": str(root),
        "database": settings.database,
        "streamlit": {
            **streamlit.as_dict(),
            "host": settings.streamlit_host,
            "port": settings.streamlit_port,
        },
        "advanced_reader": {
            **advanced_reader.as_dict(),
            "host": settings.advanced_reader_host,
            "port": settings.advanced_reader_port,
        },
        "supervisor": supervisor.as_dict(),
    }


def observe_runtime(
    settings: RuntimeSettings,
    *,
    store: RuntimeStateStore | None = None,
    repository: Path | None = None,
) -> RuntimeObservation:
    """Classify the current ports without writing or trusting stale metadata."""
    root = (repository or repository_root()).resolve()
    runtime_store = store or RuntimeStateStore()
    streamlit_pids = listening_pids(settings.streamlit_port)
    reader_pids = listening_pids(settings.advanced_reader_port)
    streamlit = inspect_process(streamlit_pids[0]) if len(streamlit_pids) == 1 else None
    reader = inspect_process(reader_pids[0]) if len(reader_pids) == 1 else None
    record = runtime_store.load()

    if len(streamlit_pids) > 1 or len(reader_pids) > 1:
        return RuntimeObservation(
            RuntimeStateKind.AMBIGUOUS,
            "Hay más de un listener en uno de los puertos del runtime.",
            record=record,
        )

    if record is not None:
        supervisor_raw = record.get("supervisor")
        supervisor_pid = supervisor_raw.get("pid") if isinstance(supervisor_raw, dict) else None
        supervisor = inspect_process(supervisor_pid) if isinstance(supervisor_pid, int) else None
        valid_record = (
            record.get("format_version") == RUNTIME_STATE_VERSION
            and record.get("repository") == str(root)
            and record.get("database") == settings.database
            and isinstance(record.get("runtime_id"), str)
            and _same_identity(supervisor, supervisor_raw)
            and _same_identity(streamlit, record.get("streamlit"))
            and _same_identity(reader, record.get("advanced_reader"))
            and supervisor is not None
            and streamlit is not None
            and reader is not None
            and _matches_supervisor(supervisor, root)
            and _matches_streamlit(streamlit, settings, root)
            and _matches_reader(reader, settings, root)
            and probe_streamlit(
                settings.streamlit_host,
                settings.streamlit_port,
                timeout=settings.request_timeout,
            )
            and (health := probe_advanced_reader(
                settings.advanced_reader_host,
                settings.advanced_reader_port,
                timeout=settings.request_timeout,
            )) is not None
            and health.ready
            and health.database == settings.database
        )
        if valid_record:
            return RuntimeObservation(
                RuntimeStateKind.OWNED,
                "Runtime MathMongo confirmado mediante metadata y /proc.",
                record=record,
                streamlit=streamlit,
                advanced_reader=reader,
                supervisor=supervisor,
            )
        return RuntimeObservation(
            RuntimeStateKind.STALE,
            "La metadata de MathMongo no coincide con procesos saludables actuales.",
            record=record,
            streamlit=streamlit,
            advanced_reader=reader,
            supervisor=supervisor,
        )

    if not streamlit_pids and not reader_pids:
        return RuntimeObservation(RuntimeStateKind.STOPPED, "No hay runtime local escuchando.")

    if (
        streamlit is not None
        and reader is not None
        and _matches_streamlit(streamlit, settings, root)
        and _matches_reader(reader, settings, root)
        and probe_streamlit(settings.streamlit_host, settings.streamlit_port, timeout=settings.request_timeout)
        and (health := probe_advanced_reader(
            settings.advanced_reader_host,
            settings.advanced_reader_port,
            timeout=settings.request_timeout,
        )) is not None
        and health.ready
        and health.database == settings.database
    ):
        return RuntimeObservation(
            RuntimeStateKind.ORPHAN,
            "Se encontró un runtime huérfano con firmas canónicas de este repositorio.",
            streamlit=streamlit,
            advanced_reader=reader,
        )

    return RuntimeObservation(
        RuntimeStateKind.FOREIGN,
        "Un proceso no confirmado ocupa uno de los puertos del runtime.",
        streamlit=streamlit,
        advanced_reader=reader,
    )


__all__ = [
    "RUNTIME_STATE_FILENAME",
    "RUNTIME_STATE_VERSION",
    "ProcessIdentity",
    "RuntimeObservation",
    "RuntimeStateKind",
    "RuntimeStateStore",
    "build_runtime_record",
    "inspect_process",
    "listening_pids",
    "observe_runtime",
    "repository_root",
]
