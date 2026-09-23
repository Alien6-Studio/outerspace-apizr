"""The documented peer also works through the production invocation API."""

import pytest

from apizr.extension_runtime import Limits, PluginFailed, invoke_extension

pytestmark = pytest.mark.timeout(20)


def test_demo(extension_python):
    def call(operation, arguments):
        return invoke_extension(
            extension_python,
            "invocation_demo",
            operation,
            arguments,
            limits=Limits(wall_time_ms=3000),
            environment={},
        )

    for operation, arguments in (("unknown", {}), ("describe", {})):
        with pytest.raises(PluginFailed):
            call(operation, arguments)
        assert call("describe", {"source_digest": "abc"}).result == {
            "source_digest": "abc",
            "message": "demo extension reached",
        }
