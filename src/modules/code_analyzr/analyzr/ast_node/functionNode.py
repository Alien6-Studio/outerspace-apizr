import ast

from .annotationNode import AnnotationNode
from .argNode import ArgNode
from .astNode import AstNode


class FunctionNode(AstNode):
    def __init__(self, node):
        super().__init__(node)
        self.name = node.name
        self.args = self.get_args()
        self.returns = AnnotationNode(node.returns)
        self.selected = True
        if isinstance(node, ast.AsyncFunctionDef):
            self.is_async = True

    def get_args(self):
        args = self.node.args
        if args.vararg or args.kwarg:
            raise ValueError(
                f"Function {self.node.name}: *args and **kwargs cannot be exposed as a fixed JSON schema"
            )
        positional = args.posonlyargs + args.args
        required_count = len(positional) - len(args.defaults)
        result = []
        for index, node in enumerate(positional):
            argument = ArgNode(node)
            if index < len(args.posonlyargs):
                argument.kind = "positional_only"
            if index >= required_count:
                argument.has_default = True
            result.append(argument)
        for node, default in zip(args.kwonlyargs, args.kw_defaults):
            argument = ArgNode(node)
            argument.kind = "keyword_only"
            if default is not None:
                argument.has_default = True
            result.append(argument)
        return result
