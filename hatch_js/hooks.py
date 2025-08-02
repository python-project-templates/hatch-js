from typing import Type

from hatchling.plugin import hookimpl

from .plugin import HatchJsBuildHook


@hookimpl
def hatch_register_build_hook() -> Type[HatchJsBuildHook]:
    return HatchJsBuildHook
