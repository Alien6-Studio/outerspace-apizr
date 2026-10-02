"""One static CLI grammar and bounded local backend for three shell adapters."""

import argparse
import sys
from collections.abc import Sequence

from apizr.completion_spec import COMMANDS

SHELLS = ("bash", "zsh", "fish")
FILES = "__apizr_files__"


def candidates(words: Sequence[str]) -> tuple[str, ...]:
    if len(words) > 128 or any(
        len(word) > 2048 or any(ord(c) < 32 for c in word) for word in words
    ):
        return ()
    node = COMMANDS
    prefix = words[-1] if words else ""
    previous = words[:-1]
    pending = None
    position = 0
    options = True
    for word in previous:
        if pending is not None:
            pending = None
            continue
        if options and word == "--":
            options = False
            continue
        if options and word.startswith("-"):
            key, equals, _ = word.partition("=")
            option = node["options"].get(key)
            if option is None:
                return ()
            if option["value"] and not equals:
                pending = option
            continue
        if word in node["commands"]:
            node = node["commands"][word]
            position = 0
        elif position < len(node["arguments"]):
            if node["arguments"][position]["nargs"] not in ("*", "+"):
                position += 1
        else:
            return ()
    lead = ""
    if pending is None and options and prefix.startswith("--") and "=" in prefix:
        key, _, prefix = prefix.partition("=")
        pending = node["options"].get(key)
        if pending is None:
            return ()
        lead = key + "="
    if pending is not None:
        values = pending["choices"]
        if not values and pending["path"]:
            return (FILES,)
    elif options and prefix.startswith("-"):
        values = list(node["options"])
    elif node["commands"]:
        values = list(node["commands"])
    elif position < len(node["arguments"]):
        argument = node["arguments"][position]
        values = argument["choices"]
        if not values and argument["path"]:
            return (FILES,)
    else:
        values = []
    return tuple(lead + value for value in sorted(values) if value.startswith(prefix))


def script(shell: str) -> str:
    if shell == "bash":
        return """# Apizr modern CLI completion; source this file explicitly.
_apizr_complete() {
    local candidate current="${COMP_WORDS[COMP_CWORD]}"
    COMPREPLY=()
    while IFS= read -r candidate; do
        if [[ "$candidate" == "__apizr_files__" ]]; then
            while IFS= read -r candidate; do COMPREPLY+=("$candidate"); done < <(compgen -f -- "$current")
        else
            COMPREPLY+=("$candidate")
        fi
    done < <(command apizr __complete -- "${COMP_WORDS[@]:1:COMP_CWORD}")
}
complete -F _apizr_complete apizr
"""
    if shell == "zsh":
        return """#compdef apizr
_apizr() {
    local -a candidates
    candidates=("${(@f)$(command apizr __complete -- "${words[@]:1:$((CURRENT - 1))}")}")
    if [[ "${candidates[1]}" == "__apizr_files__" ]]; then
        _files
    elif (( ${#candidates} )); then
        compadd -- "${candidates[@]}"
    fi
}
compdef _apizr apizr
"""
    if shell == "fish":
        return """# Apizr modern CLI completion; install this file explicitly.
function __apizr_candidates
    set -l words (commandline -opc)
    set -e words[1]
    set -l current (commandline -ct)
    set -l candidates (command apizr __complete -- $words "$current")
    if test "$candidates[1]" = __apizr_files__
        __fish_complete_path "$current"
    else
        printf '%s\\n' $candidates
    end
end
complete -c apizr -f -a '(__apizr_candidates)'
"""
    raise ValueError("completion_shell_invalid")


def main(argv: Sequence[str], *, backend: bool = False) -> int:
    if backend:
        words = list(argv)
        if words[:1] == ["--"]:
            words = words[1:]
        for value in candidates(words):
            print(value)
        return 0
    parser = argparse.ArgumentParser(prog="apizr completion")
    parser.add_argument("shell", choices=SHELLS)
    args = parser.parse_args(argv)
    sys.stdout.write(script(args.shell))
    return 0
