# Copyright 2026 SwaggerValidator Service Authors
#
# Updated Unit Tests for Swagger/OpenAPI Validation Service.

import unittest
import json
import tempfile
from pathlib import Path
from core import CoreValidator


class TestSwaggerValidator(unittest.TestCase):
    def setUp(self):
        self.validator = CoreValidator()

    def create_temp_spec_file(self, content_dict, suffix=".json"):
        """Creates a temporary file with spec content and returns its path."""
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8")
        json.dump(content_dict, tmp)
        tmp.close()
        return tmp.name

    def delete_temp_file(self, path):
        Path(path).unlink(missing_ok=True)

    def test_unsupported_file_extension(self):
        self.assertFalse(self.validator.load_spec("test_spec.txt"))
        self.assertFalse(self.validator.status)
        self.assertEqual(len(self.validator.errors), 1)
        self.assertEqual(self.validator.errors[0]["category"], "File Validation")
        self.assertIn("Unsupported file format", self.validator.errors[0]["message"])

    def test_file_not_found(self):
        self.assertFalse(self.validator.load_spec("non_existent_file.json"))
        self.assertFalse(self.validator.status)
        self.assertEqual(len(self.validator.errors), 1)
        self.assertEqual(self.validator.errors[0]["category"], "File Validation")
        self.assertIn("File not found", self.validator.errors[0]["message"])

    def test_invalid_json_syntax(self):
        tmp_name = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
        tmp_name.write("{ malformed json")
        tmp_name.close()

        self.assertFalse(self.validator.load_spec(tmp_name.name))
        self.assertFalse(self.validator.status)
        self.assertEqual(self.validator.errors[0]["category"], "Syntax Validation")
        self.assertIn("Malformed JSON", self.validator.errors[0]["message"])
        
        self.delete_temp_file(tmp_name.name)

    def test_missing_openapi_structure(self):
        spec = {
            "info": {
                "title": "Minimal API",
                "version": "1.0.0"
            }
            # missing openapi and paths
        }
        path = self.create_temp_spec_file(spec)
        self.assertTrue(self.validator.load_spec(path))
        self.assertTrue(self.validator.validate())
        
        resp = self.validator.get_response_dict()
        self.assertFalse(resp["status"])
        
        # Should have structure validation errors
        categories = [e["category"] for e in resp["errors"]]
        self.assertIn("OpenAPI Structure Validation", categories)
        
        self.delete_temp_file(path)

    def test_valid_openapi_with_warnings(self):
        spec = {
            "openapi": "3.0.0",
            "info": {
                "title": "API with warnings",
                "version": "1.0.0"
                # description missing (warning)
            },
            "paths": {
                "/users": {
                    "get": {
                        # summary/description missing (warning)
                        "responses": {
                            "200": {
                                "description": "OK",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object"
                                        }
                                    }
                                }
                                # example missing (warning)
                            }
                        }
                    }
                }
            }
        }
        path = self.create_temp_spec_file(spec)
        self.assertTrue(self.validator.load_spec(path))
        self.assertTrue(self.validator.validate())
        
        resp = self.validator.get_response_dict()
        
        # Status should be true as there are no blocking errors
        self.assertTrue(resp["status"])
        self.assertEqual(len(resp["errors"]), 0)
        
        # Should contain documentation warnings
        self.assertTrue(len(resp["warnings"]) > 0)
        self.assertTrue(any("Endpoint summary missing" in w for w in resp["warnings"]))
        
        self.delete_temp_file(path)

    def test_path_parameter_not_defined(self):
        spec = {
            "openapi": "3.0.0",
            "info": {
                "title": "Test Path Params",
                "version": "1.0.0"
            },
            "paths": {
                "/users/{id}": {
                    "get": {
                        "responses": {
                            "200": {"description": "OK"}
                        }
                    }
                }
            }
        }
        path = self.create_temp_spec_file(spec)
        self.assertTrue(self.validator.load_spec(path))
        self.assertTrue(self.validator.validate())
        
        resp = self.validator.get_response_dict()
        self.assertFalse(resp["status"])
        
        # Check path parameter error
        err = resp["errors"][0]
        self.assertEqual(err["category"], "Path Validation")
        self.assertIn("Path parameter 'id' not defined", err["message"])
        
        # Suggestion should exist
        self.assertTrue(any("Define path parameter" in s for s in resp["suggestions"]))

        self.delete_temp_file(path)

    def test_broken_reference_error(self):
        spec = {
            "openapi": "3.0.0",
            "info": {
                "title": "Test References",
                "version": "1.0.0"
            },
            "paths": {
                "/users": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "OK",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "$ref": "#/components/schemas/NonExistent"
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        path = self.create_temp_spec_file(spec)
        self.assertTrue(self.validator.load_spec(path))
        self.assertTrue(self.validator.validate())
        
        resp = self.validator.get_response_dict()
        self.assertFalse(resp["status"])
        
        errs = [e for e in resp["errors"] if e["category"] == "Reference Validation"]
        self.assertEqual(len(errs), 1)
        self.assertIn("Broken reference", errs[0]["message"])
        
        # Suggestion should suggest defining the schema
        self.assertTrue(any("Define missing schema" in s for s in resp["suggestions"]))
        
        self.delete_temp_file(path)


if __name__ == "__main__":
    unittest.main()
