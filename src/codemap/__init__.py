"""
Codemap - A smart code indexer for AI assistants.

Maintains a real-time map of your codebase in CLAUDE.md files.
"""

__version__ = "0.1.0"
__author__ = "Your Name"

from .indexer import CodeIndexer, FileInfo
from .monitor import CodeMonitor

__all__ = ["CodeIndexer", "FileInfo", "CodeMonitor", "__version__"]