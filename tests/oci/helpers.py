from apizr.inspection import inspect_source
from apizr.oci.model import ExecutionPolicyV2, RuntimeImage
from apizr.oci.planner import plan

IMAGE = RuntimeImage(image="sha256:" + "0" * 64, platform="linux/amd64")


def planned(source="def f(): return 1", image=IMAGE, **changes):
    raw = source.encode() if isinstance(source, str) else source
    return plan(
        inspect_source(raw, module_name="oci_sample"),
        raw,
        "f",
        ExecutionPolicyV2.model_validate(changes),
        image,
    ), raw
