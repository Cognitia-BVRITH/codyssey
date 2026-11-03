from pathlib import Path

from codyssey.localization.index import build_index

SAMPLE = '''\
"""users module"""

class UserService:
    """Creates users."""

    def create_user(self, name: str) -> dict:
        """Create a user."""
        return {"name": name}


def helper(x, y=2):
    return x + y
'''


def write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_indexes_functions_with_line_ranges(tmp_path: Path) -> None:
    write(tmp_path, "proj/users.py", SAMPLE)

    index = build_index(tmp_path)

    (helper,) = index.search_symbol("helper")
    assert helper.kind == "function"
    assert helper.file == "proj/users.py"
    assert (helper.start_line, helper.end_line) == (11, 12)
    assert helper.signature == "def helper(x, y=2)"


def test_indexes_classes_and_methods(tmp_path: Path) -> None:
    write(tmp_path, "proj/users.py", SAMPLE)

    index = build_index(tmp_path)

    (cls,) = index.search_symbol("UserService")
    assert cls.kind == "class"
    assert cls.docstring == "Creates users."
    assert (cls.start_line, cls.end_line) == (3, 8)

    (method,) = index.search_symbol("UserService.create_user")
    assert method.kind == "method"
    assert method.signature == "def create_user(self, name: str) -> dict"
    assert (method.start_line, method.end_line) == (6, 8)


def test_search_by_short_name_finds_methods(tmp_path: Path) -> None:
    write(tmp_path, "proj/users.py", SAMPLE)

    index = build_index(tmp_path)

    assert [s.qualified_name for s in index.search_symbol("create_user")] == [
        "UserService.create_user"
    ]
    assert index.search_symbol("missing_name") == []


def test_skips_virtualenv_and_cache_folders(tmp_path: Path) -> None:
    write(tmp_path, "proj/users.py", SAMPLE)
    write(tmp_path, ".venv/lib/other.py", "def not_ours():\n    pass\n")

    index = build_index(tmp_path)

    assert index.search_symbol("not_ours") == []
    assert index.symbols_in_file("proj/users.py") != []


def test_unparseable_file_is_recorded_not_fatal(tmp_path: Path) -> None:
    write(tmp_path, "good.py", "def ok():\n    return 1\n")
    write(tmp_path, "broken.py", "def broken(:\n")

    index = build_index(tmp_path)

    assert index.search_symbol("ok") != []
    assert "broken.py" in index.errors
