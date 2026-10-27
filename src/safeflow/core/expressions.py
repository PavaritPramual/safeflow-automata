"""Typed expression subset shared by the interpreter and UPPAAL exporter.

Parsing uses Python's AST, never eval/exec. Calls, indexing, arithmetic and
arbitrary attributes are deliberately outside this language.
"""
import ast
import operator


COMPARE = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
           ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge}
SIGNS = {ast.Eq: '==', ast.NotEq: '!=', ast.Lt: '<', ast.LtE: '<=', ast.Gt: '>', ast.GtE: '>='}


def reference(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return node.value.id + '.' + node.attr
    raise ValueError('unsupported_expression_reference')


class Expression:
    def __init__(self, text, symbols):
        if type(text) is not str or len(text) > 4096:
            raise ValueError('expression_string_required')
        try:
            self.tree = ast.parse(text, mode='eval').body
        except (SyntaxError, RecursionError) as exc:
            raise ValueError('invalid_expression') from exc
        if sum(1 for _ in ast.walk(self.tree)) > 256:
            raise ValueError('expression_too_complex')
        self.text, self.symbols = text, symbols
        if self._type(self.tree) != 'bool':
            raise ValueError('boolean_expression_required')

    def _type(self, node):
        if isinstance(node, ast.Constant):
            if type(node.value) is bool: return 'bool'
            if type(node.value) is int and abs(node.value) <= 2147483647: return 'number'
            if type(node.value) is str: return ('literal', node.value)
            raise ValueError('unsupported_literal')
        if isinstance(node, (ast.Name, ast.Attribute)):
            key = reference(node)
            if key not in self.symbols: raise ValueError('unknown_reference:' + key)
            return self.symbols[key]
        if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            if any(self._type(v) != 'bool' for v in node.values): raise ValueError('boolean_operand_required')
            return 'bool'
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            if self._type(node.operand) != 'bool': raise ValueError('boolean_operand_required')
            return 'bool'
        if isinstance(node, ast.Compare):
            for left, op, right in zip([node.left] + node.comparators, node.ops, node.comparators):
                if type(op) not in COMPARE: raise ValueError('unsupported_comparison')
                a, b = self._type(left), self._type(right)
                if isinstance(a, tuple) and a[0] == 'literal': a, b = b, a
                if isinstance(b, tuple) and b[0] == 'literal':
                    if not isinstance(a, tuple) or a[0] != 'enum' or b[1] not in a[1]:
                        raise ValueError('invalid_enum_literal:' + str(b[1]))
                elif a != b:
                    raise ValueError('incompatible_expression_types')
                if not isinstance(op, (ast.Eq, ast.NotEq)) and a != 'number':
                    raise ValueError('numeric_comparison_required')
            return 'bool'
        raise ValueError('unsupported_expression_node:' + type(node).__name__)

    def evaluate(self, context):
        def visit(n):
            if isinstance(n, ast.Constant): return n.value
            if isinstance(n, (ast.Name, ast.Attribute)): return context[reference(n)]
            if isinstance(n, ast.BoolOp):
                values = [visit(x) for x in n.values]
                return all(values) if isinstance(n.op, ast.And) else any(values)
            if isinstance(n, ast.UnaryOp): return not visit(n.operand)
            return all(COMPARE[type(op)](visit(a), visit(b))
                       for a, op, b in zip([n.left] + n.comparators, n.ops, n.comparators))
        return visit(self.tree)

    def uppaal(self, names, enums):
        def visit(n):
            if isinstance(n, ast.Constant):
                if type(n.value) is bool: return str(n.value).lower()
                if type(n.value) is str: return str(enums[n.value])
                return str(n.value)
            if isinstance(n, (ast.Name, ast.Attribute)): return names[reference(n)]
            if isinstance(n, ast.BoolOp):
                return '(' + (' && ' if isinstance(n.op, ast.And) else ' || ').join(visit(x) for x in n.values) + ')'
            if isinstance(n, ast.UnaryOp): return '!(' + visit(n.operand) + ')'
            return '(' + ' && '.join('(' + visit(a) + SIGNS[type(op)] + visit(b) + ')'
                    for a, op, b in zip([n.left] + n.comparators, n.ops, n.comparators)) + ')'
        return visit(self.tree)
