import json
import os
import subprocess
import sys
import tarfile
import zipfile
from importlib.metadata import distribution
from pathlib import Path

import pytest


@pytest.mark.parametrize("production_only", [False, True])
@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
@pytest.mark.parametrize("version", ["standard", "editable"])
@pytest.mark.parametrize("custom_first", [True, False])
def test_pnpm_licenses_in_wheel_built_from_sdist(tmp_path, production_only, newline, version, custom_first):
    project = tmp_path / "source"
    (project / "project").mkdir(parents=True)
    (project / "project/__init__.py").write_text("", encoding="utf-8")
    (project / "js").mkdir()
    dist = distribution("hatch-js")
    license_file = next(file for file in dist.files or [] if file.name == "LICENSE" and any(part.endswith(".dist-info") for part in file.parts))
    original = Path(str(dist.locate_file(license_file))).read_bytes().replace(b"\r\n", b"\n").replace(b"\n", newline)
    for name in ("license-fixture", "license-dev-fixture"):
        dependency = tmp_path / name
        dependency.mkdir()
        (dependency / "package.json").write_text(json.dumps({"name": name, "version": "1.0.0", "license": "Apache-2.0"}), encoding="utf-8")
        (dependency / "LICENSE").write_bytes(original)
        (dependency / "NOTICE").write_bytes(b"Fixture authors and attribution.\n")
        with tarfile.open(project / f"{name}.tgz", "w:gz") as archive:
            archive.add(dependency, arcname="package")
    (project / "js/package.json").write_text(
        json.dumps(
            {
                "name": "frontend",
                "private": True,
                "scripts": {"build": "node build.mjs"},
                "dependencies": {"license-fixture": "file:../license-fixture.tgz"},
                "devDependencies": {"license-dev-fixture": "file:../license-dev-fixture.tgz"},
            }
        ),
        encoding="utf-8",
    )
    (project / "js/build.mjs").write_text(
        "import { writeFileSync } from 'node:fs';\nwriteFileSync('../project/frontend.js', 'built frontend');\n", encoding="utf-8"
    )
    (project / "extra.txt").write_text("Other hook's editable output", encoding="utf-8")
    (project / "normal.txt").write_text("Configured forced output", encoding="utf-8")
    (project / "hatch_build.py").write_text(
        "from hatchling.builders.hooks.plugin.interface import BuildHookInterface\n"
        "class CustomBuildHook(BuildHookInterface):\n"
        "    def initialize(self, version, build_data):\n"
        "        if version == 'editable':\n"
        "            build_data['force_include_editable']['extra.txt'] = 'project/extra.txt'\n",
        encoding="utf-8",
    )
    (project / "pyproject.toml").write_text(
        f"""[build-system]
requires = ["hatchling", "hatch-js"]
build-backend = "hatchling.build"
[project]
name = "license-project"
version = "0.1.0"
[tool.hatch.build.targets.sdist]
include = ["/project", "/js", "/*.tgz", "/pyproject.toml", "/hatch_build.py", "/extra.txt", "/normal.txt"]
[tool.hatch.build.targets.wheel]
packages = ["project"]
[tool.hatch.build.targets.wheel.force-include]
"normal.txt" = "project/normal.txt"
{"[tool.hatch.build.hooks.custom]" if custom_first else ""}
[tool.hatch.build.hooks.hatch-js]
path = "js"
tool = "pnpm"
targets = ["project/frontend.js"]
[tool.hatch.build.hooks.hatch-js.licenses]
destination = "project/licenses/pnpm.json"
production-only = {str(production_only).lower()}
{"[tool.hatch.build.hooks.custom]" if not custom_first else ""}
""",
        encoding="utf-8",
    )
    environment = {key: value for key, value in os.environ.items() if key != "SKIP_HATCH_JS"}
    environment["CI"] = "true"
    subprocess.run([sys.executable, "-m", "build", "--sdist", "--no-isolation"], cwd=project, env=environment, check=True)
    assert not (project / "js/node_modules").exists()
    extracted = tmp_path / "extracted"
    with tarfile.open(next((project / "dist").glob("*.tar.gz"))) as archive:
        assert not any(name.endswith("licenses/pnpm.json") for name in archive.getnames())
        archive.extractall(extracted, filter="data")
    source = next(extracted.iterdir())
    command = (
        [sys.executable, "-m", "build", "--wheel", "--no-isolation"]
        if version == "standard"
        else [sys.executable, "-c", "from hatchling.build import build_editable; build_editable('dist')"]
    )
    subprocess.run(command, cwd=source, env=environment, check=True)
    with zipfile.ZipFile(next((source / "dist").glob("*.whl"))) as wheel:
        if version == "standard":
            assert wheel.read("project/frontend.js") == b"built frontend"
        else:
            assert wheel.read("project/extra.txt") == b"Other hook's editable output"
        if version == "standard" or not custom_first:
            assert wheel.read("project/normal.txt") == b"Configured forced output"
        assert wheel.namelist().count("project/licenses/pnpm.json") == 1
        output = json.loads(wheel.read("project/licenses/pnpm.json"))
    assert output["root_name"] == "frontend"
    names = {library["package_name"] for library in output["libraries"]}
    assert names == ({"license-fixture"} if production_only else {"license-fixture", "license-dev-fixture"})
    for library in output["libraries"]:
        assert library["package_version"] == "1.0.0"
        assert library["license"] == "Apache-2.0"
        assert library["files"] == [
            {"path": "LICENSE", "text": original.decode("utf-8")},
            {"path": "NOTICE", "text": "Fixture authors and attribution.\n"},
        ]
    assert not (source / "project/licenses").exists()
