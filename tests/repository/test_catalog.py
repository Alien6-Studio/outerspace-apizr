import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from apizr.capabilities.model import Digest
from apizr.inspection import json_bytes
from apizr.readiness import State
from apizr.repository import (
    Catalog,
    Code,
    ScanPolicy,
    catalog_bytes,
    catalog_digest,
    policy_bytes,
    policy_digest,
    scan,
    scan_sources,
)
from apizr.repository.model import SourceUnit, capability_entries, repository_digest
from apizr.repository.modules import module_name

FIXTURES = Path(__file__).parents[1] / "fixtures/catalog"


def test_reviewed_catalog_and_schemas():
    catalog = scan(FIXTURES / "v1/project", policy=ScanPolicy(source_roots=("src",)))
    assert catalog_bytes(catalog) == (FIXTURES / "v1/catalog.json").read_bytes()
    assert Catalog.model_validate_json(catalog_bytes(catalog)) == catalog
    for model, name in [(Catalog, "catalog"), (ScanPolicy, "scan")]:
        schema = model.model_json_schema()
        assert schema == json.loads(
            (
                Path(__file__).parents[2] / f"docs/specs/apizr-{name}-v1.schema.json"
            ).read_bytes()
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(
            (catalog if name == "catalog" else catalog.scan_policy).model_dump(
                mode="json"
            )
        )
    assert len(catalog.capabilities) == 2
    assert catalog.statistics.readiness[State.READY] == 2
    assert catalog.statistics.sources == 3
    assert catalog.sources[0].module == "project"
    assert catalog.sources[0].is_package
    assert catalog.exit_code == 0
    assert (
        len(
            {
                catalog_digest(catalog).value,
                catalog.repository_digest.value,
                catalog.scan_policy_digest.value,
            }
        )
        == 3
    )


@pytest.mark.parametrize(
    "value",
    [
        "../outside",
        "/absolute",
        "src/../outside",
        "C:\\outside",
        "C:/outside",
        "",
        "a\0b",
    ],
)
def test_policy_rejects_escaping_roots(value):
    with pytest.raises(ValueError):
        ScanPolicy(source_roots=(value,))


@pytest.mark.parametrize(
    "change",
    [
        {"source_roots": ()},
        {"source_roots": (".", "src")},
        {"source_roots": ("src", "src/pkg")},
        {"included_suffixes": ()},
        {"included_suffixes": (".ipynb",)},
        {"symlinks": "follow"},
        {"max_source_files": 0},
        {"max_file_bytes": 0},
        {"excluded_directories": ("a/b",)},
    ],
)
def test_policy_rejects_ambiguous_or_unbounded_options(change):
    with pytest.raises(ValueError):
        ScanPolicy(**change)


def test_equivalent_policy_order_and_explicit_differences():
    a = ScanPolicy(
        source_roots=("tools/", "src", "src"),
        excluded_directories=("b", "a"),
        included_suffixes=(".py", ".py"),
    )
    b = ScanPolicy(source_roots=("src", "tools"), excluded_directories=("a", "b", "a"))
    assert policy_bytes(a) == policy_bytes(b)
    assert policy_digest(a) == policy_digest(b)
    c = ScanPolicy(source_roots=("src", "tools"), excluded_directories=("a",))
    assert policy_digest(a) != policy_digest(c)
    assert catalog_digest(scan_sources([], policy=a)) != catalog_digest(
        scan_sources([], policy=c)
    )


@pytest.mark.parametrize(
    "path,root,module",
    [
        ("src/project/pricing.py", "src", "project.pricing"),
        ("src/project/__init__.py", "src", "project"),
        ("project/tools.py", ".", "project.tools"),
        ("λ.py", ".", "λ"),
    ],
)
def test_lexical_module_identity(path, root, module):
    assert module_name(path, root) == module


@pytest.mark.parametrize(
    "path", ["__init__.py", "bad-name.py", "a.b.py", "class.py", "a-b/__init__.py"]
)
def test_invalid_modules_are_inventory_errors(path):
    catalog = scan_sources([(path, b"def f(): return 1")])
    assert catalog.sources[0].module is None
    assert catalog.sources[0].source_digest is not None
    assert [d.code for d in catalog.diagnostics] == [Code.MODULE]
    assert catalog.exit_code == 1 and not catalog.capabilities


def test_collisions_namespaces_and_rejected_declarations():
    collision = scan(
        FIXTURES / "collision", policy=ScanPolicy(source_roots=("src_b", "src_a"))
    )
    assert len(collision.sources) == 2
    assert not collision.capabilities
    assert {d.code for d in collision.diagnostics} == {Code.COLLISION}
    assert all(s.inspection is None for s in collision.sources)
    assert collision.exit_code == 1
    roots = scan(FIXTURES / "root")
    assert roots.capabilities[0].id == "python:project.tools:run"
    namespace = scan_sources(
        [("a/run.py", b"def run(): return 1"), ("b/run.py", b"def run(): return 2")]
    )
    assert {e.id for e in namespace.capabilities} == {
        "python:a.run:run",
        "python:b.run:run",
    }
    normalization = scan_sources(
        [("K.py", b"def f(): pass"), ("\u212a.py", b"def f(): pass")]
    )
    assert not normalization.capabilities and normalization.exit_code == 1
    declarations = scan_sources(
        [
            (
                "declarations.py",
                b"def f(): pass\ndef f(): pass\ndef g(): yield 1\n@unknown\ndef h(): pass",
            )
        ]
    )
    inspection = declarations.sources[0].inspection
    assert inspection.capability_ir.diagnostics
    assert declarations.statistics.readiness[State.AMBIGUOUS] == 1
    assert declarations.statistics.readiness[State.UNSUPPORTED] == 1
    assert declarations.statistics.readiness[State.CONDITIONAL] == 1
    assert declarations.exit_code == 1
    for entry in declarations.capabilities:
        assessment = next(
            a for a in inspection.readiness.assessments if a.capability_id == entry.id
        )
        assert entry.readiness == assessment.state
        assert entry.can_generate_interface == assessment.can_generate_interface


def test_conditional_and_unsupported_alone_are_inventory_successes():
    for code in [b"@unknown\ndef f(): pass", b"def f(): yield 1"]:
        catalog = scan_sources([("module.py", code)])
        assert catalog.exit_code == 0
        assert not catalog.capabilities[0].can_generate_interface


@pytest.mark.parametrize(
    "fault",
    [
        "policy",
        "repository",
        "capabilities",
        "duplicate_capability",
        "duplicate_source",
        "unselected",
        "uninspected",
        "inspection_digest",
        "module",
        "size",
        "package",
        "path",
        "root",
        "digest_without_inspection",
    ],
)
def test_catalog_and_source_linkage_cannot_be_forged(fault):
    catalog = scan_sources([("one.py", b"def f(): return 1")])
    data = catalog.model_dump(mode="json")
    source = data["sources"][0]
    if fault in {"policy", "repository"}:
        data["scan_policy_digest" if fault == "policy" else "repository_digest"][
            "value"
        ] = "0" * 64
    elif fault == "capabilities":
        data["capabilities"][0]["can_generate_interface"] = False
    elif fault == "duplicate_capability":
        data["capabilities"] *= 2
    elif fault == "duplicate_source":
        data["sources"] *= 2
    elif fault == "unselected":
        data["scan_policy"]["source_roots"] = ["src"]
        policy = ScanPolicy.model_validate(data["scan_policy"])
        data["scan_policy_digest"] = policy_digest(policy).model_dump(mode="json")
        data["repository_digest"] = repository_digest(
            policy, catalog.sources, ()
        ).model_dump(mode="json")
    elif fault == "uninspected":
        source["inspection"] = None
        source["inspection_digest"] = None
    elif fault == "inspection_digest":
        source["inspection_digest"]["value"] = "0" * 64
    elif fault == "module":
        source["module"] = "other"
    elif fault == "size":
        source["size"] = None
    elif fault == "package":
        source["is_package"] = True
    elif fault == "path":
        source["path"] = "./one.py"
    elif fault == "root":
        source["source_root"] = "./"
    elif fault == "digest_without_inspection":
        source["inspection"] = None
    with pytest.raises(ValueError):
        Catalog.model_validate(data)


def test_collision_inspections_and_readiness_membership_are_not_trusted():
    policy = ScanPolicy(source_roots=("a", "b"))
    good = scan_sources([("a/module.py", b"def f(): return 1")], policy=policy)
    other = good.sources[0].model_copy(
        update={"path": "b/module.py", "source_root": "b"}
    )
    data = good.model_dump(mode="json")
    data["sources"].append(other.model_dump(mode="json"))
    data["repository_digest"] = repository_digest(
        policy, (good.sources[0], other), ()
    ).model_dump(mode="json")
    with pytest.raises(ValueError, match="Colliding"):
        Catalog.model_validate(data)
    unit = good.sources[0]
    bad_inspection = unit.inspection.model_copy(
        update={
            "readiness": unit.inspection.readiness.model_copy(
                update={"assessments": ()}
            )
        }
    )
    with pytest.raises(ValueError, match="membership"):
        capability_entries((unit.model_copy(update={"inspection": bad_inspection}),))
    assert Digest.of_bytes(json_bytes(unit.inspection)) == unit.inspection_digest
    with pytest.raises(ValueError):
        catalog_bytes(good.model_copy(update={"capabilities": ()}))
    with pytest.raises(ValueError):
        SourceUnit.model_validate(
            {**unit.model_dump(mode="json"), "source_digest": None}
        )
