# Using Fast Apizr

!!! warning "Removed in 0.4.6"

    This historical pipeline is deprecated during 0.4.6 development and will be
    removed before publication. Use `apizr inspect`, explicit exposure selection,
    and `apizr generate rest` or `apizr generate mcp`. See the
    [migration guide](../../releases/migrate-0.4.6.md).

Generate an API from Code Analyzr metadata:

```sh
uv run python -m apizr.modules.fast_apizr.main metadata.json --force --module_name business --api_filename business_api.py --output .output/api
```

Place `business.py` and its dependencies beside the generated API before running it. The metadata is a positional argument. Options also include `--configuration` and `--encoding`. Use the main `apizr` CLI to automate copying local modules and creating Docker files.
