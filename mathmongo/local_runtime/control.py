"""Safe lifecycle commands for the supervised local MathMongo runtime."""

# ruff: noqa: D107

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from mathmongo.config import redact_mongo_uri
from mathmongo.launcher import LaunchError
from mathmongo.launcher import require_unprivileged_user
from mathmongo.local_runtime.models import LocalRuntimeError
from mathmongo.local_runtime.models import RuntimeSettings
from mathmongo.local_runtime.processes import sanitize_log_line
from mathmongo.local_runtime.state import ProcessIdentity
from mathmongo.local_runtime.state import RuntimeObservation
from mathmongo.local_runtime.state import RuntimeStateKind
from mathmongo.local_runtime.state import RuntimeStateStore
from mathmongo.local_runtime.state import inspect_process
from mathmongo.local_runtime.state import observe_runtime
from mathmongo.local_runtime.state import repository_root
from mathmongo.mongodb_service import mongodb_reachable


@dataclass(frozen=True)
class RuntimeAction:
    """One user-facing result with no secrets or raw process environment."""

    changed: bool
    observation: RuntimeObservation
    message: str


def _runtime_command(settings: RuntimeSettings, executable: str) -> list[str]:
    return [
        executable,
        "-m",
        "mathmongo.local_runtime",
        "--database",
        settings.database,
        "--streamlit-host",
        settings.streamlit_host,
        "--streamlit-port",
        str(settings.streamlit_port),
        "--advanced-reader-host",
        settings.advanced_reader_host,
        "--advanced-reader-port",
        str(settings.advanced_reader_port),
        "--log-level",
        settings.log_level,
    ]


class RuntimeController:
    """Control only a runtime whose state and live processes agree exactly."""

    def __init__(
        self,
        settings: RuntimeSettings,
        *,
        mongo_uri: str,
        environment: Mapping[str, str] | None = None,
        store: RuntimeStateStore | None = None,
        executable: str | None = None,
        repository: Path | None = None,
        popen_factory=subprocess.Popen,
        mongo_probe=mongodb_reachable,
        monotonic=time.monotonic,
        sleep=time.sleep,
    ) -> None:
        self.settings = settings
        self.mongo_uri = mongo_uri
        self.environment = dict(os.environ if environment is None else environment)
        self.store = store or RuntimeStateStore(self.environment)
        self.executable = executable or sys.executable
        self.repository = (repository or repository_root()).resolve()
        self._popen = popen_factory
        self._mongo_probe = mongo_probe
        self._monotonic = monotonic
        self._sleep = sleep

    def status(self) -> RuntimeObservation:
        """Inspect status without creating metadata or opening database collections."""
        return observe_runtime(self.settings, store=self.store, repository=self.repository)

    def doctor(self) -> tuple[RuntimeObservation, bool]:
        """Return runtime state and a read-only MongoDB prerequisite check."""
        return self.status(), self._mongo_probe(self.mongo_uri, self.settings.database)

    def _require_mongo(self) -> None:
        if self._mongo_probe(self.mongo_uri, self.settings.database):
            return
        raise LocalRuntimeError(
            "No fue posible comunicarse con MongoDB. Verifica el estado del servicio "
            "y vuelve a probar la conexión. Ejecuta `make status` o `mathmongo runtime doctor`. "
            f"Host configurado: {redact_mongo_uri(self.mongo_uri)}."
        )

    @staticmethod
    def _require_application_user() -> None:
        try:
            require_unprivileged_user()
        except LaunchError as exc:
            raise LocalRuntimeError(str(exc)) from exc

    def _clear_stale_metadata(self, observation: RuntimeObservation) -> None:
        if observation.kind is RuntimeStateKind.STALE:
            self.store.clear()

    def _foreign_port_message(self, observation: RuntimeObservation) -> str:
        details: list[str] = []
        for label, port, identity in (
            ("Streamlit", self.settings.streamlit_port, observation.streamlit),
            (
                "Advanced Reader",
                self.settings.advanced_reader_port,
                observation.advanced_reader,
            ),
        ):
            if identity is None:
                continue
            command = sanitize_log_line(" ".join(identity.command))
            details.append(
                f"{label}: puerto {port}, PID {identity.pid}, CWD {identity.cwd}, comando {command}."
            )
        occupied = details or [observation.message]
        return (
            f"El puerto {self.settings.streamlit_port} o {self.settings.advanced_reader_port} "
            "está ocupado por otra aplicación. MathMongo no detuvo ese proceso. "
            + " ".join(occupied)
        )

    def start(self) -> RuntimeAction:
        """Start a fresh detached supervisor after conservative port checks."""
        self._require_application_user()
        observation = self.status()
        if observation.kind is RuntimeStateKind.OWNED:
            return RuntimeAction(
                False,
                observation,
                "El runtime MathMongo ya está activo. Usa `make restart` para reiniciarlo de forma segura.",
            )
        if observation.kind is RuntimeStateKind.ORPHAN:
            raise LocalRuntimeError(
                "Se detectó un runtime huérfano de este repositorio. No se detuvo automáticamente. "
                "Revísalo con `mathmongo runtime status` o recupéralo de forma explícita con "
                "`mathmongo runtime restart --recover-orphan`."
            )
        if observation.kind in {RuntimeStateKind.FOREIGN, RuntimeStateKind.AMBIGUOUS}:
            alternative = (
                str(self.settings.streamlit_port + 1)
                if self.settings.streamlit_port < 65535
                else "<puerto-libre>"
            )
            raise LocalRuntimeError(
                f"{self._foreign_port_message(observation)} "
                f"o elige otro puerto, por ejemplo `--streamlit-port {alternative}`."
            )
        self._clear_stale_metadata(observation)
        observation = self.status()
        if observation.kind is not RuntimeStateKind.STOPPED:
            raise LocalRuntimeError(
                "Los puertos no quedaron libres después de descartar metadata stale. No se inició otro runtime."
            )
        self._require_mongo()
        command = _runtime_command(self.settings, self.executable)
        environment = dict(self.environment)
        environment["MONGODB_DB"] = self.settings.database
        environment["MONGODB_URI"] = self.mongo_uri
        try:
            process = self._popen(
                command,
                cwd=str(self.repository),
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                close_fds=True,
                shell=False,
            )
        except (OSError, ValueError) as exc:
            raise LocalRuntimeError("No se pudo iniciar el supervisor local de MathMongo.") from exc

        deadline = self._monotonic() + self.settings.startup_timeout
        while self._monotonic() < deadline:
            current = self.status()
            if (
                current.kind is RuntimeStateKind.OWNED
                and current.supervisor is not None
                and current.supervisor.pid == process.pid
            ):
                return RuntimeAction(True, current, "Runtime MathMongo iniciado y verificado.")
            if process.poll() is not None:
                break
            self._sleep(min(0.1, self.settings.poll_interval))
        raise LocalRuntimeError(
            "El supervisor local no confirmó su identidad a tiempo. Consulta `mathmongo runtime doctor`."
        )

    def _wait_until_stopped(self, *, timeout: float) -> RuntimeObservation:
        deadline = self._monotonic() + timeout
        observation = self.status()
        while self._monotonic() < deadline:
            observation = self.status()
            if observation.kind is RuntimeStateKind.STOPPED:
                return observation
            self._sleep(min(0.1, self.settings.poll_interval))
        return observation

    def _signal_verified(self, identity: ProcessIdentity, signum: int) -> bool:
        current = inspect_process(identity.pid)
        if current != identity:
            return False
        try:
            os.kill(identity.pid, signum)
            return True
        except OSError:
            return False

    def stop(self, *, force: bool = False) -> RuntimeAction:
        """Stop only a live runtime confirmed by state and procfs identity."""
        observation = self.status()
        if observation.kind is RuntimeStateKind.STOPPED:
            return RuntimeAction(False, observation, "El runtime MathMongo ya está detenido.")
        if observation.kind is not RuntimeStateKind.OWNED or observation.supervisor is None:
            raise LocalRuntimeError(
                "No se detuvo ningún proceso: el runtime no tiene una identidad confirmada. "
                "MathMongo nunca detiene procesos extranjeros o ambiguos."
            )
        if not self._signal_verified(observation.supervisor, signal.SIGTERM):
            raise LocalRuntimeError("La identidad del supervisor cambió antes de detenerlo; no se envió señal.")
        stopped = self._wait_until_stopped(timeout=self.settings.shutdown_timeout)
        if stopped.kind is RuntimeStateKind.STOPPED:
            self.store.clear(runtime_id=str(observation.record.get("runtime_id")))
            return RuntimeAction(True, stopped, "Runtime MathMongo detenido limpiamente.")
        if not force:
            raise LocalRuntimeError(
                "El runtime no terminó tras SIGTERM. No se aplicó SIGKILL. "
                "Revisa el estado o repite con `--force` para terminar sólo los PIDs verificados."
            )
        # Force is deliberately narrow: revalidate each identity from the signed
        # state snapshot before signalling it.  No PID is targeted from a port scan.
        for identity in (
            observation.supervisor,
            observation.streamlit,
            observation.advanced_reader,
        ):
            if identity is not None:
                self._signal_verified(identity, signal.SIGKILL)
        stopped = self._wait_until_stopped(timeout=self.settings.shutdown_timeout)
        if stopped.kind is not RuntimeStateKind.STOPPED:
            raise LocalRuntimeError("No se pudo confirmar el cierre del runtime verificado.")
        self.store.clear(runtime_id=str(observation.record.get("runtime_id")))
        return RuntimeAction(True, stopped, "Runtime MathMongo detenido con la política --force.")

    def _recover_orphan(self, observation: RuntimeObservation) -> None:
        if observation.kind is not RuntimeStateKind.ORPHAN:
            raise LocalRuntimeError("--recover-orphan sólo se permite para un runtime huérfano confirmado.")
        for identity in (observation.streamlit, observation.advanced_reader):
            if identity is None or not self._signal_verified(identity, signal.SIGTERM):
                raise LocalRuntimeError("La identidad del runtime huérfano cambió; no se detuvo ningún proceso.")
        stopped = self._wait_until_stopped(timeout=self.settings.shutdown_timeout)
        if stopped.kind is not RuntimeStateKind.STOPPED:
            raise LocalRuntimeError(
                "El runtime huérfano no terminó tras SIGTERM. No se aplicó SIGKILL automáticamente."
            )

    def restart(self, *, recover_orphan: bool = False, force: bool = False) -> RuntimeAction:
        """Restart one owned runtime, with explicit opt-in recovery for an orphan."""
        observation = self.status()
        if observation.kind is RuntimeStateKind.ORPHAN:
            if not recover_orphan:
                raise LocalRuntimeError(
                    "Se detectó un runtime huérfano. Para reemplazar sólo sus procesos verificados usa "
                    "`mathmongo runtime restart --recover-orphan`."
                )
            self._recover_orphan(observation)
        elif observation.kind is RuntimeStateKind.OWNED:
            self.stop(force=force)
        elif observation.kind in {RuntimeStateKind.STOPPED, RuntimeStateKind.STALE}:
            return self.start()
        else:
            raise LocalRuntimeError(
                "No se reinició ningún proceso: los puertos no pertenecen a un runtime MathMongo confirmado."
            )
        return self.start()


__all__ = ["RuntimeAction", "RuntimeController"]
