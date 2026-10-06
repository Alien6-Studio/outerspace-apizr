"""Module initialization facts retained by Inspection; never reparse source."""

from apizr.capabilities.model import Digest
from apizr.readiness.model import Code, Reason
from apizr.repository.model import SourceUnit


def initialization_reasons(unit: SourceUnit) -> tuple[Reason, ...] | None:
    """None means unavailable evidence, including nonempty no-callable units.

    Function-body imports are assessed when that function is required, rather
    than being mistaken for module initialization. An empty unit is proven by
    its Catalog-bound size/digest. A namespace has no SourceUnit to execute.
    """
    if unit.inspection is None:
        return None
    declarations = unit.inspection.readiness.assessments
    if not declarations and (
        unit.size != 0 or unit.source_digest != Digest.of_bytes(b"")
    ):
        return None
    return tuple(
        sorted(
            {
                (reason.line, reason.code.value, reason.parameter): reason
                for declaration in declarations
                for reason in declaration.dimensions.execution.reasons
                if reason.code == Code.INITIALIZATION
                or (
                    reason.code in {Code.DYNAMIC_IMPORT, Code.DEPENDENCY}
                    and not any(
                        other.source.line <= reason.line <= other.source.end_line
                        for other in declarations
                    )
                )
            }.values(),
            key=lambda reason: (reason.line, reason.code.value),
        )
    )
