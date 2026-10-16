"""All legacy FastAPI entrypoints converge on the deprecated renderer."""

import pytest

from apizr.main import convert
from apizr.modules.fast_apizr.app import create_file
from apizr.modules.fast_apizr.configuration import FastApizrConfiguration
from apizr.modules.fast_apizr.generator.analyzr import Analyzr
from apizr.modules.fast_apizr.generator.fastApiAppGenerator import FastApiAppGenerator


@pytest.mark.parametrize("entry", ["pipeline", "http", "renderer"])
def test_legacy_entrypoints_warn_before_rendering(entry, tmp_path, capsys):
    conf = FastApizrConfiguration()
    metadata = Analyzr(functions=[])
    source = tmp_path / "business.py"
    source.write_text("def value() -> int:\n    return 1\n")
    with pytest.warns(DeprecationWarning, match="removed in 0.4.6"):
        if entry == "pipeline":
            convert(source, tmp_path / "output")
        elif entry == "http":
            create_file(conf, metadata)
        else:
            FastApiAppGenerator(conf, metadata).gen_fastapi_app()
    assert "apizr inspect" in capsys.readouterr().err
