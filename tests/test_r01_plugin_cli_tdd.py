"""Locked Frontier TDD suite for R-01: generic `--plugin` CLI flag and `SHS_PLUGINS`."""
from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path
import sys

import pytest

from shslisp.__main__ import build_parser, main


def test_parser_accepts_repeatable_plugin_flag() -> None:
    parser = build_parser()
    args = parser.parse_args(["--plugin", "pkg.a", "--plugin", "pkg.b:register", "-e", "(+ 1 2)"])
    assert args.plugins == ["pkg.a", "pkg.b:register"]


def test_cli_eval_with_plugin_module_and_custom_attr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plugin_file = tmp_path / "demo_plugin_r01.py"
    plugin_file.write_text(
        "from shslisp.embed import install_primitives\n"
        "def custom_install(env):\n"
        "    install_primitives(env, [('triple', lambda x: x * 3)], source='demo_plugin_r01')\n"
        "def install(env):\n"
        "    install_primitives(env, [('double', lambda x: x * 2)], source='demo_plugin_r01')\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--plugin", "demo_plugin_r01", "--plugin", "demo_plugin_r01:custom_install", "-e", "(+ (double 5) (triple 4))"])
    assert rc == 0
    assert buf.getvalue().strip() == "22"


def test_cli_run_script_gosh_style_with_plugin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plugin_file = tmp_path / "demo_plugin_r01_run.py"
    plugin_file.write_text(
        "from shslisp.embed import install_primitives\n"
        "def install(env):\n"
        "    install_primitives(env, [('magic-num', lambda: 42)], source='demo_plugin_r01_run')\n",
        encoding="utf-8",
    )
    script = tmp_path / "prog.scm"
    script.write_text("(display (magic-num)) (newline)\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--plugin", "demo_plugin_r01_run", str(script)])
    assert rc == 0
    assert buf.getvalue().strip() == "42"


def test_cli_reads_shs_plugins_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    plugin_file = tmp_path / "demo_plugin_r01_env.py"
    plugin_file.write_text(
        "from shslisp.embed import install_primitives\n"
        "def install(env):\n"
        "    install_primitives(env, [('env-ok', lambda: 99)], source='demo_plugin_r01_env')\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("SHS_PLUGINS", os.pathsep.join(["demo_plugin_r01_env"]))

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["-e", "(env-ok)"])
    assert rc == 0
    assert buf.getvalue().strip() == "99"


def test_cli_bad_plugin_fails_loudly_with_nonzero_exit(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["--plugin", "nonexistent_plugin_module_xyz", "-e", "(+ 1 2)"])
    assert rc != 0
    err = capsys.readouterr().err
    assert "nonexistent_plugin_module_xyz" in err
