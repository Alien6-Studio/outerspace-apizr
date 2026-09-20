# Using Code Analyzr

Analyze a script without generating an API:

```sh
uv run python -m src.modules.code_analyzr.main path/to/business.py --force --output metadata.json
```

The file is a positional argument. Options include `--analyze function1,function2`, `--ignore helper`, `--configuration config.yaml`, `--version 3.11`, and `--encoding utf-8`. The standalone module prompts when neither `--force` nor a configuration is provided.

For the complete pipeline, use `uv run apizr --script path/to/business.py`.
