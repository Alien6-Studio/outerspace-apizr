"""MCPB entry point; retain the registry launcher's existing admission boundary."""

from apizr_mcp.launcher import main

if __name__ == "__main__":
    raise SystemExit(main())
