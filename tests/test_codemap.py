"""Basic tests for codemap."""

import tempfile
from pathlib import Path

import pytest

from codemap.models import FileInfo, ProjectConfig
from codemap.config import ConfigManager
from codemap.indexer import CodeIndexer


def test_project_config():
    """Test ProjectConfig creation."""
    config = ProjectConfig(
        path=Path("/test/path"),
        enabled=True,
        ignore_patterns=[".git", "__pycache__"],
        file_extensions=[".py", ".js"],
    )
    
    assert config.path == Path("/test/path")
    assert config.enabled is True
    assert ".git" in config.ignore_patterns
    assert ".py" in config.file_extensions


def test_file_info():
    """Test FileInfo creation."""
    info = FileInfo(
        path=Path("/test/file.py"),
        relative_path="file.py",
        size=1024,
        modified=1234567890.0,
        hash="abcdef123456",
        functions=[{"name": "test", "line": 1}],
        classes=[{"name": "TestClass", "line": 10}],
    )
    
    assert info.path == Path("/test/file.py")
    assert info.size == 1024
    assert len(info.functions) == 1
    assert len(info.classes) == 1


def test_indexer_initialization():
    """Test CodeIndexer initialization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = ProjectConfig(
            path=Path(tmpdir),
            file_extensions=[".py"],
        )
        
        indexer = CodeIndexer(config)
        assert indexer.root_path == Path(tmpdir)
        assert indexer.config == config


def test_indexer_scan_empty_directory():
    """Test scanning an empty directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = ProjectConfig(
            path=Path(tmpdir),
            file_extensions=[".py"],
        )
        
        indexer = CodeIndexer(config)
        file_index = indexer.scan_directory()
        
        assert len(file_index) == 0


def test_indexer_scan_with_python_file():
    """Test scanning a directory with a Python file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a test Python file
        test_file = Path(tmpdir) / "test.py"
        test_file.write_text("""
def hello():
    '''Say hello.'''
    print("Hello, world!")

class Greeter:
    '''A greeting class.'''
    def greet(self, name):
        return f"Hello, {name}!"
""")
        
        config = ProjectConfig(
            path=Path(tmpdir),
            file_extensions=[".py"],
        )
        
        indexer = CodeIndexer(config)
        file_index = indexer.scan_directory()
        
        assert len(file_index) == 1
        assert "test.py" in file_index
        
        file_info = file_index["test.py"]
        assert len(file_info.functions) == 2  # hello and greet methods
        function_names = [f["name"] for f in file_info.functions]
        assert "hello" in function_names
        assert "greet" in function_names
        hello_func = next(f for f in file_info.functions if f["name"] == "hello")
        assert hello_func["docstring"] == "Say hello."
        
        assert len(file_info.classes) == 1
        assert file_info.classes[0]["name"] == "Greeter"
        assert file_info.classes[0]["docstring"] == "A greeting class."


def test_config_manager_initialization():
    """Test ConfigManager initialization."""
    # This will use temporary directories from platformdirs
    config_manager = ConfigManager()
    
    assert config_manager.config_dir.exists()
    assert config_manager.data_dir.exists()
    assert config_manager.state_dir.exists()


def test_config_manager_add_remove_project():
    """Test adding and removing projects."""
    config_manager = ConfigManager()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        
        # Add project
        project = config_manager.add_project(project_path)
        assert project.path == project_path
        assert str(project_path) in config_manager.projects
        
        # List projects
        projects = config_manager.list_projects()
        assert len(projects) >= 1
        assert any(p.path == project_path for p in projects)
        
        # Remove project
        removed = config_manager.remove_project(project_path)
        assert removed is True
        assert str(project_path) not in config_manager.projects