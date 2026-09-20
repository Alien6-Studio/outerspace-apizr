import importlib

if feature_enabled:
    import optional_service


def preview(value: int) -> int:
    from .pricing import calculate
    return calculate(value)


def load_plugin(name: str):
    return importlib.import_module(name)
