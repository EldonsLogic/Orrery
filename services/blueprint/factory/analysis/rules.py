"""Rule tables for the static analyser. Plain data; internal tool, so engine module names appear here by design."""
from __future__ import annotations

import re

from .codes import (CREDENTIAL, DESERIALISE, DYNAMIC_CODE, DYNAMIC_IMPORT, FILESYSTEM, HIGH, INTERNALS, INTROSPECTION,
                    LOW, MEDIUM, NETWORK, PROCESS, SECRETS)

# Imports matched by module prefix: (code, severity, message).
MODULE_RULES = {
    **{m: (NETWORK, HIGH, "network client or socket module") for m in (
        "socket", "ssl", "http", "urllib", "urllib3", "requests", "httpx", "aiohttp", "ftplib", "smtplib", "poplib",
        "imaplib", "telnetlib", "xmlrpc", "websocket", "websockets", "paramiko", "asyncio.streams", "socketserver",
        "grpc", "boto3", "botocore", "webbrowser", "selectors")},
    **{m: (PROCESS, HIGH, "process or shell execution module") for m in (
        "subprocess", "pty", "pexpect", "sh", "plumbum", "multiprocessing", "concurrent.futures.process", "ctypes",
        "cffi", "signal", "resource", "asyncio.subprocess")},
    **{m: (DYNAMIC_IMPORT, HIGH, "dynamic import or loader module") for m in (
        "importlib", "runpy", "pkgutil", "imp", "zipimport", "pkg_resources", "code", "codeop")},
    **{m: (DESERIALISE, HIGH, "unsafe deserialisation module") for m in ("pickle", "cPickle", "marshal", "shelve", "dill",
                                                                          "cloudpickle", "jsonpickle")},
    **{m: (SECRETS, HIGH, "credential store or environment loader") for m in ("keyring", "dotenv", "decouple",
                                                                              "environs", "netrc")},
    **{m: (INTERNALS, HIGH, "engine-internal or platform-internal module") for m in (
        "frappe", "erpnext", "bench", "apps.engine", "services.gateway", "services.provisioning", "services.control_plane",
        "sqlalchemy", "psycopg2", "pymysql", "MySQLdb", "redis", "pymongo", "sqlite3")},
    "builtins": (INTROSPECTION, HIGH, "direct access to the builtins module"),
    "gc": (INTROSPECTION, HIGH, "garbage-collector introspection"),
    "inspect": (INTROSPECTION, MEDIUM, "interpreter introspection"),
}

# Model SDKs: undeclared unless the manifest says dataHandling.sendsDataToModels is true.
MODEL_SDKS = ("anthropic", "openai", "google.generativeai", "google.genai", "cohere", "litellm", "langchain", "transformers",
              "mistralai", "ollama", "vertexai")

# Qualified names (after resolving import aliases) matched by prefix on attribute use and from-imports.
NAME_RULES = {
    "os.environ": (SECRETS, HIGH, "reads environment variables (may hold secrets)"),
    "os.getenv": (SECRETS, HIGH, "reads environment variables (may hold secrets)"),
    "os.getenvb": (SECRETS, HIGH, "reads environment variables (may hold secrets)"),
    "os.system": (PROCESS, HIGH, "runs a shell command"),
    "os.popen": (PROCESS, HIGH, "runs a shell command"),
    "os.fork": (PROCESS, HIGH, "forks a process"),
    "os.kill": (PROCESS, HIGH, "signals a process"),
    "os.execv": (PROCESS, HIGH, "replaces the process"),
    "os.execl": (PROCESS, HIGH, "replaces the process"),
    "os.execve": (PROCESS, HIGH, "replaces the process"),
    "os.execvp": (PROCESS, HIGH, "replaces the process"),
    "os.execlp": (PROCESS, HIGH, "replaces the process"),
    "os.spawn": (PROCESS, HIGH, "spawns a process"),
    "os.posix_spawn": (PROCESS, HIGH, "spawns a process"),
    "os.startfile": (PROCESS, HIGH, "launches a program"),
    "os.chdir": (FILESYSTEM, HIGH, "changes the working folder"),
    "os.chroot": (FILESYSTEM, HIGH, "changes the root folder"),
    "os.symlink": (FILESYSTEM, HIGH, "creates a symlink"),
    "os.link": (FILESYSTEM, HIGH, "creates a hard link"),
    "os.chmod": (FILESYSTEM, HIGH, "changes permissions"),
    "os.chown": (FILESYSTEM, HIGH, "changes ownership"),
    "os.remove": (FILESYSTEM, MEDIUM, "deletes a file"),
    "os.unlink": (FILESYSTEM, MEDIUM, "deletes a file"),
    "os.rmdir": (FILESYSTEM, MEDIUM, "deletes a folder"),
    "os.removedirs": (FILESYSTEM, MEDIUM, "deletes folders"),
    "os.rename": (FILESYSTEM, MEDIUM, "moves a file"),
    "os.replace": (FILESYSTEM, MEDIUM, "moves a file"),
    "os.walk": (FILESYSTEM, MEDIUM, "walks folders"),
    "os.listdir": (FILESYSTEM, MEDIUM, "lists a folder"),
    "os.scandir": (FILESYSTEM, MEDIUM, "lists a folder"),
    "os.path.expanduser": (FILESYSTEM, HIGH, "resolves the user's home folder"),
    "os.path.expandvars": (SECRETS, HIGH, "expands environment variables"),
    "os.path.realpath": (FILESYSTEM, LOW, "resolves a path outside the component"),
    "shutil.rmtree": (FILESYSTEM, HIGH, "deletes a folder tree"),
    "shutil": (FILESYSTEM, MEDIUM, "bulk file operations"),
    "glob": (FILESYSTEM, MEDIUM, "folder search"),
    "pathlib.Path.home": (FILESYSTEM, HIGH, "resolves the user's home folder"),
    "pathlib.Path.cwd": (FILESYSTEM, LOW, "reads the working folder"),
    "pathlib.Path.resolve": (FILESYSTEM, LOW, "resolves a path outside the component"),
    "pathlib.Path.symlink_to": (FILESYSTEM, HIGH, "creates a symlink"),
    "pathlib.Path.hardlink_to": (FILESYSTEM, HIGH, "creates a hard link"),
    "pathlib.Path.unlink": (FILESYSTEM, MEDIUM, "deletes a file"),
    "pathlib.Path.rmdir": (FILESYSTEM, MEDIUM, "deletes a folder"),
    "tempfile.gettempdir": (FILESYSTEM, MEDIUM, "writes outside the component"),
    "sys.modules": (INTROSPECTION, HIGH, "reaches loaded modules"),
    "sys.settrace": (INTROSPECTION, HIGH, "installs a trace hook"),
    "sys.setprofile": (INTROSPECTION, HIGH, "installs a profile hook"),
    "sys._getframe": (INTROSPECTION, HIGH, "reads caller frames"),
    "sys.path": (DYNAMIC_IMPORT, MEDIUM, "changes the import path"),
    "sys.meta_path": (DYNAMIC_IMPORT, HIGH, "installs an import hook"),
    "sys.path_hooks": (DYNAMIC_IMPORT, HIGH, "installs an import hook"),
    "yaml.load": (DESERIALISE, HIGH, "unsafe yaml.load can build objects (use safe_load)"),
    "yaml.unsafe_load": (DESERIALISE, HIGH, "unsafe yaml loader"),
    "yaml.full_load": (DESERIALISE, MEDIUM, "full yaml loader"),
    "os.add_dll_directory": (DYNAMIC_IMPORT, HIGH, "loads native libraries"),
    "threading.Thread": (PROCESS, MEDIUM, "background thread outlives the call"),
    "asyncio.create_subprocess_exec": (PROCESS, HIGH, "spawns a process"),
    "asyncio.create_subprocess_shell": (PROCESS, HIGH, "runs a shell command"),
    "asyncio.open_connection": (NETWORK, HIGH, "opens a network connection"),
    "asyncio.start_server": (NETWORK, HIGH, "opens a network listener"),
}

BUILTIN_CALLS = {
    "eval": (DYNAMIC_CODE, HIGH, "eval runs text as code"),
    "exec": (DYNAMIC_CODE, HIGH, "exec runs text as code"),
    "compile": (DYNAMIC_CODE, HIGH, "compile builds code from text"),
    "__import__": (DYNAMIC_IMPORT, HIGH, "__import__ loads a module by name"),
    "breakpoint": (PROCESS, HIGH, "breakpoint opens a debugger"),
    "input": (PROCESS, MEDIUM, "blocks waiting for input"),
}

INTROSPECTION_ATTRS = frozenset({
    "__subclasses__", "__globals__", "__builtins__", "__code__", "__closure__", "__mro__", "__bases__",
    "__getattribute__", "__reduce__", "__reduce_ex__", "__loader__", "__spec__", "f_globals", "f_locals", "f_back",
    "f_builtins", "gi_frame", "gi_code", "cr_frame", "cr_code", "tb_frame", "ag_frame", "co_code"})

DANGEROUS_NAMES = frozenset({
    "eval", "exec", "compile", "__import__", "open", "system", "popen", "subprocess", "os", "importlib", "builtins",
    "__builtins__", "getattr", "setattr", "globals", "environ", "getenv", "socket", "pickle"})

DECODERS = frozenset({
    "base64.b64decode", "base64.b32decode", "base64.b16decode", "base64.a85decode", "base64.b85decode",
    "base64.urlsafe_b64decode", "base64.decodebytes", "codecs.decode", "zlib.decompress", "bz2.decompress",
    "lzma.decompress", "gzip.decompress", "binascii.unhexlify", "binascii.a2b_base64", "bytes.fromhex"})

SENSITIVE_PATHS = (
    re.compile(r"(^|/)\.env(\.[\w-]+)?(/|$)"), re.compile(r"(^|/)\.ssh(/|$)"), re.compile(r"(^|/)\.aws(/|$)"),
    re.compile(r"(^|/)\.kube(/|$)"), re.compile(r"(^|/)\.gnupg(/|$)"), re.compile(r"(^|/)(\.netrc|\.pypirc|\.npmrc|"
                                                                                  r"\.git-credentials|\.pgpass)$"),
    re.compile(r"(^|/)id_(rsa|dsa|ecdsa|ed25519)(\.pub)?$"), re.compile(r"^/etc/(passwd|shadow|sudoers)"),
    re.compile(r"^/proc/"), re.compile(r"(^|/)credentials(\.json)?$"), re.compile(r"(^|/)secrets?\.(json|ya?ml|toml)$"),
    re.compile(r"(^|/)Library/Keychains(/|$)"),
)

# Secret-looking patterns are assembled at import time so this file never holds a literal credential or key header.
_PEM = "-----" + "BEGIN " + r"(?:[A-Z0-9]+ )*" + "PRIVATE " + "KEY-----"
SECRET_LITERALS = (
    (re.compile(_PEM), "private key block"),
    (re.compile("AK" + "IA" + "[0-9A-Z]{16}"), "cloud access key id"),
    (re.compile("gh" + "[pousr]_" + "[A-Za-z0-9]{36,}"), "source-host token"),
    (re.compile("xox" + "[baprs]-" + "[A-Za-z0-9-]{10,}"), "chat token"),
    (re.compile("sk" + "-" + "[A-Za-z0-9_-]{24,}"), "api key"),
    (re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), "signed token"),
)
SECRET_NAME = re.compile(r"(pass(word|wd)?|secret|token|api[_-]?key|private[_-]?key|credential|auth)", re.I)
PLACEHOLDER = re.compile(r"^(|x+|\*+|changeme|change[_-]me|example|dummy|test|none|null|todo|<.*>|\$\{.*\}|\{\{.*\}\})$", re.I)
URL = re.compile(r"\b(?:https?|wss?|ftp|sftp|ssh|smtp)://([^\s/'\"<>:]+)", re.I)
SAFE_HOST_SUFFIX = (".example", ".invalid", ".test", "example.com", "example.org", "example.net")
BLOB = re.compile(r"^[A-Za-z0-9+/=_-]{120,}$")
HEXBLOB = re.compile(r"^(?:[0-9a-fA-F]{2}){60,}$")
URL_KEYS = frozenset({"url", "uri", "endpoint", "webhook", "host", "href", "base_url", "baseurl", "callback"})
CODE_KEYS = frozenset({"script", "code", "server_script", "python", "expression", "formula", "condition",
                       "handler"})

BINARY_EXT = frozenset({".pyc", ".pyo", ".so", ".pyd", ".dll", ".dylib", ".exe", ".bin", ".whl", ".egg", ".zip", ".tar",
                        ".gz", ".tgz", ".bz2", ".xz", ".7z", ".jar", ".class", ".wasm", ".o", ".a", ".msi", ".dmg",
                        ".apk", ".pkl", ".pickle", ".npy", ".npz", ".db", ".sqlite", ".sqlite3"})
SCRIPT_EXT = frozenset({".js", ".mjs", ".cjs", ".ts", ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd", ".rb", ".php", ".pl",
                        ".lua", ".vbs", ".r", ".scala", ".go", ".rs", ".java", ".c", ".cc", ".cpp", ".h", ".swift"})
TEXT_EXT = frozenset({".md", ".txt", ".csv", ".tsv", ".po", ".pot", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".html",
                      ".css", ".svg", ".xml", ".rst", ".jinja", ".j2", ".ndjson", ".jsonl", ".gitignore", ""})
