import json
import os
import subprocess

import pytest

from crew import agent
from crew.agent import AgentError, agent_argv, agent_env, noreply_email, read_token
from crew.cli import main

AGENT_LOGIN = "agent-b"
AGENT_ID = 42
TOKEN = "tok-SECRET-123"
GH_DIR = agent.Path("/nonexistent/crew-gh")


class FakeRun:
    """Stands in for ``subprocess.run`` answering ``gh api user``."""

    def __init__(self, login=AGENT_LOGIN, user_id=AGENT_ID):
        self.answer = json.dumps({"login": login, "id": user_id})
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, stdout=self.answer, stderr="")


class FakeExec:
    def __init__(self):
        self.calls = []

    def __call__(self, file, argv, env):
        self.calls.append((file, argv, env))
        self.cwd = os.getcwd()


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project with a config and a mode-600 token file; ``gh`` and ``exec`` are faked."""
    root = tmp_path / "project"
    (root / ".crew").mkdir(parents=True)
    (root / ".crew" / "config.yaml").write_text(
        f"repo: example/app\nowner_login: owner-a\nagent_login: {AGENT_LOGIN}\n"
    )
    token_file = tmp_path / "agent-token"
    token_file.write_text(TOKEN + "\n")
    token_file.chmod(0o600)
    monkeypatch.setenv(agent.TOKEN_FILE_ENV, str(token_file))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-config"))  # no registry
    fake_run, fake_exec = FakeRun(), FakeExec()
    monkeypatch.setattr(agent, "RUN", fake_run)
    monkeypatch.setattr(agent, "EXEC", fake_exec)
    return root, token_file, fake_run, fake_exec


def test_agent_argv_roles_and_model():
    assert agent_argv("implementer", "Use crew:implement on issue #12", None) == [
        "claude",
        "--agent",
        "crew:implementer",
        "--settings",
        agent.STATUS_LINE_SETTINGS,
        "Use crew:implement on issue #12",
    ]
    assert agent_argv("reviewer", "Use crew:review on PR #3", "sonnet") == [
        "claude",
        "--agent",
        "crew:reviewer",
        "--model",
        "sonnet",
        "--settings",
        agent.STATUS_LINE_SETTINGS,
        "Use crew:review on PR #3",
    ]
    assert agent_argv("lead", None, None) == [
        "claude",
        "--agent",
        "crew:lead",
        "--settings",
        agent.STATUS_LINE_SETTINGS,
    ]
    with pytest.raises(AgentError) as excinfo:
        agent_argv("janitor", None, None)
    assert all(role in str(excinfo.value) for role in agent.ROLES)


def test_noreply_email():
    assert noreply_email("botty", 42) == "42+botty@users.noreply.github.com"


def test_token_path_default_and_override(tmp_path):
    assert agent.token_path({}) == agent.Path(agent.DEFAULT_TOKEN_FILE).expanduser()
    assert agent.token_path({agent.TOKEN_FILE_ENV: str(tmp_path / "t")}) == tmp_path / "t"


def test_missing_token_refuses(project, capsys):
    root, token_file, _, fake_exec = project
    token_file.unlink()
    with pytest.raises(AgentError):
        read_token(token_file)
    cases = [
        lambda: None,  # missing
        lambda: (token_file.write_text("\n"), token_file.chmod(0o600)),  # empty
        lambda: (token_file.write_text(TOKEN), token_file.chmod(0o644)),  # readable by others
    ]
    for make_case in cases:
        make_case()
        if token_file.exists():
            with pytest.raises(AgentError):
                read_token(token_file)
        assert main(["agent", "lead", "--root", str(root)]) == 2
        err = capsys.readouterr().err
        assert err.startswith("crew: error: ") and err.count("\n") == 1
        assert TOKEN not in err
    assert fake_exec.calls == []


def test_token_for_other_account_refuses(project, monkeypatch, capsys):
    root, _, _, fake_exec = project
    monkeypatch.setattr(agent, "RUN", FakeRun(login="someone", user_id=1))
    assert main(["agent", "lead", "--root", str(root)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("crew: error: ") and err.count("\n") == 1
    assert "someone" in err and AGENT_LOGIN in err
    assert fake_exec.calls == []


def test_whoami_passes_token_only_in_env():
    fake_run = FakeRun()
    assert agent.whoami(TOKEN, run=fake_run) == (AGENT_LOGIN, AGENT_ID)
    ((args, kwargs),) = fake_run.calls
    assert TOKEN not in " ".join(args)
    assert kwargs["env"]["GH_TOKEN"] == TOKEN


def _git(env, *args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture
def git_repo(tmp_path):
    """A temp repo and a temp HOME whose global config stores credentials."""
    home = tmp_path / "home"
    home.mkdir()
    (home / ".gitconfig").write_text("[credential]\n\thelper = store\n")
    repo = tmp_path / "repo"
    repo.mkdir()
    base = {"HOME": str(home), "PATH": os.environ["PATH"], "GIT_CONFIG_NOSYSTEM": "1"}
    _git(base, "init", "-q", cwd=repo)
    return repo, agent_env(base, TOKEN, "botty", 42, GH_DIR)


def test_git_config_resets_credential_helpers(git_repo):
    repo, env = git_repo
    helpers = _git(env, "config", "--get-all", "credential.https://github.com.helper", cwd=repo)
    assert helpers.split("\n")[:2] == ["", "!gh auth git-credential"]
    assert _git(env, "config", "user.email", cwd=repo).strip() == noreply_email("botty", 42)
    assert _git(env, "config", "user.name", cwd=repo).strip() == "botty"
    assert env["GH_TOKEN"] == TOKEN


def test_ssh_remote_rewritten_to_https(git_repo):
    repo, env = git_repo
    _git(env, "remote", "add", "origin", "git@github.com:example/app.git", cwd=repo)
    url = _git(env, "ls-remote", "--get-url", "origin", cwd=repo).strip()
    assert url == "https://github.com/example/app.git"


def test_existing_git_config_count_kept():
    base = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.pager", "GIT_CONFIG_VALUE_0": "cat"}
    env = agent_env(base, TOKEN, "botty", 42, GH_DIR)
    assert env["GIT_CONFIG_COUNT"] == "7"
    assert (env["GIT_CONFIG_KEY_0"], env["GIT_CONFIG_VALUE_0"]) == ("core.pager", "cat")
    assert env["GIT_CONFIG_KEY_1"] == "user.name"
    assert base["GIT_CONFIG_COUNT"] == "1"


def test_check_never_prints_token(project, capsys):
    root, _, _, fake_exec = project
    assert main(["agent", "lead", "--check", "--root", str(root)]) == 0
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        f"gh: {AGENT_LOGIN}",
        "gh config: isolated",
        f"git: {AGENT_LOGIN} {noreply_email(AGENT_LOGIN, AGENT_ID)}",
        "push: https via gh (ssh rewritten)",
        "plugin: unknown (registry not found)",
    ]
    assert "SECRET" not in captured.out + captured.err
    assert fake_exec.calls == []


def test_launch_execs_claude_with_env(project):
    root, _, _, fake_exec = project
    main(["agent", "reviewer", "Use crew:review on PR #3", "--auto", "--root", str(root)])
    ((file, argv, env),) = fake_exec.calls
    assert file == "claude"
    assert argv == [
        "claude",
        "--agent",
        "crew:reviewer",
        "--permission-mode",
        "auto",
        "--settings",
        agent.STATUS_LINE_SETTINGS,
        "Use crew:review on PR #3",
    ]
    assert env["GH_TOKEN"] == TOKEN
    assert "GIT_CONFIG_COUNT" in env


def test_missing_claude_binary_is_an_error(project, monkeypatch, capsys):
    root, *_ = project

    def no_claude(file, argv, env):
        raise FileNotFoundError(2, "No such file or directory", file)

    monkeypatch.setattr(agent, "EXEC", no_claude)
    assert main(["agent", "lead", "--root", str(root)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("crew: error: ") and "claude" in err


def test_ssh_disabled_for_every_form(git_repo, tmp_path):
    repo, env = git_repo
    with open(env["HOME"] + "/.gitconfig", "a") as config:
        config.write('[url "git@github.com:"]\n\tpushInsteadOf = https://github.com/\n')
    _git(env, "remote", "add", "origin", "https://github.com/example/app.git", cwd=repo)
    _git(env, "remote", "add", "alias", "github-alias:example/app.git", cwd=repo)
    _git(env, "commit", "-q", "--allow-empty", "-m", "t", cwd=repo)
    # Whatever URL git ends up with, an ssh transport must refuse rather than use the owner's key.
    for command in (["push", "origin", "HEAD:main"], ["ls-remote", "alias"]):
        result = subprocess.run(
            ["git", *command], cwd=repo, env=env, capture_output=True, text=True
        )
        assert result.returncode != 0
        assert "ssh disabled" in result.stderr


def test_ssh_url_form_rewritten_to_https(git_repo):
    repo, env = git_repo
    _git(env, "remote", "add", "origin", "ssh://git@github.com/example/app.git", cwd=repo)
    url = _git(env, "ls-remote", "--get-url", "origin", cwd=repo).strip()
    assert url == "https://github.com/example/app.git"


def test_inherited_github_tokens_cleared():
    base = {
        "GITHUB_TOKEN": "owner",
        "GH_ENTERPRISE_TOKEN": "o",
        "GITHUB_ENTERPRISE_TOKEN": "o",
        "GH_HOST": "ghe.example.com",
        "PATH": "/bin",
    }
    env = agent_env(base, TOKEN, "botty", 42, GH_DIR)
    assert not {"GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN", "GH_HOST"} & set(
        env
    )
    assert env["PATH"] == "/bin"


def test_whoami_ignores_inherited_github_vars(monkeypatch):
    monkeypatch.setenv("GH_HOST", "ghe.example.com")
    monkeypatch.setenv("GITHUB_TOKEN", "owner")
    fake_run = FakeRun()
    agent.whoami(TOKEN, run=fake_run)
    ((_, kwargs),) = fake_run.calls
    assert "GH_HOST" not in kwargs["env"] and "GITHUB_TOKEN" not in kwargs["env"]


def test_agent_login_equal_to_owner_refuses(project, monkeypatch, capsys):
    root, _, _, fake_exec = project
    (root / ".crew" / "config.yaml").write_text(
        "repo: example/app\nowner_login: owner-a\nagent_login: Owner-A\n"
    )
    monkeypatch.setattr(agent, "RUN", FakeRun(login="Owner-A", user_id=7))
    assert main(["agent", "lead", "--root", str(root)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("crew: error: ") and "owner" in err
    assert fake_exec.calls == []


def test_gh_config_dir_isolated(tmp_path):
    base = {"GH_CONFIG_DIR": str(tmp_path / "owner-gh"), "XDG_RUNTIME_DIR": str(tmp_path)}
    first = agent.new_gh_config_dir(base)
    env = agent_env(base, TOKEN, "botty", 42, first)
    assert env["GH_CONFIG_DIR"] == str(first) != base["GH_CONFIG_DIR"]
    assert first.is_dir() and list(first.iterdir()) == []
    assert agent.stat.S_IMODE(first.stat().st_mode) == 0o700
    assert agent.new_gh_config_dir(base) != first


def test_agent_login_case_insensitive(project):
    root, _, _, fake_exec = project
    (root / ".crew" / "config.yaml").write_text(
        "repo: example/app\nowner_login: owner-a\nagent_login: Agent-B\n"
    )
    assert main(["agent", "lead", "--root", str(root)]) == 0
    assert len(fake_exec.calls) == 1


@pytest.mark.parametrize("value", ["abc", "-1"])
def test_bad_git_config_count_is_clean_error(project, monkeypatch, capsys, value):
    root, _, _, fake_exec = project
    monkeypatch.setenv("GIT_CONFIG_COUNT", value)
    assert main(["agent", "lead", "--root", str(root)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("crew: error: ") and err.count("\n") == 1
    assert "GIT_CONFIG_COUNT" in err
    assert fake_exec.calls == []


def test_root_sets_session_cwd(project, monkeypatch, tmp_path):
    root, _, _, fake_exec = project
    monkeypatch.chdir(tmp_path)
    main(["agent", "lead", "--root", str(root)])
    assert fake_exec.cwd == str(root)


def test_check_prints_isolated_gh_config(project, capsys):
    root, *_ = project
    assert main(["agent", "lead", "--check", "--root", str(root)]) == 0
    assert "gh config: isolated" in capsys.readouterr().out.splitlines()


def _registry(config_dir, plugins):
    (config_dir / "plugins").mkdir(parents=True, exist_ok=True)
    (config_dir / "plugins" / "installed_plugins.json").write_text(
        json.dumps({"version": 2, "plugins": plugins})
    )


def test_plugin_installed_reads_registry(tmp_path):
    env = {"CLAUDE_CONFIG_DIR": str(tmp_path)}
    assert agent.plugin_installed(env) is None
    _registry(tmp_path, {"other@x": []})
    assert agent.plugin_installed(env) is False
    _registry(tmp_path, {"crew@agent-crew": [{"scope": "user"}]})
    assert agent.plugin_installed(env) is True
    (tmp_path / "plugins" / "installed_plugins.json").write_text("[1, 2]")
    assert agent.plugin_installed(env) is None


def test_agent_without_plugin_prints_install_command(project, tmp_path, capsys):
    root, token_file, fake_run, fake_exec = project
    _registry(tmp_path / "claude-config", {"other@x": []})
    token_file.unlink()
    assert main(["agent", "lead", "--root", str(root)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("crew: error: ") and err.count("\n") == 1
    assert "crew plugin is not installed" in err and agent.PLUGIN_INSTALL in err
    assert fake_exec.calls == [] and fake_run.calls == []


def test_check_reports_installed_plugin(project, tmp_path, capsys):
    root, *_ = project
    _registry(tmp_path / "claude-config", {"crew@agent-crew": [{"scope": "user"}]})
    assert main(["agent", "lead", "--check", "--root", str(root)]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "plugin: crew installed"


def test_plugin_installed_honours_project_scope(tmp_path):
    env = {"CLAUDE_CONFIG_DIR": str(tmp_path)}
    project = tmp_path / "app"
    entry = {"scope": "project", "projectPath": str(project)}
    _registry(tmp_path, {"crew@agent-crew": [entry]})
    assert agent.plugin_installed(env, tmp_path / "other") is False
    assert agent.plugin_installed(env, project) is True
    assert agent.plugin_installed(env, project / ".crew" / "worktrees" / "unit-3") is True
    assert agent.plugin_installed(env, tmp_path / "app2") is False


def test_plugin_enabled_by_project_settings(tmp_path):
    env = {"CLAUDE_CONFIG_DIR": str(tmp_path / "config")}
    entry = {"scope": "project", "projectPath": str(tmp_path / "elsewhere")}
    _registry(tmp_path / "config", {"crew@agent-crew": [entry]})
    project = tmp_path / "sandbox"
    (project / ".claude").mkdir(parents=True)
    worktree = project / ".crew" / "worktrees" / "unit-1"
    assert agent.plugin_installed(env, project) is False
    (project / ".claude" / "settings.json").write_text(
        json.dumps({"enabledPlugins": {"crew@agent-crew": True}})
    )
    assert agent.plugin_installed(env, project) is True
    assert agent.plugin_installed(env, worktree) is True
    (project / ".claude" / "settings.json").write_text(
        json.dumps({"enabledPlugins": {"crew@agent-crew": False}})
    )
    assert agent.plugin_installed(env, project) is False
