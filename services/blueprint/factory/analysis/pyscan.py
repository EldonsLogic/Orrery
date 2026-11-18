"""AST scan of one Python source text. Nothing is imported or executed. Fail closed on anything unparseable.

Posture (SEC-010 review): allow-list, not deny-list. Imports must be on R.SAFE_MODULES, a required component, the
component's own package or a module it ships; dangerous builtins may only be called directly; any other reference,
alias or rebinding of them, and any non-data dunder, is HIGH.
"""
from __future__ import annotations

import ast
import re

from . import rules as R
from .codes import (CREDENTIAL, FILESYSTEM, HIGH, INTROSPECTION, LOW, MEDIUM, NETWORK, OBFUSCATION, PROCESS, SECRETS,
                    UNDECLARED, UNPARSEABLE, Issue)


class Declared:
    """What the manifest and the component folder declare. Used for the import allow-list."""

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


def _under(name: str, prefixes) -> bool:
    return any(name == p or name.startswith(p + ".") for p in prefixes)


def _lit(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _bad_path(p: str):
    if p.startswith(("/", "~", "\\")) or re.match(r"^[A-Za-z]:[\\/]", p):
        return "absolute or home path"
    if ".." in re.split(r"[\\/]", p):
        return "path leaves the component folder ('..')"
    return None


def _dunder(n: str) -> bool:
    return len(n) > 4 and n.startswith("__") and n.endswith("__")


class Scanner(ast.NodeVisitor):
    def __init__(self, path: str, declared: Declared, line_offset: int = 0, max_rel_level: int = 0):
        self.path, self.d, self.off, self.max_rel = path, declared, line_offset, max_rel_level
        self.names: dict = {}         # local name -> qualified dotted name
        self.modules: set = set()     # local names bound to module objects
        self.issues: dict = {}
        self._callee: set = set()     # id() of nodes in call position
        self._attr_base: set = set()  # id() of Names used as the base of an attribute
        self._methods: set = set()
        self._annot: set = set()      # id() of string constants inside annotations
        self._chr = 0

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
            builtin = node.id in R.BUILTIN_CALLS or node.id in ("bytes", "bytearray")
            root = self.names.get(node.id, node.id if builtin else None)
            if root is None:
                return None
            parts.append(root)
            return ".".join(reversed(parts))
        return None

    def _bind(self, node, name: str, what: str):
        if name in R.DANGEROUS_BUILTINS or name == "__builtins__":
            self.add(node, OBFUSCATION, HIGH, f"{what} rebinds the builtin '{name}' (hides or fakes a dangerous call)")

    def _qcheck(self, node, q: str):
        """Rules for a resolved dotted name (attribute use, from-import, imported name use)."""
        if q == "os" or q.startswith("."):
            return
        if q.startswith("os."):
            parts = q.split(".")
            if q in R.OS_ALLOWED or (len(parts) == 3 and parts[1] == "path" and parts[2] in R.OS_PATH_ALLOWED):
                return
            key, rule = _match(q, R.NAME_RULES)
            self.add(node, rule[0] if rule else PROCESS, HIGH, f"'{q}' is outside the allowed os surface (os.path "
                     f"helpers only){': ' + rule[2] if rule else ''}")
            return
        key, rule = _match(q, R.NAME_RULES)
        if rule:
            self.add(node, rule[0], rule[1], f"'{q}': {rule[2]}")

    # imports
    def _allowed(self, mod: str) -> bool:
        top = mod.split(".")[0]
        if top == "components":
            dotted = mod[len("components."):] if "." in mod else ""
            allowed = self.d.requires + ((self.d.own_id,) if self.d.own_id else ())
            return bool(dotted) and _under(dotted, allowed)
        if _under(mod, R.SAFE_DENY):
            return False
        return _under(mod, R.SAFE_MODULES) or top in self.d.local

    def _module(self, node, mod: str, full: tuple = ()):
        high = False
        key, rule = _match(mod, R.MODULE_RULES)
        if rule:
            self.add(node, rule[0], rule[1], f"import of '{mod}': {rule[2]}")
            high = rule[1] == HIGH
        if _match(mod, {m: 1 for m in R.MODEL_SDKS})[1]:
            why = "" if self.d.sends_to_models else " (and the manifest does not set dataHandling.sendsDataToModels)"
            self.add(node, UNDECLARED, HIGH, f"model SDK '{mod}': components reach models only through the platform{why}")
            high = True
        ok = self._allowed(mod) or bool(full and all(self._allowed(f) for f in full))
        denied = [f for f in full if _under(f, R.SAFE_DENY)]
        if (denied or not ok) and not high:
            what = denied[0] if denied else mod
            self.add(node, UNDECLARED, HIGH, f"import of '{what}' is not on the allow-list (safe standard modules, "
                     "required components, the component's own files)")

    def visit_Import(self, node):
        for a in node.names:
            self._module(node, a.name)
            if a.name.split(".")[0] == "os":
                self._qcheck(node, a.name)
            bound = a.asname or a.name.split(".")[0]
            self._bind(node, bound, "import")
            self.names[bound] = a.name if a.asname else a.name.split(".")[0]
            self.modules.add(bound)

    def visit_ImportFrom(self, node):
        if any(a.name == "*" for a in node.names):
            self.add(node, OBFUSCATION, HIGH, "star import hides which names it binds")
        if node.level:  # relative import: must stay inside the component
            if node.level > self.max_rel:
                self.add(node, UNDECLARED, HIGH, f"relative import (level {node.level}) leaves the component")
            for a in node.names:
                self._bind(node, a.asname or a.name, "import")
                self.names[a.asname or a.name] = "." + a.name
            return
        mod = node.module or ""
        full = tuple(f"{mod}.{a.name}" for a in node.names if a.name != "*")
        self._module(node, mod, full)
        for a in node.names:
            f = f"{mod}.{a.name}"
            bound = a.asname or a.name
            self._bind(node, bound, "import")
            self.names[bound] = f
            if f in R.SAFE_SUBMODULES:
                self.modules.add(bound)
            key, rule = _match(f, R.MODULE_RULES)
            if rule and key != _match(mod, R.MODULE_RULES)[0]:
                self.add(node, rule[0], rule[1], f"import of '{f}': {rule[2]}")
            self._qcheck(node, f)

    # definitions and bindings
    def visit_ClassDef(self, node):
        self._bind(node, node.name, "class")
        for st in node.body:
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._methods.add(id(st))
        self.generic_visit(node)

    def _func(self, node):
        if id(node) not in self._methods:  # a method named 'open' does not shadow the builtin
            self._bind(node, node.name, "function")
        if node.returns is not None:
            self._mark_annot(node.returns)
        self.generic_visit(node)

    visit_FunctionDef = visit_AsyncFunctionDef = _func

    def visit_arg(self, node):
        self._bind(node, node.arg, "parameter")
        if node.annotation is not None:
            self._mark_annot(node.annotation)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        if node.name:
            self._bind(node, node.name, "except")
        self.generic_visit(node)

    def visit_Global(self, node):
        for n in node.names:
            self._bind(node, n, "global")

    visit_Nonlocal = visit_Global

    def _mark_annot(self, ann):
        for n in ast.walk(ann):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                self._annot.add(id(n))

    # names and attributes
    def visit_Attribute(self, node):
        if isinstance(node.value, ast.Name):
            self._attr_base.add(id(node.value))
        q = self.qual(node)
        if q:
            self._qcheck(node, q)
        a = node.attr
        if a in R.INTROSPECTION_ATTRS:
            self.add(node, INTROSPECTION, HIGH, f"attribute '{a}' reaches interpreter internals")
        elif _dunder(a) and a not in R.SAFE_DUNDER_READ and not (a in R.SAFE_DUNDER_CALL and id(node) in self._callee):
            self.add(node, INTROSPECTION, HIGH, f"dunder attribute '{a}' is not allowed")
        self.generic_visit(node)

    def visit_Name(self, node):
        n = node.id
        if not n.isascii():
            self.add(node, OBFUSCATION, MEDIUM, "non-ASCII identifier (possible look-alike characters)")
            return
        if not isinstance(node.ctx, ast.Load):
            self._bind(node, n, "assignment")
            return
        if n in ("__builtins__", "__loader__") or (_dunder(n) and n not in R.SAFE_DUNDER_NAMES):
            self.add(node, INTROSPECTION, HIGH, f"'{n}' reaches interpreter internals")
        elif n in R.DANGEROUS_BUILTINS and id(node) not in self._callee:
            self.add(node, R.DANGEROUS_BUILTINS[n], HIGH, f"builtin '{n}' referenced without a direct call "
                     "(aliasing or passing it hides the call)")
        elif n in self.modules and id(node) not in self._attr_base:
            self.add(node, OBFUSCATION, HIGH, f"module '{self.names.get(n, n)}' used as a value (aliasing hides "
                     "what is called)")
        else:
            q = self.names.get(n)
            if q and q != n:
                self._qcheck(node, q)

    def visit_Call(self, node):
        self._callee.add(id(node.func))
        q = self.qual(node.func)
        fname = node.func.id if isinstance(node.func, ast.Name) else None
        if fname in R.BUILTIN_CALLS:  # never skipped: rebinding these names is itself HIGH
            c, s, m = R.BUILTIN_CALLS[fname]
            self.add(node, c, s, m)
        if fname == "open":
            self._open(node)
        if q in ("io.open", "io.FileIO", "os.open", "os.fdopen", "codecs.open", "tempfile.mkstemp", "tempfile.mkdtemp",
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
        if fname in ("getattr", "setattr", "delattr"):
            self._getattr(node, fname)
        if fname == "chr" and isinstance(node.args[0] if node.args else None, ast.Constant):
            self._chr += 1
        self.generic_visit(node)

    def _getattr(self, node, fname):
        if len(node.args) < 2 or any(isinstance(a, ast.Starred) for a in node.args) or node.keywords:
            self.add(node, OBFUSCATION, HIGH, f"{fname} with unpacked arguments hides what is reached")
            return
        target, name = node.args[0], _lit(node.args[1])
        if name is None:
            self.add(node, OBFUSCATION, HIGH, f"{fname} with a computed attribute name hides what is called")
        elif name in R.DANGEROUS_NAMES or name in R.INTROSPECTION_ATTRS or R.DANGEROUS_NAME_RX.match(name):
            self.add(node, OBFUSCATION, HIGH, f"{fname} used to reach '{name}' by name")
        if isinstance(target, ast.Name) and target.id in self.modules:
            self.add(node, OBFUSCATION, HIGH, f"{fname} on module '{self.names.get(target.id, target.id)}' bypasses "
                     "the attribute rules")

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
        if id(node) in self._annot:  # string annotations are evaluated as code by typing helpers
            self._expr(node, v)
        for rx, what in R.SECRET_LITERALS:
            if rx.search(v):
                self.add(node, CREDENTIAL, HIGH, f"hard-coded {what}")
        if len(v) < 400:
            if any(rx.search(v) for rx in R.SENSITIVE_PATHS):
                self.add(node, SECRETS, HIGH, f"names a credential or system file: {v[:60]!r}")
            m = R.URL.search(v)
            if m and not m.group(1).lower().endswith(R.SAFE_HOST_SUFFIX):
                self.add(node, NETWORK, MEDIUM, f"URL literal to host '{m.group(1)[:60]}'")
        if R.FORMAT_WALK.search(v):
            self.add(node, INTROSPECTION, HIGH, "format string walks to private or dunder attributes")
        if R.BLOB.match(v) or R.HEXBLOB.match(v):
            self.add(node, OBFUSCATION, MEDIUM, f"long encoded string ({len(v)} characters)")

    def _expr(self, node, text):
        try:
            tree = ast.parse(text.strip(), mode="eval")
        except (SyntaxError, ValueError, RecursionError, MemoryError):
            return  # not an expression (for example a Literal value); never evaluated as code
        off = self.off
        self.off = off + getattr(node, "lineno", 1) - 1
        try:
            self.visit(tree)
        finally:
            self.off = off

    def visit_Assign(self, node):
        self._cred(node, node.targets, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        self._mark_annot(node.annotation)
        if node.value is not None:
            self._cred(node, [node.target], node.value)
        self.generic_visit(node)

    def _cred(self, node, targets, value):
        s = _lit(value)
        if s is None or R.PLACEHOLDER.match(s) or not R.looks_secret(s):
            return
        for t in targets:
            n = t.id if isinstance(t, ast.Name) else t.attr if isinstance(t, ast.Attribute) else None
            if n and R.secret_name(n):
                self.add(node, CREDENTIAL, HIGH, f"literal assigned to '{n}' looks like a hard-coded credential")

    def visit_Subscript(self, node):
        v = node.value
        if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id in ("globals", "locals", "vars"):
            self.add(node, OBFUSCATION, HIGH, "indexes the namespace dictionary by a computed name")
        self.generic_visit(node)


def scan_python(text: str, path: str, declared: Declared, line_offset: int = 0, mode: str = "exec",
                embedded: bool = False, source: bytes | None = None, max_rel_level: int = 0) -> list:
    """Return issues for one source text. Unparseable text is a HIGH finding (fail closed).

    source: the raw file bytes, parsed as the interpreter reads them (the caller has already refused any coding
    line other than utf-8). embedded: a script inside JSON; the caller decides what a parse failure means.
    """
    out: dict = {}
    try:
        tree = ast.parse(source if source is not None else text, filename=path, mode=mode)
    except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
        line = getattr(exc, "lineno", None) or 1
        i = Issue(path, line + line_offset, UNPARSEABLE, LOW if embedded else HIGH,
                  f"cannot parse as Python ({type(exc).__name__}); not analysed")
        return [i]
    sc = Scanner(path, declared, line_offset, max_rel_level)
    try:
        sc.visit(tree)
    except RecursionError:
        return [Issue(path, 1 + line_offset, UNPARSEABLE, HIGH, "nesting too deep to analyse")]
    out.update(sc.issues)
    if sc._chr >= 4:
        out[(1, OBFUSCATION, "chr")] = Issue(path, 1 + line_offset, OBFUSCATION, MEDIUM,
                                             "text built from many chr() calls")
    for n, ln in enumerate(text.splitlines(), 1):
        if len(ln) > 2000:
            out[(n, OBFUSCATION, "long")] = Issue(path, n + line_offset, OBFUSCATION, MEDIUM,
                                                  f"line of {len(ln)} characters (minified or packed code)")
    return list(out.values())
