"""test that prompt behavior is correct in supported shells"""
from __future__ import absolute_import, unicode_literals

import os
import subprocess

import pytest

import virtualenv


ENV_DEFAULT = "env"
ENV_CUSTOM = "env_custom"

PREFIX_DEFAULT = "({}) ".format(ENV_DEFAULT)
PREFIX_CUSTOM = "!!!ENV!!!"

OUTPUT_FILE = "outfile"

VIRTUAL_ENV_DISABLE_PROMPT = "VIRTUAL_ENV_DISABLE_PROMPT"
VIRTUAL_ENV = "VIRTUAL_ENV"


@pytest.fixture(scope="module")
def tmp_root(tmp_path_factory):
    """Provide Path to root with default and custom venvs created."""
    root = tmp_path_factory.mktemp("env_root")
    virtualenv.create_environment(str(root / ENV_DEFAULT), no_setuptools=True, no_pip=True, no_wheel=True)
    virtualenv.create_environment(
        str(root / ENV_CUSTOM), prompt=PREFIX_CUSTOM, no_setuptools=True, no_pip=True, no_wheel=True
    )
    return root


@pytest.fixture(scope="function")
def clean_env():
    """Provide a fresh copy of the shell environment."""
    return os.environ.copy()


def fix_PS1_return(result, trim_newline=True):
    """Replace select byte values with escape sequences."""
    result = result.replace(b"\x1b", b"\\e")
    result = result.replace(b"\x07", b"\\a")

    # For some reason, indexing a single value into a bytes string
    # gives the underlying integer value. b'\n' --> 10
    if trim_newline and result[-1] == 10:
        return result[:-1]
    else:
        return result


def test_functional_env_root(tmp_root):
    assert subprocess.call("ls", cwd=str(tmp_root), shell=True) == 0


def test_nonzero_exit(tmp_root):
    assert subprocess.call("exit 1", cwd=str(tmp_root), shell=True) == 1


class TestBashPrompts:
    @staticmethod
    @pytest.fixture(scope="class")
    def PS1():
        return os.environ.get("PS1")

    @staticmethod
    def test_suppressed_prompt_default_env(tmp_root, PS1, clean_env):
        clean_env.update({VIRTUAL_ENV_DISABLE_PROMPT: "1"})
        command = '. {0}/bin/activate && echo "$PS1"'.format(ENV_DEFAULT)
        result = subprocess.check_output(command, cwd=str(tmp_root), shell=True, env=clean_env)
        result = fix_PS1_return(result)

        # This assert MUST be made by encoding PS1, **NOT** by decoding
        # result. Python's decoding machinery mangles the content of the
        # returned $PS1 ~irretrievably.
        assert result == PS1.encode()
