"""Lexical allocation budgets applied before a JSON decoder builds its graph."""


def preflight_json(
    raw: bytes | str, *, max_bytes: int, max_nodes: int, max_depth: int
) -> str:
    """Count containers, keys and scalar tokens without materializing JSON values.

    This is a resource check, not a syntax validator. The ordinary JSON decoder
    still validates syntax. UTF-8 is explicit so an alternate encoding cannot
    conceal structural delimiters. Escaped quotes and delimiters inside strings
    never count as structure. The only growing state is a bounded depth counter.
    """
    if len(raw) > max_bytes:
        raise ValueError("json_byte_limit")
    if isinstance(raw, bytes):
        text = raw.decode("utf-8-sig")
    else:
        if len(raw.encode("utf-8")) > max_bytes:
            raise ValueError("json_byte_limit")
        text = raw
    quoted = escaped = scalar = False
    nodes = depth = 0
    for character in text:
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
            continue
        if character in " \t\r\n,:]}":
            scalar = False
            if character in "]}":
                depth -= 1
                if depth < 0:
                    raise ValueError("json_structure_invalid")
            continue
        if character in "[{":
            depth += 1
            scalar = False
            nodes += 1
        elif character == '"':
            quoted = True
            scalar = False
            nodes += 1
        elif not scalar:
            scalar = True
            nodes += 1
        if nodes > max_nodes or depth > max_depth:
            raise ValueError("json_structure_limit")
    return text
