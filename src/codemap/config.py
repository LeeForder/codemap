"""Configuration management for codemap using platformdirs."""

import json
from pathlib import Path
from typing import Dict, List, Optional

from platformdirs import user_config_dir, user_data_dir, user_state_dir
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .models import ProjectConfig


class GlobalConfig(BaseSettings):
    """Global configuration for codemap."""
    
    model_config = SettingsConfigDict(
        env_prefix="CODEMAP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore extra environment variables
    )
    
    # Global settings
    daemon_enabled: bool = Field(default=True, description="Run as background daemon")
    daemon_port: int = Field(default=8765, description="Port for daemon communication")
    update_delay: float = Field(default=2.0, description="Delay before updating index")
    
    # Default patterns
    default_ignore_patterns: List[str] = Field(
        default=[
            '.git', '__pycache__', 'node_modules', '.venv', 'venv', 
            'dist', 'build', '.pytest_cache', '.mypy_cache', '.coverage',
            '*.pyc', '*.pyo', '*.pyd', '.DS_Store', 'thumbs.db'
        ]
    )
    
    default_file_extensions: List[str] = Field(
        default=[
            '.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.cpp', '.c',
            '.h', '.hpp', '.cs', '.rb', '.go', '.rs', '.php', '.swift',
            '.kt', '.scala', '.r', '.m', '.mm', '.sh', '.bash', '.zsh'
        ]
    )
    
    config_files: List[str] = Field(
        default=[
            'package.json', 'requirements.txt', 'setup.py', 'pyproject.toml',
            'Cargo.toml', 'go.mod', 'composer.json', 'Gemfile', '.env.example',
            'Dockerfile', 'docker-compose.yml', '.gitignore', 'Makefile'
        ]
    )


class ConfigManager:
    """Manages codemap configuration and project registry."""
    
    def __init__(self):
        self.config_dir = Path(user_config_dir("codemap", "codemap"))
        self.data_dir = Path(user_data_dir("codemap", "codemap"))
        self.state_dir = Path(user_state_dir("codemap", "codemap"))
        
        # Create directories if they don't exist
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
        self.config_file = self.config_dir / "config.json"
        self.projects_file = self.config_dir / "projects.json"
        self.pid_file = self.state_dir / "codemap.pid"
        
        self.global_config = GlobalConfig()
        self.projects: Dict[str, ProjectConfig] = self._load_projects()
    
    def _load_projects(self) -> Dict[str, ProjectConfig]:
        """Load projects from configuration file."""
        if not self.projects_file.exists():
            return {}
        
        try:
            with open(self.projects_file, 'r') as f:
                data = json.load(f)
                projects = {}
                for path, config in data.items():
                    projects[path] = ProjectConfig(
                        path=Path(path),
                        **config
                    )
                return projects
        except Exception:
            return {}
    
    def save_projects(self):
        """Save projects to configuration file."""
        data = {}
        for path, project in self.projects.items():
            data[str(path)] = {
                "enabled": project.enabled,
                "ignore_patterns": project.ignore_patterns,
                "file_extensions": project.file_extensions,
                "max_file_size": project.max_file_size,
                "max_depth": project.max_depth,
                "include_config_files": project.include_config_files,
                "update_delay": project.update_delay,
            }
        
        with open(self.projects_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def add_project(self, path: Path, config: Optional[Dict] = None) -> ProjectConfig:
        """Add a project to monitor."""
        path = path.resolve()
        
        if str(path) in self.projects:
            return self.projects[str(path)]
        
        # Create project config with defaults
        project_config = ProjectConfig(
            path=path,
            ignore_patterns=config.get("ignore_patterns", self.global_config.default_ignore_patterns) if config else self.global_config.default_ignore_patterns,
            file_extensions=config.get("file_extensions", self.global_config.default_file_extensions) if config else self.global_config.default_file_extensions,
            **(config or {})
        )
        
        self.projects[str(path)] = project_config
        self.save_projects()
        return project_config
    
    def remove_project(self, path: Path) -> bool:
        """Remove a project from monitoring."""
        path = str(path.resolve())
        if path in self.projects:
            del self.projects[path]
            self.save_projects()
            return True
        return False
    
    def get_project(self, path: Path) -> Optional[ProjectConfig]:
        """Get configuration for a specific project."""
        return self.projects.get(str(path.resolve()))
    
    def list_projects(self) -> List[ProjectConfig]:
        """List all monitored projects."""
        return list(self.projects.values())
    
    def is_daemon_running(self) -> bool:
        """Check if the daemon is running."""
        if not self.pid_file.exists():
            return False
        
        try:
            with open(self.pid_file, 'r') as f:
                pid = int(f.read().strip())
            
            # Check if process exists
            import os
            import platform
            
            if platform.system() == "Windows":
                # Windows-specific process check
                import subprocess
                try:
                    result = subprocess.run(
                        ["tasklist", "/FI", f"PID eq {pid}"],
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    # If the PID appears in the output, the process exists
                    return str(pid) in result.stdout
                except Exception:
                    return False
            else:
                # Unix-like systems
                os.kill(pid, 0)
                return True
        except (ValueError, ProcessLookupError, PermissionError, OSError):
            # Clean up stale PID file
            self.pid_file.unlink(missing_ok=True)
            return False
    
    def set_daemon_pid(self, pid: int):
        """Save daemon PID."""
        with open(self.pid_file, 'w') as f:
            f.write(str(pid))
    
    def clear_daemon_pid(self):
        """Clear daemon PID file."""
        self.pid_file.unlink(missing_ok=True)
    
    def cleanup_stale_projects(self) -> int:
        """Remove projects that no longer exist on disk."""
        removed_count = 0
        stale_paths = []
        
        for path_str, project in self.projects.items():
            if not project.path.exists():
                stale_paths.append(path_str)
        
        for path_str in stale_paths:
            del self.projects[path_str]
            removed_count += 1
        
        if removed_count > 0:
            self.save_projects()
        
        return removed_count