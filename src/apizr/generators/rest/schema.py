"""REST-specific OpenAPI construction from shared interface schemas."""

from pydantic import JsonValue

from apizr.interfaces.schema import ContractError as ContractError
from apizr.interfaces.schema import json_schema
from apizr.interfaces.schema import lower as lower
from apizr.interfaces.schema import request_schema as request_schema

from .model import Endpoint


def openapi(endpoints: tuple[Endpoint, ...]) -> dict[str, JsonValue]:
    paths: dict[str, JsonValue] = {
        "/health": {
            "get": {
                "operationId": "apizr_health",
                "responses": {
                    "200": {
                        "description": "Service health",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"status": {"const": "ok"}},
                                    "required": ["status"],
                                }
                            }
                        },
                    }
                },
            }
        },
    }
    for endpoint in endpoints:
        operation: dict[str, JsonValue] = {
            "operationId": endpoint.capability_id,
            "x-apizr-capability-id": endpoint.capability_id,
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": request_schema(endpoint)}},
            },
            "responses": {
                "200": {
                    "description": "Function result (return enforcement: none)",
                    "content": {
                        "application/json": {"schema": json_schema(endpoint.returns)}
                    },
                },
                "422": {"description": "Invalid request"},
                "500": {"description": "Internal server error"},
            },
        }
        if endpoint.description:
            operation["description"] = endpoint.description
        paths[endpoint.route] = {"post": operation}
    return {
        "openapi": "3.1.0",
        "info": {"title": "Apizr REST API", "version": "apizr.rest/v1"},
        "paths": paths,
    }
