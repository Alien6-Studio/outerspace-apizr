"""Semantic regressions: an import/reference is not a possible direct call."""

import pytest

from apizr.graph import Code, build_graph
from apizr.graph.model import RelationshipKind as K
from apizr.repository import ScanPolicy, scan_sources


def graph(files, **kwargs):
    sources = {p: s.encode() if isinstance(s, str) else s for p, s in files.items()}
    catalog = scan_sources(sources.items(), **kwargs)
    return build_graph(
        catalog, {s.path: sources[s.path] for s in catalog.sources if s.inspection}
    )


def edges(g, kind):
    return {(r.source, r.target) for r in g.relationships if r.kind == kind}


def test_import_reference_and_call_are_distinct():
    g = graph(
        {
            "a.py": "from b import f\nimport b\ndef use(): return b.f\ndef call(): return f()",
            "b.py": "def f(): return 1",
        }
    )
    assert edges(g, K.CAPABILITY) == {("python-module:a", "python:b:f")}
    assert edges(g, K.CALL) == {("python:a:call", "python:b:f")}
    assert edges(g, K.MODULE) == {("python-module:a", "python-module:b")}
    assert g.callers_of("python:b:f") == ("python:a:call",)
    assert g.module_dependencies("a") == ("python-module:b",)
    assert g.capability_calls("python:a:use") == ()
    assert all(r.syntax_evidence == "observed" for r in g.relationships)
    assert all(
        r.resolution_evidence == ("observed" if r.kind == K.CONTAINS else "inferred")
        for r in g.relationships
    )


@pytest.mark.parametrize(
    "declaration,expression",
    [
        ("from shop.pricing import total", "total"),
        ("from shop.pricing import total as calc", "calc"),
        ("import shop.pricing as p", "p.total"),
        ("import shop.pricing", "shop.pricing.total"),
        ("from shop import pricing", "pricing.total"),
        ("from . import pricing", "pricing.total"),
        ("from .pricing import total as t", "t"),
    ],
)
def test_supported_import_aliases(declaration, expression):
    g = graph(
        {
            "shop/__init__.py": "",
            "shop/pricing.py": "def total(): return 1",
            "shop/checkout.py": declaration
            + "\ndef run(): return "
            + expression
            + "()",
        }
    )
    assert g.capability_calls("python:shop.checkout:run") == (
        "python:shop.pricing:total",
    )
    record = next(i for i in g.imports if i.source == "python-module:shop.checkout")
    assert record.scope == "module_scope"
    assert record.names[0].name in {"shop.pricing", "pricing", "total"}


def test_longest_imported_prefix_and_same_name_modules():
    g = graph(
        {
            "a.py": "import p.x\nimport p.y\ndef run(): return p.x.run(), p.y.run()",
            "p/x.py": "def run(): return 1",
            "p/y.py": "def run(): return 2",
        }
    )
    assert g.capability_calls("python:a:run") == ("python:p.x:run", "python:p.y:run")


@pytest.mark.parametrize(
    "body",
    [
        "def run(f):\n f()",
        "def run(*f):\n f()",
        "def run(**f):\n f()",
        "def run():\n f()\n f = None",
        "def run():\n f()\n f: object",
        "def run():\n f()\n f += 1",
        "def run():\n f()\n del f",
        "def run():\n f()\n import b as f",
        "def run():\n f()\n from b import f",
        "def run():\n for f in []: f()",
        "def run():\n with manager() as f: f()",
        "def run():\n try: f()\n except Exception as f: pass",
        'def run():\n match value:\n  case {"v": f}: f()',
        "def run():\n match value:\n  case [*f]: f()",
        "def run():\n match value:\n  case {**f}: f()",
        "def run():\n f()\n def f(): pass",
        "def run():\n f()\n class f: pass",
        "def run():\n (f := replacement)\n f()",
        "def run():\n [f() for f in callbacks]",
        "def run():\n [f := value for value in []]\n f()",
        "def run():\n global f\n f = replacement\n f()",
        "def run():\n nonlocal f\n f()",
        "def run():\n from b import *\n f()",
    ],
)
def test_scope_wide_local_shadowing_cannot_resolve_global(body):
    g = graph({"a.py": "def f(): return 1\n" + body, "b.py": "def f(): return 2"})
    assert not g.capability_calls("python:a:run")


@pytest.mark.parametrize(
    "rebound",
    [
        "f = replacement",
        "f: object = replacement",
        "del f",
        "for f in []: pass",
        "with manager() as f: pass",
        "try: pass\nexcept Exception as f: pass",
        "match value:\n case f: pass",
        "(f := replacement)",
        "def f(): return 0",
        "class f: pass",
        "import c as f",
    ],
)
def test_module_import_rebinding_prevents_calls(rebound):
    g = graph(
        {
            "a.py": "from b import f\n" + rebound + "\ndef run(): return f()",
            "b.py": "def f(): return 1",
        }
    )
    assert ("python:a:run", "python:b:f") not in edges(g, K.CALL)
    assert Code.REBOUND in {d.code for d in g.diagnostics}


def test_duplicate_import_alias_does_not_choose_arbitrary_target():
    g = graph(
        {
            "a.py": "from b import f as x, g as x\ndef run(): return x()",
            "b.py": "def f(): pass\ndef g(): pass",
        }
    )
    assert not g.capability_calls("python:a:run")
    assert Code.REBOUND in {d.code for d in g.diagnostics}


def test_annotations_without_values_do_not_rebind_module_import():
    g = graph(
        {
            "a.py": "from b import f\nf: object\ndef run(): return f()",
            "b.py": "def f(): return 1",
        }
    )
    assert g.capability_calls("python:a:run") == ("python:b:f",)


def test_local_imports_global_declarations_and_definition_order():
    g = graph(
        {
            "a.py": "def first(): return second()\ndef second(): return 1\ndef local():\n from b import f as x\n return x()\ndef global_call():\n global second\n return second()",
            "b.py": "def f(): return 1",
        }
    )
    assert g.capability_calls("python:a:first") == ("python:a:second",)
    assert g.capability_calls("python:a:global_call") == ("python:a:second",)
    assert g.capability_calls("python:a:local") == ("python:b:f",)
    assert any(
        i.scope == "capability_scope" and i.source == "python:a:local"
        for i in g.imports
    )


def test_nested_scopes_excluded_but_comprehensions_and_conditionals_kept():
    g = graph(
        {
            "a.py": """def f(): return 1
def run():
 def inner():
  import hidden
  f()
 async def other(): f()
 class C:
  import hidden_class
  f()
 callback = lambda: f()
 if condition:
  f()
 values = [f() for x in items]
 values2 = [f() for f in items]
 return values
"""
        }
    )
    calls = [r for r in g.relationships if r.kind == K.CALL]
    assert [r.line for r in calls] == [12, 13]
    assert all(r.availability == "conditional" for r in calls)
    assert not g.imports


@pytest.mark.parametrize(
    "expression",
    [
        "service.f()",
        "self.f()",
        "factory().f()",
        "obj.method()",
        'registry["f"]()',
        "getattr(module, name)()",
        "callback()",
    ],
)
def test_arbitrary_objects_and_higher_order_values_unresolved(expression):
    g = graph(
        {"a.py": "def f(): return 1\ndef run(callback=None): return " + expression}
    )
    assert not g.capability_calls("python:a:run")
    assert not g.diagnostics


def test_assigned_alias_is_not_points_to_resolution():
    g = graph({"a.py": "def f(): return 1\ncalc = f\ndef run(): return calc()"})
    assert not g.capability_calls("python:a:run")


def test_relative_package_resolution_and_beyond_ancestry():
    g = graph(
        {
            "p/__init__.py": "from . import pricing",
            "p/pricing.py": "def total(): return 1",
            "p/sub/__init__.py": "from ..pricing import total\ndef f(): return total()",
            "p/sub/a.py": "from ..pricing import total\ndef f(): return total()",
            "bad.py": "from ..outside import missing",
        }
    )
    assert g.capability_calls("python:p.sub:f") == ("python:p.pricing:total",)
    assert g.capability_calls("python:p.sub.a:f") == ("python:p.pricing:total",)
    assert Code.RELATIVE in {d.code for d in g.diagnostics}
    assert not g.complete
    assert not any(n.kind == "external_module" and "outside" in n.id for n in g.nodes)


@pytest.mark.parametrize(
    "export",
    ["def pricing(): return 1", "pricing = 1", "from elsewhere import pricing"],
)
def test_from_import_submodule_export_ambiguity(export):
    g = graph(
        {
            "p/__init__.py": export,
            "p/pricing.py": "def total(): return 1",
            "a.py": "from p import pricing\ndef f(): return pricing.total()",
        }
    )
    assert not g.capability_calls("python:a:f")
    assert Code.IMPORT in {d.code for d in g.diagnostics}
    assert (
        next(i for i in g.imports if i.source == "python-module:a").names[0].resolution
        == "ambiguous"
    )


def test_noncapability_and_external_symbols_are_not_fabricated():
    g = graph(
        {
            "config.py": "SETTINGS = {}",
            "a.py": "from config import SETTINGS\nimport requests.sessions\nfrom other import f\ndef run(): return f()",
        }
    )
    assert edges(g, K.MODULE) == {("python-module:a", "python-module:config")}
    assert edges(g, K.EXTERNAL) == {
        ("python-module:a", "python-external:requests.sessions"),
        ("python-module:a", "python-external:other"),
    }
    assert not edges(g, K.CAPABILITY)
    assert not edges(g, K.CALL)
    assert not g.diagnostics
    assert g.complete


def test_conditional_import_not_stable_but_caller_readiness_independent():
    g = graph(
        {
            "a.py": "if flag:\n from b import f\ndef run(): return f()\n@decorator\ndef conditional_caller(): return stable()\ndef stable(): return 1",
            "b.py": "def f(): return 1",
        }
    )
    assert not g.capability_calls("python:a:run")
    assert g.capability_calls("python:a:conditional_caller") == ("python:a:stable",)
    assert (
        next(r for r in g.relationships if r.kind == K.CAPABILITY).availability
        == "conditional"
    )


@pytest.mark.parametrize(
    "source",
    [
        "@decorator\ndef f(): return 1",
        "if flag:\n def f(): return 1",
        "def f(): return 1\nf = replacement",
    ],
)
def test_target_readiness_binding_is_authority(source):
    g = graph(
        {
            "a.py": "from b import f\nimport b\ndef run(): return f(), b.f()",
            "b.py": source,
        }
    )
    assert not g.capability_calls("python:a:run")
    assert not edges(g, K.CAPABILITY)
    assert {Code.IMPORT, Code.CALL} <= {d.code for d in g.diagnostics}


def test_same_module_unstable_target_and_self_recursion():
    g = graph(
        {
            "a.py": "@decorator\ndef unstable(): pass\ndef run(): return unstable()\ndef recursive(): return recursive()"
        }
    )
    assert g.capability_calls("python:a:run") == ()
    assert Code.CALL in {d.code for d in g.diagnostics}
    assert g.capability_calls("python:a:recursive") == ("python:a:recursive",)


def test_dynamic_imports_are_uncertain_and_star_never_expands():
    g = graph(
        {
            "a.py": """import importlib as il
from importlib import import_module as load
def run():
 __import__("b")
 il.import_module("b")
 load("b")
""",
            "c.py": "from b import *\ndef run(): return f()",
            "b.py": "def f(): return 1",
        }
    )
    assert len([d for d in g.diagnostics if d.code == Code.DYNAMIC]) == 3
    assert Code.STAR in {d.code for d in g.diagnostics}
    assert not edges(g, K.CALL)
    assert not edges(g, K.CAPABILITY)
    assert ("python-module:a", "python-module:b") not in edges(g, K.MODULE)


def test_dynamic_builtin_shadow_and_local_dynamic_alias():
    g = graph(
        {
            "a.py": 'def f(__import__): return __import__("x")\ndef g():\n from importlib import import_module\n return import_module(name)\ndef h():\n import importlib\n return importlib.import_module(name)'
        }
    )
    assert [d.line for d in g.diagnostics if d.code == Code.DYNAMIC] == [4, 7]


def test_cycles_and_repeated_same_line_occurrences():
    g = graph(
        {
            "a.py": "import b\ndef f():\n b.g(); b.g()",
            "b.py": "import a\ndef g(): return a.f()",
        }
    )
    assert g.complete
    assert g.capability_calls("python:a:f") == ("python:b:g",)
    assert g.capability_calls("python:b:g") == ("python:a:f",)
    calls = [
        r for r in g.relationships if r.source == "python:a:f" and r.kind == K.CALL
    ]
    assert len(calls) == 2 and calls[0].column != calls[1].column


def test_collision_targets_never_become_local_or_external_nodes():
    policy = ScanPolicy(source_roots=("src", "other"))
    g = graph(
        {
            "src/p.py": "def f(): pass",
            "other/p.py": "def f(): pass",
            "src/a.py": "import p\nfrom p import f\ndef g(): return p.f(), f()",
        },
        policy=policy,
    )
    assert not any(n.module == "p" for n in g.nodes)
    assert not edges(g, K.CALL)
    assert Code.COLLISION in {d.code for d in g.diagnostics}
    assert not g.complete


@pytest.mark.parametrize(
    "export", ["from . import pricing", "import p.pricing as pricing"]
)
def test_package_submodule_import_does_not_conflict_with_itself(export):
    g = graph(
        {
            "p/__init__.py": export,
            "p/pricing.py": "def total(): return 1",
            "a.py": "from p import pricing\ndef f(): return pricing.total()",
        }
    )
    assert g.capability_calls("python:a:f") == ("python:p.pricing:total",)
    assert not g.diagnostics


def test_module_dynamic_and_star_external_and_conditional_body_import():
    g = graph(
        {
            "a.py": '__import__("x")\ndef run():\n if flag:\n  import optional\n return 1',
            "c.py": "from unknown import *",
        }
    )
    assert {Code.DYNAMIC, Code.STAR} <= {d.code for d in g.diagnostics}
    assert ("python:a:run", "python-external:optional") in edges(g, K.EXTERNAL)
    assert (
        next(i for i in g.imports if i.source == "python:a:run").availability
        == "conditional"
    )


def test_local_import_after_call_and_dynamic_alias_attribute_not_resolved():
    g = graph(
        {
            "a.py": "def run():\n b.f()\n import b\n return b.f()\nimport importlib\ndef other(): return importlib.ordinary()",
            "b.py": "def f(): return 1",
        }
    )
    assert len([r for r in g.relationships if r.kind == K.CALL]) == 1
    assert Code.CALL in {d.code for d in g.diagnostics}
    assert Code.DYNAMIC not in {d.code for d in g.diagnostics}


def test_submodule_collision_is_not_external_fallback():
    g = graph(
        {
            "one/p/__init__.py": "",
            "one/p/sub.py": "def f(): pass",
            "two/p/sub.py": "def f(): pass",
            "one/a.py": "from p import sub\ndef run(): return sub.f()",
        },
        policy=ScanPolicy(source_roots=("one", "two")),
    )
    assert Code.IMPORT in {d.code for d in g.diagnostics}
    assert not g.capability_calls("python:a:run")


def test_tuple_starred_bindings_async_targets_and_importlib_repository_shadow():
    g = graph(
        {
            "a.py": "def f(): pass\nasync def run():\n x, *f = values\n async for f in values: f()\n async with manager() as f: f()\ndef kw(*, f): return f()",
            "b.py": "from importlib import import_module\ndef run(): return import_module.f()",
            "importlib/import_module.py": "def f(): return 1",
        }
    )
    assert not g.capability_calls("python:a:run")
    assert not g.capability_calls("python:a:kw")
    assert g.capability_calls("python:b:run") == ("python:importlib.import_module:f",)
    assert Code.DYNAMIC not in {d.code for d in g.diagnostics}


def test_type_alias_binding_is_not_a_stable_import_on_supported_parsers():
    g = graph(
        {
            "a.py": "from b import f\ntype f = int\ndef run(): return f()",
            "b.py": "def f(): return 1",
        }
    )
    assert not g.capability_calls("python:a:run")


def test_conditional_containment_retains_catalog_source_availability():
    g = graph({"a.py": "if flag:\n def f(): return 1"})
    assert (
        next(r for r in g.relationships if r.kind == K.CONTAINS).availability
        == "conditional"
    )


def test_generic_type_parameters_shadow_module_capabilities():
    g = graph({"a.py": "def f(): return 1\ndef run[f](): return f()"})
    assert not g.capability_calls("python:a:run")


def test_lazy_type_alias_expressions_do_not_belong_to_enclosing_callable():
    g = graph({"a.py": "def f(): return 1\ndef run():\n type Alias = f()\n return 1"})
    assert not g.capability_calls("python:a:run")


@pytest.mark.timeout(5)
def test_wide_import_declarations_are_indexed_without_quadratic_alias_search():
    declaration = "import " + ",".join(f"lib{i} as alias{i}" for i in range(2500))
    g = graph(
        {
            "a.py": declaration
            + "\ndef run():\n"
            + "\n".join(f" alias{i}.call()" for i in range(2500))
        }
    )
    assert len(edges(g, K.EXTERNAL)) == 2500
    assert not g.capability_calls("python:a:run")
    assert not g.diagnostics


def test_resolved_references_are_distinct_from_calls_and_imports():
    g = graph(
        {
            "a.py": "import b\nfrom b import f as alias\ndef reference(): return b.f, alias\ndef invoke(): return b.f()\ndef indirect():\n callback = alias\n return callback()",
            "b.py": "def f(): return 1",
        }
    )
    assert edges(g, K.REFERENCE) == {
        ("python:a:reference", "python:b:f"),
        ("python:a:indirect", "python:b:f"),
    }
    assert edges(g, K.CALL) == {("python:a:invoke", "python:b:f")}
    assert (
        len(
            [
                r
                for r in g.relationships
                if r.source == "python:a:reference" and r.kind == K.REFERENCE
            ]
        )
        == 2
    )
    assert edges(g, K.CAPABILITY) == {("python-module:a", "python:b:f")}


@pytest.mark.parametrize(
    "body",
    [
        "def reference(f): return f",
        "def reference():\n return f\n f = replacement",
        "def reference():\n def inner(): return f\n return inner",
        "def reference(): return lambda: f",
        "def reference(): return f.attribute",
        "def reference(): return [f for f in values]",
    ],
)
def test_references_respect_shadowing_nested_scopes_and_attribute_boundaries(body):
    g = graph({"a.py": "def f(): return 1\n" + body})
    assert ("python:a:reference", "python:a:f") not in edges(g, K.REFERENCE)


def test_conditional_references_and_unstable_reference_diagnostics():
    g = graph(
        {
            "a.py": "def f(): return 1\n@decorator\ndef uncertain(): return 1\ndef reference():\n if flag: return f\n return uncertain"
        }
    )
    edge = next(r for r in g.relationships if r.kind == K.REFERENCE)
    assert edge.target == "python:a:f" and edge.availability == "conditional"
    assert Code.REFERENCE in {d.code for d in g.diagnostics}
    assert not edges(g, K.CALL)


def test_bare_dynamic_import_reference_does_not_claim_dynamic_invocation():
    g = graph(
        {
            "a.py": "from importlib import import_module\ndef reference(): return import_module, __import__"
        }
    )
    assert Code.DYNAMIC not in {d.code for d in g.diagnostics}
    assert not edges(g, K.REFERENCE)
