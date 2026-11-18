import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "kallibragent"))

from axc_refresher_hook import run_if_enabled  # noqa: E402


def test_hook_does_nothing_without_setting(tmp_path):
    assert run_if_enabled(tmp_path) is None


def test_hook_runs_the_repo_script(tmp_path, capsys):
    repo = tmp_path / "repo"
    (repo / "push").mkdir(parents=True)
    (repo / "push" / "refresher_push.py").write_text("print('push summary line')\nimport sys\nsys.exit(3)\n")
    here = tmp_path / "agent"
    here.mkdir()
    (here / "refresher_push.json").write_text(json.dumps({"repo": str(repo)}))
    assert run_if_enabled(here) == 3
    assert "push summary line" in capsys.readouterr().out


def test_hook_reports_a_bad_setting(tmp_path, capsys):
    (tmp_path / "refresher_push.json").write_text(json.dumps({"repo": str(tmp_path / "missing")}))
    assert run_if_enabled(tmp_path) == 1
    assert "refresher_push.py" in capsys.readouterr().out
