"""Foreground supervisor for Streamlit and the Advanced Reader."""

# ruff: noqa: D102, D107

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from collections.abc import Mapping
from collections.abc import Sequence
from contextlib import contextmanager
from pathlib import Path
from types import FrameType
from typing import Any

from mathmongo.launcher import port_available
from mathmongo.launcher import resolve_streamlit_app
from mathmongo.local_runtime.health import loopback_url
from mathmongo.local_runtime.health import probe_advanced_reader
from mathmongo.local_runtime.health import probe_streamlit
from mathmongo.local_runtime.models import DEFAULT_ADVANCED_READER_HOST
from mathmongo.local_runtime.models import DEFAULT_ADVANCED_READER_PORT
from mathmongo.local_runtime.models import DEFAULT_DATABASE
from mathmongo.local_runtime.models import DEFAULT_LOG_LEVEL
from mathmongo.local_runtime.models import DEFAULT_STREAMLIT_HOST
from mathmongo.local_runtime.models import DEFAULT_STREAMLIT_PORT
from mathmongo.local_runtime.models import LOG_LEVELS
from mathmongo.local_runtime.models import AdvancedReaderHealth
from mathmongo.local_runtime.models import LocalRuntimeError
from mathmongo.local_runtime.models import RuntimeSettings
from mathmongo.local_runtime.models import ServiceDisposition
from mathmongo.local_runtime.processes import ManagedChild
from mathmongo.local_runtime.processes import ProcessLike
from mathmongo.local_runtime.processes import build_advanced_reader_command
from mathmongo.local_runtime.processes import build_child_environment
from mathmongo.local_runtime.processes import build_streamlit_command

PortCheck = Callable[[str, int], bool]
ReaderProbe = Callable[..., AdvancedReaderHealth | None]
StreamlitProbe = Callable[..., bool]
PopenFactory = Callable[..., ProcessLike]


class _ShutdownRequestedError(Exception):
    pass


def build_parser() -> argparse.ArgumentParser:
    """Create the public ``python -m mathmongo.local_runtime`` parser."""
    parser = argparse.ArgumentParser(
        prog="python -m mathmongo.local_runtime",
        description="Inicia y supervisa los servicios locales de MathMongo.",
    )
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    parser.add_argument("--streamlit-host", default=DEFAULT_STREAMLIT_HOST)
    parser.add_argument("--streamlit-port", type=int, default=DEFAULT_STREAMLIT_PORT)
    parser.add_argument("--advanced-reader-host", default=DEFAULT_ADVANCED_READER_HOST)
    parser.add_argument("--advanced-reader-port", type=int, default=DEFAULT_ADVANCED_READER_PORT)
    parser.add_argument("--log-level", choices=sorted(LOG_LEVELS), default=DEFAULT_LOG_LEVEL)
    return parser


def settings_from_args(argv: Sequence[str] | None = None) -> RuntimeSettings:
    """Parse and validate one invocation without reading or writing user configuration."""
    args = build_parser().parse_args(argv)
    return RuntimeSettings(
        database=args.database,
        streamlit_host=args.streamlit_host,
        streamlit_port=args.streamlit_port,
        advanced_reader_host=args.advanced_reader_host,
        advanced_reader_port=args.advanced_reader_port,
        log_level=args.log_level,
    )


class LocalRuntimeSupervisor:
    """Own, monitor, and reap only the service processes created by this run."""

    def __init__(
        self,
        settings: RuntimeSettings,
        *,
        base_environment: Mapping[str, str] | None = None,
        executable: str | None = None,
        port_check: PortCheck = port_available,
        reader_probe: ReaderProbe = probe_advanced_reader,
        streamlit_probe: StreamlitProbe = probe_streamlit,
        app_resolver: Callable[[], Path] = resolve_streamlit_app,
        popen_factory: PopenFactory = subprocess.Popen,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        emit: Callable[[str], None] | None = None,
    ) -> None:
        self.settings = settings
        self._base_environment = dict(os.environ if base_environment is None else base_environment)
        self._executable = executable or sys.executable
        self._port_check = port_check
        self._reader_probe = reader_probe
        self._streamlit_probe = streamlit_probe
        self._app_resolver = app_resolver
        self._popen_factory = popen_factory
        self._monotonic = monotonic
        self._sleep = sleep
        self._output = emit or (lambda line: print(line, flush=True))
        self._output_lock = threading.Lock()
        self._shutdown_signal: int | None = None
        self._owned_children: list[ManagedChild] = []
        self._reader_disposition = ServiceDisposition.UNAVAILABLE
        self._streamlit_disposition = ServiceDisposition.UNAVAILABLE

    @property
    def reader_disposition(self) -> ServiceDisposition:
        return self._reader_disposition

    @property
    def streamlit_disposition(self) -> ServiceDisposition:
        return self._streamlit_disposition

    def _emit(self, line: str) -> None:
        with self._output_lock:
            self._output(line)

    def request_shutdown(self, signum: int = signal.SIGINT) -> None:
        """Request cooperative shutdown; actual process work stays outside signal handlers."""
        if self._shutdown_signal is None:
            self._shutdown_signal = int(signum)

    def _raise_if_shutdown(self) -> None:
        if self._shutdown_signal is not None:
            raise _ShutdownRequestedError

    def _reader_health(self) -> AdvancedReaderHealth | None:
        return self._reader_probe(
            self.settings.advanced_reader_host,
            self.settings.advanced_reader_port,
            timeout=self.settings.request_timeout,
        )

    def _streamlit_health(self) -> bool:
        return bool(
            self._streamlit_probe(
                self.settings.streamlit_host,
                self.settings.streamlit_port,
                timeout=self.settings.request_timeout,
            )
        )

    def _inspect_reader(self) -> bool:
        if self._port_check(
            self.settings.advanced_reader_host,
            self.settings.advanced_reader_port,
        ):
            return False
        health = self._reader_health()
        if health is None or health.status != "ok" or health.service != "mathmongo-advanced-reader":
            raise LocalRuntimeError(
                f"El puerto {self.settings.advanced_reader_port} está ocupado por otro proceso."
            )
        if health.database != self.settings.database:
            raise LocalRuntimeError(
                "El Advanced Reader activo usa la base "
                f"'{health.database}', pero MathMongo solicita '{self.settings.database}'. "
                "Detén el lector anterior o inicia ambos con la misma base.\n"
                f"ss -ltnp | grep ':{self.settings.advanced_reader_port}'"
            )
        if not health.frontend_ready:
            raise LocalRuntimeError(
                "El Advanced Reader activo coincide con la base solicitada, "
                "pero su frontend no está listo."
            )
        self._reader_disposition = ServiceDisposition.REUSED
        return True

    def _inspect_streamlit(self) -> None:
        if self._port_check(self.settings.streamlit_host, self.settings.streamlit_port):
            return
        is_streamlit = self._streamlit_health()
        detail = (
            "ya responde como Streamlit, pero esta ejecución no puede confirmar su identidad"
            if is_streamlit
            else "está ocupado por otro proceso"
        )
        alternative = (
            str(self.settings.streamlit_port + 1)
            if self.settings.streamlit_port < 65535
            else "<puerto-libre>"
        )
        raise LocalRuntimeError(
            f"El puerto {self.settings.streamlit_port} {detail}. "
            "No se detuvo el proceso existente. Usa, por ejemplo: "
            f"make run STREAMLIT_PORT={alternative}"
        )

    def _resolve_streamlit_app(self) -> Path:
        try:
            app_path = self._app_resolver()
        except Exception as exc:
            raise LocalRuntimeError(
                "No se pudo localizar la aplicación Streamlit instalada."
            ) from exc
        if not isinstance(app_path, Path):
            app_path = Path(app_path)
        if app_path.name != "editor_streamlit.py":
            raise LocalRuntimeError("La entrada Streamlit instalada no es válida.")
        return app_path

    def _start_child(
        self,
        *,
        name: str,
        prefix: str,
        command: list[str],
        environment: Mapping[str, str],
    ) -> ManagedChild:
        try:
            child = ManagedChild.start(
                name=name,
                prefix=prefix,
                command=command,
                environment=environment,
                emit=self._emit,
                popen_factory=self._popen_factory,
            )
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            raise LocalRuntimeError(f"No se pudo iniciar {name}.") from exc
        self._owned_children.append(child)
        return child

    def _report_diagnostics(self, child: ManagedChild) -> None:
        if child.poll() is not None:
            child.finish_logs()
        for line in child.diagnostics()[-8:]:
            self._emit(f"[{child.name}] diagnóstico: {line}")

    def _wait_for_reader(self, child: ManagedChild) -> None:
        deadline = self._monotonic() + self.settings.startup_timeout
        while self._monotonic() < deadline:
            self._raise_if_shutdown()
            returncode = child.poll()
            if returncode is not None:
                self._report_diagnostics(child)
                raise LocalRuntimeError("Advanced Reader terminó antes de estar listo.")
            health = self._reader_health()
            if health is not None:
                if (
                    health.status != "ok"
                    or health.service != "mathmongo-advanced-reader"
                    or health.database != self.settings.database
                ):
                    self._report_diagnostics(child)
                    raise LocalRuntimeError(
                        "Advanced Reader respondió con una identidad local inesperada."
                    )
                if health.frontend_ready:
                    return
            self._sleep(self.settings.poll_interval)
        self._report_diagnostics(child)
        raise LocalRuntimeError("Advanced Reader no respondió a tiempo.")

    def _wait_for_streamlit(self, child: ManagedChild) -> None:
        deadline = self._monotonic() + self.settings.startup_timeout
        while self._monotonic() < deadline:
            self._raise_if_shutdown()
            if child.poll() is not None:
                self._report_diagnostics(child)
                raise LocalRuntimeError("Streamlit terminó antes de estar listo.")
            if self._streamlit_health():
                return
            self._sleep(self.settings.poll_interval)
        self._report_diagnostics(child)
        raise LocalRuntimeError("Streamlit no respondió a tiempo.")

    def _print_ready(self) -> None:
        self._emit("MathMongo local runtime")
        self._emit("")
        self._emit(f"Database: {self.settings.database}")
        self._emit(
            "Streamlit: "
            f"{loopback_url(self.settings.streamlit_host, self.settings.streamlit_port)} "
            f"({self._streamlit_disposition.value})"
        )
        self._emit(
            "Advanced Reader: "
            f"{loopback_url(self.settings.advanced_reader_host, self.settings.advanced_reader_port)} "
            f"({self._reader_disposition.value})"
        )
        self._emit("Advanced Reader health: ready")
        self._emit("")
        self._emit("Press Ctrl+C to stop services started by this launcher.")

    def _monitor(self) -> int:
        while self._shutdown_signal is None:
            for child in tuple(self._owned_children):
                returncode = child.poll()
                if returncode is not None:
                    self._report_diagnostics(child)
                    self._emit(f"{child.name} terminó inesperadamente.")
                    return returncode if returncode != 0 else 1
            self._sleep(self.settings.poll_interval)
        return 130 if self._shutdown_signal == signal.SIGINT else 143

    def _stop_owned_children(self) -> None:
        children = tuple(reversed(self._owned_children))
        self._owned_children.clear()
        for child in children:
            try:
                child.stop(timeout=self.settings.shutdown_timeout)
            except (OSError, subprocess.SubprocessError, ValueError):
                self._emit(f"No se pudo confirmar el cierre limpio de {child.name}.")

    @contextmanager
    def _signal_handlers(self, enabled: bool):
        if not enabled:
            yield
            return
        previous: dict[int, Any] = {}

        def handle(signum: int, _frame: FrameType | None) -> None:
            self.request_shutdown(signum)

        try:
            for signum in (signal.SIGINT, signal.SIGTERM):
                previous[signum] = signal.getsignal(signum)
                signal.signal(signum, handle)
            yield
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)

    def run(self, *, install_signal_handlers: bool = True) -> int:
        """Run both services in the foreground and always reap owned children."""
        with self._signal_handlers(install_signal_handlers):
            try:
                self._raise_if_shutdown()
                reader_reused = self._inspect_reader()
                self._raise_if_shutdown()
                self._inspect_streamlit()
                self._raise_if_shutdown()
                environment = build_child_environment(
                    self.settings,
                    base_environment=self._base_environment,
                )
                app_path = self._resolve_streamlit_app()
                self._raise_if_shutdown()
                if reader_reused:
                    self._emit("Advanced Reader compatible encontrado; se reutilizará.")
                else:
                    self._raise_if_shutdown()
                    reader = self._start_child(
                        name="Advanced Reader",
                        prefix="advanced-reader",
                        command=build_advanced_reader_command(
                            self.settings,
                            executable=self._executable,
                        ),
                        environment=environment,
                    )
                    self._reader_disposition = ServiceDisposition.STARTED
                    self._wait_for_reader(reader)
                self._raise_if_shutdown()
                streamlit = self._start_child(
                    name="Streamlit",
                    prefix="streamlit",
                    command=build_streamlit_command(
                        self.settings,
                        app_path,
                        executable=self._executable,
                    ),
                    environment=environment,
                )
                self._streamlit_disposition = ServiceDisposition.STARTED
                self._wait_for_streamlit(streamlit)
                self._raise_if_shutdown()
                self._print_ready()
                return self._monitor()
            except KeyboardInterrupt:
                self.request_shutdown(signal.SIGINT)
                return 130
            except _ShutdownRequestedError:
                return 130 if self._shutdown_signal == signal.SIGINT else 143
            finally:
                self._stop_owned_children()


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point with safe errors and no traceback for operational failures."""
    try:
        settings = settings_from_args(argv)
        return LocalRuntimeSupervisor(settings).run()
    except LocalRuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


__all__ = [
    "LocalRuntimeSupervisor",
    "build_parser",
    "main",
    "settings_from_args",
]
