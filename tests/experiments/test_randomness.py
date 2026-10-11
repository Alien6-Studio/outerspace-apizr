"""Literal randomness evidence without framework imports or execution claims."""

import ast
import json
import os
import subprocess
import sys

import pytest
from pydantic import ValidationError

from apizr.experiments import EvidenceOrigin as O
from apizr.experiments import (
    RandomnessControl,
    RandomnessDiagnostic,
    RandomnessResult,
    _lexical,
    discover_randomness,
    randomness,
)


def scan(source):
    return discover_randomness(source, source_reference="train.py")


def controls(source):
    return {
        (item.provider, item.name): (item.value, item.origin)
        for item in scan(source).controls
    }


@pytest.mark.parametrize(
    "statement,call,provider,name",
    [
        ("import random", "random.seed", "python.random", "seed"),
        ("import random as rnd", "rnd.seed", "python.random", "seed"),
        ("from random import seed", "seed", "python.random", "seed"),
        ("from random import seed as set_seed", "set_seed", "python.random", "seed"),
        ("import numpy as np", "np.random.seed", "numpy", "random.seed"),
        ("from numpy import random as rnd", "rnd.seed", "numpy", "random.seed"),
        ("import numpy.random", "numpy.random.seed", "numpy", "random.seed"),
        ("import numpy.random as nr", "nr.default_rng", "numpy", "random.default_rng"),
        (
            "from numpy.random import default_rng as rng",
            "rng",
            "numpy",
            "random.default_rng",
        ),
        ("import numpy as np", "np.random.default_rng", "numpy", "random.default_rng"),
        ("import torch", "torch.manual_seed", "torch", "manual_seed"),
        ("from torch import manual_seed as seed", "seed", "torch", "manual_seed"),
        ("import torch as pt", "pt.manual_seed", "torch", "manual_seed"),
        (
            "import tensorflow as tf",
            "tf.random.set_seed",
            "tensorflow",
            "random.set_seed",
        ),
        (
            "import tensorflow",
            "tensorflow.random.set_seed",
            "tensorflow",
            "random.set_seed",
        ),
        (
            "from tensorflow.random import set_seed",
            "set_seed",
            "tensorflow",
            "random.set_seed",
        ),
        (
            "from tensorflow import random as tr",
            "tr.set_seed",
            "tensorflow",
            "random.set_seed",
        ),
    ],
)
def test_fixed_literals(statement, call, provider, name):
    observed = controls(f"{statement}\n{call}(42)")
    assert observed[provider, name] == (42, O.STATIC)
    if provider in {"torch", "tensorflow"}:
        assert (provider, "accelerator_determinism") in observed
        assert observed[provider, "accelerator_determinism"] == (None, O.UNKNOWN)


@pytest.mark.parametrize(
    "expression,value",
    [
        ("42", 42),
        ("-42", -42),
        ("+42", 42),
        ("1.5", 1.5),
        ("-1.5", -1.5),
        ("'fixed'", "fixed"),
        ("''", ""),
    ],
)
def test_stdlib_finite_literals(expression, value):
    assert controls(f"import random\nrandom.seed({expression})")[
        "python.random", "seed"
    ] == (value, O.STATIC)


@pytest.mark.parametrize(
    "api",
    [
        "random.seed",
        "numpy.random.seed",
        "numpy.random.default_rng",
        "torch.manual_seed",
        "tensorflow.random.set_seed",
    ],
)
@pytest.mark.parametrize(
    "expression,code",
    [
        ("seed", "dynamic_randomness_control"),
        ("config.seed", "dynamic_randomness_control"),
        ("40+2", "dynamic_randomness_control"),
        ("get_seed()", "dynamic_randomness_control"),
        ("*seeds", "dynamic_randomness_control"),
        ("None", "uncontrolled_randomness"),
        ("", "uncontrolled_randomness"),
        ("True", "unsupported_randomness_literal"),
        ("[]", "dynamic_randomness_control"),
        ("b'x'", "unsupported_randomness_literal"),
        ("1e999", "unsupported_randomness_literal"),
    ],
)
def test_unknown_values(api, expression, code):
    result = scan(f"import {api.split('.')[0]}\n{api}({expression})")
    assert all(
        item.value is None and item.origin is O.UNKNOWN for item in result.controls
    )
    assert code in {item.code for item in result.diagnostics}


@pytest.mark.parametrize(
    "api,expression",
    [
        ("numpy.random.seed", "-1"),
        ("numpy.random.seed", str(2**32)),
        ("numpy.random.default_rng", "-1"),
        ("torch.manual_seed", str(2**63)),
        ("tensorflow.random.set_seed", "1.5"),
        ("numpy.random.seed", "'text'"),
        ("random.seed", str(2**63)),
        ("random.seed", "'" + "x" * 8193 + "'"),
        ("random.seed", repr("\ud800")),
    ],
)
def test_unsupported_literals(api, expression):
    result = scan(f"import {api.split('.')[0]}\n{api}({expression})")
    assert result.controls[0].value is None
    assert "unsupported_randomness_literal" in {d.code for d in result.diagnostics}
    assert expression not in result.model_dump_json()


@pytest.mark.parametrize(
    "source",
    [
        "import random\nrandom.seed(a=42)",
        "import numpy as np\nnp.random.default_rng(seed=42)",
    ],
)
def test_keyword_seed(source):
    assert scan(source).controls[0].value == 42


@pytest.mark.parametrize(
    "args",
    ["42, 43", "42, a=43", "a=42, a=43", "42, version=1", "42, **kwargs", "wrong=42"],
)
def test_unsupported_arguments_are_unknown(args):
    result = scan(f"import random\nrandom.seed({args})")
    assert result.controls[0].value is None
    assert result.diagnostics[0].code == "unsupported_randomness_arguments"


@pytest.mark.parametrize(
    "statement,call,name",
    [
        (
            "from sklearn.ensemble import RandomForestClassifier",
            "RandomForestClassifier",
            "ensemble.RandomForestClassifier.random_state",
        ),
        (
            "from sklearn.model_selection import train_test_split as split",
            "split",
            "model_selection.train_test_split.random_state",
        ),
        (
            "import sklearn.cluster as cluster",
            "cluster.KMeans",
            "cluster.KMeans.random_state",
        ),
        (
            "import sklearn.cluster",
            "sklearn.cluster.KMeans",
            "cluster.KMeans.random_state",
        ),
        ("from sklearn import cluster as c", "c.KMeans", "cluster.KMeans.random_state"),
    ],
)
def test_sklearn_keyword_evidence(statement, call, name):
    source = f"{statement}\n{call}(data, n_estimators=200, random_state=42)"
    assert controls(source) == {("sklearn", name): (42, O.STATIC)}
    assert scan(source).relevant_distributions == ("scikit-learn",)


@pytest.mark.parametrize(
    "keyword,code",
    [
        ("random_state=seed", "dynamic_randomness_control"),
        ("random_state=None", "uncontrolled_randomness"),
        ("random_state=-1", "unsupported_randomness_literal"),
        ("random_state=42, **kwargs", "unsupported_randomness_arguments"),
        ("random_state=42, random_state=43", "unsupported_randomness_arguments"),
    ],
)
def test_sklearn_unknown(keyword, code):
    result = scan(
        f"from sklearn.ensemble import RandomForestClassifier as RFC\nRFC({keyword})"
    )
    assert result.controls[0].value is None
    assert result.diagnostics[0].code == code


def test_separate_controls_and_no_random_state_keyword():
    result = scan(
        "import numpy as np\nimport sklearn.cluster as c\nnp.random.seed(1)\nnp.random.default_rng(2)\nc.KMeans(random_state=3)\nc.Other(random_state=4)\nc.NoSeed(5)"
    )
    assert [item.value for item in result.controls] == [2, 1, 3, 4]


@pytest.mark.parametrize(
    "values,conflict",
    [
        ("42\n42", False),
        ("42\n43", True),
        ("42\nseed", True),
        ("seed\n42", True),
        ("42\n43\n42", True),
        ("None\nNone", False),
        ("1\n1.0", True),
    ],
)
def test_conflicts_never_choose_first_or_last(values, conflict):
    calls = "\n".join(f"random.seed({value})" for value in values.splitlines())
    result = scan("import random\n" + calls)
    assert len(result.controls) == 1
    assert (
        "randomness_control_conflict" in {d.code for d in result.diagnostics}
    ) == conflict
    if conflict:
        assert (
            result.controls[0].value is None and result.controls[0].origin is O.UNKNOWN
        )


@pytest.mark.parametrize(
    "source",
    [
        "np.random.seed(42)",
        "import numpy as np\nnp = fake\nnp.random.seed(42)",
        "import numpy as np\nnp.random.seed = fake\nnp.random.seed(42)",
        "import numpy as np\nnp.random = fake\nnp.random.seed(42)",
        "if condition:\n import numpy as np\nnp.random.seed(42)",
        "from numpy.random import *\nseed(42)",
        "import numpy as np\nfrom other import *\nnp.random.seed(42)",
        "import numpy as np\ndef train(np):\n np.random.seed(42)",
        "import numpy as np\ndef train():\n np.random.seed(42)\n np=other",
        "import numpy as np\n(lambda np: np.random.seed(42))(other)",
        "np.random.seed(42)\nimport numpy as np",
        "from .numpy.random import seed\nseed(42)",
        "from sklearn.ensemble import RandomForestClassifier as RFC\nRFC=other\nRFC(random_state=42)",
        "from other import seed\nseed(42)",
        "import random\nfactory().seed(42)",
        "import random\nrandom.Random(42)",
    ],
)
def test_untrusted_bindings_do_not_grant_framework_authority(source):
    assert not scan(source).controls


@pytest.mark.parametrize(
    "source",
    [
        "import numpy as np\ndef train():\n np.random.seed(42)",
        "def train():\n import numpy as np\n np.random.seed(42)",
        "import numpy as np\ndef outer():\n def inner():\n  np.random.seed(42)",
        "import numpy as np\nclass C:\n np=other\n def train(self):\n  np.random.seed(42)",
        "import numpy as np\n(lambda: np.random.seed(42))",
        "import numpy as np\n[np.random.seed(42) for i in items]",
    ],
)
def test_nested_static_presence(source):
    assert controls(source) == {("numpy", "random.seed"): (42, O.STATIC)}


def test_bounded_and_invalid_sources(monkeypatch):
    for source in ("def invalid(", b"\xff", "\ud800"):
        assert scan(source).diagnostics[0].code == "randomness_source_invalid"
    result = discover_randomness("pass", source_reference="/private/secret.py")
    assert result.diagnostics[0].source is None
    assert "secret" not in result.model_dump_json()
    assert (
        scan("#" * (_lexical.MAX_SOURCE_BYTES + 1)).diagnostics[0].code
        == "randomness_discovery_limit"
    )
    monkeypatch.setattr(
        randomness,
        "bounded_tree",
        lambda source: _lexical.bounded_tree(source, max_nodes=2),
    )
    result = scan("import random\nrandom.seed(42)")
    assert result.diagnostics[0].code == "randomness_discovery_limit"
    assert result.diagnostics[0].source == "train.py"


def test_result_limits():
    for source in (
        "import random\n" + "random.seed(dynamic)\n" * 513,
        "import sklearn\n"
        + "\n".join(f"sklearn.Call{i}(random_state=42)" for i in range(129)),
    ):
        result = scan(source)
        assert not result.controls
        assert result.diagnostics[0].code == "randomness_discovery_limit"


def test_name_length_has_no_synthetic_truncation():
    result = scan("import sklearn\nsklearn." + "a" * 129 + "(random_state=42)")
    assert not result.controls
    assert result.diagnostics[0].code == "randomness_control_name_invalid"


def test_mapping_is_versionless_source_candidates():
    result = scan(
        "import pandas, numpy, company_internal_library\nfrom sklearn import cluster\nimport joblib\nif enabled:\n import torch\nfrom tensorflow import random\nfrom .pandas import other\nfrom unknown import *"
    )
    assert result.relevant_distributions == (
        "joblib",
        "numpy",
        "pandas",
        "scikit-learn",
        "tensorflow",
        "torch",
    )
    assert not result.controls
    assert "version" not in result.model_dump_json()


def test_generic_ignored(monkeypatch):
    tree = ast.parse("import torch\ndef f():\n torch.manual_seed(42)")
    tree.body[1].type_params = [ast.Name(id="torch", ctx=ast.Store())]
    monkeypatch.setattr(randomness, "bounded_tree", lambda source: tree)
    assert not scan("ignored").controls


def test_strict_result_contracts():
    control = RandomnessControl(
        provider="numpy", name="random.seed", value=42, origin=O.STATIC
    )
    with pytest.raises(ValidationError, match="randomness_origin_invalid"):
        RandomnessResult(controls=(control.model_copy(update={"origin": O.RUNTIME}),))
    with pytest.raises(ValidationError, match="duplicate_identity"):
        RandomnessResult(controls=(control, control))
    with pytest.raises(ValidationError, match="randomness_distribution_invalid"):
        RandomnessResult(relevant_distributions=("invented",))
    with pytest.raises(ValidationError, match="duplicate_identity"):
        RandomnessResult(relevant_distributions=("numpy", "numpy"))
    with pytest.raises(ValidationError):
        RandomnessResult(controls=[control])
    diagnostic = RandomnessDiagnostic(code="randomness_source_invalid")
    assert RandomnessResult(diagnostics=(diagnostic, diagnostic)).diagnostics == (
        diagnostic,
    )


def test_hashseed_ordering(tmp_path):
    source = "import torch\nimport numpy as np\nfrom sklearn.cluster import KMeans\nKMeans(random_state=42)\nnp.random.seed(42)\ntorch.manual_seed(42)"
    code = f'from apizr.experiments import discover_randomness; print(discover_randomness({source!r},source_reference="train.py").model_dump_json())'
    outputs = [
        subprocess.check_output(
            [sys.executable, "-c", code],
            env={**os.environ, "PYTHONHASHSEED": str(seed)},
            cwd=tmp_path,
            text=True,
        )
        for seed in (1, 71)
    ]
    assert outputs[0] == outputs[1] == scan(source).model_dump_json() + "\n"
    assert json.loads(outputs[0])["controls"]
