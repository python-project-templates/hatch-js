from __future__ import annotations

from logging import getLogger
from os import getenv
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

from .structs import HatchJsBuildConfig, HatchJsBuildPlan
from .utils import import_string

__all__ = ("HatchJsBuildHook",)


class HatchJsBuildHook(BuildHookInterface[HatchJsBuildConfig]):
    """The hatch-js build hook."""

    PLUGIN_NAME = "hatch-js"
    _logger = getLogger(__name__)

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

        # Perform any cleanup actions
        build_plan.cleanup()
