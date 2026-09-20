import os
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from apizr.graph import build_graph, graph_bytes, graph_digest, graph_repository
from apizr.graph.model import RelationshipKind as K
from apizr.repository import ScanPolicy, catalog_digest, scan_sources

NAME = st.sampled_from(["calculate", "reserve", "run", "λ", "total"])


def build(files):
    c = scan_sources(files.items())
    return c, build_graph(c, {s.path: files[s.path] for s in c.sources if s.inspection})


def topology(g):
    return {(r.source, r.kind, r.target) for r in g.relationships}


@given(st.permutations(["a.py", "b.py", "c.py"]), st.integers(0, 100))
@settings(max_examples=15)
def test_mapping_and_relocation_independence(order, value):
    files = {
        "a.py": b"import b\ndef run(): return b.f()",
        "b.py": f"def f(): return {value}".encode(),
        "c.py": b"pass",
    }
    _, expected = build(files)
    _, reordered = build({p: files[p] for p in order})
    assert graph_bytes(expected) == graph_bytes(reordered)
    outputs = []
    for _ in range(2):
        with tempfile.TemporaryDirectory() as directory:
            for p in order:
                (Path(directory) / p).write_bytes(files[p])
            outputs.append(graph_bytes(graph_repository(directory).graph))
    assert outputs == [graph_bytes(expected)] * 2


@given(st.integers(1, 20), st.integers(-100, 100))
def test_comments_body_mutation_and_locations_have_distinct_digests_same_topology(
    blank_lines, value
):
    first = {"a.py": b"def f(): return 0\ndef run(): return f()"}
    second = {
        "a.py": (
            "# Comment\n"
            + "\n" * blank_lines
            + f"def f(): return {value}\ndef run(): return f()"
        ).encode()
    }
    c1, g1 = build(first)
    c2, g2 = build(second)
    assert c1.repository_digest != c2.repository_digest
    assert catalog_digest(c1) != catalog_digest(c2)
    assert graph_digest(g1) != graph_digest(g2)
    assert topology(g1) == topology(g2)
    assert {n.id for n in g1.nodes} == {n.id for n in g2.nodes}


@given(NAME, st.sampled_from(["alias", "p", "subtotal", "κ"]))
def test_alias_equivalent_call_topology(name, alias):
    source = f"def {name}(): return 1".encode()
    variants = [
        f"import shop.pricing as {alias}\ndef run(): return {alias}.{name}()",
        f"from shop import pricing as {alias}\ndef run(): return {alias}.{name}()",
        f"from shop.pricing import {name} as {alias}\ndef run(): return {alias}()",
    ]
    calls = []
    for variant in variants:
        _, g = build({"shop/pricing.py": source, "a.py": variant.encode()})
        calls.append(
            edges := {(r.source, r.target) for r in g.relationships if r.kind == K.CALL}
        )
        assert edges == {("python:a:run", f"python:shop.pricing:{name}")}
    assert calls[0] == calls[1] == calls[2]


@given(
    NAME,
    st.sampled_from(["parameter", "assignment", "loop", "comprehension", "walrus"]),
)
def test_shadowing_never_creates_cross_module_calls(name, form):
    headers = f"from b import {name}\n"
    bodies = {
        "parameter": f"def run({name}): return {name}()",
        "assignment": f"def run():\n {name} = None\n return {name}()",
        "loop": f"def run():\n for {name} in []: {name}()",
        "comprehension": f"def run(): return [{name}() for {name} in []]",
        "walrus": f"def run():\n ({name} := None)\n return {name}()",
    }
    _, g = build(
        {
            "a.py": (headers + bodies[form]).encode(),
            "b.py": f"def {name}(): return 1".encode(),
        }
    )
    assert not g.capability_calls("python:a:run")


@given(NAME, st.permutations(["one/p.py", "two/p.py", "one/a.py"]))
def test_collisions_never_resolve_in_any_enumeration(name, order):
    files = {
        "one/p.py": f"def {name}(): return 1".encode(),
        "two/p.py": f"def {name}(): return 2".encode(),
        "one/a.py": f"import p\ndef run(): return p.{name}()".encode(),
    }
    c = scan_sources(
        ((p, files[p]) for p in order), policy=ScanPolicy(source_roots=("two", "one"))
    )
    g = build_graph(c, {s.path: files[s.path] for s in c.sources if s.inspection})
    assert not g.capability_calls("python:a:run")
    assert not any(n.module == "p" for n in g.nodes)


@given(st.permutations(["a.py", "b.py"]), NAME)
def test_cycles_are_deterministic(order, name):
    files = {
        "a.py": f"import b\ndef {name}(): return b.{name}()".encode(),
        "b.py": f"import a\ndef {name}(): return a.{name}()".encode(),
    }
    _, g = build(files)
    _, reordered = build({p: files[p] for p in order})
    assert graph_bytes(g) == graph_bytes(reordered)
    assert g.capability_calls(f"python:a:{name}") == (f"python:b:{name}",)
    assert g.capability_calls(f"python:b:{name}") == (f"python:a:{name}",)


def test_actual_scandir_reverse_order(monkeypatch, tmp_path):
    for directory, name in [("src", "b"), ("src", "a"), ("src/pkg", "c")]:
        path = tmp_path / directory / f"{name}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"def {name}(): return 1")
    policy = ScanPolicy(source_roots=("src",))
    expected = graph_bytes(graph_repository(tmp_path, scan_policy=policy).graph)
    original = os.scandir

    class Reversed:
        def __init__(self, path):
            with original(path) as items:
                self.items = list(items)[::-1]

        def __enter__(self):
            return iter(self.items)

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(os, "scandir", Reversed)
    assert graph_bytes(graph_repository(tmp_path, scan_policy=policy).graph) == expected
