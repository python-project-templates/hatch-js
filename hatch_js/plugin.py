from __future__ import annotations

import json
from logging import getLogger
from os import getenv
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from hatchling.builders.utils import normalize_inclusion_map

from .licenses import collect_licenses
from .structs import HatchJsBuildConfig, HatchJsBuildPlan
from .utils import import_string

__all__ = ("HatchJsBuildHook",)


class HatchJsBuildHook(BuildHookInterface):
    """The hatch-js build hook."""

    PLUGIN_NAME = "hatch-js"
    _logger = getLogger(__name__)
    _license_directory: TemporaryDirectory[str] | None = None

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        """Initialize the plugin."""
        # Log some basic information
        project_name = self.metadata.config["project"]["name"]
        self._logger.info("Initializing hatch-js plugin version %s", version)
        self._logger.info(f"Running hatch-js: {project_name}")

        # Only run if creating wheel
        # TODO: Add support for specify sdist-plan
        if self.target_name != "wheel":
            self._logger.info("ignoring target name %s", self.target_name)
            return

        # Skip if SKIP_HATCH_JS is set
        # TODO: Support CLI once https://github.com/pypa/hatch/pull/1743
        if getenv("SKIP_HATCH_JS"):
            self._logger.info("Skipping the build hook since SKIP_HATCH_JS was set")
            return

        # Get build config class or use default
        build_config_class = import_string(self.config["build-config-class"]) if "build-config-class" in self.config else HatchJsBuildConfig

        # Instantiate build config
        config = build_config_class(name=project_name, **self.config)

        if config.licenses is not None:
            self._validate_license_destination(config.licenses.destination, build_data)

        # Get build plan class or use default
        build_plan_class = import_string(self.config["build-plan-class"]) if "build-plan-class" in self.config else HatchJsBuildPlan

        # Instantiate builder
        build_plan = build_plan_class(**config.model_dump())

        # Generate commands
        build_plan.generate()

        # Log commands if in verbose mode
        if config.verbose:
            for command in build_plan.commands:
                self._logger.warning(command)

        # Execute build plan
        build_plan.execute()

        if config.licenses is not None:
            self._validate_license_destination(config.licenses.destination, build_data)
            self._cleanup_licenses()
            directory = TemporaryDirectory(prefix="hatch-js-licenses-")
            try:
                project = Path(self.root) / (config.path or Path(self.root))
                bundle = collect_licenses(project.resolve(), config.licenses, Path(self.root))
                output = Path(directory.name) / "pnpm.json"
                output.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                build_data.setdefault("force_include", {})[str(output)] = config.licenses.destination
                if version == "editable":
                    if not build_data.get("force_include_editable"):
                        normal = build_data["force_include"]
                        combined = self.build_config.get_force_include() if self.build_config is not None else {}
                        combined.update(normalize_inclusion_map(normal, self.root))
                        normal.clear()
                        normal.update(combined)
                        build_data["force_include_editable"] = normal
                    build_data["force_include_editable"][str(output)] = config.licenses.destination
            except BaseException:
                directory.cleanup()
                raise
            self._license_directory = directory

        # Perform any cleanup actions
        build_plan.cleanup()

    def _validate_license_destination(self, value: str, build_data: dict[str, Any]) -> None:
        destination = PurePosixPath(value)
        paths = {Path(self.root) / value}
        inclusions = list(build_data.get("force_include", {}).values())
        inclusions.extend(build_data.get("force_include_editable", {}).values())
        if self.build_config is not None:
            raw = str(Path(value))
            mapped = self.build_config.get_distribution_path(raw)
            if Path(mapped).as_posix() != value:
                raise ValueError("License destination is rewritten by Hatch sources; choose an unmapped wheel-relative destination.")
            inclusions.extend(self.build_config.get_force_include().values())
            for source, replacement in self.build_config.sources.items():
                if raw.startswith(replacement):
                    paths.add(Path(self.root) / (source + raw[len(replacement) :]))
        for existing in paths:
            if existing.exists() or existing.is_symlink() or any(parent.is_file() for parent in existing.parents):
                raise ValueError(f"License destination collision: '{destination}' already exists in the project.")
        for included in inclusions:
            mapped = self.build_config.get_distribution_path(str(Path(included))) if self.build_config is not None else included
            other = PurePosixPath(Path(mapped).as_posix())
            if destination == other or destination in other.parents or other in destination.parents:
                raise ValueError(f"License destination collision with force_include: '{included}'.")

    def _cleanup_licenses(self) -> None:
        if self._license_directory is not None:
            self._license_directory.cleanup()
            self._license_directory = None

    def finalize(self, version: str, build_data: dict[str, Any], artifact_path: str) -> None:
        self._cleanup_licenses()

    def clean(self, versions: list[str]) -> None:
        self._cleanup_licenses()
