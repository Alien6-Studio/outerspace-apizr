"""An eligible input must be usable without resolving source-level aliases."""

import pytest

from apizr.inspection import inspect_source
from apizr.readiness.model import Code, State


@pytest.mark.parametrize(
    "source",
    [
        "from typing import List as Sequence\ndef f(x: Sequence[int]): pass",
        "from typing import List as int\ndef f(x: int): pass",
        "from typing import Any as Value\ndef f(x: Value): pass",
        "from typing import Optional as Maybe\ndef f(x: Maybe[str]): pass",
    ],
)
def test_unrecorded_type_alias_meaning_is_not_interface_ready(source):
    assessment = inspect_source(source, module_name="aliases").readiness.assessments[0]
    assert assessment.dimensions.inputs.state == State.CONDITIONAL
    assert not assessment.can_generate_interface
    assert Code.UNRESOLVED_TYPE in {
        reason.code for reason in assessment.dimensions.inputs.reasons
    }
