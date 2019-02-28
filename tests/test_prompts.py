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

SHELL_LIST = ["bash", "fish", "csh", "xonsh", "cmd", "powershell"]
COMMANDS = {"powershell": ". ", "cmd": ""}


def platform_check_skip(platform, shell):
    """Return non-empty string if tests should be skipped."""
    platform_incompat = "No sane provision for {} on {} yet"

    if (sys.platform.startswith("win") and shell in ["bash", "csh", "fish"]) or (
        sys.platform.startswith("linux") and shell in ["cmd", "powershell"]
    ):
        pytest.skip(platform_incompat.format(shell, platform))

    if shell == "xonsh" and sys.version_info < (3, 4):
        pytest.skip("xonsh requires Python 3.4 at least")


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


@pytest.mark.parametrize("shell", SHELL_LIST)
@pytest.mark.parametrize("env", [ENV_DEFAULT, ENV_CUSTOM])
def test_suppressed_prompt(shell, env, tmp_root, clean_env, preamble_cmds, prompt_cmds, activate_cmds):
    """Confirm VIRTUAL_ENV_DISABLE_PROMPT suppresses prompt changes on activate."""
    platform_check_skip(sys.platform, shell)

    script_name = SCRIPT_TEMPLATE.format(shell, "suppress", env)
    output_name = OUTPUT_TEMPLATE.format(shell, "suppress", env)

    clean_env.update({VIRTUAL_ENV_DISABLE_PROMPT: "1"})

    command = COMMANDS.get(shell, "source ")

    # The "echo foo" here copes with some oddity of xonsh in certain emulated terminal
    # contexts: xonsh can dump stuff into the first line of the recorded script output,
    # so we have to include a dummy line of output that can get munged w/o consequence.
    (tmp_root[0] / script_name).write_text(
        dedent(
            """\
        {preamble}
        echo foo
        {prompt}
        {command}{env}/{bindir}/{act}
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

    assert 0 == subprocess.call(command, cwd=str(tmp_root[0]), shell=True, env=clean_env)

    lines = (tmp_root[0] / output_name).read_bytes().split(b"\n")

    # Is the prompt suppressed?
    assert lines[1] == lines[2], lines


@pytest.mark.parametrize("shell", SHELL_LIST)
@pytest.mark.parametrize(["env", "prefix"], [(ENV_DEFAULT, PREFIX_DEFAULT), (ENV_CUSTOM, PREFIX_CUSTOM)])
def test_activated_prompt(shell, env, prefix, tmp_root, preamble_cmds, prompt_cmds, activate_cmds):
    """Confirm prompt modification behavior with and without --prompt specified."""
    platform_check_skip(sys.platform, shell)

    script_name = SCRIPT_TEMPLATE.format(shell, "normal", env)
    output_name = OUTPUT_TEMPLATE.format(shell, "normal", env)

    command = COMMANDS.get(shell, "source ")

    # The "echo foo" here copes with some oddity of xonsh in certain emulated terminal
    # contexts: xonsh can dump stuff into the first line of the recorded script output,
    # so we have to include a dummy line of output that can get munged w/o consequence.
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

    # Activated prompt. This construction copes with messes like fish's ANSI codes for colorizing.
    # It's not as rigorous as I would like, but it provides assurance to the key pieces
    # of content that should be present.
    before, env_marker, after = lines[2].partition(prefix.encode("utf-8"))
    assert env_marker != b"", lines
    assert lines[1] in after, lines
