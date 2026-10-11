from hatchling.builders.utils import normalize_inclusion_map

from hatch_js.tests.test_licenses import hook, wheel_config

pytest_plugins = ["hatch_js.tests.test_licenses"]


def test_normal_hook_override_survives_editable_license_collection(project):
    root, _, _ = project
    (root / "normal.txt").write_text("Original forced content", encoding="utf-8")
    config = wheel_config(root, {"packages": ["project"], "force-include": {"normal.txt": "project/normal.txt"}})
    builder = hook(root, {"licenses": {"destination": "project/licenses/pnpm.json"}}, build_config=config)
    data = {"force_include": {"normal.txt": "project/override.txt"}, "force_include_editable": {}}
    builder.initialize("editable", data)
    effective = normalize_inclusion_map(data["force_include_editable"], str(root))
    assert effective[str(root / "normal.txt")] == "project/override.txt"
    assert "project/licenses/pnpm.json" in effective.values()
    builder.finalize("editable", data, "unused.whl")
