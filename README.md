# Codemap

A smart code indexer that maintains a real-time map of your codebase for AI assistants like Claude Code.

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)

## Features

🔍 **Smart Analysis**: Extracts functions, classes, and imports from Python, JavaScript/TypeScript, Lua, and AutoHotkey files  
⚡ **Real-time Monitoring**: Watches for file changes and updates indexes automatically  
🎯 **Multi-Project Support**: Monitor multiple projects simultaneously  
📊 **Rich CLI**: Beautiful command-line interface with progress indicators  
⚙️ **Configurable**: Customize file patterns, ignore rules, and update behavior  
🚀 **Efficient**: Only re-indexes changed files with smart caching  

## Installation

Install globally with pipx (recommended):
```bash
pipx install codemap
```

Or with pip:
```bash
pip install codemap
```

## Quick Start

Initialize codemap in your project:
```bash
cd your-project
codemap init
```

Start monitoring (daemon mode):
```bash
codemap start
```

Add another project to monitoring:
```bash
codemap add /path/to/another/project
```

## Usage

### Commands

| Command | Description |
|---------|-------------|
| `codemap` | Add current directory to monitoring |
| `codemap init` | Initialize codemap in current directory |
| `codemap add [path]` | Add a project to monitoring |
| `codemap remove [path]` | Remove a project from monitoring |
| `codemap list` | List all monitored projects |
| `codemap status` | Show daemon status |
| `codemap start` | Start monitoring daemon (detached) |
| `codemap start --foreground` | Start daemon in foreground |
| `codemap stop` | Stop monitoring daemon |
| `codemap logs` | Show daemon logs |
| `codemap logs --follow` | Follow daemon logs in real-time |
| `codemap cleanup` | Remove stale project references |

### Configuration

Codemap uses [platformdirs](https://github.com/platformdirs/platformdirs) to store configuration in standard locations:

- **Linux**: `~/.config/codemap/`
- **macOS**: `~/Library/Application Support/codemap/`
- **Windows**: `%APPDATA%\codemap\`

Environment variables (prefix with `CODEMAP_`):
- `CODEMAP_DAEMON_PORT=8765`
- `CODEMAP_UPDATE_DELAY=2.0`

### Daemon Operation

Codemap runs as a background daemon that monitors multiple projects simultaneously:

- **Detached Mode** (default): `codemap start` runs in the background, returns immediately
- **Foreground Mode**: `codemap start --foreground` runs in the terminal (useful for debugging)
- **Automatic Startup**: Add projects with `codemap add` then start the daemon
- **Graceful Shutdown**: `codemap stop` sends SIGTERM, then SIGKILL if needed
- **Logs**: Stored in `~/.local/state/codemap/daemon.log` (Linux/macOS)
- **PID Management**: Daemon PID tracked for reliable start/stop operations

## CLAUDE.md Structure

The generated index includes:

1. **Project Overview**: Statistics and directory info
2. **Directory Structure**: Visual tree representation  
3. **Configuration Files**: Project configuration files
4. **Python Modules**: Classes, functions, and imports
5. **JavaScript/TypeScript**: Functions and classes  
6. **Lua Scripts**: Functions and imports
7. **AutoHotkey Scripts**: Functions, labels, hotkeys, and includes
8. **Other Files**: Additional source files
9. **Recent Changes**: Last 10 modified files

## Example Output

```markdown
# Current Code Index

*Last updated: 2024-06-14 16:22:38*

## Project Overview

**Root Directory:** `my-project`
**Total Files Indexed:** 42

## Directory Structure

```
├── src/
│   ├── main.py
│   └── utils/
│       └── helpers.py
├── tests/
│   └── test_main.py
└── package.json
```

## Python Modules

### `src/main.py`
**Functions:**
- `main()` (line 10) - Application entry point
- `setup_logging()` (line 5) - Configure logging

**Key Imports:** `os`, `sys`, `logging`
```

## How It Works

1. **File Monitoring**: Uses `watchdog` for efficient file system monitoring
2. **Code Analysis**: Parses Python, JavaScript/TypeScript, Lua, and AutoHotkey to extract structure
3. **Smart Indexing**: Only re-analyzes changed files with MD5 hash comparison
4. **Index Generation**: Creates/updates `CLAUDE.md` with current codebase map
5. **Multi-Project**: Manages multiple projects from a central configuration

## Development

Clone and install in development mode:

```bash
git clone https://github.com/yourusername/codemap.git
cd codemap
pip install -e ".[dev]"
```

Run tests:
```bash
pytest tests/ -v
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.