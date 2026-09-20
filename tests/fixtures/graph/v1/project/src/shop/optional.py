if feature_enabled:
    import optional_service


def preview(value: int) -> int:
    from .pricing import calculate
    return calculate(value)


def load_plugin(name: str):
    import importlib
    return importlib.import_module(name)


from optional_exports import *
