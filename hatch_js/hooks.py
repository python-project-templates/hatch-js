from hatchling.plugin import hookimpl

from .plugin import HatchJsBuildHook


@hookimpl
def hatch_register_build_hook() -> type[HatchJsBuildHook]:
    return HatchJsBuildHook
