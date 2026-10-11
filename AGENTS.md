# Repository development

Use the official development branch `0.4.5`. Keep stable `master`, published
versions and release/tag/publication workflows outside development changes unless
explicitly requested by the user.

## Package composition

Read [the package composition rule](docs/architecture/code-organization.md) before
adding or moving production code. `architecture/packages.toml` is the normative
ownership inventory and `scripts/check_package_architecture.py` is its executable
structural gate.

- Place code in its owning domain. A domain is a responsibility, not a generic
  `utils`, `helpers`, `common` or `services` collection.
- A composition package assembles declared subdomains. Its initializer exports or
  dispatches; it must not acquire new business models or operations.
- Introduce a subpackage only for a coherent independently named responsibility.
  Declare its owner and convert a subdivided leaf to composition explicitly.
- Add no root implementation and no root migration exception. Existing exceptions
  are migration debt; remove an entry when its implementation moves.
- Internal code uses canonical imports. Compatibility facades only forward to the
  single implementation; do not put logic in them or use their docstrings to
  bypass checks.
- Keep CLI adapters outside domains, core plugin management outside optional SDKs,
  and plugin sibling dependencies within the declared acyclic lifecycle graph.
- Preserve embedded runtime resources, generated contracts, installed imports and
  the existing coverage/security gates when moving implementations.

Run `python3 scripts/check_package_architecture.py` and relevant qualification
before committing. This gate also runs in pre-commit and CI. Structural checks do
not replace review of cohesion and dependency meaning.
