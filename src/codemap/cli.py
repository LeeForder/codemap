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
    import logging
    import sys
    
    config_manager.set_daemon_pid(os.getpid())
    
    # Configure logging for daemon (especially important for detached Windows process)
    log_file = config_manager.state_dir / "daemon.log"
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info("Starting codemap daemon")
    
    print("[green]Starting codemap daemon in foreground...[/green]")
    print("[yellow]Press Ctrl+C to stop[/yellow]")
    
    from .monitor import CodeMonitor
    monitor = CodeMonitor()
    
    try:
        asyncio.run(monitor.run())
    except KeyboardInterrupt:
        print("\n[yellow]Daemon stopped[/yellow]")
        logger.info("Daemon stopped by user")
    except Exception as e:
        logger.error(f"Daemon failed: {e}", exc_info=True)
        print(f"[red]Daemon failed: {e}[/red]")
    finally:
        config_manager.clear_daemon_pid()


def _run_daemon_detached(config_manager):
    """Run the daemon detached from the terminal."""
    import subprocess
    import sys
    import platform
    
    # Create the daemon process
    daemon_cmd = [
        sys.executable, "-m", "codemap", "start", "--foreground"
    ]
    
    # Get log file path
    log_file = config_manager.state_dir / "daemon.log"
    
    try:
        # Start the daemon process detached
        with open(log_file, 'w') as f:
            # Platform-specific process creation
            if platform.system() == "Windows":
                # Windows-specific flags for detached process without visible window
                process = subprocess.Popen(
                    daemon_cmd,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    creationflags=(
                        subprocess.CREATE_NEW_PROCESS_GROUP | 
                        subprocess.DETACHED_PROCESS | 
                        subprocess.CREATE_NO_WINDOW
                    ),
                    cwd=os.getcwd(),
                )
            else:
                # Unix-like systems
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
    import signal
    import platform
    import time
    
    config_manager = ConfigManager()
    
    if not config_manager.is_daemon_running():
        print("[yellow]Daemon is not running[/yellow]")
        return
    
    try:
        # Read PID and send signal
        with open(config_manager.pid_file, 'r') as f:
            pid = int(f.read().strip())
        
        if platform.system() == "Windows":
            # Windows process termination
            import subprocess
            try:
                # Try graceful termination first
                subprocess.run(["taskkill", "/PID", str(pid)], check=True, capture_output=True)
                time.sleep(1)
                
                # Check if process still exists
                result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True)
                if str(pid) in result.stdout:
                    # Force kill if still running
                    print("[yellow]Process didn't stop gracefully, forcing...[/yellow]")
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=True, capture_output=True)
                    time.sleep(0.5)
            except subprocess.CalledProcessError:
                # Process might already be gone
                pass
        else:
            # Unix-like systems - use proper signal constants
            # Send SIGTERM
            os.kill(pid, signal.SIGTERM)
            
            # Wait a moment and check if it stopped
            time.sleep(1)
            
            try:
                # Check if process still exists
                os.kill(pid, 0)
                # If we get here, process is still running, try SIGKILL
                print("[yellow]Process didn't stop gracefully, forcing...[/yellow]")
                os.kill(pid, signal.SIGKILL)
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


@app.command(name="debug", help="Enable debug logging and monitoring diagnostics")
def debug_monitoring(
    enable_logs: bool = typer.Option(
        True,
        "--enable-logs/--no-logs",
        help="Enable debug logging for monitoring",
    ),
    test_file: bool = typer.Option(
        False,
        "--test-file",
        help="Create a test file and monitor changes",
    ),
):
    """Enable debug logging and run monitoring diagnostics."""
    import logging
    import tempfile
    import os
    from pathlib import Path
    
    if enable_logs:
        # Configure logging
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        print("[green]Debug logging enabled[/green]")
    
    if test_file:
        print("[cyan]Running file monitoring test...[/cyan]")
        
        # Create a temporary directory for testing
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            test_file_path = temp_path / "test.py"
            
            print(f"[cyan]Test directory: {temp_path}[/cyan]")
            
            # Add the test directory to monitoring
            config_manager = ConfigManager()
            project = config_manager.add_project(temp_path)
            
            # Start monitoring
            from .monitor import ProjectMonitor
            monitor = ProjectMonitor(project)
            monitor.start()
            
            try:
                # Create test file
                print("[yellow]Creating test file...[/yellow]")
                test_file_path.write_text("def hello():\n    print('Hello, World!')\n")
                
                # Wait and modify
                import time
                time.sleep(2)
                print("[yellow]Modifying test file...[/yellow]")
                test_file_path.write_text("def hello():\n    print('Hello, Modified World!')\n")
                
                # Wait for processing
                time.sleep(3)
                print("[green]Test completed - check logs above for debug information[/green]")
                
            finally:
                monitor.stop()
                config_manager.remove_project(temp_path)


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
            # Cross-platform tail -f implementation
            import time
            with open(log_file, 'r') as f:
                # First, show the last N lines
                f.seek(0, 2)  # Go to end of file
                file_size = f.tell()
                
                # Read backwards to find the last N lines
                lines_found = 0
                position = file_size
                chunk_size = 1024
                
                while lines_found < lines and position > 0:
                    chunk_start = max(0, position - chunk_size)
                    f.seek(chunk_start)
                    chunk = f.read(position - chunk_start)
                    lines_found += chunk.count('\n')
                    position = chunk_start
                
                # Now read forward from the position we found
                if lines_found > lines:
                    # Skip extra lines at the beginning
                    for _ in range(lines_found - lines):
                        f.readline()
                
                # Print initial lines
                while True:
                    line = f.readline()
                    if not line:
                        break
                    print(line.rstrip())
                
                # Follow mode - keep reading new lines
                try:
                    while True:
                        line = f.readline()
                        if line:
                            print(line.rstrip())
                        else:
                            time.sleep(0.1)  # Small delay to avoid busy-waiting
                except KeyboardInterrupt:
                    pass
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


@app.command(name="debug", help="Debug file monitoring issues")
def debug_monitor(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose debugging",
    ),
    test_file: bool = typer.Option(
        False,
        "--test-file",
        "-t",
        help="Create a test file to verify monitoring",
    ),
):
    """Debug file monitoring issues with detailed diagnostics."""
    from rich.console import Console
    from rich.panel import Panel
    import platform
    import time
    
    console = Console()
    
    console.print(Panel("[bold]Codemap File Monitoring Debug[/bold]", expand=False))
    
    config_manager = ConfigManager()
    current_dir = Path.cwd()
    
    # Check platform
    console.print(f"[cyan]Platform:[/cyan] {platform.system()} ({platform.platform()})")
    console.print(f"[cyan]Python:[/cyan] {sys.version}")
    console.print(f"[cyan]Current directory:[/cyan] {current_dir}")
    
    # Check if current directory is monitored
    projects = config_manager.list_projects()
    is_monitored = any(str(p.path.resolve()) == str(current_dir.resolve()) for p in projects)
    
    if is_monitored:
        console.print("[green]✓ Current directory is being monitored[/green]")
    else:
        console.print("[red]✗ Current directory is NOT being monitored[/red]")
        console.print("Run 'codemap add .' to add it")
        return
    
    # Check daemon status
    if config_manager.is_daemon_running():
        console.print("[green]✓ Daemon is running[/green]")
        pid_file = config_manager.state_dir / "daemon.pid"
        if pid_file.exists():
            pid = pid_file.read_text().strip()
            console.print(f"[cyan]  PID:[/cyan] {pid}")
    else:
        console.print("[red]✗ Daemon is NOT running[/red]")
        console.print("Run 'codemap start' to start it")
        return
    
    # Check log file
    log_file = config_manager.state_dir / "daemon.log"
    if log_file.exists():
        console.print(f"[green]✓ Log file exists[/green]: {log_file}")
        size = log_file.stat().st_size
        console.print(f"[cyan]  Size:[/cyan] {size} bytes")
        if size > 0:
            console.print("[cyan]  Last 5 lines:[/cyan]")
            lines = log_file.read_text().splitlines()
            for line in lines[-5:]:
                console.print(f"    {line}")
        else:
            console.print("[yellow]  Warning: Log file is empty[/yellow]")
    else:
        console.print("[red]✗ Log file does not exist[/red]")
    
    # Check CLAUDE.md
    claude_file = current_dir / "CLAUDE.md"
    if claude_file.exists():
        console.print("[green]✓ CLAUDE.md exists[/green]")
        mtime = claude_file.stat().st_mtime
        console.print(f"[cyan]  Last modified:[/cyan] {time.ctime(mtime)}")
        size = claude_file.stat().st_size
        console.print(f"[cyan]  Size:[/cyan] {size} bytes")
    else:
        console.print("[red]✗ CLAUDE.md does not exist[/red]")
    
    # Test file monitoring if requested
    if test_file:
        console.print("\n[bold]Testing file monitoring...[/bold]")
        
        test_filename = f"test_monitor_{int(time.time())}.py"
        test_path = current_dir / test_filename
        
        # Get initial CLAUDE.md mtime
        initial_mtime = claude_file.stat().st_mtime if claude_file.exists() else 0
        
        console.print(f"Creating test file: {test_filename}")
        test_path.write_text(f"""# Test file created at {time.ctime()}
def test_function():
    return "This is a test"
""")
        
        console.print("Waiting for index update (up to 15 seconds)...")
        
        # Wait for update
        updated = False
        for i in range(30):  # 15 seconds with 0.5s intervals
            if claude_file.exists():
                current_mtime = claude_file.stat().st_mtime
                if current_mtime > initial_mtime:
                    console.print(f"[green]✓ Index updated after {(i+1)*0.5:.1f} seconds[/green]")
                    
                    # Check if test file is in index
                    content = claude_file.read_text()
                    if test_filename in content:
                        console.print("[green]✓ Test file appears in index[/green]")
                    else:
                        console.print("[red]✗ Test file does NOT appear in index[/red]")
                    
                    updated = True
                    break
            
            time.sleep(0.5)
            console.print(".", end="")
        
        if not updated:
            console.print("\n[red]✗ Index was NOT updated within 15 seconds[/red]")
            console.print("This indicates a problem with file monitoring")
        
        # Clean up
        if test_path.exists():
            test_path.unlink()
            console.print(f"\nCleaned up test file: {test_filename}")
    
    if verbose:
        console.print(f"\n[bold]Configuration Details:[/bold]")
        console.print(f"[cyan]State directory:[/cyan] {config_manager.state_dir}")
        console.print(f"[cyan]Config file:[/cyan] {config_manager.config_file}")
        
        console.print(f"\n[bold]Monitored Projects:[/bold]")
        for project in projects:
            console.print(f"[cyan]Path:[/cyan] {project.path}")
            console.print(f"[cyan]  Enabled:[/cyan] {project.enabled}")
            console.print(f"[cyan]  Update delay:[/cyan] {project.update_delay}s")
            console.print(f"[cyan]  File extensions:[/cyan] {', '.join(project.file_extensions)}")


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