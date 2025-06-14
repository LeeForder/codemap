"""Data models for codemap."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class FileInfo:
    """Information about a single file in the codebase."""
    
    path: Path
    relative_path: str
    size: int
    modified: float
    hash: str
    functions: List[Dict[str, str]] = field(default_factory=list)
    classes: List[Dict[str, str]] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class ProjectConfig:
    """Configuration for a monitored project."""
    
    path: Path
    enabled: bool = True
    ignore_patterns: List[str] = field(default_factory=list)
    file_extensions: List[str] = field(default_factory=list)
    max_file_size: int = 1048576  # 1MB
    max_depth: int = 10
    include_config_files: bool = True
    update_delay: float = 2.0