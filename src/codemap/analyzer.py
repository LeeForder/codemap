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
                        "docstring": docstring.split('\n')[0] if docstring else "",
                        "args": [arg.arg for arg in node.args.args]
                    })
                elif isinstance(node, ast.ClassDef):
                    docstring = ast.get_docstring(node) or ""
                    classes.append({
                        "name": node.name,
                        "line": node.lineno,
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
                    "line": content[:match.start()].count('\n') + 1
                })
        
        for match in re.finditer(class_pattern, content):
            classes.append({
                "name": match.group(1),
                "line": content[:match.start()].count('\n') + 1,
                "extends": match.group(2) or None
            })
        
        for match in re.finditer(import_pattern, content):
            imports.append(match.group(1))
        
        return functions, classes, imports