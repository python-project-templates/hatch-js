from pathlib import Path

import pytest

from hatch_js.structs import HatchJsBuildPlan


@pytest.mark.parametrize("targets", [None, []])
def test_execute_uses_working_directory_by_default(tmp_path, monkeypatch, targets):
    monkeypatch.chdir(tmp_path)
    directories = []

    def run(command):
        directories.append(Path.cwd())
        return 0

    monkeypatch.setattr("hatch_js.structs.system_call", run)
    plan = HatchJsBuildPlan(targets=targets)
    plan.generate()
    plan.execute()
    assert directories == [tmp_path, tmp_path]
