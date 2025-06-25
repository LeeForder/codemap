"""File system monitoring for codemap."""

import asyncio
import time
from pathlib import Path
from typing import Dict, Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .config import ConfigManager
from .indexer import CodeIndexer
from .models import ProjectConfig


class ProjectMonitor(FileSystemEventHandler):
    """Monitor a single project for file changes."""
    
    def __init__(self, project_config: ProjectConfig):
        self.config = project_config
        self.indexer = CodeIndexer(project_config)
        self.pending_update = False
        self.last_event_time = time.time()
        self.observer: Optional[Observer] = None
    
    def _should_process(self, event: FileSystemEvent) -> bool:
        """Check if an event should trigger an index update."""
        if event.is_directory:
            return False
        
        # Normalize path for Windows compatibility
        path = Path(event.src_path).resolve()
        
        # Don't process CLAUDE.md itself
        if path.name == "CLAUDE.md":
            return False
        
        # Check if file should be ignored
        if self.indexer._should_ignore(path):
            return False
        
        # Check if it's a relevant file type
        from .config import GlobalConfig
        return (path.suffix in self.config.file_extensions or
                path.name in GlobalConfig().config_files)
    
    def on_any_event(self, event: FileSystemEvent):
        """Handle any file system event."""
        if event.event_type in ['created', 'modified', 'deleted', 'moved']:
            if self._should_process(event):
                self.last_event_time = time.time()
                self.pending_update = True
    
    async def process_updates(self):
        """Process pending updates with debouncing."""
        while True:
            if self.pending_update:
                # Wait for activity to settle
                time_since_last = time.time() - self.last_event_time
                if time_since_last >= self.config.update_delay:
                    self.pending_update = False
                    if self.indexer.update_index():
                        print(f"[{time.strftime('%H:%M:%S')}] Updated index for {self.config.path}")
            
            await asyncio.sleep(0.5)
    
    def start(self):
        """Start monitoring the project."""
        if not self.config.path.exists():
            print(f"Warning: Project path {self.config.path} does not exist, skipping...")
            return
            
        if self.observer is None:
            import platform
            if platform.system() == "Windows":
                # Use polling observer on Windows for better reliability
                from watchdog.observers.polling import PollingObserver
                self.observer = PollingObserver(timeout=1)
            else:
                self.observer = Observer()
            
            # Use resolved path for consistency
            self.observer.schedule(self, str(self.config.path.resolve()), recursive=True)
            self.observer.start()
            
            # Initial index generation
            if self.indexer.update_index():
                print(f"[{time.strftime('%H:%M:%S')}] Created initial index for {self.config.path}")
    
    def stop(self):
        """Stop monitoring the project."""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None


class CodeMonitor:
    """Monitor multiple projects for changes."""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.monitors: Dict[str, ProjectMonitor] = {}
        self.running = False
    
    def add_project(self, path: Path, start_monitoring: bool = True) -> ProjectConfig:
        """Add a project to monitor."""
        project_config = self.config_manager.add_project(path)
        
        if start_monitoring and self.running:
            self._start_project_monitor(project_config)
        
        return project_config
    
    def remove_project(self, path: Path) -> bool:
        """Remove a project from monitoring."""
        path_str = str(path.resolve())
        
        # Stop monitor if running
        if path_str in self.monitors:
            self.monitors[path_str].stop()
            del self.monitors[path_str]
        
        return self.config_manager.remove_project(path)
    
    def _start_project_monitor(self, project_config: ProjectConfig):
        """Start monitoring a specific project."""
        path_str = str(project_config.path.resolve())
        
        if path_str not in self.monitors and project_config.enabled:
            monitor = ProjectMonitor(project_config)
            monitor.start()
            self.monitors[path_str] = monitor
    
    async def run(self):
        """Run the monitoring service."""
        import signal
        import platform
        
        self.running = True
        
        # Set up signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            print(f"\nReceived signal {signum}, shutting down gracefully...")
            self.stop()
        
        # Windows only supports SIGINT (Ctrl+C) and SIGBREAK
        if platform.system() == "Windows":
            signal.signal(signal.SIGINT, signal_handler)
            # SIGBREAK is Windows-specific, similar to SIGTERM
            if hasattr(signal, 'SIGBREAK'):
                signal.signal(signal.SIGBREAK, signal_handler)
        else:
            # Unix-like systems support more signals
            signal.signal(signal.SIGTERM, signal_handler)
            signal.signal(signal.SIGINT, signal_handler)
        
        # Start monitoring all enabled projects
        for project in self.config_manager.list_projects():
            if project.enabled:
                self._start_project_monitor(project)
        
        print(f"Monitoring {len(self.monitors)} project(s)")
        
        # Run update processors for all monitors
        tasks = []
        for monitor in self.monitors.values():
            tasks.append(asyncio.create_task(monitor.process_updates()))
        
        try:
            if tasks:
                await asyncio.gather(*tasks)
            else:
                # No projects to monitor, just wait
                print("No projects to monitor. Waiting for configuration changes...")
                while self.running:
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            print("Monitoring tasks cancelled")
        except KeyboardInterrupt:
            print("\nShutting down monitors...")
        finally:
            self.stop()
    
    def stop(self):
        """Stop all monitors."""
        self.running = False
        for monitor in self.monitors.values():
            monitor.stop()
        self.monitors.clear()