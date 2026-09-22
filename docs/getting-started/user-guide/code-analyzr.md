# Using Code Analyzr

Analyze a script without generating an API:

```sh
uv run python -m apizr.modules.code_analyzr.main path/to/business.py --force --output metadata.json
```

The file is a positional argument. Options include `--analyze function1,function2`, `--ignore helper`, `--configuration config.yaml`, `--version 3.11`, and `--encoding utf-8`. The standalone module prompts when neither `--force` nor a configuration is provided.

For the complete pipeline, use `uv run apizr --script path/to/business.py`.

0.3 adds a [class/method inventory](../../modules/code-analyzr.md#classes-and-methods-in-03)
without exposing those methods automatically. Duplicate selected function names
and overload sets are rejected before API generation; use an explicit unambiguous
wrapper or exclude the name with `--ignore`.
