import json
import subprocess
from pathlib import Path

import pytest
from hatchling.builders.wheel import WheelBuilder
from hatchling.metadata.core import ProjectMetadata

from hatch_js.plugin import HatchJsBuildHook


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "js").mkdir()
    (tmp_path / "project").mkdir()
    (tmp_path / "js/package.json").write_text(json.dumps({"name": "frontend", "dependencies": {"dependency": "1.0.0"}}), encoding="utf-8")
    dependency = tmp_path / "js/node_modules/dependency"
    dependency.mkdir(parents=True)
    (dependency / "package.json").write_text(json.dumps({"name": "dependency", "version": "1.0.0", "license": "MIT"}), encoding="utf-8")
    (dependency / "LICENSE").write_bytes(b"Copyright fixture authors\r\nPermission is hereby granted.\r\n")
    (dependency / "NOTICE").write_bytes(b"Original third-party attribution.\n")
    monkeypatch.setattr("hatch_js.structs.system_call", lambda command: 0)
    output = {"MIT": [{"name": "dependency", "versions": ["1.0.0"], "paths": [str(dependency)], "license": "MIT"}]}

    def collect(command, **kwargs):
        assert command[:4] == ["pnpm", "licenses", "list", "--json"]
        assert Path(kwargs["cwd"]).resolve() == (tmp_path / "js").resolve()
        return subprocess.CompletedProcess(command, 0, json.dumps(output), "")

    monkeypatch.setattr(subprocess, "run", collect)
    return tmp_path, dependency, output


def hook(root, config=None, target="wheel", build_config=None):
    return HatchJsBuildHook(
        root=str(root),
        config={"path": "js", "tool": "pnpm", **(config or {})},
        build_config=build_config,
        metadata=ProjectMetadata(str(root), None, {"project": {"name": "project", "version": "0.1.0"}}),
        directory=str(root / "dist"),
        target_name=target,
    )


def bundle(build_data):
    source, destination = next(iter(build_data["force_include"].items()))
    assert destination == "project/licenses/pnpm.json"
    return json.loads(Path(source).read_bytes()), Path(source)


def test_wheel_bundle_preserves_original_license_and_notice(project):
    root, _, _ = project
    builder = hook(root, {"licenses": {"destination": "project/licenses/pnpm.json"}})
    data = {}
    builder.initialize("standard", data)
    result, source = bundle(data)
    assert result == {
        "root_name": "frontend",
        "libraries": [
            {
                "package_name": "dependency",
                "package_version": "1.0.0",
                "license": "MIT",
                "files": [
                    {"path": "LICENSE", "text": "Copyright fixture authors\r\nPermission is hereby granted.\r\n"},
                    {"path": "NOTICE", "text": "Original third-party attribution.\n"},
                ],
            }
        ],
    }
    assert not (root / "project/licenses").exists()
    builder.finalize("standard", data, "unused.whl")
    assert not source.exists()


@pytest.mark.parametrize("version", ["standard", "editable"])
def test_builds_collect_licenses_and_cleanup_on_clean(project, version):
    root, _, _ = project
    builder = hook(root, {"licenses": {"destination": "project/licenses/pnpm.json"}})
    data = {}
    builder.initialize(version, data)
    _, source = bundle(data)
    assert source.exists()
    builder.clean([version])
    assert not source.exists()


@pytest.mark.parametrize("skip", ["disabled", "sdist", "environment"])
def test_collection_is_opt_in_and_respects_skips(project, monkeypatch, skip):
    root, _, _ = project
    if skip == "environment":
        monkeypatch.setenv("SKIP_HATCH_JS", "1")
    config = {} if skip == "disabled" else {"licenses": {"destination": "project/licenses/pnpm.json"}}
    builder = hook(root, config, target="sdist" if skip == "sdist" else "wheel")
    data = {}
    builder.initialize("standard", data)
    assert "force_include" not in data


def test_notice_only_override_does_not_satisfy_missing_license(project):
    root, dependency, _ = project
    (dependency / "LICENSE").unlink()
    (root / "overrides.json").write_text(
        json.dumps(
            {
                "libraries": [
                    {
                        "package_name": "dependency",
                        "package_version": "1.0.0",
                        "license": "MIT",
                        "files": [{"path": "NOTICE", "text": "Original third-party attribution.\n"}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing license text"):
        hook(root, {"licenses": {"destination": "project/licenses/pnpm.json", "previous": "overrides.json"}}).initialize("standard", {})


@pytest.mark.parametrize("text", ["Original terms", "Replacement terms"])
def test_override_checks_original_unrecognized_file(project, text):
    root, dependency, _ = project
    (dependency / "LICENSE").unlink()
    (dependency / "terms.txt").write_text("Original terms", encoding="utf-8")
    (root / "overrides.json").write_text(
        json.dumps(
            {
                "libraries": [
                    {"package_name": "dependency", "package_version": "1.0.0", "license": "MIT", "files": [{"path": "terms.txt", "text": text}]}
                ]
            }
        ),
        encoding="utf-8",
    )
    builder = hook(root, {"licenses": {"destination": "project/licenses/pnpm.json", "previous": "overrides.json"}})
    data = {}
    if text != "Original terms":
        with pytest.raises(ValueError, match="conflicts"):
            builder.initialize("standard", data)
    else:
        builder.initialize("standard", data)
        result, _ = bundle(data)
        assert result["libraries"][0]["files"][-1] == {"path": "terms.txt", "text": "Original terms"}
        builder.finalize("standard", data, "unused.whl")


def test_override_fills_absent_declared_license_file(project):
    root, dependency, output = project
    (dependency / "LICENSE").unlink()
    expression = "SEE LICENSE IN terms.txt"
    (dependency / "package.json").write_text(json.dumps({"name": "dependency", "version": "1.0.0", "license": expression}), encoding="utf-8")
    output[expression] = output.pop("MIT")
    output[expression][0]["license"] = expression
    (root / "overrides.json").write_text(
        json.dumps(
            {
                "libraries": [
                    {
                        "package_name": "dependency",
                        "package_version": "1.0.0",
                        "license": expression,
                        "files": [{"path": "terms.txt", "text": "Original terms"}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    builder = hook(root, {"licenses": {"destination": "project/licenses/pnpm.json", "previous": "overrides.json"}})
    data = {}
    builder.initialize("standard", data)
    result, _ = bundle(data)
    assert result["libraries"][0]["files"] == [
        {"path": "NOTICE", "text": "Original third-party attribution.\n"},
        {"path": "terms.txt", "text": "Original terms"},
    ]
    builder.finalize("standard", data, "unused.whl")


def wheel_config(root, target_config):
    builder = WheelBuilder(
        str(root), config={"project": {"name": "project", "version": "0.1.0"}, "tool": {"hatch": {"build": {"targets": {"wheel": target_config}}}}}
    )
    return builder.config


def test_collection_checks_configured_force_include(project):
    root, _, _ = project
    (root / "existing.txt").write_text("Existing content", encoding="utf-8")
    config = wheel_config(root, {"packages": ["project"], "force-include": {"existing.txt": "project/licenses/pnpm.json"}})
    with pytest.raises(ValueError, match="collision"):
        hook(root, {"licenses": {"destination": "project/licenses/pnpm.json"}}, build_config=config).initialize("standard", {})


def test_collection_checks_source_layout_collision(project):
    root, _, _ = project
    (root / "src/project/licenses").mkdir(parents=True)
    (root / "src/project/licenses/pnpm.json").write_text("Source original", encoding="utf-8")
    config = wheel_config(root, {"packages": ["src/project"]})
    with pytest.raises(ValueError, match="collision"):
        hook(root, {"licenses": {"destination": "project/licenses/pnpm.json"}}, build_config=config).initialize("standard", {})
    assert (root / "src/project/licenses/pnpm.json").read_text() == "Source original"


def test_collection_rejects_rewritten_destination(project):
    root, _, _ = project
    config = wheel_config(root, {"packages": ["project"], "sources": {"project": "mapped"}})
    with pytest.raises(ValueError, match="sources"):
        hook(root, {"licenses": {"destination": "project/licenses/pnpm.json"}}, build_config=config).initialize("standard", {})


def test_collection_checks_post_build_destination(project, monkeypatch):
    root, _, _ = project

    def build(command):
        (root / "project/licenses").mkdir(exist_ok=True)
        (root / "project/licenses/pnpm.json").write_text("Build output", encoding="utf-8")
        return 0

    monkeypatch.setattr("hatch_js.structs.system_call", build)
    with pytest.raises(ValueError, match="collision"):
        hook(root, {"licenses": {"destination": "project/licenses/pnpm.json"}}).initialize("standard", {})


@pytest.mark.parametrize("tool", ["npm", "yarn", "jlpm"])
def test_collection_rejects_unsupported_managers(project, tool, monkeypatch):
    root, _, _ = project
    monkeypatch.setattr("hatch_js.structs.which", lambda value: value)
    with pytest.raises(ValueError, match="pnpm"):
        hook(root, {"tool": tool, "licenses": {"destination": "project/licenses/pnpm.json"}}).initialize("standard", {})


@pytest.mark.parametrize(
    "destination",
    [
        "",
        "/tmp/licenses.json",
        "../escape.json",
        "project/../escape.json",
        "C:/licenses.json",
        "project\\licenses.json",
        "project//licenses.json",
        "project/./licenses.json",
        "project.dist-info/licenses.json",
    ],
)
def test_collection_rejects_unsafe_destinations(project, destination):
    root, _, _ = project
    with pytest.raises(ValueError, match="destination"):
        hook(root, {"licenses": {"destination": destination}}).initialize("standard", {})


def test_collection_rejects_existing_package_file(project):
    root, _, _ = project
    (root / "project/licenses").mkdir()
    (root / "project/licenses/pnpm.json").write_text("original", encoding="utf-8")
    with pytest.raises(ValueError, match="collision"):
        hook(root, {"licenses": {"destination": "project/licenses/pnpm.json"}}).initialize("standard", {})
    assert (root / "project/licenses/pnpm.json").read_text() == "original"


@pytest.mark.parametrize("destination", ["project/licenses/pnpm.json", "project/licenses", "project/licenses/pnpm.json/child"])
def test_collection_rejects_force_include_collisions(project, destination):
    root, _, _ = project
    with pytest.raises(ValueError, match="collision"):
        hook(root, {"licenses": {"destination": "project/licenses/pnpm.json"}}).initialize("standard", {"force_include": {"existing": destination}})


def test_collection_checks_both_inclusion_maps_for_same_source(project):
    root, _, _ = project
    with pytest.raises(ValueError, match="collision"):
        hook(root, {"licenses": {"destination": "project/licenses/pnpm.json"}}).initialize(
            "standard",
            {
                "force_include": {"existing": "project/licenses/pnpm.json"},
                "force_include_editable": {"existing": "project/other.txt"},
            },
        )


def test_notice_alone_does_not_satisfy_missing_license(project):
    root, dependency, _ = project
    (dependency / "LICENSE").unlink()
    with pytest.raises(ValueError, match="missing license text"):
        hook(root, {"licenses": {"destination": "project/licenses/pnpm.json"}}).initialize("standard", {})


def test_reviewed_override_fills_missing_license_but_retains_notice(project):
    root, dependency, _ = project
    (dependency / "LICENSE").unlink()
    (root / "overrides.json").write_text(
        json.dumps(
            {
                "libraries": [
                    {
                        "package_name": "dependency",
                        "package_version": "1.0.0",
                        "license": "MIT",
                        "files": [{"path": "LICENSE", "text": "Reviewed original license."}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    builder = hook(root, {"licenses": {"destination": "project/licenses/pnpm.json", "previous": "overrides.json"}})
    data = {}
    builder.initialize("standard", data)
    result, _ = bundle(data)
    assert result["libraries"][0]["files"] == [
        {"path": "LICENSE", "text": "Reviewed original license."},
        {"path": "NOTICE", "text": "Original third-party attribution.\n"},
    ]
    builder.finalize("standard", data, "unused.whl")


@pytest.mark.parametrize("change", ["version", "expression"])
def test_reviewed_override_does_not_match_different_version_or_expression(project, change):
    root, dependency, _ = project
    (dependency / "LICENSE").unlink()
    (root / "overrides.json").write_text(
        json.dumps(
            {
                "libraries": [
                    {
                        "package_name": "dependency",
                        "package_version": "2.0.0" if change == "version" else "1.0.0",
                        "license": "Apache-2.0" if change == "expression" else "MIT",
                        "files": [{"path": "LICENSE", "text": "Reviewed original license."}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing license text"):
        hook(root, {"licenses": {"destination": "project/licenses/pnpm.json", "previous": "overrides.json"}}).initialize("standard", {})


@pytest.mark.parametrize("text", [b"", b"  \n", b"NOT FOUND", b"\xff"])
def test_collection_rejects_empty_placeholder_or_non_utf8_license(project, text):
    root, dependency, _ = project
    (dependency / "LICENSE").write_bytes(text)
    with pytest.raises(ValueError):
        hook(root, {"licenses": {"destination": "project/licenses/pnpm.json"}}).initialize("standard", {})


def test_collection_rejects_symlink_escape(project):
    root, dependency, _ = project
    (dependency / "LICENSE").unlink()
    (root / "outside").write_text("External private text", encoding="utf-8")
    (dependency / "LICENSE").symlink_to(root / "outside")
    with pytest.raises(ValueError, match="outside"):
        hook(root, {"licenses": {"destination": "project/licenses/pnpm.json"}}).initialize("standard", {})


def test_collection_keeps_multiple_versions_separate(project):
    root, dependency, output = project
    other = dependency.with_name("older")
    other.mkdir()
    (other / "package.json").write_text(json.dumps({"name": "dependency", "version": "0.9.0", "license": "MIT"}), encoding="utf-8")
    (other / "LICENSE").write_text("Older original license", encoding="utf-8")
    output["MIT"][0]["versions"].append("0.9.0")
    output["MIT"][0]["paths"].append(str(other))
    builder = hook(root, {"licenses": {"destination": "project/licenses/pnpm.json"}})
    data = {}
    builder.initialize("standard", data)
    result, _ = bundle(data)
    assert [(item["package_version"], item["files"][0]["text"]) for item in result["libraries"]] == [
        ("0.9.0", "Older original license"),
        ("1.0.0", "Copyright fixture authors\r\nPermission is hereby granted.\r\n"),
    ]
    builder.finalize("standard", data, "unused.whl")


def test_collection_includes_license_directory_and_declared_file(project):
    root, dependency, _ = project
    (dependency / "LICENSE").unlink()
    (dependency / "licenses").mkdir()
    (dependency / "licenses/MIT.txt").write_text("License in directory", encoding="utf-8")
    (dependency / "terms.txt").write_text("Declared license terms", encoding="utf-8")
    (dependency / "package.json").write_text(
        json.dumps({"name": "dependency", "version": "1.0.0", "license": "SEE LICENSE IN terms.txt"}), encoding="utf-8"
    )
    builder = hook(root, {"licenses": {"destination": "project/licenses/pnpm.json"}})
    data = {}
    builder.initialize("standard", data)
    result, _ = bundle(data)
    assert result["libraries"][0]["files"] == [
        {"path": "NOTICE", "text": "Original third-party attribution.\n"},
        {"path": "licenses/MIT.txt", "text": "License in directory"},
        {"path": "terms.txt", "text": "Declared license terms"},
    ]
    builder.finalize("standard", data, "unused.whl")


@pytest.mark.parametrize("malformation", ["paths", "name", "version", "empty", "empty-group"])
def test_collection_rejects_incomplete_or_mismatched_graph(project, malformation):
    root, _, output = project
    if malformation == "paths":
        output["MIT"][0]["paths"] = []
    elif malformation == "empty":
        output.clear()
    elif malformation == "empty-group":
        output["MIT"].clear()
    elif malformation == "name":
        output["MIT"][0]["name"] = "different"
    else:
        output["MIT"][0]["versions"] = ["0.9.0"]
    with pytest.raises(ValueError):
        hook(root, {"licenses": {"destination": "project/licenses/pnpm.json"}}).initialize("standard", {})


def test_failed_javascript_build_does_not_collect(project, monkeypatch):
    root, _, _ = project
    monkeypatch.setattr("hatch_js.structs.system_call", lambda command: 1)
    data = {}
    with pytest.raises(RuntimeError):
        hook(root, {"licenses": {"destination": "project/licenses/pnpm.json"}}).initialize("standard", data)
    assert "force_include" not in data


@pytest.mark.parametrize("output", ["invalid json", "[]", '{"error": {"message": "missing store"}}'])
def test_collection_rejects_malformed_collector_output(project, monkeypatch, output):
    root, _, _ = project
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: subprocess.CompletedProcess(command, 0, output, ""))
    with pytest.raises(ValueError):
        hook(root, {"licenses": {"destination": "project/licenses/pnpm.json"}}).initialize("standard", {})


def test_collector_failure_does_not_register_bundle(project, monkeypatch):
    root, _, _ = project

    def fail(command, **kwargs):
        raise subprocess.CalledProcessError(1, command, stderr="missing pnpm store")

    monkeypatch.setattr(subprocess, "run", fail)
    data = {}
    with pytest.raises(subprocess.CalledProcessError):
        hook(root, {"licenses": {"destination": "project/licenses/pnpm.json"}}).initialize("standard", data)
    assert "force_include" not in data
