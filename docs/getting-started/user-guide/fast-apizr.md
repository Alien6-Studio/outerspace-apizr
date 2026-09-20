# Using Fast Apizr

Generate an API from Code Analyzr metadata:

```sh
uv run python -m apizr.modules.fast_apizr.main metadata.json --force --module_name business --api_filename business_api.py --output .output/api
```

Place `business.py` and its dependencies beside the generated API before running it. The metadata is a positional argument. Options also include `--configuration` and `--encoding`. Use the main `apizr` CLI to automate copying local modules and creating Docker files.
