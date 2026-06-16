# Copyright 2026 SwaggerValidator Service Authors
#
# Validator CLI and FastAPI Service Wrapper.

import argparse
import sys
import json
from pathlib import Path
from core import CoreValidator

# FastAPI imports (optional but available in the virtual environment)
try:
    from fastapi import FastAPI, Body, HTTPException
    from pydantic import BaseModel
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


# Define request body schema for the HTTP API
if FASTAPI_AVAILABLE:
    class ValidationRequest(BaseModel):
        swaggerPath: str


    app = FastAPI(
        title="Swagger/OpenAPI Validation Service",
        description="A validation service that checks if Swagger/OpenAPI specifications are valid and Postman-importable."
    )


    @app.post("/validate")
    async def validate_endpoint(payload: ValidationRequest):
        """
        Accepts a Swagger/OpenAPI file path and validates it.
        """
        validator = CoreValidator()
        
        # Load specification
        # We try loading the path as-is
        loaded = validator.load_spec(payload.swaggerPath)
        
        # Even if load_spec fails, validator.validate() is called to format the failure response.
        # But if load_spec returns false, validator.validate() will bypass rules and return the parsed status.
        validator.validate()
        
        return validator.get_response_dict()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Swagger/OpenAPI Validation CLI and Service."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--input",
        help="Path or URL to the Swagger/OpenAPI specification file to validate."
    )
    group.add_argument(
        "--server",
        action="store_true",
        help="Start the HTTP API validation service."
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8185,
        help="Port to run the HTTP service on (default: 8185)."
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host interface to bind the server to (default: 0.0.0.0)."
    )
    return parser.parse_args()


def run_cli(input_path):
    validator = CoreValidator()
    
    # Load and validate
    validator.load_spec(input_path)
    validator.validate()

    # Output JSON directly to stdout
    result = validator.get_response_dict()
    print(json.dumps(result, indent=2))
    
    # Exit with code 1 if status is false, else 0
    if not validator.status:
        sys.exit(1)
    sys.exit(0)


def run_server(host, port):
    if not FASTAPI_AVAILABLE:
        print("Error: FastAPI and Uvicorn must be installed to run as an HTTP server.", file=sys.stderr)
        sys.exit(1)
        
    print(f"Starting Swagger/OpenAPI Validation Service on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)


def main():
    args = parse_args()
    if args.input:
        run_cli(args.input)
    elif args.server:
        run_server(args.host, args.port)


if __name__ == "__main__":
    main()
