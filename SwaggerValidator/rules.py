# Copyright 2026 SwaggerValidator Service Authors
#
# Refactored OpenAPI 3.x and Swagger 2.0 validation rules.

import re

def validate_all(spec, resolved_spec, broken_refs, circular_refs):
    """
    Runs all validation rules against the specification.
    spec: The raw parsed specification dictionary (with unresolved references).
    resolved_spec: The specification dictionary with resolved references.
    broken_refs: Set/list of broken references found during parsing.
    circular_refs: Set/list of circular references found during parsing.
    
    Returns:
      errors: List of dicts [{"category": str, "message": str}]
      warnings: List of strings
      suggestions: List of strings
    """
    errors = []
    warnings = []
    suggestions = []

    # Basic dictionary check
    if not isinstance(spec, dict):
        errors.append({
            "category": "Syntax Validation",
            "message": "Input spec is not a valid JSON/YAML object structure."
        })
        return errors, warnings, suggestions

    # 1. Structure & Version check
    validate_openapi_structure(spec, errors, warnings, suggestions)

    # If basic structure is missing, we can't run further semantic rules
    if not spec.get("paths") or not isinstance(spec.get("paths"), dict):
        return errors, warnings, suggestions

    # 2. Add parser-detected reference issues
    for ref in broken_refs:
        errors.append({
            "category": "Reference Validation",
            "message": f"Broken reference '{ref}'"
        })
        # Parse schema name if possible to suggest defining it
        schema_name = ref.split("/")[-1] if "/" in ref else "Schema"
        suggestions.append(f"Define missing schema '{schema_name}'.")

    for ref in circular_refs:
        errors.append({
            "category": "Reference Validation",
            "message": f"Circular reference detected at '{ref}'"
        })

    # 3. Path Validation
    validate_paths(spec, resolved_spec, errors, warnings, suggestions)

    # 4. Request Validation
    validate_requests(spec, resolved_spec, errors, warnings, suggestions)

    # 5. Response Validation
    validate_responses(spec, resolved_spec, errors, warnings, suggestions)

    # 6. Schema Validation
    validate_schemas(spec, resolved_spec, errors, warnings, suggestions)

    # 7. Security Validation
    validate_security(spec, resolved_spec, errors, warnings, suggestions)

    # 8. Documentation Validation
    validate_documentation(spec, resolved_spec, errors, warnings, suggestions)

    # Remove duplicates from warnings and suggestions to keep the output clean
    warnings = list(dict.fromkeys(warnings))
    suggestions = list(dict.fromkeys(suggestions))

    return errors, warnings, suggestions


def validate_openapi_structure(spec, errors, warnings, suggestions):
    category = "OpenAPI Structure Validation"
    
    # Check version field
    if "openapi" not in spec and "swagger" not in spec:
        errors.append({
            "category": category,
            "message": "Missing openapi version field (e.g. 'openapi' or 'swagger')."
        })
        suggestions.append("Add 'openapi: 3.0.0' or 'openapi: 3.1.0' to define the specification version.")
    elif "openapi" in spec:
        version = str(spec["openapi"])
        if not (version.startswith("3.0") or version.startswith("3.1")):
            errors.append({
                "category": category,
                "message": f"Unsupported OpenAPI version '{version}'. Only OpenAPI 3.x is supported."
            })
            suggestions.append("Upgrade the specification to OpenAPI version 3.0.x or 3.1.x.")
    elif "swagger" in spec:
        version = str(spec["swagger"])
        if version != "2.0":
            errors.append({
                "category": category,
                "message": f"Unsupported Swagger version '{version}'. Only Swagger 2.0 or OpenAPI 3.x is supported."
            })

    # Check required sections
    if "info" not in spec:
        errors.append({
            "category": category,
            "message": "Missing info section."
        })
        suggestions.append("Add an 'info' section containing 'title' and 'version' properties.")
    else:
        info = spec["info"]
        if not isinstance(info, dict):
            errors.append({
                "category": category,
                "message": "Info section must be a JSON/YAML object."
            })
        else:
            if "title" not in info or not info["title"]:
                errors.append({
                    "category": category,
                    "message": "Missing info.title field."
                })
                suggestions.append("Specify a 'title' for the API in the 'info' section.")
            if "version" not in info or not info["version"]:
                errors.append({
                    "category": category,
                    "message": "Missing info.version field."
                })
                suggestions.append("Specify a 'version' for the API in the 'info' section.")

    if "paths" not in spec:
        errors.append({
            "category": category,
            "message": "Missing paths section."
        })
        suggestions.append("Add a 'paths' section to declare API endpoints.")


def validate_paths(spec, resolved_spec, errors, warnings, suggestions):
    category = "Path Validation"
    paths = spec.get("paths", {})
    if not isinstance(paths, dict):
        return

    valid_methods = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
    verb_patterns = [
        r"/get[A-Z0-9]", r"/create[A-Z0-9]", r"/delete[A-Z0-9]", r"/update[A-Z0-9]", r"/remove[A-Z0-9]",
        r"/get-", r"/create-", r"/delete-", r"/update-", r"/remove-",
        r"/get_", r"/create_", r"/delete_", r"/update_", r"/remove_"
    ]

    for path_template, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue

        # Check REST conventions (Warning)
        for pattern in verb_patterns:
            if re.search(pattern, path_template):
                warnings.append(f"Path naming does not follow REST conventions: '{path_template}'.")
                suggestions.append(f"Rename path '{path_template}' to use plural nouns (e.g. '/users' instead of '/getUsers').")
                break

        # Check duplicate path definitions (if any, although dict keys are unique in YAML/JSON,
        # user might define path templates that resolve to same endpoint like `/users/{id}` and `/users/{userId}`)
        # We can run a check for equivalent normalized paths:
        # e.g. `/users/{id}` normalized is `/users/{}`, `/users/{userId}` normalized is `/users/{}`.

        # Find path parameters defined in path template (e.g. {id}, {userId})
        path_params_in_template = re.findall(r'\{([a-zA-Z0-9_]+)\}', path_template)

        # Get resolved path item to inspect parameters
        resolved_path_item = resolved_spec.get("paths", {}).get(path_template, {})
        if not isinstance(resolved_path_item, dict):
            resolved_path_item = {}

        path_level_params = resolved_path_item.get("parameters", [])
        if not isinstance(path_level_params, list):
            path_level_params = []

        # Validate operations in this path
        for method, operation in path_item.items():
            if method.startswith("x-"):
                continue
            if method in {"summary", "description", "servers", "parameters"}:
                continue

            loc_str = f"{method.upper()} {path_template}"

            if method not in valid_methods:
                errors.append({
                    "category": category,
                    "message": f"Invalid HTTP method '{method}' at path '{path_template}'."
                })
                continue

            if not isinstance(operation, dict):
                continue

            # Combined list of parameters for path parameter verification
            resolved_operation = resolved_path_item.get(method, {})
            op_level_params = resolved_operation.get("parameters", [])
            if not isinstance(op_level_params, list):
                op_level_params = []

            all_params = op_level_params + [p for p in path_level_params if p.get("name") not in [op_p.get("name") for op_p in op_level_params]]

            # Check path parameters
            for param_name in path_params_in_template:
                param_def = next((p for p in all_params if p.get("name") == param_name and p.get("in") == "path"), None)
                if not param_def:
                    errors.append({
                        "category": category,
                        "message": f"Path parameter '{param_name}' not defined for {loc_str}."
                    })
                    suggestions.append(f"Define path parameter '{param_name}' in the parameters list for {loc_str}.")
                else:
                    if not param_def.get("required"):
                        errors.append({
                            "category": category,
                            "message": f"Path parameter '{param_name}' must be marked as required for {loc_str}."
                        })
                        suggestions.append(f"Set 'required: true' for path parameter '{param_name}' in {loc_str}.")


def validate_requests(spec, resolved_spec, errors, warnings, suggestions):
    category = "Request Validation"
    paths = resolved_spec.get("paths", {})
    if not isinstance(paths, dict):
        return

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method not in {"get", "put", "post", "delete", "options", "head", "patch"}:
                continue
            if not isinstance(operation, dict):
                continue

            loc_str = f"{method.upper()} {path}"

            # requestBody checks
            if method in {"post", "put", "patch"}:
                rb = operation.get("requestBody")
                if rb:
                    if not isinstance(rb, dict):
                        errors.append({
                            "category": category,
                            "message": f"Invalid request body definition in {loc_str}."
                        })
                    else:
                        content = rb.get("content")
                        if not content or not isinstance(content, dict):
                            errors.append({
                                "category": category,
                                "message": f"Missing content definition in request body for {loc_str}."
                            })
                            suggestions.append(f"Add a 'content' object under requestBody for {loc_str}.")
                        else:
                            for media_type, media_item in content.items():
                                if not isinstance(media_item, dict) or "schema" not in media_item:
                                    errors.append({
                                        "category": category,
                                        "message": f"Missing schema in request body content type '{media_type}' for {loc_str}."
                                    })
                                    suggestions.append(f"Define a 'schema' object under requestBody content type '{media_type}' for {loc_str}.")

            # Parameter checks
            parameters = operation.get("parameters", [])
            if isinstance(parameters, list):
                for idx, param in enumerate(parameters):
                    if not isinstance(param, dict):
                        continue
                    p_name = param.get("name", f"param[{idx}]")
                    p_in = param.get("in")
                    p_loc = f"{loc_str} (parameter: {p_name})"

                    if p_in not in {"query", "header", "path", "cookie"}:
                        errors.append({
                            "category": category,
                            "message": f"Invalid parameter definition location 'in: {p_in}' for parameter '{p_name}' in {loc_str}."
                        })
                        continue

                    # Validate schema exists
                    if "schema" not in param:
                        errors.append({
                            "category": category,
                            "message": f"Parameter '{p_name}' is missing schema definition in {loc_str}."
                        })
                        suggestions.append(f"Add a 'schema' property to parameter '{p_name}' in {loc_str}.")

                    # Warning on description
                    if not param.get("description"):
                        warnings.append(f"Missing parameter description for '{p_name}' in {loc_str}.")
                        suggestions.append(f"Add a 'description' to parameter '{p_name}' in {loc_str}.")


def validate_responses(spec, resolved_spec, errors, warnings, suggestions):
    category = "Response Validation"
    paths = resolved_spec.get("paths", {})
    if not isinstance(paths, dict):
        return

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method not in {"get", "put", "post", "delete", "options", "head", "patch"}:
                continue
            if not isinstance(operation, dict):
                continue

            loc_str = f"{method.upper()} {path}"
            responses = operation.get("responses")

            if not responses or not isinstance(responses, dict):
                errors.append({
                    "category": category,
                    "message": f"Missing response definitions in {loc_str}."
                })
                suggestions.append(f"Add a 'responses' object for {loc_str} with at least one success status code.")
                continue

            # Verify existence of success response code (200, 201, 202, 204 or 2XX)
            has_success = False
            for code in responses.keys():
                if code in {"200", "201", "202", "204"} or code.startswith("2"):
                    has_success = True
                    break

            if not has_success:
                errors.append({
                    "category": category,
                    "message": f"Missing success response code (2xx) for {loc_str}."
                })
                suggestions.append(f"Define at least one successful response status code (e.g. 200 or 201) under {loc_str}.responses.")

            # Validate response schema and warnings
            for code, resp in responses.items():
                if not isinstance(resp, dict):
                    continue

                resp_loc = f"{loc_str} (response: {code})"

                if not resp.get("description"):
                    warnings.append(f"Response description missing for status '{code}' in {loc_str}.")
                    suggestions.append(f"Add a 'description' to response status '{code}' in {loc_str}.")

                if code == "204":
                    continue  # 204 has no content

                content = resp.get("content")
                if not content:
                    # Fail validation if success response contains no content/schema structure
                    if code.startswith("2") and code != "204":
                        errors.append({
                            "category": category,
                            "message": f"Success response '{code}' has no content defined in {loc_str}."
                        })
                        suggestions.append(f"Add a 'content' object with schema under response '{code}' in {loc_str}.")
                else:
                    if not isinstance(content, dict):
                        errors.append({
                            "category": category,
                            "message": f"Invalid content object format in response '{code}' for {loc_str}."
                        })
                    else:
                        for media_type, media_item in content.items():
                            if not isinstance(media_item, dict) or "schema" not in media_item:
                                errors.append({
                                    "category": category,
                                    "message": f"Invalid response schema under content type '{media_type}' for response '{code}' in {loc_str}."
                                })
                                suggestions.append(f"Specify a 'schema' object for content type '{media_type}' in response '{code}' of {loc_str}.")


def validate_schemas(spec, resolved_spec, errors, warnings, suggestions):
    category = "Schema Validation"
    components = resolved_spec.get("components", {})
    if not isinstance(components, dict):
        return
    schemas = components.get("schemas", {})
    if not isinstance(schemas, dict):
        return

    allowed_types = {"string", "integer", "number", "boolean", "array", "object"}

    for s_name, schema in schemas.items():
        if not isinstance(schema, dict):
            continue
        
        s_loc = f"components.schemas.{s_name}"
        validate_single_schema(schema, s_loc, allowed_types, errors, warnings, suggestions)


def validate_single_schema(schema, loc, allowed_types, errors, warnings, suggestions):
    category = "Schema Validation"
    if not isinstance(schema, dict):
        return

    s_type = schema.get("type")
    
    if not s_type:
        has_combinator = any(key in schema for key in ["allOf", "anyOf", "oneOf"])
        if not has_combinator and "$ref" not in schema:
            errors.append({
                "category": category,
                "message": f"Missing schema type at '{loc}'."
            })
            suggestions.append(f"Specify a 'type' (e.g. 'object', 'string') for schema at '{loc}'.")
    else:
        if s_type not in allowed_types:
            errors.append({
                "category": category,
                "message": f"Unknown schema type '{s_type}' at '{loc}'."
            })
            suggestions.append(f"Replace invalid type '{s_type}' with a valid one (string, integer, number, boolean, array, object).")

    # Required validation
    required = schema.get("required")
    if required:
        if not isinstance(required, list):
            errors.append({
                "category": category,
                "message": f"'required' property must be an array at '{loc}'."
            })
        else:
            properties = schema.get("properties", {})
            for req_field in required:
                if not isinstance(properties, dict) or req_field not in properties:
                    errors.append({
                        "category": category,
                        "message": f"Required property '{req_field}' is not defined under 'properties' in '{loc}'."
                    })
                    suggestions.append(f"Define required property '{req_field}' under properties in '{loc}'.")

    # Enum validation
    enum_vals = schema.get("enum")
    if enum_vals:
        if not isinstance(enum_vals, list):
            errors.append({
                "category": category,
                "message": f"Enum definition must be an array at '{loc}'."
            })
        elif s_type:
            # Check type consistency
            for val in enum_vals:
                is_valid = True
                if s_type == "string" and not isinstance(val, str):
                    is_valid = False
                elif s_type == "integer" and not (isinstance(val, int) and not isinstance(val, bool)):
                    is_valid = False
                elif s_type == "number" and not isinstance(val, (int, float)):
                    is_valid = False
                elif s_type == "boolean" and not isinstance(val, bool):
                    is_valid = False

                if not is_valid:
                    errors.append({
                        "category": category,
                        "message": f"Invalid enum value definition '{val}' for type '{s_type}' at '{loc}'."
                    })
                    suggestions.append(f"Change enum value '{val}' to match the defined schema type '{s_type}' at '{loc}'.")

    # Warning on property descriptions
    properties = schema.get("properties", {})
    if isinstance(properties, dict):
        for prop_name, prop_schema in properties.items():
            if isinstance(prop_schema, dict):
                if not prop_schema.get("description"):
                    warnings.append(f"Schema property missing description: '{loc}.{prop_name}'.")
                    suggestions.append(f"Add a 'description' to property '{prop_name}' in '{loc}'.")
                validate_single_schema(prop_schema, f"{loc}.{prop_name}", allowed_types, errors, warnings, suggestions)

    # Array items
    if s_type == "array":
        items = schema.get("items")
        if not items:
            errors.append({
                "category": category,
                "message": f"Array schema missing 'items' definition at '{loc}'."
            })
            suggestions.append(f"Add 'items' definition to array schema at '{loc}'.")
        elif isinstance(items, dict):
            validate_single_schema(items, f"{loc}.items", allowed_types, errors, warnings, suggestions)


def validate_security(spec, resolved_spec, errors, warnings, suggestions):
    category = "Security Validation"
    components = resolved_spec.get("components", {})
    if not isinstance(components, dict):
        return

    security_schemes = components.get("securitySchemes", {})
    defined_schemes = set()

    if security_schemes and isinstance(security_schemes, dict):
        for s_name in security_schemes.keys():
            defined_schemes.add(s_name)

    # Check endpoints referencing schemes
    global_security = spec.get("security", [])
    has_any_security = len(global_security) > 0

    if isinstance(global_security, list):
        for idx, sec_req in enumerate(global_security):
            if not isinstance(sec_req, dict):
                continue
            for scheme_name in sec_req.keys():
                if scheme_name not in defined_schemes:
                    errors.append({
                        "category": category,
                        "message": f"Security scheme referenced but not defined: '{scheme_name}'."
                    })
                    suggestions.append(f"Define referenced security scheme '{scheme_name}' in components.securitySchemes.")

    paths = spec.get("paths", {})
    if isinstance(paths, dict):
        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            for method, operation in path_item.items():
                if method not in {"get", "put", "post", "delete", "options", "head", "patch"}:
                    continue
                if not isinstance(operation, dict):
                    continue

                loc_str = f"{method.upper()} {path}"
                op_security = operation.get("security")

                if op_security is not None:
                    if isinstance(op_security, list):
                        if len(op_security) > 0:
                            has_any_security = True
                        for idx, sec_req in enumerate(op_security):
                            if not isinstance(sec_req, dict):
                                continue
                            for scheme_name in sec_req.keys():
                                if scheme_name not in defined_schemes:
                                    errors.append({
                                        "category": category,
                                        "message": f"Security scheme referenced but not defined: '{scheme_name}' for {loc_str}."
                                    })
                                    suggestions.append(f"Define referenced security scheme '{scheme_name}' in components.securitySchemes.")

    # Warning if no security scheme configured
    if not has_any_security:
        warnings.append("No security scheme configured for the specification.")
        suggestions.append("Define securitySchemes and reference them globally or on individual endpoints to secure your API.")


def validate_documentation(spec, resolved_spec, errors, warnings, suggestions):
    # Documentation checks are warnings only
    paths = resolved_spec.get("paths", {})
    if not isinstance(paths, dict):
        return

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method not in {"get", "put", "post", "delete", "options", "head", "patch"}:
                continue
            if not isinstance(operation, dict):
                continue

            loc_str = f"{method.upper()} {path}"

            if not operation.get("summary"):
                warnings.append(f"Endpoint summary missing: {loc_str}")
                suggestions.append(f"Add a brief 'summary' for endpoint {loc_str}.")
            if not operation.get("description"):
                warnings.append(f"Endpoint description missing: {loc_str}")
                suggestions.append(f"Add a 'description' to detail the behavior of endpoint {loc_str}.")

            # Examples check (warnings only)
            has_example = False
            
            # Check response examples
            responses = operation.get("responses", {})
            if isinstance(responses, dict):
                for code, resp in responses.items():
                    if isinstance(resp, dict):
                        content = resp.get("content", {})
                        if isinstance(content, dict):
                            for media_type, media_item in content.items():
                                if isinstance(media_item, dict):
                                    if "example" in media_item or "examples" in media_item:
                                        has_example = True
                                    schema = media_item.get("schema", {})
                                    if isinstance(schema, dict) and ("example" in schema or "examples" in schema):
                                        has_example = True

            # Check request body examples
            rb = operation.get("requestBody")
            if isinstance(rb, dict):
                content = rb.get("content", {})
                if isinstance(content, dict):
                    for media_type, media_item in content.items():
                        if isinstance(media_item, dict):
                            if "example" in media_item or "examples" in media_item:
                                    has_example = True
                            schema = media_item.get("schema", {})
                            if isinstance(schema, dict) and ("example" in schema or "examples" in schema):
                                has_example = True

            if not has_example:
                warnings.append(f"No example provided for request/response in {loc_str}.")
                suggestions.append(f"Provide request and response examples for {loc_str} to improve documentation.")

    # Schema description check (warnings)
    components = resolved_spec.get("components", {})
    if isinstance(components, dict):
        schemas = components.get("schemas", {})
        if isinstance(schemas, dict):
            for s_name, schema in schemas.items():
                if isinstance(schema, dict) and not schema.get("description"):
                    warnings.append(f"Schema description missing: 'components.schemas.{s_name}'")
                    suggestions.append(f"Add a 'description' to schema definition 'components.schemas.{s_name}'.")
