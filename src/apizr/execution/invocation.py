"""Use the proven shared binder without importing user code in the parent."""

import json

from pydantic import JsonValue

from apizr.interfaces.model import InvocationContract
from apizr.interfaces.runtime import RuntimeInvocation, arguments


def runtime_contract(contract: InvocationContract) -> RuntimeInvocation:
    # Typed wire representation of a validated model, not a second contract model.
    return json.loads(contract.model_dump_json())


def validate_arguments(contract: InvocationContract, payload: JsonValue) -> None:
    def placeholder() -> None:
        pass

    # The shared binder's function parameter is unused; no user function is needed
    # to validate/reconstruct the contract. Values are sent as JSON, never pickle.
    arguments(placeholder, runtime_contract(contract), payload)
