import importlib
import sys
from importlib import metadata

import pytest

from apizr.extensions.plugins.api import GROUP, PipelinePlugin, load_plugins
from apizr.main import convert


@pytest.fixture
def installed(tmp_path, monkeypatch):
    site = tmp_path / "site"
    site.mkdir()
    monkeypatch.syspath_prepend(str(site))

    def install(name="note", body=None, group=GROUP, value="delivery_plugin:Note"):
        info = site / (name + "-1.0.dist-info")
        info.mkdir()
        (info / "METADATA").write_text(
            f"Metadata-Version: 2.1\nName: {name}\nVersion: 1.0\n"
        )
        (info / "entry_points.txt").write_text(f"[{group}]\n{name} = {value}\n")
        (site / "delivery_plugin.py").write_text(
            body
            or """from apizr.extensions.plugins.api import PipelinePlugin
class Note(PipelinePlugin):
    after = 'FastApizrStep'
    def execute(self, context):
        context.result = ('note', context.options.get('text', context.data['api_module']))
        context.write_output('note', 'delivery.txt')
        return context
"""
        )
        importlib.invalidate_caches()

    yield install
    sys.modules.pop("delivery_plugin", None)


def source(tmp_path):
    path = tmp_path / "sample.py"
    path.write_text("def f(x: int): return x + 1\n")
    return path


def test_real_installed_entry_point_explicit_activation_and_options(
    tmp_path, installed
):
    installed()
    config = tmp_path / "config.yaml"
    config.write_text("plugin_options:\n  note:\n    text: delivered\n")
    input_path = source(tmp_path)
    plain = tmp_path / "plain"
    convert(
        input_path, plain, configuration=config, skip_pipreqs=True, skip_docker=True
    )
    assert "delivery_plugin" not in sys.modules
    assert not (plain / "delivery.txt").exists()
    result = convert(
        input_path,
        tmp_path / "extended",
        configuration=config,
        plugins=["note"],
        skip_pipreqs=True,
        skip_docker=True,
    )
    assert (tmp_path / "extended/delivery.txt").read_text() == "delivered"
    assert "delivery.txt" in result["files"]
    assert (tmp_path / "extended/sample_api.py").read_bytes() == (
        plain / "sample_api.py"
    ).read_bytes()


def test_no_discovery_when_disabled(monkeypatch):
    monkeypatch.setattr(
        metadata, "entry_points", lambda **kw: pytest.fail("implicit plugin discovery")
    )
    assert load_plugins([]) == []


def test_missing_duplicate_and_versioned_group_fail_before_loading(installed):
    installed(group="apizr.pipeline.v2")
    with pytest.raises(ValueError, match="expected one"):
        load_plugins(["note"])
    with pytest.raises(ValueError, match="only be selected once"):
        load_plugins(["note", "note"])
    assert "delivery_plugin" not in sys.modules


@pytest.mark.parametrize(
    "body,message",
    [
        ("class Note: pass", "subclass"),
        (
            "from apizr.extensions.plugins.api import PipelinePlugin\nclass Note(PipelinePlugin):\n api_version=2\n def execute(self, context): return context",
            "unsupported API",
        ),
        ('raise RuntimeError("import failed")', "Cannot load"),
    ],
)
def test_incompatible_plugins_refused(installed, body, message):
    installed(body=body)
    with pytest.raises(ValueError, match=message):
        load_plugins(["note"])


@pytest.mark.parametrize(
    "body,message",
    [
        ('raise RuntimeError("failure")', "Pipeline plugin:note failed"),
        ("return None", "must return a Context"),
        (
            "context.output_dir = context.source_dir\n        return context",
            "same output directory",
        ),
        (
            'context.input_path = context.source_dir / "absent.py"\n        return context',
            "invalid input path",
        ),
    ],
)
def test_plugin_failures_are_actionable(tmp_path, installed, body, message):
    installed(
        body='from apizr.extensions.plugins.api import PipelinePlugin\nclass Note(PipelinePlugin):\n    after="FastApizrStep"\n    def execute(self, context):\n        '
        + body
        + "\n"
    )
    with pytest.raises((ValueError, RuntimeError), match=message):
        convert(
            source(tmp_path),
            tmp_path / "out",
            plugins=["note"],
            skip_pipreqs=True,
            skip_docker=True,
        )


def test_disabled_anchor_rejected(tmp_path, installed):
    installed()
    with pytest.raises(ValueError, match="requires enabled step"):
        convert(
            source(tmp_path),
            tmp_path / "out",
            plugins=["note"],
            skip_fastapi=True,
            skip_pipreqs=True,
            skip_docker=True,
        )


def test_multiple_plugins_keep_requested_order_and_registry_isolation(
    tmp_path, monkeypatch
):
    from apizr.extensions.context import Context
    from apizr.extensions.engine import AutomationEngine

    class First(PipelinePlugin):
        after = "CodeAnalyzrStep"

        def execute(self, context):
            context.result = ("order", context.data.get("order", "") + "first")
            return context

    class Second(First):
        def execute(self, context):
            assert context.data["order"] == "first"
            context.result = ("order", "firstsecond")
            context.write_output("order", "order.txt")
            return context

    monkeypatch.setattr(
        "apizr.main.load_plugins", lambda names: [("first", First), ("second", Second)]
    )
    convert(
        source(tmp_path),
        tmp_path / "out",
        plugins=["first", "second"],
        skip_pipreqs=True,
        skip_docker=True,
    )
    assert (tmp_path / "out/order.txt").read_text() == "firstsecond"
    engine = AutomationEngine()
    engine.add_plugin("first", First, Context())
    with pytest.raises(ValueError, match="Duplicate"):
        engine.add_plugin("first", First, Context())
    assert "plugin:first" not in AutomationEngine().registry
