"""File system monitoring for codemap."""

import asyncio
import logging
import time
import threading
from pathlib import Path
from typing import Dict, Optional, Set

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .config import ConfigManager
from .indexer import CodeIndexer
from .models import ProjectConfig

# Set up logging for debugging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ProjectMonitor(FileSystemEventHandler):
    """Monitor a single project for file changes."""
    
    def __init__(self, project_config: ProjectConfig):
        self.config = project_config
        self.indexer = CodeIndexer(project_config)
        self.pending_update = False
        self.last_event_time = time.time()
        self.observer: Optional[Observer] = None
        self._lock = threading.Lock()
        # Track recently processed paths to avoid duplicate events
        self.recent_paths: Set[str] = set()
        self.recent_paths_cleanup_time = time.time()
        # Event deduplication for Windows multiple events
        self.recent_events: Dict[str, float] = {}
        self.event_dedup_timeout = 1.0  # 1 second window for deduplication
    
    def _should_process(self, event: FileSystemEvent) -> bool:
        """Check if an event should trigger an index update."""
        if event.is_directory:
            logger.debug(f"Ignoring directory event: {event.src_path}")
            return False
        
        # Normalize path for Windows compatibility
        path = Path(event.src_path).resolve()
        path_str = str(path)
        logger.debug(f"Processing check for: {path_str}")
        
        # Don't process CLAUDE.md itself (check this first)
        if path.name == "CLAUDE.md":
            logger.debug(f"Ignoring CLAUDE.md: {path_str}")
            return False
        
        # Check if file should be ignored
        if self.indexer._should_ignore(path):
            logger.debug(f"File should be ignored (gitignore/patterns): {path_str}")
            return False
        
        # Check if it's a relevant file type
        from .config import GlobalConfig
        suffix_match = path.suffix in self.config.file_extensions
        config_match = path.name in GlobalConfig().config_files
        
        if not (suffix_match or config_match):
            logger.debug(f"File extension {path.suffix} not in monitored extensions")
            return False
        
        logger.debug(f"File extension check: {path.suffix} in {self.config.file_extensions} = {suffix_match}")
        logger.debug(f"Config file check: {path.name} in config files = {config_match}")
        
        # Only do minimal recent processing check to avoid duplicate processing within very short time
        # This is mainly to handle Windows multiple events for the same file change
        with self._lock:
            current_time = time.time()
            
            # Clean up old entries every 30 seconds
            if current_time - self.recent_paths_cleanup_time > 30:
                self.recent_paths.clear()
                self.recent_paths_cleanup_time = current_time
            
            # Only ignore if processed within last 100ms (very short window)
            recent_key = f"{path_str}:{current_time // 0.1}"  # 100ms buckets
            if recent_key in self.recent_paths:
                logger.debug(f"Recently processed (within 100ms), ignoring: {path_str}")
                return False
            
            # Add to recent paths with timestamp bucket
            self.recent_paths.add(recent_key)
        
        logger.debug(f"Final should_process result: True")
        return True
    
    def on_any_event(self, event: FileSystemEvent):
        """Handle any file system event."""
        logger.debug(f"Event received: {event.event_type} for {event.src_path}")
        
        if event.event_type in ['created', 'modified', 'deleted', 'moved']:
            # Check for duplicate events (Windows often sends multiple events)
            current_time = time.time()
            event_key = f"{event.src_path}:{event.event_type}"
            
            # Clean up old events periodically
            if current_time - self.recent_paths_cleanup_time > 5.0:
                self.recent_events = {k: v for k, v in self.recent_events.items() 
                                    if current_time - v < self.event_dedup_timeout}
                self.recent_paths_cleanup_time = current_time
            
            # Check if this is a duplicate event
            if event_key in self.recent_events:
                time_since_last = current_time - self.recent_events[event_key]
                if time_since_last < self.event_dedup_timeout:
                    logger.debug(f"Ignoring duplicate event: {event_key} (last seen {time_since_last:.2f}s ago)")
                    return
            
            # Record this event
            self.recent_events[event_key] = current_time
            
            should_process = self._should_process(event)
            logger.debug(f"Should process event: {should_process}")
            
            if should_process:
                with self._lock:
                    self.last_event_time = time.time()
                    self.pending_update = True
                    logger.debug(f"Set pending_update=True for {self.config.path}")
            else:
                logger.debug(f"Ignoring event for {event.src_path}")
        else:
            logger.debug(f"Ignoring event type: {event.event_type}")
    
    async def process_updates(self):
        """Process pending updates with debouncing."""
        consecutive_errors = 0
        
        while True:
            try:
                with self._lock:
                    has_pending = self.pending_update
                    time_since_last = time.time() - self.last_event_time if has_pending else 0
                
                if has_pending:
                    logger.debug(f"Pending update detected, time since last: {time_since_last:.2f}s")
                    # Wait for activity to settle
                    if time_since_last >= self.config.update_delay:
                        logger.debug(f"Processing update for {self.config.path}")
                        with self._lock:
                            self.pending_update = False
                        
                        try:
                            if self.indexer.update_index():
                                print(f"[{time.strftime('%H:%M:%S')}] Updated index for {self.config.path}")
                                consecutive_errors = 0
                            else:
                                logger.debug("Index update returned False")
                        except Exception as e:
                            consecutive_errors += 1
                            print(f"[{time.strftime('%H:%M:%S')}] Error updating index: {e}")
                            logger.debug(f"Exception details: {e}", exc_info=True)
                            if consecutive_errors > 3:
                                print(f"[{time.strftime('%H:%M:%S')}] Too many consecutive errors, waiting longer...")
                                await asyncio.sleep(5)
                    else:
                        logger.debug(f"Waiting for settle time: {self.config.update_delay - time_since_last:.2f}s remaining")
                
                # Use shorter sleep for better responsiveness
                await asyncio.sleep(0.2)
                
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"[{time.strftime('%H:%M:%S')}] Unexpected error in process_updates: {e}")
                await asyncio.sleep(1)
    
    def start(self):
        """Start monitoring the project."""
        if not self.config.path.exists():
            print(f"Warning: Project path {self.config.path} does not exist, skipping...")
            return
            
        if self.observer is None:
            import platform
            if platform.system() == "Windows":
                # Try native Windows observer first, fall back to polling
                try:
                    self.observer = Observer()
                    logger.debug("Using native Windows Observer")
                except Exception as e:
                    logger.debug(f"Native observer failed: {e}, falling back to PollingObserver")
                    try:
                        from watchdog.observers.polling import PollingObserver
                        self.observer = PollingObserver(timeout=0.5)
                        logger.debug("Using PollingObserver with 0.5s timeout")
                    except Exception as e2:
                        print(f"[{time.strftime('%H:%M:%S')}] Failed to create any observer: {e2}")
                        return
            else:
                self.observer = Observer()
            
            try:
                # Use resolved path for consistency
                watch_path = str(self.config.path.resolve())
                logger.debug(f"Scheduling observer for path: {watch_path}")
                self.observer.schedule(self, watch_path, recursive=True)
                logger.debug("Starting observer...")
                self.observer.start()
                logger.debug(f"Observer started successfully for {watch_path}")
                print(f"[{time.strftime('%H:%M:%S')}] Started monitoring {watch_path}")
            except Exception as e:
                print(f"[{time.strftime('%H:%M:%S')}] Failed to start observer: {e}")
                logger.debug(f"Observer start failed: {e}", exc_info=True)
                self.observer = None
                return
            
            # Initial index generation
            try:
                if self.indexer.update_index():
                    print(f"[{time.strftime('%H:%M:%S')}] Created initial index for {self.config.path}")
            except Exception as e:
                print(f"[{time.strftime('%H:%M:%S')}] Failed to create initial index: {e}")
    
    def stop(self):
        """Stop monitoring the project."""
        if self.observer:
            try:
                self.observer.stop()
                self.observer.join(timeout=5)  # Add timeout to prevent hanging
            except Exception as e:
                print(f"[{time.strftime('%H:%M:%S')}] Error stopping observer: {e}")
            finally:
                self.observer = None


class CodeMonitor:
    """Monitor multiple projects for changes."""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.monitors: Dict[str, ProjectMonitor] = {}
        self.running = False
        self.update_tasks: Dict[str, asyncio.Task] = {}
    
    def add_project(self, path: Path, start_monitoring: bool = True) -> ProjectConfig:
        """Add a project to monitor."""
        project_config = self.config_manager.add_project(path)
        
        if start_monitoring and self.running:
            self._start_project_monitor(project_config)
        
        return project_config
    
    def remove_project(self, path: Path) -> bool:
        """Remove a project from monitoring."""
        path_str = str(path.resolve())
        
        # Cancel update task if running
        if path_str in self.update_tasks:
            self.update_tasks[path_str].cancel()
            del self.update_tasks[path_str]
        
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
            
            # Create update task if we're in an event loop
            try:
                loop = asyncio.get_running_loop()
                task = loop.create_task(monitor.process_updates())
                self.update_tasks[path_str] = task
            except RuntimeError:
                # Not in an event loop yet
                pass
    
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
        
        # Create update tasks for monitors that don't have them yet
        for path_str, monitor in self.monitors.items():
            if path_str not in self.update_tasks:
                self.update_tasks[path_str] = asyncio.create_task(monitor.process_updates())
        
        try:
            if self.update_tasks:
                # Monitor tasks and restart if they fail
                while self.running:
                    # Check task health
                    for path_str, task in list(self.update_tasks.items()):
                        if task.done():
                            try:
                                # Check if task failed
                                task.result()
                            except Exception as e:
                                print(f"[{time.strftime('%H:%M:%S')}] Update task for {path_str} failed: {e}")
                                
                                # Restart the task
                                if path_str in self.monitors:
                                    print(f"[{time.strftime('%H:%M:%S')}] Restarting update task for {path_str}")
                                    self.update_tasks[path_str] = asyncio.create_task(
                                        self.monitors[path_str].process_updates()
                                    )
                    
                    # Short sleep to prevent busy waiting
                    await asyncio.sleep(1)
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
        
        # Cancel all update tasks
        for task in self.update_tasks.values():
            task.cancel()
        
        # Wait for tasks to complete
        if self.update_tasks:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If we're in the event loop, gather with timeout
                    asyncio.create_task(
                        asyncio.wait_for(
                            asyncio.gather(*self.update_tasks.values(), return_exceptions=True),
                            timeout=5.0
                        )
                    )
            except Exception:
                pass
        
        # Stop all monitors
        for monitor in self.monitors.values():
            monitor.stop()
        
        self.monitors.clear()
        self.update_tasks.clear()