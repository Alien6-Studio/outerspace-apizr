"""Preserve the REST v1 standalone wire artifact while sharing its implementation.

Only legacy type spellings/fields and imports are restored here. Every executable
integrity/binding/validation function comes verbatim from the shared runtime.
The existing golden manifest pins the complete result, including adapter bytes.
"""

from importlib.resources import files


def runtime_source() -> str:
    package = files("apizr.generators.rest")
    common = (
        files("apizr.interfaces").joinpath("runtime.py").read_text(encoding="utf-8")
    )
    body = (
        common[common.index("JSON: TypeAlias") :]
        .replace("RuntimeInvocation", "RuntimeEndpoint")
        .replace("SourcePlan", "RuntimePlan")
    )
    body = body.replace(
        "    capability_id: str\n", "    capability_id: str\n    route: str\n"
    )
    body = body.replace(
        "    source: RuntimeSource\n",
        "    source: RuntimeSource\n    endpoints: list[RuntimeEndpoint]\n",
    )
    body = body.replace(
        "class IntegrityError",
        'LOGGER = logging.getLogger("apizr.rest")\n\n\nclass IntegrityError',
    )
    transport = package.joinpath("runtime.py").read_text(encoding="utf-8")
    return (
        package.joinpath("templates/preamble.txt").read_text(encoding="utf-8")
        + "\n"
        + body.rstrip()
        + "\n\n\n"
        + transport[transport.index("def create_app(") :]
    )
