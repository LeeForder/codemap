"""Code analysis utilities for extracting structure from source files."""

import ast
import re
from typing import Dict, List, Tuple


class CodeAnalyzer:
    """Analyzes code files to extract structure information."""
    
    @staticmethod
    def analyze_python(content: str) -> Tuple[List[Dict], List[Dict], List[str]]:
        """Extract functions, classes, and imports from Python code."""
        functions = []
        classes = []
        imports = []
        
        try:
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    docstring = ast.get_docstring(node) or ""
                    functions.append({
                        "name": node.name,
                        "line": node.lineno,
                        "end_line": node.end_lineno if hasattr(node, 'end_lineno') else node.lineno,
                        "docstring": docstring.split('\n')[0] if docstring else "",
                        "args": [arg.arg for arg in node.args.args]
                    })
                elif isinstance(node, ast.ClassDef):
                    docstring = ast.get_docstring(node) or ""
                    classes.append({
                        "name": node.name,
                        "line": node.lineno,
                        "end_line": node.end_lineno if hasattr(node, 'end_lineno') else node.lineno,
                        "docstring": docstring.split('\n')[0] if docstring else "",
                        "bases": [base.id for base in node.bases if hasattr(base, 'id')]
                    })
                elif isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)
        except:
            pass
        
        return functions, classes, imports
    
    @staticmethod
    def analyze_javascript(content: str) -> Tuple[List[Dict], List[Dict], List[str]]:
        """Extract functions and classes from JavaScript/TypeScript code."""
        functions = []
        classes = []
        imports = []
        
        # Simple regex-based extraction
        func_pattern = r'(?:function\s+(\w+)|const\s+(\w+)\s*=\s*(?:async\s*)?\(.*?\)\s*=>|(?:async\s+)?(\w+)\s*\(.*?\)\s*\{)'
        class_pattern = r'class\s+(\w+)(?:\s+extends\s+(\w+))?'
        import_pattern = r'import\s+.*?\s+from\s+[\'"](.+?)[\'"]'
        
        for match in re.finditer(func_pattern, content, re.MULTILINE):
            name = match.group(1) or match.group(2) or match.group(3)
            if name:
                functions.append({
                    "name": name,
                    "line": content[:match.start()].count('\n') + 1,
                    "end_line": None  # Not available with regex parsing
                })
        
        for match in re.finditer(class_pattern, content):
            classes.append({
                "name": match.group(1),
                "line": content[:match.start()].count('\n') + 1,
                "end_line": None,  # Not available with regex parsing
                "extends": match.group(2) or None
            })
        
        for match in re.finditer(import_pattern, content):
            imports.append(match.group(1))
        
        return functions, classes, imports
    
    @staticmethod
    def analyze_lua(content: str) -> Tuple[List[Dict], List[Dict], List[str]]:
        """Extract functions from Lua code."""
        functions = []
        classes = []  # Lua doesn't have classes, but may have metatables
        imports = []
        
        # Regular expressions for Lua patterns
        # Function patterns: function name(...), local function name(...), name = function(...)
        func_patterns = [
            # Standard function declaration
            r'^\s*(?:local\s+)?function\s+(\w+(?:\.\w+)*)\s*\((.*?)\)',
            # Table method declaration (obj:method or obj.method)
            r'^\s*(\w+(?:\.\w+)*):(\w+)\s*=\s*function\s*\((.*?)\)',
            r'^\s*(\w+(?:\.\w+)*)\.(\w+)\s*=\s*function\s*\((.*?)\)',
            # Variable assignment to function
            r'^\s*(?:local\s+)?(\w+)\s*=\s*function\s*\((.*?)\)'
        ]
        
        # Require/import patterns
        require_pattern = r'require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)'
        
        lines = content.split('\n')
        
        # Track function ends using indentation and 'end' keywords
        # Only capture top-level functions (not nested ones)
        in_function = False
        function_depth = 0
        
        for i, line in enumerate(lines):
            line_num = i + 1
            
            # Track function depth
            if re.match(r'^\s*(?:local\s+)?function\b', line) or re.search(r'=\s*function\s*\(', line):
                function_depth += 1
                
            # Check for 'end' keyword
            if re.match(r'^\s*end\b', line):
                if function_depth > 0:
                    function_depth -= 1
            
            # Only process top-level functions
            if function_depth > 1:
                continue
            
            # Check for function declarations
            for pattern in func_patterns:
                match = re.match(pattern, line)
                if match:
                    if len(match.groups()) == 3:  # Table method pattern
                        table_name = match.group(1)
                        method_name = match.group(2)
                        args_str = match.group(3)
                        func_name = f"{table_name}:{method_name}"
                    elif len(match.groups()) == 2:  # Regular function pattern
                        func_name = match.group(1)
                        args_str = match.group(2)
                    else:
                        continue
                    
                    # Parse arguments
                    args = [arg.strip() for arg in args_str.split(',') if arg.strip()]
                    
                    # Find the end of the function
                    end_line = line_num
                    indent_level = len(line) - len(line.lstrip())
                    depth_count = 1
                    
                    for j in range(i + 1, len(lines)):
                        current_line = lines[j]
                        # Track nested functions
                        if re.match(r'^\s*(?:local\s+)?function\b', current_line) or re.search(r'=\s*function\s*\(', current_line):
                            depth_count += 1
                        elif re.match(r'^\s*end\b', current_line):
                            depth_count -= 1
                            if depth_count == 0:
                                end_line = j + 1
                                break
                    
                    functions.append({
                        "name": func_name,
                        "line": line_num,
                        "end_line": end_line,
                        "args": args
                    })
                    break
            
            # Check for requires
            require_matches = re.findall(require_pattern, line)
            imports.extend(require_matches)
        
        return functions, classes, imports