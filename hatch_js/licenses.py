from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

_LICENSE = re.compile(r"^(?:licen[cs]es?|copying)(?:[._-].*)?$", re.IGNORECASE)
_NOTICE = re.compile(r"^(?:copyright|notices?|authors?|third[-_]?party[-_]?(?:notices?|licenses?))(?:[._-].*)?$", re.IGNORECASE)


def relative_path(value: str) -> str:
    parts = value.split("/")
    if not value or ":" in value or "\\" in value or any(part in ("", ".", "..") or part.endswith((".dist-info", ".data")) for part in parts):
        raise ValueError("License destination/file path must be a relative path without traversal or reserved wheel directories.")
    return value


class PnpmLicenseConfig(BaseModel):
    """Opt-in collection of original license texts from pnpm dependencies."""

    model_config = ConfigDict(populate_by_name=True)

    destination: str = Field(description="Package-relative path of the license JSON in the wheel.")
    production_only: bool = Field(default=False, alias="production-only")
    previous: Path | None = Field(default=None, description="Reviewed bundle used to fill missing license texts, relative to the project root.")

    @field_validator("destination")
    @classmethod
    def validate_destination(cls, value: str) -> str:
        relative_path(value)
        if len(PurePosixPath(value).parts) < 2:
            raise ValueError("License destination must be inside a package directory.")
        return value


class LicenseFile(BaseModel):
    path: str
    text: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return relative_path(value)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value.strip() or value.strip().casefold() in ("not found", "unknown"):
            raise ValueError("Dependency is missing license text; supply original text in a reviewed licenses.previous bundle.")
        return value


class LibraryLicense(BaseModel):
    package_name: str = Field(min_length=1)
    package_version: str = Field(min_length=1)
    license: str = Field(min_length=1)
    files: list[LicenseFile] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_paths(self) -> LibraryLicense:
        if len({file.path for file in self.files}) != len(self.files):
            raise ValueError("Duplicate license file paths in reviewed bundle.")
        return self


class PnpmPackage(BaseModel):
    name: str = Field(min_length=1)
    versions: list[str] = Field(min_length=1)
    paths: list[Path] = Field(min_length=1)

    @model_validator(mode="after")
    def matching_paths(self) -> PnpmPackage:
        if len(self.versions) != len(self.paths):
            raise ValueError("pnpm license package versions and paths do not match.")
        return self


def _read_file(directory: Path, file: Path) -> LicenseFile:
    if not file.resolve().is_relative_to(directory.resolve()):
        raise ValueError(f"License file '{file.name}' points outside its dependency package.")
    if not file.is_file():
        raise ValueError(f"Dependency is missing license text in '{file.name}'.")
    return LicenseFile(path=file.relative_to(directory).as_posix(), text=file.read_bytes().decode("utf-8"))


def _read_files(directory: Path, manifest: dict) -> tuple[dict[str, LicenseFile], bool]:
    candidates: set[Path] = set()
    primary: set[Path] = set()
    for entry in directory.iterdir():
        if entry.is_dir() and entry.name.casefold() in ("license", "licenses", "licence", "licences"):
            for file in entry.rglob("*"):
                if file.is_file():
                    candidates.add(file)
                    if not _NOTICE.fullmatch(file.name):
                        primary.add(file)
        elif _LICENSE.fullmatch(entry.name) or _NOTICE.fullmatch(entry.name):
            candidates.add(entry)
            if _LICENSE.fullmatch(entry.name):
                primary.add(entry)
    expression = manifest.get("license", "")
    if isinstance(expression, str) and expression.upper().startswith("SEE LICENSE IN "):
        declared = directory / relative_path(expression[len("SEE LICENSE IN ") :].strip())
        if declared.exists() or declared.is_symlink():
            candidates.add(declared)
            primary.add(declared)
    files = {}
    for file in sorted(candidates):
        record = _read_file(directory, file)
        files[record.path] = record
    return files, bool(primary)


def collect_licenses(directory: Path, config: PnpmLicenseConfig, root: Path) -> dict:
    """Collect the pnpm graph and retain original file contents without absolute paths."""
    manifest = json.loads((directory / "package.json").read_bytes())
    previous = {}
    if config.previous is not None:
        reviewed = json.loads((root / config.previous).read_bytes())
        if not isinstance(reviewed, dict) or not isinstance(reviewed.get("libraries"), list):
            raise ValueError("Reviewed license bundle must contain a libraries list.")
        for library in TypeAdapter(list[LibraryLicense]).validate_python(reviewed["libraries"]):
            key = (library.package_name, library.package_version, library.license)
            if key in previous:
                raise ValueError("Duplicate dependency in reviewed license bundle.")
            previous[key] = library
    command = ["pnpm", "licenses", "list", "--json"]
    if config.production_only:
        command.append("--prod")
    result = subprocess.run(command, cwd=directory, check=True, capture_output=True, text=True)
    output = {} if result.stdout.strip() == "No licenses in packages found" else json.loads(result.stdout)
    groups = TypeAdapter(dict[str, list[PnpmPackage]]).validate_python(output)
    dependency_fields = ["dependencies", "optionalDependencies"]
    if not config.production_only:
        dependency_fields.append("devDependencies")
    if not any(groups.values()) and any(manifest.get(field) for field in dependency_fields):
        raise ValueError("pnpm returned an empty license graph for a project with dependencies.")
    libraries = {}
    for expression, packages in groups.items():
        for package in packages:
            for version, path in zip(package.versions, package.paths, strict=True):
                package_manifest = json.loads((path / "package.json").read_bytes())
                if package_manifest.get("name") != package.name or package_manifest.get("version") != version:
                    raise ValueError(f"pnpm package identity does not match its manifest: {package.name}@{version}.")
                files, has_license = _read_files(path, package_manifest)
                key = (package.name, version, expression)
                if not has_license:
                    override = previous.get(key)
                    if override is None or not any(not _NOTICE.fullmatch(PurePosixPath(file.path).name) for file in override.files):
                        raise ValueError(
                            f"Dependency '{package.name}@{version}' is missing license text. Supply a reviewed licenses.previous bundle."
                        )
                    for file in override.files:
                        original = path / file.path
                        if original.exists() or original.is_symlink():
                            files[file.path] = _read_file(path, original)
                        if file.path in files and files[file.path] != file:
                            raise ValueError(f"Reviewed license text conflicts with original '{file.path}' for '{package.name}@{version}'.")
                        files[file.path] = file
                library = LibraryLicense(
                    package_name=package.name, package_version=version, license=expression, files=[files[name] for name in sorted(files)]
                )
                if key in libraries and libraries[key] != library:
                    raise ValueError(f"Conflicting installed copies of dependency '{package.name}@{version}'.")
                libraries[key] = library
    return {"root_name": manifest["name"], "libraries": [libraries[key].model_dump() for key in sorted(libraries)]}
