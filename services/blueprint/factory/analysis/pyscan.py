"""AST scan of one Python source text. Nothing is imported or executed. Fail closed on anything unparseable."""
from __future__ import annotations

import ast
import re
import sys

from . import rules as R
from .codes import (CREDENTIAL, DYNAMIC_CODE, FILESYSTEM, HIGH, INTROSPECTION, LOW, MEDIUM, NETWORK, OBFUSCATION, SECRETS,
                    UNDECLARED, UNPARSEABLE, Issue)

STDLIB = getattr(sys, "stdlib_module_names", None) or frozenset()
TEST_TOOLS = frozenset({"pytest", "_pytest"})


class Declared:
    """What the manifest and the component folder declare. Used for the undeclared-capability rules."""

    def __init__(self, requires: tuple = (), sends_to_models: bool = False, local: frozenset = frozenset(),
                 own_id: str = ""):
        self.requires, self.sends_to_models, self.local, self.own_id = tuple(requires), sends_to_models, local, own_id


def _match(name: str, table):
    """Longest-prefix match of a dotted name against a rule table (exact or followed by a dot)."""
    parts = name.split(".")
    for n in range(len(parts), 0, -1):
        key = ".".join(parts[:n])
        if key in table:
            return key, table[key]
    return None, None


def _lit(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _bad_path(p: str):
    if p.startswith(("/", "~", "\\")) or re.match(r"^[A-Za-z]:[\\/]", p):
        return "absolute or home path"
    if ".." in re.split(r"[\\/]", p):
        return "path leaves the component folder ('..')"
    return None


class Scanner(ast.NodeVisitor):
    def __init__(self, path: str, declared: Declared, line_offset: int = 0):
        self.path, self.d, self.off = path, declared, line_offset
        self.names: dict = {}      # local name -> qualified dotted name
        self.issues: dict = {}

    def add(self, node, code, sev, msg):
        line = getattr(node, "lineno", 1) + self.off
        self.issues[(line, code, msg)] = Issue(self.path, line, code, sev, msg)

    def qual(self, node):
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Call):  # Path("x").read_text -> pathlib.Path.read_text
            base = self.qual(node.func)
            if base is None:
                return None
            parts.append(base)
            return ".".join(reversed(parts))
        if isinstance(node, ast.Name):
            root = self.names.get(node.id, node.id if node.id in R.BUILTIN_CALLS else None)
            if root is None:
                return None
            parts.append(root)
            return ".".join(reversed(parts))
        return None

    # imports
    def _module(self, node, mod: str, from_names=()):
        top = mod.split(".")[0]
        key, rule = _match(mod, R.MODULE_RULES)
        if rule:
            self.add(node, rule[0], rule[1], f"import of '{mod}': {rule[2]}")
        key, rule = _match(mod, R.NAME_RULES)
        if rule and mod != "os":
            self.add(node, rule[0], rule[1], f"import of '{mod}': {rule[2]}")
        if _match(mod, {m: 1 for m in R.MODEL_SDKS})[1] and not self.d.sends_to_models:
            self.add(node, UNDECLARED, HIGH, f"model SDK '{mod}' but the manifest does not set "
                     "dataHandling.sendsDataToModels (data could leave through a model call)")
        if top == "components":
            rest = mod.split(".")[1:]
            dotted = ".".join(rest)
            allowed = [r for r in self.d.requires + ((self.d.own_id,) if self.d.own_id else ())]
            if not any(dotted == a or dotted.startswith(a + ".") or a.startswith(dotted + ".") for a in allowed):
                self.add(node, UNDECLARED, MEDIUM, f"imports component '{dotted}' that the manifest does not list in 'requires'")
        elif top and top not in STDLIB and top not in TEST_TOOLS and top not in self.d.local and top != "__future__":
            if not rule and not _match(mod, {m: 1 for m in R.MODEL_SDKS})[1]:
                self.add(node, UNDECLARED, MEDIUM, f"imports third-party module '{top}' that the component does not "
                         "provide and the manifest does not declare")

    def visit_Import(self, node):
        for a in node.names:
            self._module(node, a.name)
            self.names[(a.asname or a.name).split(".")[0]] = a.name if a.asname else a.name.split(".")[0]

    def visit_ImportFrom(self, node):
        if node.level:  # relative import stays in the component
            for a in node.names:
                self.names[a.asname or a.name] = "." + a.name
            return
        mod = node.module or ""
        self._module(node, mod)
        for a in node.names:
            full = f"{mod}.{a.name}" if mod else a.name
            self.names[a.asname or a.name] = full
            key, rule = _match(full, R.MODULE_RULES)
            if rule and full != mod and key != _match(mod, R.MODULE_RULES)[0]:
                self.add(node, rule[0], rule[1], f"import of '{full}': {rule[2]}")
            key, rule = _match(full, R.NAME_RULES)
            if rule:
                self.add(node, rule[0], rule[1], f"import of '{full}': {rule[2]}")

    # names and attributes
    def visit_Attribute(self, node):
        q = self.qual(node)
        if q:
            key, rule = _match(q, R.NAME_RULES)
            if rule:
                self.add(node, rule[0], rule[1], f"'{q}': {rule[2]}")
        if node.attr in R.INTROSPECTION_ATTRS:
            self.add(node, INTROSPECTION, HIGH, f"attribute '{node.attr}' reaches interpreter internals")
        self.generic_visit(node)

    def visit_Name(self, node):
        if node.id == "__builtins__" or node.id in ("globals", "__loader__"):
            self.add(node, INTROSPECTION, HIGH, f"'{node.id}' reaches interpreter internals")
        elif not node.id.isascii():
            self.add(node, OBFUSCATION, MEDIUM, "non-ASCII identifier (possible look-alike characters)")
        else:
            q = self.names.get(node.id)
            if q and q != node.id and isinstance(node.ctx, ast.Load):
                key, rule = _match(q, R.NAME_RULES)
                if rule and q.count(".") >= 1 and q.split(".")[0] in ("os", "shutil", "glob", "yaml", "sys", "pathlib", "tempfile", "asyncio", "threading"):
                    self.add(node, rule[0], rule[1], f"'{q}': {rule[2]}")

    def visit_Call(self, node):
        q = self.qual(node.func)
        fname = node.func.id if isinstance(node.func, ast.Name) else None
        if fname in R.BUILTIN_CALLS and fname not in self.names:
            c, s, m = R.BUILTIN_CALLS[fname]
            self.add(node, c, s, m)
        if fname in ("open",) and "open" not in self.names:
            self._open(node)
        if q in ("io.open", "os.open", "os.fdopen", "codecs.open", "tempfile.mkstemp", "tempfile.mkdtemp",
                 "tempfile.NamedTemporaryFile"):
            self._open(node)
        if q in ("pathlib.Path", "pathlib.PurePath", "pathlib.PosixPath", "os.path.join", "os.path.abspath"):
            for a in node.args[:1]:
                s = _lit(a)
                why = _bad_path(s) if s else None
                if why:
                    self.add(node, FILESYSTEM, HIGH, f"{why}: {s[:60]!r}")
        if q in R.DECODERS:
            self.add(node, OBFUSCATION, MEDIUM, f"decodes embedded data at run time ({q})")
        if fname in ("getattr", "setattr", "delattr", "hasattr") and len(node.args) >= 2:
            name = _lit(node.args[1])
            if name is None:
                self.add(node, OBFUSCATION, HIGH, f"{fname} with a computed attribute name hides what is called")
            elif name in R.DANGEROUS_NAMES or name in R.INTROSPECTION_ATTRS:
                self.add(node, OBFUSCATION, HIGH, f"{fname} used to reach '{name}' by name")
        if fname == "chr" and isinstance(node.args[0] if node.args else None, ast.Constant):
            self._chr = getattr(self, "_chr", 0) + 1
        self.generic_visit(node)

    def _open(self, node):
        arg = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg in ("file", "path")), None)
        if arg is None:
            return
        s = _lit(arg)
        if s is None:
            self.add(node, FILESYSTEM, MEDIUM, "opens a file whose path is computed at run time")
            return
        why = _bad_path(s)
        if why:
            self.add(node, FILESYSTEM, HIGH, f"{why}: {s[:60]!r}")

    def visit_Constant(self, node):
        v = node.value
        if not isinstance(v, str) or len(v) > 100_000:
            return
        for rx, what in R.SECRET_LITERALS:
            if rx.search(v):
                self.add(node, CREDENTIAL, HIGH, f"hard-coded {what}")
        if len(v) < 400:
            if any(rx.search(v) for rx in R.SENSITIVE_PATHS):
                self.add(node, SECRETS, HIGH, f"names a credential or system file: {v[:60]!r}")
            m = R.URL.search(v)
            if m and not m.group(1).lower().endswith(R.SAFE_HOST_SUFFIX):
                self.add(node, NETWORK, MEDIUM, f"URL literal to host '{m.group(1)[:60]}'")
        if R.BLOB.match(v) or R.HEXBLOB.match(v):
            self.add(node, OBFUSCATION, MEDIUM, f"long encoded string ({len(v)} characters)")

    def visit_Assign(self, node):
        self._cred(node, node.targets, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        if node.value is not None:
            self._cred(node, [node.target], node.value)
        self.generic_visit(node)

    def _cred(self, node, targets, value):
        s = _lit(value)
        if s is None or len(s) < 8 or R.PLACEHOLDER.match(s):
            return
        for t in targets:
            n = t.id if isinstance(t, ast.Name) else t.attr if isinstance(t, ast.Attribute) else None
            if n and R.SECRET_NAME.search(n):
                self.add(node, CREDENTIAL, HIGH, f"literal assigned to '{n}' looks like a hard-coded credential")

    def visit_Subscript(self, node):
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id in ("globals", "locals", "vars"):
            self.add(node, OBFUSCATION, HIGH, "indexes the namespace dictionary by a computed name")
        self.generic_visit(node)


def scan_python(text: str, path: str, declared: Declared, line_offset: int = 0, mode: str = "exec", embedded: bool = False) -> list:
    """Return issues for one source text. Unparseable text is a HIGH finding (fail closed)."""
    out: dict = {}
    try:
        tree = ast.parse(text, filename=path, mode=mode)
    except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
        line = getattr(exc, "lineno", None) or 1
        i = Issue(path, line + line_offset, UNPARSEABLE, LOW if embedded else HIGH,
                  f"cannot parse as Python ({type(exc).__name__}); not analysed")
        return [i]
    sc = Scanner(path, declared, line_offset)
    try:
        sc.visit(tree)
    except RecursionError:
        return [Issue(path, 1 + line_offset, UNPARSEABLE, HIGH, "nesting too deep to analyse")]
    out.update(sc.issues)
    if getattr(sc, "_chr", 0) >= 4:
        out[(1, OBFUSCATION, "chr")] = Issue(path, 1 + line_offset, OBFUSCATION, MEDIUM,
                                             "text built from many chr() calls")
    for n, ln in enumerate(text.splitlines(), 1):
        if len(ln) > 2000:
            out[(n, OBFUSCATION, "long")] = Issue(path, n + line_offset, OBFUSCATION, MEDIUM,
                                                  f"line of {len(ln)} characters (minified or packed code)")
    return list(out.values())
