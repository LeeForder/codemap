"""Command-line interface for codemap."""

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich import print
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import ConfigManager
from .monitor import CodeMonitor

app = typer.Typer(
    name="codemap",
    help="Smart code indexer that maintains a real-time map of your codebase for AI assistants.",
    rich_markup_mode="rich",
)
console = Console()


def version_callback(value: bool):
    """Show version and exit."""
    if value:
        print(f"[cyan]codemap[/cyan] version [green]{__version__}[/green]")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
):
    """
    Codemap - Smart code indexer for AI assistants.
    
    By default, running 'codemap' will add the current directory to monitoring.
    """
    pass


@app.command(name="add", help="Add a project to monitor")
def add_project(
    path: Optional[Path] = typer.Argument(
        None,
        help="Path to the project directory (defaults to current directory)",
    ),
):
    """Add a project to codemap monitoring."""
    if path is None:
        path = Path.cwd()
    
    path = path.resolve()
    
    if not path.exists() or not path.is_dir():
        print(f"[red]Error:[/red] {path} is not a valid directory")
        raise typer.Exit(1)
    
    config_manager = ConfigManager()
    
    # Check if already monitoring
    if config_manager.get_project(path):
        print(f"[yellow]Already monitoring:[/yellow] {path}")
        return
    
    # Add the project
    project = config_manager.add_project(path)
    print(f"[green]Added project:[/green] {path}")
    
    # Start monitoring if daemon is running
    if config_manager.is_daemon_running():
        print("[cyan]Daemon is running - project will be monitored automatically[/cyan]")
    else:
        print("[yellow]Daemon not running - start with 'codemap start'[/yellow]")


@app.command(name="remove", help="Remove a project from monitoring")
def remove_project(
    path: Optional[Path] = typer.Argument(
        None,
        help="Path to the project directory (defaults to current directory)",
    ),
):
    """Remove a project from codemap monitoring."""
    if path is None:
        path = Path.cwd()
    
    path = path.resolve()
    
    config_manager = ConfigManager()
    
    if config_manager.remove_project(path):
        print(f"[green]Removed project:[/green] {path}")
    else:
        print(f"[red]Error:[/red] Project not found: {path}")
        raise typer.Exit(1)


@app.command(name="list", help="List all monitored projects")
def list_projects():
    """List all projects being monitored."""
    config_manager = ConfigManager()
    projects = config_manager.list_projects()
    
    if not projects:
        print("[yellow]No projects being monitored[/yellow]")
        return
    
    table = Table(title="Monitored Projects")
    table.add_column("Path", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Files", justify="right")
    
    for project in projects:
        status = "✓ Enabled" if project.enabled else "✗ Disabled"
        
        # Count files if CLAUDE.md exists
        file_count = "-"
        claude_md = project.path / "CLAUDE.md"
        if claude_md.exists():
            try:
                with open(claude_md, 'r') as f:
                    content = f.read()
                    # Count files by counting file entries in the index
                    # Look for patterns like "### `filename`" or "- `filename`"
                    import re
                    # Count Python module sections
                    py_modules = len(re.findall(r'### `[^`]+\.py`', content))
                    # Count other file references  
                    other_files = len(re.findall(r'### `[^`]+\.[^`]+`', content)) - py_modules
                    # Count simple file listings
                    listed_files = len(re.findall(r'^- `[^`]+\.[^`]+`', content, re.MULTILINE))
                    
                    total = py_modules + other_files + listed_files
                    if total > 0:
                        file_count = str(total)
            except:
                pass
        
        table.add_row(str(project.path), status, file_count)
    
    console.print(table)


@app.command(name="status", help="Show codemap daemon status")
def show_status():
    """Show the status of the codemap daemon."""
    config_manager = ConfigManager()
    
    if config_manager.is_daemon_running():
        print("[green]✓ Daemon is running[/green]")
        
        # Show monitored projects
        projects = config_manager.list_projects()
        enabled_count = sum(1 for p in projects if p.enabled)
        print(f"[cyan]Monitoring {enabled_count} project(s)[/cyan]")
    else:
        print("[red]✗ Daemon is not running[/red]")
        print("[yellow]Start with 'codemap start'[/yellow]")


@app.command(name="start", help="Start the codemap daemon")
def start_daemon(
    foreground: bool = typer.Option(
        False,
        "--foreground",
        "-f",
        help="Run in foreground instead of detaching",
    ),
):
    """Start the codemap monitoring daemon."""
    config_manager = ConfigManager()
    
    if config_manager.is_daemon_running():
        print("[yellow]Daemon is already running[/yellow]")
        return
    
    # Clean up stale projects first
    removed_count = config_manager.cleanup_stale_projects()
    if removed_count > 0:
        print(f"[yellow]Cleaned up {removed_count} stale project(s)[/yellow]")
    
    if foreground:
        # Run in foreground
        _run_daemon_foreground(config_manager)
    else:
        # Run detached
        _run_daemon_detached(config_manager)


def _run_daemon_foreground(config_manager):
    """Run the daemon in foreground mode."""
    config_manager.set_daemon_pid(os.getpid())
    
    print("[green]Starting codemap daemon in foreground...[/green]")
    print("[yellow]Press Ctrl+C to stop[/yellow]")
    
    monitor = CodeMonitor()
    
    try:
        asyncio.run(monitor.run())
    except KeyboardInterrupt:
        print("\n[yellow]Daemon stopped[/yellow]")
    finally:
        config_manager.clear_daemon_pid()


def _run_daemon_detached(config_manager):
    """Run the daemon detached from the terminal."""
    import subprocess
    import sys
    
    # Create the daemon process
    daemon_cmd = [
        sys.executable, "-m", "codemap", "start", "--foreground"
    ]
    
    # Get log file path
    log_file = config_manager.state_dir / "daemon.log"
    
    try:
        # Start the daemon process detached
        with open(log_file, 'w') as f:
            process = subprocess.Popen(
                daemon_cmd,
                stdout=f,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,  # Detach from parent
                cwd=os.getcwd(),
            )
        
        # Give it a moment to start
        import time
        time.sleep(1)
        
        # Check if it's actually running
        if process.poll() is None:
            config_manager.set_daemon_pid(process.pid)
            print(f"[green]✓ Daemon started successfully[/green] (PID: {process.pid})")
            print(f"[cyan]Logs: {log_file}[/cyan]")
        else:
            print("[red]Failed to start daemon[/red]")
            print(f"[yellow]Check logs: {log_file}[/yellow]")
            raise typer.Exit(1)
            
    except Exception as e:
        print(f"[red]Error starting daemon:[/red] {e}")
        raise typer.Exit(1)


@app.command(name="stop", help="Stop the codemap daemon")
def stop_daemon():
    """Stop the codemap monitoring daemon."""
    config_manager = ConfigManager()
    
    if not config_manager.is_daemon_running():
        print("[yellow]Daemon is not running[/yellow]")
        return
    
    try:
        # Read PID and send signal
        with open(config_manager.pid_file, 'r') as f:
            pid = int(f.read().strip())
        
        # Send SIGTERM
        os.kill(pid, 15)
        
        # Wait a moment and check if it stopped
        import time
        time.sleep(1)
        
        try:
            # Check if process still exists
            os.kill(pid, 0)
            # If we get here, process is still running, try SIGKILL
            print("[yellow]Process didn't stop gracefully, forcing...[/yellow]")
            os.kill(pid, 9)  # SIGKILL
            time.sleep(0.5)
        except ProcessLookupError:
            # Process is gone, which is what we want
            pass
        
        config_manager.clear_daemon_pid()
        print("[green]✓ Daemon stopped[/green]")
        
    except ProcessLookupError:
        # Process already gone
        config_manager.clear_daemon_pid()
        print("[green]✓ Daemon stopped[/green]")
    except PermissionError:
        print("[red]Permission denied - cannot stop daemon[/red]")
        raise typer.Exit(1)
    except Exception as e:
        print(f"[red]Error stopping daemon:[/red] {e}")
        raise typer.Exit(1)


@app.command(name="init", help="Initialize codemap in the current directory")
def init_project(
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force initialization even if CLAUDE.md exists",
    ),
):
    """Initialize codemap in the current directory."""
    path = Path.cwd()
    claude_md = path / "CLAUDE.md"
    
    if claude_md.exists() and not force:
        print("[yellow]CLAUDE.md already exists[/yellow]")
        print("Use --force to overwrite")
        raise typer.Exit(1)
    
    # Add project and generate initial index
    config_manager = ConfigManager()
    project = config_manager.add_project(path)
    
    from .indexer import CodeIndexer
    indexer = CodeIndexer(project)
    
    if indexer.update_index():
        print(f"[green]✓ Created CLAUDE.md in {path}[/green]")
        print("[cyan]Project added to monitoring list[/cyan]")
    else:
        print("[red]Failed to create index[/red]")
        raise typer.Exit(1)


@app.command(name="cleanup", help="Remove stale projects that no longer exist")
def cleanup_projects():
    """Remove projects from monitoring that no longer exist on disk."""
    config_manager = ConfigManager()
    removed_count = config_manager.cleanup_stale_projects()
    
    if removed_count > 0:
        print(f"[green]Cleaned up {removed_count} stale project(s)[/green]")
    else:
        print("[cyan]No stale projects found[/cyan]")


@app.command(name="logs", help="Show daemon logs")
def show_logs(
    follow: bool = typer.Option(
        False,
        "--follow",
        "-f",
        help="Follow log output",
    ),
    lines: int = typer.Option(
        50,
        "--lines",
        "-n",
        help="Number of lines to show",
    ),
):
    """Show daemon logs."""
    config_manager = ConfigManager()
    log_file = config_manager.state_dir / "daemon.log"
    
    if not log_file.exists():
        print("[yellow]No log file found[/yellow]")
        print(f"Expected location: {log_file}")
        return
    
    try:
        if follow:
            # Follow mode using tail -f equivalent
            import subprocess
            subprocess.run(["tail", "-f", str(log_file)])
        else:
            # Show last N lines
            with open(log_file, 'r') as f:
                all_lines = f.readlines()
                start_line = max(0, len(all_lines) - lines)
                for line in all_lines[start_line:]:
                    print(line.rstrip())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"[red]Error reading logs:[/red] {e}")


# Default command when no subcommand is provided
@app.command(name="", help="Add current directory to monitoring (default)")
def default_command(
    ctx: typer.Context,
):
    """Default action - add current directory to monitoring."""
    # If no command was provided, add current directory
    if ctx.invoked_subcommand is None:
        add_project(None)


if __name__ == "__main__":
    app()