# Copyright 2026 SwaggerValidator Service Authors
#
# Core validation service engine.

import json
import urllib.request
import urllib.parse
from pathlib import Path
import copy
from rules import validate_all


class CoreValidator:
    def __init__(self):
        self.raw_spec = None
        self.resolved_spec = None
        self.broken_refs = set()
        self.circular_refs = set()
        
        self.status = True
        self.errors = []
        self.warnings = []
        self.suggestions = []

    def load_spec(self, input_source):
        """Loads OpenAPI specification from file path, local file, or URL."""
        # 1. Check if URL
        parsed_url = urllib.parse.urlparse(input_source)
        if parsed_url.scheme in ("http", "https"):
            try:
                # Use urllib to fetch the contents
                req = urllib.request.Request(
                    input_source, 
                    headers={'User-Agent': 'SwaggerValidator/1.0'}
                )
                with urllib.request.urlopen(req, timeout=10) as response:
                    content = response.read().decode('utf-8')
                return self.parse_content(content, input_source)
            except Exception as e:
                self.status = False
                self.errors.append({
                    "category": "File Validation",
                    "message": f"Failed to fetch specification from URL '{input_source}': {e}"
                })
                return False

        # 2. Local file path validation
        file_path = Path(input_source)
        
        # Check file extension
        suffix = file_path.suffix.lower()
        if suffix not in (".json", ".yaml", ".yml"):
            self.status = False
            self.errors.append({
                "category": "File Validation",
                "message": "Unsupported file format. Only .json, .yaml, and .yml extensions are supported."
            })
            return False

        # Check if file exists
        if not file_path.exists():
            self.status = False
            self.errors.append({
                "category": "File Validation",
                "message": f"File not found: {input_source}"
            })
            return False

        # Check readability/permissions
        try:
            with file_path.open(encoding="utf-8") as f:
                content = f.read()
        except PermissionError:
            self.status = False
            self.errors.append({
                "category": "File Validation",
                "message": "Access denied. Insufficient permissions to read the file."
            })
            return False
        except Exception as e:
            self.status = False
            self.errors.append({
                "category": "File Validation",
                "message": f"Failed to read file '{input_source}': {e}"
            })
            return False

        return self.parse_content(content, str(file_path.resolve()))

    def parse_content(self, content, source_label):
        """Parses raw YAML or JSON content."""
        # Try JSON first
        try:
            self.raw_spec = json.loads(content)
            return True
        except json.JSONDecodeError as json_err:
            # If JSON fails, try YAML
            try:
                import yaml
                self.raw_spec = yaml.safe_load(content)
                if not isinstance(self.raw_spec, dict):
                    raise ValueError("Parsed YAML is not an object/dictionary.")
                return True
            except ImportError:
                self.status = False
                self.errors.append({
                    "category": "Syntax Validation",
                    "message": "YAML specification detected but 'PyYAML' is not installed in the current environment. "
                               "Please run 'pip install pyyaml' to support YAML files, or convert the file to JSON."
                })
                return False
            except Exception as yaml_err:
                self.status = False
                
                # Provide a clean, readable syntax message
                if "JSON Error" in str(json_err) or "Expecting" in str(json_err):
                    syntax_msg = f"Malformed JSON: {json_err}"
                else:
                    syntax_msg = f"Invalid YAML/JSON syntax. YAML Error: {yaml_err}"
                    
                self.errors.append({
                    "category": "Syntax Validation",
                    "message": syntax_msg
                })
                return False

    def resolve_all_references(self):
        """Resolves all local references in the specification."""
        if not isinstance(self.raw_spec, dict):
            return

        self.broken_refs = set()
        self.circular_refs = set()
        
        self.resolved_spec = copy.deepcopy(self.raw_spec)
        self._resolve_recursive(self.resolved_spec, [], self.resolved_spec)

    def _resolve_recursive(self, node, path_stack, root_doc):
        """Recursively traverses the spec dictionary resolving $ref keys."""
        if isinstance(node, dict):
            if "$ref" in node:
                ref_value = node["$ref"]
                if not isinstance(ref_value, str):
                    return

                # Check for circular refs
                if ref_value in path_stack:
                    self.circular_refs.add(ref_value)
                    node["$ref_circular"] = ref_value
                    return

                # Resolve ref target
                resolved = self._get_ref_target(ref_value, root_doc)
                if resolved is None:
                    self.broken_refs.add(ref_value)
                    node["$ref_broken"] = ref_value
                    return

                if isinstance(resolved, dict):
                    path_stack.append(ref_value)
                    resolved_copy = copy.deepcopy(resolved)
                    self._resolve_recursive(resolved_copy, path_stack, root_doc)
                    path_stack.pop()
                    
                    # Merge resolved contents into node
                    node.pop("$ref")
                    for k, v in resolved_copy.items():
                        if k not in node:
                            node[k] = v
                else:
                    node["$ref_resolved_value"] = resolved
            else:
                for k, v in list(node.items()):
                    self._resolve_recursive(v, path_stack, root_doc)
        elif isinstance(node, list):
            for item in node:
                self._resolve_recursive(item, path_stack, root_doc)

    def _get_ref_target(self, ref, root_doc):
        """Resolves a local reference JSON pointer."""
        if not ref.startswith("#/"):
            return None

        parts = ref.split("/")
        curr = root_doc
        for part in parts[1:]:
            part = part.replace("~1", "/").replace("~0", "~")
            if isinstance(curr, dict) and part in curr:
                curr = curr[part]
            elif isinstance(curr, list) and part.isdigit():
                idx = int(part)
                if 0 <= idx < len(curr):
                    curr = curr[idx]
                else:
                    return None
            else:
                return None
        return curr

    def validate(self):
        """Runs the validation rules and constructs status response."""
        if self.raw_spec is None:
            self.status = False
            return False

        # Resolve references
        self.resolve_all_references()

        # Run semantic validations
        rule_errors, rule_warnings, rule_suggestions = validate_all(
            self.raw_spec, 
            self.resolved_spec, 
            self.broken_refs, 
            self.circular_refs
        )
        self.errors.extend(rule_errors)
        self.warnings.extend(rule_warnings)
        self.suggestions.extend(rule_suggestions)

        # Update boolean status
        self.status = len(self.errors) == 0
        return True

    def get_response_dict(self):
        """Returns the structured output dictionary format."""
        return {
            "status": self.status,
            "errors": self.errors,
            "warnings": self.warnings,
            "suggestions": self.suggestions
        }
