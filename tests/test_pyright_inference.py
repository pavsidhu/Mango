from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_pyright_reveals_expected_public_types() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pyright",
            "tests/typing/test_inference.py",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert 'Type of "User.id" is "Column[UUID]"' in output
    assert 'Type of "User.name" is "Column[str]"' in output
    assert 'Type of "User.age > 18" is "Expr[bool]"' in output
    assert 'Type of "UserRowResult.name" is "RowExpr[str]"' in output
    assert 'Type of "row_result.name" is "str"' in output
    assert 'Type of "row_query" is "Select[UserRowResult]"' in output
    assert 'Type of "users" is "list[UserRowResult]"' in output
