"""Isolated local PDF.js reader for existing MathMongo Documents."""

from mathmongo.advanced_reader.app import create_app
from mathmongo.advanced_reader.dependencies import AdvancedReaderDependencies

__all__ = ["AdvancedReaderDependencies", "create_app"]
