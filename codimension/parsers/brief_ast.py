# -*- coding: utf-8 -*-
#
# codimension - pure Python brief module info parser (ast-based)
# Copyright (C) 2010-2025  Sergey Satskiy <sergey.satskiy@gmail.com>
#
# Fallback for cdmpyparser when C extension unavailable (Python 3.11+).
# Uses ast module - compatible with Python 3.8+ grammar.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Pure-Python cdmpyparser replacement using ast module."""

from __future__ import annotations

import ast
import tokenize
from sys import maxsize

try:
    from .source_spans import SourceIndex
except ImportError:  # loaded as standalone module (conformance harness)
    from parsers.source_spans import SourceIndex

VERSION = "3.4.0-ast"


def trim_docstring(docstring):
    """PEP 257 docstring trimming."""
    if not docstring:
        return ""
    lines = docstring.expandtabs().splitlines()
    indent = maxsize
    for line in lines[1:]:
        stripped = line.lstrip()
        if stripped:
            indent = min(indent, len(line) - len(stripped))
    lines[0] = lines[0].strip()
    if indent < maxsize:
        for i in range(1, len(lines)):
            lines[i] = lines[i][indent:].rstrip()
    while lines and not lines[-1]:
        del lines[-1]
    while lines and not lines[0]:
        del lines[0]
    return "\n".join(lines)


def _abs_pos(source: str, lineno: int, col_offset: int) -> int:
    """Compute 0-based absolute character position (UTF-8-aware via SourceIndex)."""
    return SourceIndex.build(source).abs_char_pos(lineno, col_offset)


# Re-export all classes for cdmpyparser API compatibility
# (copied from cdmpyparser - data structures only)


class ModuleInfoBase:
    __slots__ = ["name", "line", "pos", "absPosition"]

    def __init__(self, name, line, pos, absPosition):
        self.name = name
        self.line = line
        self.pos = pos
        self.absPosition = absPosition

    def isPrivate(self):
        return self.name.startswith("__")

    def isProtected(self):
        return not self.isPrivate() and self.name.startswith("_")

    def _getLPA(self):
        return ":".join([str(self.line), str(self.pos), str(self.absPosition)])

    def getDisplayName(self):
        return self.name


class Encoding(ModuleInfoBase):
    __slots__ = []

    def __init__(self, encName, line, pos, absPosition):
        super().__init__(encName, line, pos, absPosition)

    def __str__(self):
        return "Encoding[" + self._getLPA() + "]: '" + self.name + "'"


class ImportWhat(ModuleInfoBase):
    __slots__ = ["alias"]

    def __init__(self, whatName, line, pos, absPosition):
        super().__init__(whatName, line, pos, absPosition)
        self.alias = ""

    def __str__(self):
        if self.alias == "":
            return self.name + "[" + self._getLPA() + "]"
        return self.name + "[" + self._getLPA() + "] as " + self.alias

    def getDisplayName(self):
        return self.name if self.alias == "" else self.name + " as " + self.alias


class Import(ModuleInfoBase):
    __slots__ = ["alias", "what"]

    def __init__(self, importName, line, pos, absPosition):
        super().__init__(importName, line, pos, absPosition)
        self.alias = ""
        self.what = []

    def __str__(self):
        out = "Import[" + self._getLPA() + "]: '" + self.name + "'"
        if self.alias != "":
            out += " as '" + self.alias + "'"
        for item in self.what:
            out += "\n    " + str(item)
        return out

    def getDisplayName(self):
        return self.name if self.alias == "" else self.name + " as " + self.alias


class Global(ModuleInfoBase):
    __slots__ = []

    def __init__(self, globalName, line, pos, absPosition):
        super().__init__(globalName, line, pos, absPosition)

    def __str__(self):
        return "Global[" + self._getLPA() + "]: '" + self.name + "'"


class ClassAttribute(ModuleInfoBase):
    __slots__ = []

    def __init__(self, attrName, line, pos, absPosition):
        super().__init__(attrName, line, pos, absPosition)

    def __str__(self):
        return "Class attribute[" + self._getLPA() + "]: '" + self.name + "'"


class InstanceAttribute(ModuleInfoBase):
    __slots__ = []

    def __init__(self, attrName, line, pos, absPosition):
        super().__init__(attrName, line, pos, absPosition)

    def __str__(self):
        return "Instance attribute[" + self._getLPA() + "]: '" + self.name + "'"


class Decorator(ModuleInfoBase):
    __slots__ = ["arguments"]

    def __init__(self, decorName, line, pos, absPosition):
        super().__init__(decorName, line, pos, absPosition)
        self.arguments = None

    def __str__(self):
        val = "Decorator[" + self._getLPA() + "]: '" + self.name
        if self.arguments is not None:
            val += "(" + ", ".join(self.arguments) + ")"
        return val + "'"

    def getDisplayName(self):
        if self.arguments is not None:
            return self.name + "(" + ", ".join(self.arguments) + ")"
        return self.name


class Docstring:
    __slots__ = ["startLine", "endLine", "line", "text"]

    def __init__(self, text, startLine, endLine):
        self.startLine = startLine
        self.endLine = endLine
        self.text = text
        self.line = endLine

    def __str__(self):
        return "Docstring[" + str(self.startLine) + ":" + str(self.endLine) + "]: '" + self.text + "'"


class Argument:
    __slots__ = ["name", "annotation", "value"]

    def __init__(self, name, annotation):
        self.name = name
        self.annotation = annotation
        self.value = None

    def __str__(self):
        output = self.name
        if self.annotation is not None:
            output += ": " + self.annotation
        if self.value is not None:
            output += "=" + self.value
        return output


class Function(ModuleInfoBase):
    __slots__ = [
        "keywordLine",
        "keywordPos",
        "colonLine",
        "colonPos",
        "docstring",
        "arguments",
        "decorators",
        "functions",
        "classes",
        "isAsync",
        "returnAnnotation",
    ]

    def __init__(
        self, funcName, line, pos, absPosition, keywordLine, keywordPos, colonLine, colonPos, isAsync, returnAnnotation
    ):
        super().__init__(funcName, line, pos, absPosition)
        self.keywordLine = keywordLine
        self.keywordPos = keywordPos
        self.colonLine = colonLine
        self.colonPos = colonPos
        self.isAsync = isAsync
        self.returnAnnotation = returnAnnotation
        self.docstring = None
        self.arguments = []
        self.decorators = []
        self.functions = []
        self.classes = []

    def isStaticMethod(self):
        return any(d.name == "staticmethod" for d in self.decorators)

    def niceStringify(self, level):
        out = (
            level * "    "
            + "Function["
            + str(self.keywordLine)
            + ":"
            + str(self.keywordPos)
            + ":"
            + self._getLPA()
            + ":"
            + str(self.colonLine)
            + ":"
            + str(self.colonPos)
            + "]: '"
            + self.name
            + "'"
        )
        if self.isAsync:
            out += " (async)"
        if self.returnAnnotation is not None:
            out += " -> '" + self.returnAnnotation + "'"
        for item in self.arguments:
            out += "\n" + level * "    " + "Argument: '" + str(item) + "'"
        for item in self.decorators:
            out += "\n" + level * "    " + str(item)
        if self.docstring is not None:
            out += "\n" + level * "    " + str(self.docstring)
        for item in self.functions:
            out += "\n" + item.niceStringify(level + 1)
        for item in self.classes:
            out += "\n" + item.niceStringify(level + 1)
        return out

    def getDisplayName(self):
        displayName = ("async " if self.isAsync else "") + self.name + "("
        displayName += ", ".join(str(a) for a in self.arguments) + ")"
        if self.returnAnnotation is not None:
            displayName += " -> " + self.returnAnnotation
        return displayName


class Class(ModuleInfoBase):
    __slots__ = [
        "keywordLine",
        "keywordPos",
        "colonLine",
        "colonPos",
        "docstring",
        "base",
        "decorators",
        "classAttributes",
        "instanceAttributes",
        "functions",
        "classes",
    ]

    def __init__(self, className, line, pos, absPosition, keywordLine, keywordPos, colonLine, colonPos):
        super().__init__(className, line, pos, absPosition)
        self.keywordLine = keywordLine
        self.keywordPos = keywordPos
        self.colonLine = colonLine
        self.colonPos = colonPos
        self.docstring = None
        self.base = []
        self.decorators = []
        self.classAttributes = []
        self.instanceAttributes = []
        self.functions = []
        self.classes = []

    def niceStringify(self, level):
        out = (
            level * "    "
            + "Class["
            + str(self.keywordLine)
            + ":"
            + str(self.keywordPos)
            + ":"
            + self._getLPA()
            + ":"
            + str(self.colonLine)
            + ":"
            + str(self.colonPos)
            + "]: '"
            + self.name
            + "'"
        )
        for item in self.base:
            out += "\n" + level * "    " + "Base class: '" + item + "'"
        for item in self.decorators:
            out += "\n" + level * "    " + str(item)
        if self.docstring is not None:
            out += "\n" + level * "    " + str(self.docstring)
        for item in self.classAttributes:
            out += "\n" + level * "    " + str(item)
        for item in self.instanceAttributes:
            out += "\n" + level * "    " + str(item)
        for item in self.functions:
            out += "\n" + item.niceStringify(level + 1)
        for item in self.classes:
            out += "\n" + item.niceStringify(level + 1)
        return out

    def getDisplayName(self):
        return self.name + ("(" + ", ".join(self.base) + ")" if self.base else "")


class BriefModuleInfo:
    __slots__ = [
        "isOK",
        "docstring",
        "encoding",
        "imports",
        "globals",
        "functions",
        "classes",
        "errors",
        "lexerErrors",
        "objectsStack",
        "_BriefModuleInfo__lastImport",
        "_BriefModuleInfo__lastDecorators",
    ]

    def __init__(self):
        self.isOK = True
        self.docstring = None
        self.encoding = None
        self.imports = []
        self.globals = []
        self.functions = []
        self.classes = []
        self.errors = []
        self.lexerErrors = []
        self.objectsStack = []
        self.__lastImport = None
        self.__lastDecorators = None

    def niceStringify(self):
        out = ""
        if self.docstring is not None:
            out += str(self.docstring)
        if self.encoding is not None:
            if out:
                out += "\n"
            out += str(self.encoding)
        for item in self.imports:
            if out:
                out += "\n"
            out += str(item)
        for item in self.globals:
            if out:
                out += "\n"
            out += str(item)
        for item in self.functions:
            if out:
                out += "\n"
            out += item.niceStringify(0)
        for item in self.classes:
            if out:
                out += "\n"
            out += item.niceStringify(0)
        return out

    def flush(self):
        self._flush_level(0)
        if self.__lastImport is not None:
            self.imports.append(self.__lastImport)

    def _onEncoding(self, encString, line, pos, absPosition):
        self.encoding = Encoding(encString, line, pos, absPosition)

    def _onGlobal(self, name, line, pos, absPosition, level):
        for item in self.globals:
            if item.name == name:
                return
        self.globals.append(Global(name, line, pos, absPosition))

    def _onClass(self, name, line, pos, absPosition, keywordLine, keywordPos, colonLine, colonPos, level):
        self._flush_level(level)
        c = Class(name, line, pos, absPosition, keywordLine, keywordPos, colonLine, colonPos)
        if self.__lastDecorators is not None:
            c.decorators = self.__lastDecorators
            self.__lastDecorators = None
        self.objectsStack.append(c)

    def _onFunction(
        self,
        name,
        line,
        pos,
        absPosition,
        keywordLine,
        keywordPos,
        colonLine,
        colonPos,
        level,
        isAsync,
        returnAnnotation,
    ):
        self._flush_level(level)
        f = Function(
            name, line, pos, absPosition, keywordLine, keywordPos, colonLine, colonPos, isAsync, returnAnnotation
        )
        if self.__lastDecorators is not None:
            f.decorators = self.__lastDecorators
            self.__lastDecorators = None
        self.objectsStack.append(f)

    def _onImport(self, name, line, pos, absPosition):
        if self.__lastImport is not None:
            self.imports.append(self.__lastImport)
        self.__lastImport = Import(name, line, pos, absPosition)

    def _onAs(self, name):
        if self.__lastImport.what:
            self.__lastImport.what[-1].alias = name
        else:
            self.__lastImport.alias = name

    def _onWhat(self, name, line, pos, absPosition):
        self.__lastImport.what.append(ImportWhat(name, line, pos, absPosition))

    def _onClassAttribute(self, name, line, pos, absPosition, level):
        attributes = self.objectsStack[level].classAttributes
        for item in attributes:
            if item.name == name:
                return
        attributes.append(ClassAttribute(name, line, pos, absPosition))

    def _onInstanceAttribute(self, name, line, pos, absPosition, level):
        if level < 1:
            return
        parent = self.objectsStack[level - 1]
        if not hasattr(parent, "instanceAttributes"):
            return  # Inside function: local variable, not instance attribute
        attributes = parent.instanceAttributes
        for item in attributes:
            if item.name == name:
                return
        attributes.append(InstanceAttribute(name, line, pos, absPosition))

    def _onDecorator(self, name, line, pos, absPosition):
        d = Decorator(name, line, pos, absPosition)
        if self.__lastDecorators is None:
            self.__lastDecorators = [d]
        else:
            self.__lastDecorators.append(d)

    def _onDecoratorArgument(self, name):
        if self.__lastDecorators[-1].arguments is None:
            self.__lastDecorators[-1].arguments = [name]
        else:
            self.__lastDecorators[-1].arguments.append(name)

    def _onDocstring(self, docstr, startLine, endLine):
        if self.objectsStack:
            self.objectsStack[-1].docstring = Docstring(trim_docstring(docstr), startLine, endLine)
        else:
            self.docstring = Docstring(trim_docstring(docstr), startLine, endLine)

    def _onArgument(self, name, annotation, value=None):
        """Append an argument; optional default ``value`` set immediately."""
        arg = Argument(name, annotation)
        if value is not None:
            arg.value = value
        self.objectsStack[-1].arguments.append(arg)

    def _onArgumentValue(self, value):
        """Set default on the most recently appended argument (compat)."""
        self.objectsStack[-1].arguments[-1].value = value

    def _onBaseClass(self, name):
        self.objectsStack[-1].base.append(name)

    def _onError(self, message):
        self.isOK = False
        if message.strip():
            self.errors.append(message)

    def _onLexerError(self, message):
        self.isOK = False
        if message.strip():
            self.lexerErrors.append(message)

    def _flush_level(self, level):
        while len(self.objectsStack) > level:
            last_idx = len(self.objectsStack) - 1
            if last_idx == 0:
                obj = self.objectsStack[0]
                if obj.__class__.__name__ == "Class":
                    self.classes.append(obj)
                else:
                    self.functions.append(obj)
                self.objectsStack = []
                break
            if self.objectsStack[last_idx].__class__.__name__ == "Class":
                self.objectsStack[last_idx - 1].classes.append(self.objectsStack[last_idx])
            else:
                self.objectsStack[last_idx - 1].functions.append(self.objectsStack[last_idx])
            del self.objectsStack[last_idx]


def _annotation_str(node):
    """Convert ast node to annotation string."""
    if node is None:
        return None
    if isinstance(node, ast.Constant):
        return str(node.value)
    try:
        return ast.unparse(node) if hasattr(ast, "unparse") else None
    except Exception:
        return None


def _expr_str(node):
    """Convert an AST expression to a short source-like string."""
    if node is None:
        return None
    try:
        if hasattr(ast, "unparse"):
            return ast.unparse(node)
    except Exception:
        pass
    if isinstance(node, ast.Constant):
        return repr(node.value)
    return None


def _is_staticmethod_node(node: ast.AST) -> bool:
    """True if ``node`` has a ``@staticmethod`` decorator."""
    for dec in getattr(node, "decorator_list", []) or []:
        if isinstance(dec, ast.Name) and dec.id == "staticmethod":
            return True
        if isinstance(dec, ast.Attribute) and dec.attr == "staticmethod":
            return True
        if isinstance(dec, ast.Call):
            func = dec.func
            if isinstance(func, ast.Name) and func.id == "staticmethod":
                return True
            if isinstance(func, ast.Attribute) and func.attr == "staticmethod":
                return True
    return False


def _method_self_name(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """Return first parameter name for instance methods; None for staticmethods."""
    if _is_staticmethod_node(node):
        return None
    args = list(node.args.posonlyargs or []) + list(node.args.args or [])
    if not args:
        return None
    return args[0].arg


def _attr_name_for_instance(target: ast.AST, self_name: str) -> str | None:
    """If ``target`` is ``self_name.attr``, return ``attr``; else None."""
    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
        if target.value.id == self_name:
            return target.attr
    return None


def _iter_bound_names(target: ast.AST):
    """Yield simple ``Name`` ids bound by an assignment target (incl. unpacking)."""
    if isinstance(target, ast.Name):
        yield target.id
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            yield from _iter_bound_names(elt)
    elif isinstance(target, ast.Starred):
        yield from _iter_bound_names(target.value)


def _iter_instance_attr_names(target: ast.AST, self_name: str):
    """Yield instance attribute names from a target (incl. unpacking of attrs)."""
    attr = _attr_name_for_instance(target, self_name)
    if attr is not None:
        yield attr
        return
    if isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            yield from _iter_instance_attr_names(elt, self_name)
    elif isinstance(target, ast.Starred):
        yield from _iter_instance_attr_names(target.value, self_name)


def _assignment_targets(stmt: ast.AST) -> list[ast.AST]:
    """Return assignable targets from Assign / AnnAssign / AugAssign."""
    if isinstance(stmt, ast.Assign):
        return list(stmt.targets)
    if isinstance(stmt, ast.AnnAssign) and stmt.target is not None:
        return [stmt.target]
    if isinstance(stmt, ast.AugAssign):
        return [stmt.target]
    return []


def _iter_suite_statements(stmts: list[ast.stmt]):
    """Yield statements in a suite, recursively into control-flow bodies (T015).

    Does **not** descend into nested function/class bodies — those are visited
    via ``visit_func`` / ``visit_class`` so attributes stay in the right scope.
    """
    for stmt in stmts:
        yield stmt
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(stmt, ast.If):
            yield from _iter_suite_statements(stmt.body)
            yield from _iter_suite_statements(stmt.orelse)
        elif isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
            yield from _iter_suite_statements(stmt.body)
            yield from _iter_suite_statements(stmt.orelse)
        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            yield from _iter_suite_statements(stmt.body)
        elif isinstance(stmt, ast.Try):
            yield from _iter_suite_statements(stmt.body)
            for handler in stmt.handlers:
                yield from _iter_suite_statements(handler.body)
            yield from _iter_suite_statements(stmt.orelse)
            yield from _iter_suite_statements(stmt.finalbody)
        else:
            # ast.TryStar (3.11+) and match/case (3.10+)
            try_star = getattr(ast, "TryStar", None)
            if try_star is not None and isinstance(stmt, try_star):
                yield from _iter_suite_statements(stmt.body)
                for handler in stmt.handlers:
                    yield from _iter_suite_statements(handler.body)
                yield from _iter_suite_statements(stmt.orelse)
                yield from _iter_suite_statements(stmt.finalbody)
                continue
            if isinstance(stmt, ast.Match):
                for case in stmt.cases:
                    yield from _iter_suite_statements(case.body)


def _emit_function_arguments(mod_info: BriefModuleInfo, arguments: ast.arguments) -> None:
    """Emit positional-only, positional, vararg, kw-only, and kwarg with correct defaults.

    Defaults on ``arguments.defaults`` map to the trailing subset of
    ``posonlyargs + args``. ``kw_defaults`` maps 1:1 to ``kwonlyargs``
    (``None`` means no default). Inserts ``/`` and bare ``*`` markers when needed
    for signature fidelity (T011/T012).
    """
    posonly = list(arguments.posonlyargs or [])
    regular = list(arguments.args or [])
    all_pos = posonly + regular
    defaults = list(arguments.defaults or [])
    default_start = len(all_pos) - len(defaults)

    def _emit_pos_arg(arg: ast.arg, index: int) -> None:
        value = None
        if index >= default_start:
            value = _expr_str(defaults[index - default_start])
        mod_info._onArgument(arg.arg, _annotation_str(arg.annotation), value)

    for i, arg in enumerate(posonly):
        _emit_pos_arg(arg, i)
    if posonly:
        mod_info._onArgument("/", None)

    for i, arg in enumerate(regular):
        _emit_pos_arg(arg, len(posonly) + i)

    if arguments.vararg is not None:
        mod_info._onArgument(
            "*" + arguments.vararg.arg,
            _annotation_str(arguments.vararg.annotation),
        )
    elif arguments.kwonlyargs:
        mod_info._onArgument("*", None)

    for arg, default in zip(arguments.kwonlyargs or [], arguments.kw_defaults or []):
        value = _expr_str(default) if default is not None else None
        mod_info._onArgument(arg.arg, _annotation_str(arg.annotation), value)

    if arguments.kwarg is not None:
        mod_info._onArgument(
            "**" + arguments.kwarg.arg,
            _annotation_str(arguments.kwarg.annotation),
        )


def _ast_to_brief(mod_info: BriefModuleInfo, source: str, filename: str) -> None:
    """Populate BriefModuleInfo from AST."""
    try:
        tree = ast.parse(source, filename, mode="exec", type_comments=True)
    except SyntaxError as e:
        mod_info.isOK = False
        mod_info.errors.append(str(e))
        return

    mod_info.isOK = True
    index = SourceIndex.build(source)

    def pos(node):
        """Return (lineno, 1-based char column, 0-based abs char position)."""
        if node is None:
            return 1, 1, 0
        begin, _end, ln, _eln, bpos, _epos = index.node_span(node)
        return ln, bpos, begin

    def docstring_from_node(node):
        doc = ast.get_docstring(node)
        if doc and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                if isinstance(first.value.value, str):
                    end_ln = getattr(first, "end_lineno", first.lineno) or first.lineno
                    return (doc, first.lineno, end_ln)
        return None

    # Module docstring
    doc = ast.get_docstring(tree)
    if doc and tree.body:
        first = tree.body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            if isinstance(first.value.value, str):
                end_ln = getattr(first, "end_lineno", first.lineno) or first.lineno
                mod_info._onDocstring(doc, first.lineno, end_ln)

    # Encoding from first lines
    import re

    for i, line in enumerate(source.split("\n")[:2]):
        if "coding" in line or "encoding" in line.lower():
            m = re.search(r"coding[:=]\s*([-\w.]+)", line)
            if m:
                ln = i + 1
                mod_info._onEncoding(m.group(1).strip(), ln, 1, index.line_start(ln))
            break

    # Module-level: imports and globals (including inside control-flow; T015/audit P0)
    for node in _iter_suite_statements(tree.body):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, ast.Import):
            for alias in node.names:
                ln, p, ap = pos(node)
                mod_info._onImport(alias.name, ln, p, ap)
                if alias.asname:
                    mod_info._onAs(alias.asname)
        elif isinstance(node, ast.ImportFrom):
            ln, p, ap = pos(node)
            level = getattr(node, "level", 0) or 0
            mod_name = ("." * level) + (node.module or "")
            mod_info._onImport(mod_name, ln, p, ap)
            for alias in node.names:
                mod_info._onWhat(alias.name, ln, p, ap)
                if alias.asname:
                    mod_info._onAs(alias.asname)
        else:
            for t in _assignment_targets(node):
                ln, p, ap = pos(node)
                for name in _iter_bound_names(t):
                    mod_info._onGlobal(name, ln, p, ap, 0)

    def visit_class(node, level):
        # Decorators first
        for dec in node.decorator_list:
            dec_name = None
            if isinstance(dec, ast.Name):
                dec_name = dec.id
            elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
                dec_name = dec.func.id
            elif hasattr(ast, "unparse"):
                try:
                    dec_name = ast.unparse(dec)
                except Exception:
                    dec_name = "decorator"
            if dec_name:
                ln, p, ap = pos(dec)
                mod_info._onDecorator(dec_name, ln, p, ap)
        ln, p, ap = pos(node)
        kw_ln, kw_p = ln, p
        colon_ln = getattr(node, "end_lineno", ln) or ln
        colon_p = 1
        mod_info._onClass(node.name, ln, p, ap, kw_ln, kw_p, colon_ln, colon_p, level)
        for base in node.bases:
            if isinstance(base, ast.Name):
                mod_info._onBaseClass(base.id)
            elif hasattr(ast, "unparse"):
                try:
                    mod_info._onBaseClass(ast.unparse(base))
                except Exception:
                    pass
        ds = docstring_from_node(node)
        if ds:
            mod_info._onDocstring(ds[0], ds[1], ds[2])

        def _handle_class_stmt(stmt: ast.AST) -> None:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit_func(stmt, level + 1)
            elif isinstance(stmt, ast.ClassDef):
                visit_class(stmt, level + 1)
            else:
                for t in _assignment_targets(stmt):
                    ln2, p2, ap2 = pos(stmt)
                    for name in _iter_bound_names(t):
                        mod_info._onClassAttribute(name, ln2, p2, ap2, level)

        for stmt in _iter_suite_statements(node.body):
            _handle_class_stmt(stmt)
        mod_info._flush_level(level)

    def visit_func(node, level):
        # Decorators first
        for dec in node.decorator_list:
            dec_name = None
            if isinstance(dec, ast.Name):
                dec_name = dec.id
            elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
                dec_name = dec.func.id
            elif hasattr(ast, "unparse"):
                try:
                    dec_name = ast.unparse(dec)
                except Exception:
                    dec_name = "decorator"
            if dec_name:
                ln, p, ap = pos(dec)
                mod_info._onDecorator(dec_name, ln, p, ap)
        ln, p, ap = pos(node)
        kw_ln, kw_p = ln, p
        colon_ln = getattr(node, "end_lineno", ln) or ln
        colon_p = 1
        ret_ann = _annotation_str(node.returns)
        is_async = isinstance(node, ast.AsyncFunctionDef)
        mod_info._onFunction(node.name, ln, p, ap, kw_ln, kw_p, colon_ln, colon_p, level, is_async, ret_ann)
        _emit_function_arguments(mod_info, node.args)
        self_name = _method_self_name(node)
        ds = docstring_from_node(node)
        if ds:
            mod_info._onDocstring(ds[0], ds[1], ds[2])

        def _collect_instance_attrs(stmt: ast.AST) -> None:
            """Record ``self.attr`` / ``cls.attr``; ignore local Name binds."""
            if self_name is None:
                return
            for t in _assignment_targets(stmt):
                for attr in _iter_instance_attr_names(t, self_name):
                    ln2, p2, ap2 = pos(stmt)
                    mod_info._onInstanceAttribute(attr, ln2, p2, ap2, level)

        for stmt in _iter_suite_statements(node.body):
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit_func(stmt, level + 1)
            elif isinstance(stmt, ast.ClassDef):
                visit_class(stmt, level + 1)
            else:
                _collect_instance_attrs(stmt)
        mod_info._flush_level(level)

    # Nested / control-flow-wrapped defs at module level (audit P0)
    for node in _iter_suite_statements(tree.body):
        if isinstance(node, ast.ClassDef):
            visit_class(node, 0)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            visit_func(node, 0)


def getBriefModuleInfoFromMemory(content: str, filename: str = "<string>") -> BriefModuleInfo:
    """Build brief module info from string content."""
    mod_info = BriefModuleInfo()
    _ast_to_brief(mod_info, content, filename)
    mod_info.flush()
    return mod_info


def getBriefModuleInfoFromFile(fileName: str) -> BriefModuleInfo:
    """Build brief module info from file using PEP 263 encoding detection."""
    with tokenize.open(fileName) as f:
        content = f.read()
    mod_info = BriefModuleInfo()
    _ast_to_brief(mod_info, content, fileName)
    mod_info.flush()
    return mod_info


def getVersion() -> str:
    """Parser version."""
    return VERSION
