"""Example narrower policy: direct accuracy_score imports and literal arguments."""

import ast
import hashlib
import json
import sys

IDENTITY = {"name": "example.literal-accuracy", "version": "1"}


def recognize(arguments):
    source = arguments["source"]
    text = source["text"]
    tree = ast.parse(text)
    aliases = {
        item.asname or item.name: node.lineno
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.level == 0
        and node.module == "sklearn.metrics"
        for item in node.names
        if item.name == "accuracy_score"
    }
    if any(
        not (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module == "sklearn.metrics"
            and all(item.name == "accuracy_score" for item in node.names)
            or isinstance(node, ast.Assign)
            and all(isinstance(target, ast.Name) for target in node.targets)
            or isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
        )
        for node in tree.body
    ):
        aliases.clear()
    if any(
        isinstance(node, ast.Call)
        and (not isinstance(node.func, ast.Name) or node.func.id not in aliases)
        for node in ast.walk(tree)
    ):
        aliases.clear()
    # A deliberately narrow alternative, not a replacement lexical resolver.
    # Any shadowing or star import makes every candidate unknown.
    if any(
        isinstance(n, ast.ImportFrom)
        and any(a.name == "*" for a in n.names)
        or isinstance(n, ast.Name)
        and isinstance(n.ctx, (ast.Store, ast.Del))
        and n.id in aliases
        or isinstance(n, ast.arg)
        and n.arg in aliases
        for n in ast.walk(tree)
    ):
        aliases.clear()
    signals = []
    for node in ast.walk(tree):
        if (
            not isinstance(node, ast.Call)
            or not isinstance(node.func, ast.Name)
            or node.func.id not in aliases
            or node.lineno < aliases[node.func.id]
            or node.keywords
        ):
            continue
        try:
            for value in node.args:
                ast.literal_eval(value)
        except (ValueError, TypeError, RecursionError):
            continue
        signals.append(
            {
                "name": "accuracy",
                "callable_name": "sklearn.metrics.accuracy_score",
                "source": source["reference"],
                "line": node.lineno,
                "column": node.col_offset,
                "origin": "static",
            }
        )
    return {
        "schema_version": "apizr.scientific-result/v1",
        "identity": IDENTITY,
        "source": source["reference"],
        "source_digest": hashlib.sha256(text.encode()).hexdigest(),
        "metric_signals": {
            "signals": signals,
            "relevant_distributions": ["scikit-learn"] if signals else [],
        },
    }


def main():
    raw = sys.stdin.buffer.read(4 * 1024 * 1024 + 1)
    if len(raw) > 4 * 1024 * 1024:
        return 2
    request = json.loads(raw)
    if request["protocol"] != "apizr.extension/v1":
        return 2
    operation = request["operation"]
    if operation == "scientific.describe":
        result = {
            "schema_version": "apizr.scientific-provider/v1",
            "identity": IDENTITY,
            "capabilities": ["metric_signals"],
        }
    elif operation == "scientific.recognize":
        result = recognize(request["arguments"])
    else:
        return 2
    print(
        json.dumps(
            {k: request[k] for k in ("protocol", "request_id", "operation")}
            | {"status": "ok", "result": result}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
