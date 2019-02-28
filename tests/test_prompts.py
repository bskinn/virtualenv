"""test that prompt behavior is correct in supported shells"""
from __future__ import absolute_import, unicode_literals

import os
import subprocess
import sys
from textwrap import dedent

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

    if (sys.platform.startswith("win") and shell in ["bash", "csh", "fish"]) or (
        sys.platform.startswith("linux") and shell in ["cmd", "powershell"]
    ):
        return platform_incompat.format(shell, platform)

    if shell == "xonsh" and sys.version_info < (3, 4):
        return "xonsh requires Python 3.4 at least"


@pytest.fixture(scope="module")
def tmp_root(tmp_path_factory):
    """Provide Path to root with default and custom venvs created."""
    root = tmp_path_factory.mktemp("env_root")
    virtualenv.create_environment(str(root / ENV_DEFAULT), no_setuptools=True, no_pip=True, no_wheel=True)
    virtualenv.create_environment(
        str(root / ENV_CUSTOM), prompt=PREFIX_CUSTOM, no_setuptools=True, no_pip=True, no_wheel=True
    )

    _, _, _, bin_dir = virtualenv.path_locations(str(root / ENV_DEFAULT))

    bin_name = os.path.split(bin_dir)[-1]

    return root, bin_name


@pytest.fixture(scope="module")
def preamble_cmds():
    return {"bash": "", "fish": "", "csh": "set prompt=%", "xonsh": "$VIRTUAL_ENV = ''; $PROMPT = '{env_name}$ '"}


@pytest.fixture(scope="module")
def prompt_cmds():
    return {
        "bash": 'echo "$PS1"',
        "fish": "fish_prompt; echo ' '",
        "csh": r"set | grep -E 'prompt\s' | sed -E 's/^prompt\s+(.*)$/\1/'",
        "xonsh": "print(__xonsh__.shell.prompt)",
    }


@pytest.fixture(scope="module")
def activate_cmds():
    return {"bash": "activate", "fish": "activate.fish", "csh": "activate.csh", "xonsh": "activate.xsh"}


@pytest.fixture(scope="function")
def clean_env():
    """Provide a fresh copy of the shell environment."""
    return os.environ.copy()


@pytest.mark.parametrize(["command", "code"], [("echo test", 0), ("exit 1", 1)])
def test_exit_code(command, code, tmp_root):
    """Confirm subprocess.call exit codes work as expected at the unit test level."""
    assert subprocess.call(command, cwd=str(tmp_root[0]), shell=True) == code


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Invalid on Windows")
class TestPrompts:
    """Container for tests of bash prompt modifications."""

    @staticmethod
    @pytest.mark.skip("Not updated yet")
    def test_suppressed_prompt_default_env(tmp_root, clean_env):
        """Confirm VIRTUAL_ENV_DISABLE_PROMPT suppresses prompt changes on activate."""
        clean_env.update({VIRTUAL_ENV_DISABLE_PROMPT: "1"})
        command = 'echo "$PS1" > {1} && . {0}/bin/activate && echo "$PS1" >> {1}'.format(ENV_DEFAULT, OUTPUT_FILE)

        assert 0 == subprocess.call(command, cwd=str(tmp_root[0]), shell=True, env=clean_env)

        lines = (tmp_root[0] / OUTPUT_FILE).read_bytes().split(b"\n")
        assert lines[0] == lines[1]


@pytest.mark.parametrize("shell", ["bash", "fish", "csh", "xonsh", "cmd", "powershell"])
@pytest.mark.parametrize(["env", "prefix"], [(ENV_DEFAULT, PREFIX_DEFAULT), (ENV_CUSTOM, PREFIX_CUSTOM)])
def test_activated_prompt(shell, env, prefix, tmp_root, preamble_cmds, prompt_cmds, activate_cmds):
    """Confirm prompt modification behavior with and without --prompt specified."""
    shell_skip = platform_check(sys.platform, shell)
    if shell_skip:
        pytest.skip(shell_skip)

    script_name = SCRIPT_TEMPLATE.format(shell, "normal", env)
    output_name = OUTPUT_TEMPLATE.format(shell, "normal", env)

    if shell == "cmd":
        command = ""
    elif shell == "powershell":
        command = ". "
    else:
        command = "source "

    (tmp_root[0] / script_name).write_text(
        dedent(
            """\
        {preamble}
        echo foo
        {prompt}
        {command}{env}/{bindir}/{act}
        {prompt}
        deactivate
        {prompt}
        """.format(
                env=env,
                command=command,
                preamble=preamble_cmds[shell],
                prompt=prompt_cmds[shell],
                act=activate_cmds[shell],
                bindir=tmp_root[1],
            )
        )
    )

    command = "{0} {1} > {2}".format(shell, script_name, output_name)

    assert 0 == subprocess.call(command, cwd=str(tmp_root[0]), shell=True)

    lines = (tmp_root[0] / output_name).read_bytes().split(b"\n")

    # Before activation and after deactivation
    assert lines[1] == lines[3], lines

    # Activated prompt. This construction copes with messes like fish's ANSI codes
    before, env_marker, after = lines[2].partition(prefix.encode("utf-8"))
    assert env_marker != b"", lines
    assert lines[1] in after, lines
