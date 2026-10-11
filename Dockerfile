# Glama MCP server image — not the product image.
# Glama (https://glama.ai/mcp) builds this file to host the Apizr analysis MCP
# server. It pins the released tag and reuses the same preparation path the CI
# smoke proofs exercise (scripts/smoke_mcp_server.prepare). OCI service images
# for generated targets are produced by the OCI plugin, not by this file.
# bookworm (glibc 2.36) is required: plugin preparation refuses glibc 2.41
# (trixie) — see src/apizr/plugins/preparation/target.py supported versions.
FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    # Outside /root so the runtime non-root user can execute the interpreter
    # the prepared virtualenvs symlink to.
    UV_PYTHON_INSTALL_DIR=/opt/uv/python

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git \
    && curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g mcp-proxy@6.7.16 \
    # Plugin preparation only accepts uv 0.12.x (src/apizr/plugins/preparation/resolver.py)
    && curl -LsSf https://astral.sh/uv/0.12.0/install.sh | UV_INSTALL_DIR="/usr/local/bin" sh \
    && uv python install 3.14 --default --preview \
    && ln -s "$(uv python find)" /usr/local/bin/python \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

WORKDIR /app

RUN git clone --depth 1 --branch v0.4.5 https://github.com/Alien6-Studio/outerspace-apizr .

RUN uv sync --locked \
    && uv run --locked python -c 'import sys; from pathlib import Path; sys.path.insert(0, str(Path.cwd() / "scripts")); from smoke_mcp_server import prepare; prepare(Path("/opt/apizr-inspection"), sys.executable)'

RUN useradd --system --create-home --shell /usr/sbin/nologin apizr \
    && chown -R apizr:apizr /opt/apizr-inspection

USER apizr

CMD ["mcp-proxy", "--", "/opt/apizr-inspection/core/bin/apizr", "mcp", "serve", \
     "--project", "/opt/apizr-inspection/project/apizr.toml", \
     "--operator-policy", "/opt/apizr-inspection/operator.json", \
     "--plugins-dir", "/opt/apizr-inspection/prepared/profile"]
