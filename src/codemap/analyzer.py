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
    
    @staticmethod
    def analyze_ahk(content: str) -> Tuple[List[Dict], List[Dict], List[str]]:
        """Extract functions, labels, and includes from AutoHotkey v1.1 code."""
        functions = []
        classes = []
        imports = []
        
        # Regular expressions for AHK patterns
        # Function pattern: FunctionName(params) { - must start line and not be keywords
        func_pattern = r'^\s*([A-Za-z_]\w*)\s*\(\s*(.*?)\s*\)\s*\{'
        
        # Label patterns: LabelName: and hotkey patterns like ^j::, F1::, etc.
        label_pattern = r'^\s*(\w+):\s*$'
        hotkey_pattern = r'^\s*((?:[~*$+^!#<>]*[a-zA-Z0-9_\s&]+|[F]\d{1,2}|[a-zA-Z0-9_]+))::\s*'
        
        # Class pattern: class ClassName {
        class_pattern = r'^\s*class\s+(\w+)(?:\s+extends\s+(\w+))?\s*\{'
        
        # Include patterns: #Include or #IncludeAgain
        include_pattern = r'^\s*#Include(?:Again)?\s+(?:<([^>]+)>|"([^"]+)"|([^\s]+))'
        
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            line_num = i + 1
            
            # Check for functions
            func_match = re.match(func_pattern, line)
            if func_match:
                func_name = func_match.group(1)
                
                # Skip common keywords that aren't functions
                if func_name.lower() in ['if', 'else', 'while', 'for', 'loop', 'try', 'catch']:
                    continue
                    
                params_str = func_match.group(2).strip()
                
                # Parse parameters
                if params_str:
                    # Split by comma and clean up parameters
                    params = [param.strip() for param in params_str.split(',') if param.strip()]
                    # Remove default values (param := default)
                    params = [param.split(':=')[0].strip() for param in params]
                else:
                    params = []
                
                # Find the end of the function by matching braces
                end_line = line_num
                brace_count = 1
                
                for j in range(i + 1, len(lines)):
                    current_line = lines[j]
                    # Count opening and closing braces
                    brace_count += current_line.count('{') - current_line.count('}')
                    if brace_count == 0:
                        end_line = j + 1
                        break
                
                functions.append({
                    "name": func_name,
                    "line": line_num,
                    "end_line": end_line,
                    "args": params,
                    "type": "function"
                })
                continue
            
            # Check for labels (but not hotkeys)
            label_match = re.match(label_pattern, line)
            if label_match and not re.match(hotkey_pattern, line):
                label_name = label_match.group(1)
                
                # Find the end of the label (until next label, function, or return)
                end_line = line_num
                for j in range(i + 1, len(lines)):
                    next_line = lines[j].strip()
                    if (re.match(label_pattern, next_line) or 
                        re.match(func_pattern, next_line) or
                        re.match(class_pattern, next_line) or
                        next_line.lower() == 'return'):
                        end_line = j
                        break
                else:
                    end_line = len(lines)
                
                functions.append({
                    "name": label_name,
                    "line": line_num,
                    "end_line": end_line,
                    "args": [],
                    "type": "label"
                })
                continue
            
            # Check for hotkeys
            hotkey_match = re.match(hotkey_pattern, line)
            if hotkey_match:
                hotkey_name = hotkey_match.group(1)
                
                # Find the end of the hotkey
                end_line = line_num
                # If the hotkey is on the same line, it ends there
                if line.strip().endswith('::'):
                    # Multi-line hotkey, find until return or next hotkey/label
                    for j in range(i + 1, len(lines)):
                        next_line = lines[j].strip()
                        if (re.match(label_pattern, next_line) or 
                            re.match(hotkey_pattern, next_line) or
                            re.match(func_pattern, next_line) or
                            next_line.lower() == 'return'):
                            end_line = j
                            break
                    else:
                        end_line = len(lines)
                
                functions.append({
                    "name": hotkey_name,
                    "line": line_num,
                    "end_line": end_line,
                    "args": [],
                    "type": "hotkey"
                })
                continue
            
            # Check for classes
            class_match = re.match(class_pattern, line)
            if class_match:
                class_name = class_match.group(1)
                extends = class_match.group(2) if class_match.group(2) else None
                
                # Find the end of the class by matching braces
                end_line = line_num
                brace_count = 1
                
                for j in range(i + 1, len(lines)):
                    current_line = lines[j]
                    brace_count += current_line.count('{') - current_line.count('}')
                    if brace_count == 0:
                        end_line = j + 1
                        break
                
                classes.append({
                    "name": class_name,
                    "line": line_num,
                    "end_line": end_line,
                    "extends": extends
                })
                continue
            
            # Check for includes
            include_match = re.match(include_pattern, line)
            if include_match:
                # Extract the filename from any of the three capture groups
                filename = include_match.group(1) or include_match.group(2) or include_match.group(3)
                if filename:
                    imports.append(filename)
        
        return functions, classes, imports
    
    @staticmethod
    def analyze_zig(content: str) -> Tuple[List[Dict], List[Dict], List[str]]:
        """Extract functions, structs, and imports from Zig code."""
        functions = []
        classes = []  # Will store structs, enums, unions
        imports = []
        
        # Regular expressions for Zig patterns
        # Function pattern: pub fn name(...) type { or fn name(...) type {
        func_pattern = r'^\s*(?:pub\s+)?(?:inline\s+)?fn\s+([a-zA-Z_]\w*)\s*\((.*?)\)(?:\s*([^{]+?))?\s*\{'
        
        # Struct/enum/union patterns
        struct_pattern = r'^\s*(?:pub\s+)?const\s+([A-Z]\w*)\s*=\s*(struct|enum|union)(?:\([^)]*\))?\s*\{'
        
        # Import pattern: const name = @import("file");
        import_pattern = r'^\s*(?:pub\s+)?const\s+\w+\s*=\s*@import\s*\(\s*"([^"]+)"\s*\)\s*;'
        
        # Test function pattern (special case)
        test_pattern = r'^\s*test\s+"([^"]+)"\s*\{'
        
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            line_num = i + 1
            
            # Check for functions
            func_match = re.match(func_pattern, line)
            if func_match:
                func_name = func_match.group(1)
                params_str = func_match.group(2).strip()
                return_type = func_match.group(3).strip() if func_match.group(3) else ""
                
                # Parse parameters
                params = []
                if params_str:
                    # Simple parameter parsing for Zig
                    param_parts = params_str.split(',')
                    for param in param_parts:
                        param = param.strip()
                        if param and ':' in param:
                            param_name = param.split(':')[0].strip()
                            params.append(param_name)
                        elif param and param != '':
                            params.append(param)
                
                # Find the end of the function by matching braces
                end_line = line_num
                brace_count = 1
                
                for j in range(i + 1, len(lines)):
                    current_line = lines[j]
                    brace_count += current_line.count('{') - current_line.count('}')
                    if brace_count == 0:
                        end_line = j + 1
                        break
                
                functions.append({
                    "name": func_name,
                    "line": line_num,
                    "end_line": end_line,
                    "args": params,
                    "return_type": return_type
                })
                continue
            
            # Check for test functions
            test_match = re.match(test_pattern, line)
            if test_match:
                test_name = test_match.group(1)
                
                # Find the end of the test by matching braces
                end_line = line_num
                brace_count = 1
                
                for j in range(i + 1, len(lines)):
                    current_line = lines[j]
                    brace_count += current_line.count('{') - current_line.count('}')
                    if brace_count == 0:
                        end_line = j + 1
                        break
                
                functions.append({
                    "name": f'test "{test_name}"',
                    "line": line_num,
                    "end_line": end_line,
                    "args": [],
                    "return_type": ""
                })
                continue
            
            # Check for structs/enums/unions
            struct_match = re.match(struct_pattern, line)
            if struct_match:
                struct_name = struct_match.group(1)
                struct_type = struct_match.group(2)
                
                # Find the end of the struct by matching braces
                end_line = line_num
                brace_count = 1
                
                for j in range(i + 1, len(lines)):
                    current_line = lines[j]
                    brace_count += current_line.count('{') - current_line.count('}')
                    if brace_count == 0:
                        end_line = j + 1
                        break
                
                classes.append({
                    "name": struct_name,
                    "line": line_num,
                    "end_line": end_line,
                    "type": struct_type
                })
                continue
            
            # Check for imports
            import_match = re.match(import_pattern, line)
            if import_match:
                filename = import_match.group(1)
                imports.append(filename)
        
        return functions, classes, imports