"""Core indexing functionality for codemap."""

import hashlib
import os
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .analyzer import CodeAnalyzer
from .models import FileInfo, ProjectConfig


class CodeIndexer:
    """Main indexer that maintains the code index."""
    
    def __init__(self, project_config: ProjectConfig):
        self.config = project_config
        self.root_path = project_config.path
        self.file_cache: Dict[str, FileInfo] = {}
        self.last_update = datetime.now()
        self.analyzer = CodeAnalyzer()
    
    def _parse_gitignore(self) -> List[str]:
        """Parse .gitignore file and return list of patterns."""
        patterns = []
        gitignore_path = self.root_path / '.gitignore'
        if gitignore_path.exists():
            try:
                with open(gitignore_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            patterns.append(line)
            except:
                pass
        return patterns
    
    def _should_ignore(self, path: Path) -> bool:
        """Check if a path should be ignored."""
        # Normalize paths for Windows compatibility
        path = path.resolve()
        root_path = self.root_path.resolve()
        
        # Always work with relative paths for consistency
        try:
            relative_path = path.relative_to(root_path)
        except ValueError:
            # Path is not under root_path
            return True
        
        parts = relative_path.parts
        name = path.name
        # Convert to forward slashes for consistent matching
        relative_str = str(relative_path).replace('\\', '/')
        
        for pattern in self.config.ignore_patterns:
            if pattern.startswith('*'):
                if name.endswith(pattern[1:]):
                    return True
            elif pattern in parts or name == pattern:
                return True
        
        # Check .gitignore patterns
        gitignore_patterns = self._parse_gitignore()
        
        for pattern in gitignore_patterns:
            # Handle directory patterns (ending with /)
            if pattern.endswith('/') and '**/' not in pattern:
                dir_pattern = pattern.rstrip('/')
                if dir_pattern in parts or name == dir_pattern:
                    return True
            # Handle glob patterns
            elif '**/' in pattern:
                # Simple handling of **/ patterns
                suffix = pattern.split('**/')[-1].rstrip('/')
                if suffix in parts or name == suffix:
                    return True
            # Handle exact matches (normalize pattern for comparison)
            elif pattern.replace('\\', '/') == relative_str or pattern == name:
                return True
            # Handle simple patterns
            elif pattern.replace('\\', '/') in relative_str:
                return True
        
        return False
    
    def _get_file_hash(self, path: Path) -> str:
        """Calculate file hash for change detection."""
        try:
            with open(path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except:
            return ""
    
    def _analyze_file(self, path: Path) -> Optional[FileInfo]:
        """Analyze a single file and extract information."""
        if not path.exists() or not path.is_file():
            return None
        
        try:
            stat = path.stat()
            if stat.st_size > self.config.max_file_size:
                return None
            
            relative_path = str(path.relative_to(self.root_path))
            file_hash = self._get_file_hash(path)
            
            # Check cache
            if relative_path in self.file_cache:
                cached = self.file_cache[relative_path]
                if cached.hash == file_hash:
                    return cached
            
            info = FileInfo(
                path=path,
                relative_path=relative_path,
                size=stat.st_size,
                modified=stat.st_mtime,
                hash=file_hash
            )
            
            # Analyze code structure
            if path.suffix == '.py':
                try:
                    content = path.read_text(encoding='utf-8')
                    info.functions, info.classes, info.imports = self.analyzer.analyze_python(content)
                except:
                    pass
            elif path.suffix in {'.js', '.jsx', '.ts', '.tsx'}:
                try:
                    content = path.read_text(encoding='utf-8')
                    info.functions, info.classes, info.imports = self.analyzer.analyze_javascript(content)
                except:
                    pass
            elif path.suffix == '.lua':
                try:
                    content = path.read_text(encoding='utf-8')
                    info.functions, info.classes, info.imports = self.analyzer.analyze_lua(content)
                except:
                    pass
            elif path.suffix == '.ahk':
                try:
                    content = path.read_text(encoding='utf-8')
                    info.functions, info.classes, info.imports = self.analyzer.analyze_ahk(content)
                except:
                    pass
            elif path.suffix == '.zig':
                try:
                    content = path.read_text(encoding='utf-8')
                    info.functions, info.classes, info.imports = self.analyzer.analyze_zig(content)
                except:
                    pass
            
            # Get file description from first line comment
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    first_line = f.readline().strip()
                    if first_line.startswith(('#', '//', '/*')):
                        info.description = first_line.lstrip('#/').strip()
            except:
                pass
            
            return info
        except:
            return None
    
    def scan_directory(self) -> Dict[str, FileInfo]:
        """Scan the entire directory tree and build file index."""
        file_index = {}
        
        for root, dirs, files in os.walk(self.root_path):
            root_path = Path(root)
            
            # Filter out ignored directories
            dirs[:] = [d for d in dirs if not self._should_ignore(root_path / d)]
            
            # Check depth
            depth = len(root_path.relative_to(self.root_path).parts)
            if depth > self.config.max_depth:
                continue
            
            for file in files:
                file_path = root_path / file
                
                if self._should_ignore(file_path):
                    continue
                
                # Include code files and config files
                from .config import GlobalConfig
                if (file_path.suffix in self.config.file_extensions or 
                    (self.config.include_config_files and file in GlobalConfig().config_files)):
                    
                    file_info = self._analyze_file(file_path)
                    if file_info:
                        file_index[file_info.relative_path] = file_info
        
        self.file_cache = file_index
        return file_index
    
    def _build_full_tree_structure(self) -> Dict[str, List[str]]:
        """Build a complete tree structure including all directories."""
        tree_dict = defaultdict(list)
        
        # Always ignore .git directory
        default_ignore = {'.git'}
        
        # First, walk through all directories
        for root, dirs, files in os.walk(self.root_path):
            root_path = Path(root)
            
            # Filter out ignored directories before processing
            filtered_dirs = []
            for d in dirs:
                if d in default_ignore:
                    continue
                dir_path = root_path / d
                if not self._should_ignore(dir_path):
                    filtered_dirs.append(d)
            dirs[:] = filtered_dirs
            
            # Check depth
            depth = len(root_path.relative_to(self.root_path).parts)
            if depth > self.config.max_depth:
                continue
            
            relative_root = str(root_path.relative_to(self.root_path))
            if relative_root == ".":
                relative_root = ""
            
            # Add directories (already filtered)
            for d in sorted(dirs):
                tree_dict[relative_root].append(d + "/")
            
            # Add files (both indexed and non-indexed)
            for f in sorted(files):
                file_path = root_path / f
                if not self._should_ignore(file_path):
                    tree_dict[relative_root].append(f)
        
        return tree_dict
    
    def generate_tree(self, file_index: Dict[str, FileInfo]) -> str:
        """Generate a directory tree representation."""
        tree_dict = self._build_full_tree_structure()
        
        def build_tree(parent: str, prefix: str = "") -> List[str]:
            lines = []
            if parent in tree_dict:
                items = sorted(tree_dict[parent])
                for i, item in enumerate(items):
                    is_last = i == len(items) - 1
                    current_prefix = "└── " if is_last else "├── "
                    lines.append(prefix + current_prefix + item)
                    
                    # If it's a directory (ends with /), recurse
                    if item.endswith("/"):
                        child_path = str(Path(parent) / item[:-1]) if parent else item[:-1]
                        extension = "    " if is_last else "│   "
                        lines.extend(build_tree(child_path, prefix + extension))
            return lines
        
        tree_lines = build_tree("")
        return "\n".join(tree_lines)
    
    def generate_index(self) -> str:
        """Generate the complete CLAUDE.md content."""
        file_index = self.scan_directory()
        
        # Separate config files from code files
        config_files = []
        code_files = []
        
        from .config import GlobalConfig
        global_config = GlobalConfig()
        
        for info in file_index.values():            
            if info.path.name in global_config.config_files:
                config_files.append(info)
            else:
                code_files.append(info)
        
        # Helper function to convert paths to forward slashes for display
        def normalize_path_for_display(path_str):
            return path_str.replace('\\', '/')
        
        # Build the index content
        content = []
        content.append("## Current Code Index\n")
        
        # Directory structure
        content.append("### Directory Structure\n")
        content.append("```")
        content.append(self.generate_tree(file_index))
        content.append("```\n")
        
        # Configuration files
        if config_files:
            content.append("### Configuration Files\n")
            for info in sorted(config_files, key=lambda x: x.relative_path):
                desc = f" - {info.description}" if info.description else ""
                display_path = normalize_path_for_display(info.relative_path)
                content.append(f"- `{display_path}`{desc}")
            content.append("")
        
        # Project code files - unified section for all code files
        if code_files:
            content.append("### Project Code Files\n")
            for info in sorted(code_files, key=lambda x: x.relative_path):
                display_path = normalize_path_for_display(info.relative_path)
                content.append(f"#### `{display_path}`")
                if info.description:
                    content.append(f"*{info.description}*\n")
                
                if info.classes:
                    content.append("**Classes:**")
                    for cls in info.classes:
                        if info.path.suffix == '.py':
                            bases = f"({', '.join(cls['bases'])})" if cls.get('bases') else ""
                            doc = f" - {cls['docstring']}" if cls.get('docstring') else ""
                        else:
                            bases = f" extends {cls['extends']}" if cls.get('extends') else ""
                            doc = ""
                        
                        line_info = f"(line {cls['line']}"
                        if cls.get('end_line') and cls['end_line'] != cls['line']:
                            line_info += f"-{cls['end_line']}"
                        line_info += ")"
                        content.append(f"- `{cls['name']}{bases}` {line_info}{doc}")
                    content.append("")
                
                if info.functions:
                    content.append("**Functions:**")
                    for func in info.functions:
                        if info.path.suffix == '.py':
                            args = f"({', '.join(func.get('args', []))})" if func.get('args') else "()"
                            doc = f" - {func['docstring']}" if func.get('docstring') else ""
                        elif info.path.suffix in {'.lua', '.js', '.jsx', '.ts', '.tsx', '.ahk', '.zig'}:
                            args = f"({', '.join(func.get('args', []))})" if func.get('args') else "()"
                            doc = ""
                        else:
                            args = "()"
                            doc = ""
                        
                        line_info = f"(line {func['line']}"
                        if func.get('end_line') and func['end_line'] != func['line']:
                            line_info += f"-{func['end_line']}"
                        line_info += ")"
                        content.append(f"- `{func['name']}{args}` {line_info}{doc}")
                    content.append("")
                
                if info.imports:
                    imports_str = ", ".join(f"`{imp}`" for imp in sorted(set(info.imports)))
                    content.append(f"**Imports:** {imports_str}\n")
                
                content.append("")
        
        return "\n".join(content)
    
    def update_index(self):
        """Update the CLAUDE.md file with current index."""
        try:
            content = self.generate_index()
            index_path = self.root_path / "CLAUDE.md"
            
            # Read existing content if file exists
            existing_content = ""
            if index_path.exists():
                try:
                    with open(index_path, 'r', encoding='utf-8') as f:
                        existing_content = f.read()
                    
                    # Insert the important notice under # CLAUDE.md if it doesn't exist
                    notice_text = "**IMPORTANT:** The \"Current Code Index\" section below is automatically updated in real-time by a third-party tool. Always consult this index first before using search tools to understand project structure and locate files efficiently."
                    
                    # Check if notice already exists (avoid duplicates)
                    if notice_text not in existing_content:
                        # Find # CLAUDE.md header
                        claude_header_match = re.search(r'^# CLAUDE\.md\s*$', existing_content, re.MULTILINE)
                        if claude_header_match:
                            # Find the end of the header line
                            header_end = claude_header_match.end()
                            
                            # Find the next content (skip any blank lines)
                            rest_content = existing_content[header_end:]
                            next_content_match = re.search(r'\n\S', rest_content)
                            
                            if next_content_match:
                                # Insert notice before the next content
                                insert_pos = header_end + next_content_match.start() + 1
                                existing_content = (existing_content[:insert_pos] + 
                                                 notice_text + "\n\n" + 
                                                 existing_content[insert_pos:])
                            else:
                                # No content after header, append notice
                                existing_content = existing_content.rstrip() + "\n\n" + notice_text + "\n\n"
                    
                    # Find and remove the existing code index section
                    # Support both old (# Current Code Index) and new (## Current Code Index) formats
                    start_marker_new = "## Current Code Index"
                    start_marker_old = "# Current Code Index"
                    
                    start_marker = None
                    if start_marker_new in existing_content:
                        start_marker = start_marker_new
                    elif start_marker_old in existing_content:
                        start_marker = start_marker_old
                    
                    if start_marker:
                        start_pos = existing_content.find(start_marker)
                        # Find the next section that's NOT part of our index content
                        # Look for headings that are same level or higher than our start marker
                        remaining = existing_content[start_pos + len(start_marker):]
                        
                        if start_marker.startswith("##"):
                            # New format: look for next ## or # heading
                            next_section = re.search(r'\n#{1,2} (?!#)', remaining)
                        else:
                            # Old format: look for next # heading (same level)
                            next_section = re.search(r'\n# (?!#)', remaining)
                        
                        if next_section:
                            end_pos = start_pos + len(start_marker) + next_section.start()
                            existing_content = existing_content[:start_pos] + existing_content[end_pos:]
                        else:
                            # No next section found, remove everything after the marker
                            existing_content = existing_content[:start_pos]
                    
                    # Ensure proper spacing
                    existing_content = existing_content.rstrip()
                    if existing_content:
                        existing_content += "\n\n"
                except Exception as e:
                    print(f"Warning: Could not read existing CLAUDE.md: {e}")
                    existing_content = ""
            
            # Write combined content
            with open(index_path, 'w', encoding='utf-8') as f:
                f.write(existing_content + content)
            
            self.last_update = datetime.now()
            return True
        except Exception as e:
            print(f"Error updating index: {e}")
            return False