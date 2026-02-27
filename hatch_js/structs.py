from __future__ import annotations

from os import chdir, curdir, system as system_call
from pathlib import Path
from shutil import which
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

__all__ = (
    "HatchJsBuildConfig",
    "HatchJsBuildPlan",
)

Toolchain = Literal["npm", "yarn", "pnpm", "jlpm"]


class HatchJsBuildConfig(BaseModel):
    """Build config values for Hatch Js Builder."""

    name: Optional[str] = Field(default=None)
    verbose: Optional[bool] = Field(default=False)

    path: Optional[Path] = Field(default=None, description="Path to the JavaScript project. Defaults to the current directory.")
    tool: Optional[Toolchain] = Field(default="npm", description="Command to run for building the project, e.g., 'npm', 'yarn', 'pnpm'")

    install_cmd: Optional[str] = Field(
        default=None, description="Custom command to run for installing dependencies. If specified, overrides the default install command."
    )
    build_cmd: Optional[str] = Field(
        default="build", description="Custom command to run for building the project. If specified, overrides the default build command."
    )

    targets: Optional[List[str]] = Field(default_factory=list, description="List of ensured targets to build")

    # Check that tool exists
    @field_validator("tool", mode="before")
    @classmethod
    def _check_tool_exists(cls, tool: Toolchain) -> Toolchain:
        if not which(tool):
            raise ValueError(f"Tool '{tool}' not found in PATH. Please install it or specify a different tool.")
        return tool

    # Validate path
    @field_validator("path", mode="before")
    @classmethod
    def validate_path(cls, path: Optional[Path]) -> Path:
        if path is None:
            return Path.cwd()
        if not isinstance(path, Path):
            path = Path(path)
        if not path.is_dir():
            raise ValueError(f"Path '{path}' is not a valid directory.")
        return path


class HatchJsBuildPlan(HatchJsBuildConfig):
    commands: List[str] = Field(default_factory=list)

    def generate(self):
        self.commands = []

        # Run installation
        if self.tool in ("npm", "pnpm"):
            if self.install_cmd:
                self.commands.append(f"{self.tool} {self.install_cmd}")
            else:
                self.commands.append(f"{self.tool} install")
        elif self.tool in ("yarn", "jlpm"):
            if self.install_cmd:
                self.commands.append(f"{self.tool} {self.install_cmd}")
            else:
                self.commands.append(f"{self.tool}")

        # Run build command
        if self.tool in ("npm", "pnpm"):
            self.commands.append(f"{self.tool} run {self.build_cmd}")
        elif self.tool in ("yarn", "jlpm"):
            self.commands.append(f"{self.tool} {self.build_cmd}")

        return self.commands

    def execute(self):
        """Execute the build commands."""

        # First navigate to the project path
        cwd = Path(curdir).resolve()
        chdir(self.path)

        for command in self.commands:
            ret = system_call(command)
            if ret != 0:
                raise RuntimeError(f"hatch-js build command failed with exit code {ret}: {command}")

        # Check that all targets exist
        # Go back to original path
        chdir(str(cwd))
        for target in self.targets:
            if not Path(target).resolve().exists():
                raise FileNotFoundError(f"Target '{target}' does not exist after build. Please check your build configuration.")
        return self.commands

    def cleanup(self):
        # No-op
        ...
