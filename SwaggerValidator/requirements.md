# Swagger/OpenAPI Validation Service - Requirements

## Objective

Develop a validation service that accepts the path of a Swagger/OpenAPI specification file and determines whether the specification is valid and can be successfully imported into Postman.

The service should return:

* Validation Status (`true` / `false`)
* Errors (if any)
* Warnings (if any)
* Suggestions (optional improvements)

No scoring, ranking, grading, or quality metrics are required.

---

# Input

## Request

The service shall accept:

```json
{
  "swaggerPath": "/path/to/swagger.yaml"
}
```

Supported formats:

* `.yaml`
* `.yml`
* `.json`

Supported versions:

* OpenAPI 3.x
* Swagger 2.0 (optional, if required)

---

# Validation Logic

## Success Criteria

Return:

```json
{
  "status": true
}
```

when:

* File can be parsed successfully.
* OpenAPI structure is valid.
* All references can be resolved.
* Specification contains no blocking validation errors.
* Specification can be imported into Postman without failure.

Warnings and suggestions may still exist.

---

## Failure Criteria

Return:

```json
{
  "status": false
}
```

when:

* Invalid YAML/JSON syntax.
* Missing required OpenAPI sections.
* Invalid schema definitions.
* Broken `$ref` references.
* Invalid request/response definitions.
* Unsupported OpenAPI structure.
* Any issue that would prevent successful import into Postman.

---

# Validation Checks

## 1. File Validation

Validate:

* File exists.
* File is readable.
* Supported extension.

Errors:

* File not found.
* Unsupported file format.
* Access denied.

---

## 2. Syntax Validation

Validate:

* Valid YAML syntax.
* Valid JSON syntax.

Errors:

Examples:

```text
Invalid YAML indentation.
Unexpected token.
Malformed JSON.
```

---

## 3. OpenAPI Structure Validation

Validate required sections:

```yaml
openapi
info
paths
```

Errors:

```text
Missing openapi field.
Missing info section.
Missing paths section.
```

---

## 4. Path Validation

Validate:

* Path definitions are valid.
* Operations contain valid HTTP methods.
* Path parameters are properly declared.

Errors:

```text
Path parameter 'id' not defined.
Invalid HTTP method.
Duplicate path definition.
```

Warnings:

```text
Path naming does not follow REST conventions.
```

---

## 5. Request Validation

Validate:

* Request body schema exists when required.
* Parameter definitions are valid.
* Content types are properly defined.

Errors:

```text
Missing schema in request body.
Invalid parameter definition.
```

Warnings:

```text
Missing parameter description.
```

---

## 6. Response Validation

Validate:

* Response definitions exist.
* Response schemas are valid.

Errors:

```text
Missing success response.
Invalid response schema.
```

Warnings:

```text
Response description missing.
```

---

## 7. Schema Validation

Validate:

* Schema types are valid.
* Required properties exist.
* Enum definitions are valid.

Errors:

```text
Unknown schema type.
Invalid enum value definition.
```

Warnings:

```text
Schema property missing description.
```

---

## 8. Reference Validation

Validate all:

```yaml
$ref
```

Errors:

```text
Broken reference:
#/components/schemas/User
```

```text
Referenced schema not found.
```

---

## 9. Security Validation

Validate referenced security schemes.

Errors:

```text
Security scheme referenced but not defined.
```

Warnings:

```text
No security scheme configured.
```

---

## 10. Documentation Validation

Warnings only.

Examples:

```text
Endpoint summary missing.
Endpoint description missing.
Schema description missing.
No example provided.
```

---

# Response Format

## Successful Validation

```json
{
  "status": true,
  "errors": [],
  "warnings": [
    "Schema 'User' is missing description.",
    "GET /users does not contain response examples."
  ],
  "suggestions": [
    "Add descriptions for all schema properties.",
    "Provide request and response examples."
  ]
}
```

---

## Failed Validation

```json
{
  "status": false,
  "errors": [
    {
      "category": "Reference Validation",
      "message": "Broken reference '#/components/schemas/User'"
    },
    {
      "category": "Schema Validation",
      "message": "Invalid schema type 'strng'"
    }
  ],
  "warnings": [
    "Endpoint summary missing for GET /users"
  ],
  "suggestions": [
    "Define missing schema 'User'.",
    "Replace invalid type 'strng' with 'string'."
  ]
}
```

---

# Functional Requirements

## FR-001

System shall accept a Swagger/OpenAPI file path.

## FR-002

System shall load and parse the specification.

## FR-003

System shall validate syntax.

## FR-004

System shall validate OpenAPI structure.

## FR-005

System shall validate paths and operations.

## FR-006

System shall validate requests and responses.

## FR-007

System shall validate schemas.

## FR-008

System shall validate references.

## FR-009

System shall validate security definitions.

## FR-010

System shall return a boolean status.

## FR-011

System shall return validation errors.

## FR-012

System shall return warnings.

## FR-013

System shall return suggestions.

## FR-014

Status shall be `false` if any error exists.

## FR-015

Status shall be `true` if no blocking errors exist, even when warnings are present.

---

# Expected Behavior

| Scenario                            | Status |
| ----------------------------------- | ------ |
| Valid Swagger, no issues            | true   |
| Valid Swagger with warnings         | true   |
| Valid Swagger with suggestions      | true   |
| Broken YAML/JSON                    | false  |
| Missing required OpenAPI fields     | false  |
| Broken references                   | false  |
| Invalid schema definitions          | false  |
| Any issue preventing Postman import | false  |
