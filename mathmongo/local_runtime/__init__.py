"""Public API for MathMongo's unified foreground local runtime."""

from mathmongo.local_runtime.health import loopback_url
from mathmongo.local_runtime.health import probe_advanced_reader
from mathmongo.local_runtime.health import probe_streamlit
from mathmongo.local_runtime.launcher import LocalRuntimeSupervisor
from mathmongo.local_runtime.launcher import build_parser
from mathmongo.local_runtime.launcher import main
from mathmongo.local_runtime.launcher import settings_from_args
from mathmongo.local_runtime.models import AdvancedReaderHealth
from mathmongo.local_runtime.models import LocalRuntimeError
from mathmongo.local_runtime.models import RuntimeSettings
from mathmongo.local_runtime.models import ServiceDisposition
from mathmongo.local_runtime.processes import DATABASE_ENV_VAR
from mathmongo.local_runtime.processes import build_advanced_reader_command
from mathmongo.local_runtime.processes import build_child_environment
from mathmongo.local_runtime.processes import build_streamlit_command

__all__ = [
    "AdvancedReaderHealth",
    "DATABASE_ENV_VAR",
    "LocalRuntimeError",
    "LocalRuntimeSupervisor",
    "RuntimeSettings",
    "ServiceDisposition",
    "build_advanced_reader_command",
    "build_child_environment",
    "build_parser",
    "build_streamlit_command",
    "loopback_url",
    "main",
    "probe_advanced_reader",
    "probe_streamlit",
    "settings_from_args",
]
