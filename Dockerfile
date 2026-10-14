# Glama hosts the analysis MCP server from the official development branch.
# Qualification uses Debian 13's measured glibc 2.41 native resolver mode.
FROM ghcr.io/astral-sh/uv:0.13.1 AS uv
FROM node:24-trixie-slim

COPY --from=uv /uv /uvx /usr/local/bin/
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    UV_PYTHON_INSTALL_DIR=/opt/uv/python

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && npm install -g mcp-proxy@6.7.16 \
    && uv python install 3.14 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ARG SOURCE_REF=0.4.6
ARG SOURCE_COMMIT
RUN git clone --depth 1 --branch "$SOURCE_REF" https://github.com/Alien6-Studio/outerspace-apizr . \
    && if [ -n "$SOURCE_COMMIT" ]; then test "$(git rev-parse HEAD)" = "$SOURCE_COMMIT"; fi
RUN uv run --no-project --python 3.14 python -c 'import sys; from pathlib import Path; sys.path.insert(0, str(Path.cwd() / "scripts")); from smoke_mcp_server import prepare; prepare(Path("/opt/apizr-inspection"), sys.executable)'

RUN useradd --system --create-home --shell /usr/sbin/nologin apizr \
    && chown -R apizr:apizr /opt/apizr-inspection
USER apizr

CMD ["mcp-proxy", "--", "/opt/apizr-inspection/core/bin/apizr", "mcp", "serve", \
     "--project", "/opt/apizr-inspection/project/apizr.toml", \
     "--operator-policy", "/opt/apizr-inspection/operator.json", \
     "--plugins-dir", "/opt/apizr-inspection/prepared/profile"]
