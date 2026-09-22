"""Versioned, explicitly enabled extension points for the legacy pipeline."""

from importlib import metadata

from ..step import Step

GROUP = "apizr.pipeline.v1"


class PipelinePlugin(Step):
    """Trusted installed extension; execute receives and returns a Context."""

    api_version = 1
    after: str = "DockerizrStep"


def load_plugins(names: list[str]) -> list[tuple[str, type[PipelinePlugin]]]:
    if not names:
        return []
    if len(names) != len(set(names)):
        raise ValueError("A pipeline plugin may only be selected once")
    entries = metadata.entry_points(group=GROUP)
    selected = []
    # Validate the complete selection before importing any extension.
    for name in names:
        matches = list(entries.select(name=name))
        if len(matches) != 1:
            raise ValueError(
                f"Pipeline plugin {name!r}: expected one installed entry point, found {len(matches)}"
            )
        selected.append((name, matches[0]))
    plugins = []
    for name, entry in selected:
        try:
            cls = entry.load()
        except Exception as exc:
            raise ValueError(f"Cannot load pipeline plugin {name!r}") from exc
        if not isinstance(cls, type) or not issubclass(cls, PipelinePlugin):
            raise ValueError(f"Pipeline plugin {name!r} must subclass PipelinePlugin")
        if cls.api_version != 1:
            raise ValueError(
                f"Pipeline plugin {name!r} uses an unsupported API version"
            )
        if not isinstance(cls.after, str):
            raise ValueError(
                f"Pipeline plugin {name!r} must declare an after step name"
            )
        plugins.append((name, cls))
    return plugins
