"""test that prompt behavior is correct in supported shells"""
from __future__ import absolute_import, unicode_literals

import os
import subprocess
import sys

import pytest

import virtualenv

ENV_DEFAULT = "env"
ENV_CUSTOM = "env_custom"

PREFIX_DEFAULT = "({}) ".format(ENV_DEFAULT)
PREFIX_CUSTOM = "---ENV---"

VIRTUAL_ENV_DISABLE_PROMPT = "VIRTUAL_ENV_DISABLE_PROMPT"
VIRTUAL_ENV = "VIRTUAL_ENV"

# {shell}.[script|out].[normal|suppress].[default|custom]
SCRIPT_TEMPLATE = "{0}.script.{1}.{2}"
OUTPUT_TEMPLATE = "{0}.out.{1}.{2}"


def platform_check(platform, shell):
    """Return non-empty string if tests should be skipped."""
    platform_incompat = "No sane provision for {} on {} yet"

    if (
        (sys.platform.startswith("win") and shell in ['bash', 'csh', 'fish'])
       or (sys.platform.startswith("linux") and shell in ['cmd', 'powershell'])
    ):
        return platform_incompat.format(shell, platform)

    if shell == 'xonsh' and sys.version_info < (3, 4):
        return "xonsh requires Python 3.4 at least"


@pytest.fixture(scope="module")
def tmp_root(tmp_path_factory):
    """Provide Path to root with default and custom venvs created."""
    root = tmp_path_factory.mktemp("env_root")
    virtualenv.create_environment(str(root / ENV_DEFAULT), no_setuptools=True, no_pip=True, no_wheel=True)
    virtualenv.create_environment(
        str(root / ENV_CUSTOM), prompt=PREFIX_CUSTOM, no_setuptools=True, no_pip=True, no_wheel=True
    )
    return root


@pytest.fixture(scope="module")
def prompt_cmds():
    return {
        "bash": 'echo "$PS1"',
    }

@pytest.fixture(scope="module")
def activate_cmds():
    return {
        "bash": "activate",
    }


@pytest.fixture(scope="function")
def clean_env():
    """Provide a fresh copy of the shell environment."""
    return os.environ.copy()


@pytest.mark.parametrize(["command", "code"], [("echo test", 0), ("exit 1", 1)])
def test_exit_code(command, code, tmp_root):
    """Confirm subprocess.call exit codes work as expected at the unit test level."""
    assert subprocess.call(command, cwd=str(tmp_root), shell=True) == code


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Invalid on Windows")
class TestPrompts:
    """Container for tests of bash prompt modifications."""

    @staticmethod
    @pytest.mark.skip("Not updated yet")
    def test_suppressed_prompt_default_env(tmp_root, clean_env):
        """Confirm VIRTUAL_ENV_DISABLE_PROMPT suppresses prompt changes on activate."""
        clean_env.update({VIRTUAL_ENV_DISABLE_PROMPT: "1"})
        command = 'echo "$PS1" > {1} && . {0}/bin/activate && echo "$PS1" >> {1}'.format(ENV_DEFAULT, OUTPUT_FILE)

        assert 0 == subprocess.call(command, cwd=str(tmp_root), shell=True, env=clean_env)

        lines = (tmp_root / OUTPUT_FILE).read_bytes().split(b"\n")
        assert lines[0] == lines[1]

@pytest.mark.parametrize('shell', ['bash'])
@pytest.mark.parametrize(["env", "prefix"], [(ENV_DEFAULT, PREFIX_DEFAULT), (ENV_CUSTOM, PREFIX_CUSTOM)])
def test_activated_prompt(shell, env, prefix, tmp_root, prompt_cmds, activate_cmds):
    """Confirm prompt modification behavior with and without --prompt specified."""
    shell_skip = platform_check(sys.platform, shell)
    if shell_skip:
        pytest.skip(shell_skip)

    script_name = SCRIPT_TEMPLATE.format(shell, 'normal', env)
    output_name = OUTPUT_TEMPLATE.format(shell, 'normal', env)

    (tmp_root / script_name).write_text("""\
        {1}
        . {0}/bin/{2}
        {1}
        deactivate
        {1}
        """.format(env, prompt_cmds[shell], activate_cmds[shell]))

    command = '{0} {1} > {2}'.format(shell, script_name, output_name)

    #~ command = (
        #~ 'bash -ci \'echo "$PS1" > {1} && . {0}/bin/activate && echo "$PS1" >> {1} && deactivate && echo "$PS1" >> {1}\''
    #~ ).format(env, OUTPUT_FILE)

    assert 0 == subprocess.call(command, cwd=str(tmp_root), shell=True)

    lines = (tmp_root / output_name).read_bytes().split(b"\n")

    # Before activation and after deactivation
    assert lines[0] == lines[2]

    # Activated prompt
    assert lines[1] == prefix.encode("utf-8") + lines[0]


