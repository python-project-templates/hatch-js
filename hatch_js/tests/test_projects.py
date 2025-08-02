from os import listdir
from shutil import rmtree
from subprocess import check_call
from sys import modules

import pytest


class TestProject:
    @pytest.mark.parametrize(
        "project",
        [
            "test_project_basic",
        ],
    )
    def test_basic(self, project):
        # cleanup
        rmtree(f"hatch_js/tests/{project}/project/extension", ignore_errors=True)
        modules.pop("project", None)

        # compile
        check_call(
            [
                "hatchling",
                "build",
                "--hooks-only",
            ],
            cwd=f"hatch_js/tests/{project}",
        )

        # assert built
        assert "extension" in listdir(f"hatch_js/tests/{project}/project")
        assert "cdn" in listdir(f"hatch_js/tests/{project}/project/extension")
