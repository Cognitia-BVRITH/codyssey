"""AST-based symbol index: a searchable map of classes and functions in a repo."""

import ast
from dataclasses import dataclass, field
from pathlib import Path

# Folders that never hold the project's own source code.
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "build",
    "dist",
    ".tox",
}

DefNode = ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef


@dataclass(frozen=True)
class Symbol:
    """One class, function, or method found in a source file."""

    name: str
    qualified_name: str  # e.g. "UserService.create_user"
    kind: str  # "class", "function", or "method"
    file: str  # path relative to the repo root, always written with "/"
    start_line: int
    end_line: int
    signature: str
    docstring: str | None


@dataclass
class SymbolIndex:
    """All symbols found in a repo, plus files that could not be read."""

    symbols: list[Symbol] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)  # file -> reason skipped

    def search_symbol(self, name: str) -> list[Symbol]:
        """Return symbols whose short or qualified name equals `name`."""
        return [symbol for symbol in self.symbols if name in (symbol.name, symbol.qualified_name)]

    def symbols_in_file(self, file: str) -> list[Symbol]:
        """Return every symbol defined in one file (path relative to repo root)."""
        return [symbol for symbol in self.symbols if symbol.file == file]


def _start_line(node: DefNode) -> int:
    """First line of a definition, including any @decorator lines above it."""
    if node.decorator_list:
        return node.decorator_list[0].lineno
    return node.lineno


def _function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    signature = f"{prefix} {node.name}({ast.unparse(node.args)})"
    if node.returns is not None:
        signature += f" -> {ast.unparse(node.returns)}"
    return signature


def _class_signature(node: ast.ClassDef) -> str:
    if not node.bases:
        return f"class {node.name}"
    bases = ", ".join(ast.unparse(base) for base in node.bases)
    return f"class {node.name}({bases})"


def _collect_symbols(
    body: list[ast.stmt],
    file: str,
    parent: str,
    in_class: bool,
    symbols: list[Symbol],
) -> None:
    """Walk one block of statements and append the symbols found to `symbols`."""
    for node in body:
        if isinstance(node, ast.ClassDef):
            qualified = f"{parent}.{node.name}" if parent else node.name
            symbols.append(
                Symbol(
                    name=node.name,
                    qualified_name=qualified,
                    kind="class",
                    file=file,
                    start_line=_start_line(node),
                    end_line=node.end_lineno or node.lineno,
                    signature=_class_signature(node),
                    docstring=ast.get_docstring(node),
                )
            )
            # Look inside the class for its methods and nested classes.
            _collect_symbols(node.body, file, qualified, True, symbols)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qualified = f"{parent}.{node.name}" if parent else node.name
            symbols.append(
                Symbol(
                    name=node.name,
                    qualified_name=qualified,
                    kind="method" if in_class else "function",
                    file=file,
                    start_line=_start_line(node),
                    end_line=node.end_lineno or node.lineno,
                    signature=_function_signature(node),
                    docstring=ast.get_docstring(node),
                )
            )
            # Functions nested inside functions are deliberately not indexed.


def build_index(repo_path: Path) -> SymbolIndex:
    """Scan every .py file under `repo_path` and return its symbol index."""
    index = SymbolIndex()
    for path in sorted(repo_path.rglob("*.py")):
        relative = path.relative_to(repo_path)
        if SKIP_DIRS.intersection(relative.parts):
            continue
        file = relative.as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=file)
        except (OSError, SyntaxError, UnicodeDecodeError, ValueError) as exc:
            index.errors[file] = f"{type(exc).__name__}: {exc}"
            continue
        _collect_symbols(tree.body, file, "", False, index.symbols)
    return index
