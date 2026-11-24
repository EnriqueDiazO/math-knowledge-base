"""Isolated local PDF.js reader for existing MathMongo Documents."""

from mathmongo.advanced_reader.dependencies import AdvancedReaderDependencies

__all__ = ["AdvancedReaderDependencies", "create_app"]


def __getattr__(name):
    """Keep the public factory while allowing services to import error types alone."""
    if name == "create_app":
        from mathmongo.advanced_reader.app import create_app

        return create_app
    raise AttributeError(name)
