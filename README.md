# Apizr website

Canonical website sources live on `gh-pages`. Product code and release qualification live on the product branches.

```sh
uv sync --locked
uv run --locked pytest -q
uv run --locked mkdocs build --strict
uv run --locked python scripts/check_html.py
uv run --locked mkdocs serve
```

Open website PRs against `gh-pages`. Its Pages workflow validates and deploys the exact built artifact. The custom domain stays `apizr.outerspace.sh`.

`site.json` declares the documented product revision and publication status. `downloads.json` binds the downloadable examples to that immutable product revision. Updating the website does not publish Python packages or the extension. Refresh these snapshots deliberately when the corresponding product changes are qualified.
