"""Observe existing recognition hooks; never resolve inputs or controls independently."""

import ast

from apizr.experiments._lexical import bounded_tree
from apizr.experiments.inputs import (
    _Discovery as InputDiscovery,  # pyright: ignore[reportPrivateUsage]
)
from apizr.experiments.model import RandomnessControl
from apizr.experiments.randomness import (
    _Discovery as RandomnessDiscovery,  # pyright: ignore[reportPrivateUsage]
)


class InputLocations(InputDiscovery):
    def __init__(self, reference: str) -> None:
        super().__init__(reference)
        self.locations: dict[str, set[tuple[int, int]]] = {}

    def input_call(self, node: ast.Call, loader: str) -> None:
        super().input_call(node, loader)
        if node.args and isinstance(node.args[0], ast.Constant):
            name = node.args[0].value
            if isinstance(name, str) and name in self.artifacts:
                self.locations.setdefault(name, set()).add(
                    (node.lineno, node.col_offset)
                )


class RandomnessLocations(RandomnessDiscovery):
    def __init__(self, reference: str) -> None:
        super().__init__(reference)
        self.locations: dict[tuple[str, str], set[tuple[int, int]]] = {}

    def record(self, control: RandomnessControl, node: ast.Call) -> None:
        super().record(control, node)
        self.locations.setdefault((control.provider, control.name), set()).add(
            (node.lineno, node.col_offset)
        )


def trace_locations(
    source: str | bytes, reference: str
) -> tuple[InputLocations, RandomnessLocations]:
    tree = bounded_tree(source)
    inputs = InputLocations(reference)
    randomness = RandomnessLocations(reference)
    inputs.visit(tree)
    randomness.visit(tree)
    return inputs, randomness
