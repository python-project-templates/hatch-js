# hatch js

Hatch plugin for JavaScript builds

[![Build Status](https://github.com/python-project-templates/hatch-js/actions/workflows/build.yaml/badge.svg?branch=main&event=push)](https://github.com/python-project-templates/hatch-js/actions/workflows/build.yaml)
[![codecov](https://codecov.io/gh/python-project-templates/hatch-js/branch/main/graph/badge.svg)](https://codecov.io/gh/python-project-templates/hatch-js)
[![License](https://img.shields.io/github/license/python-project-templates/hatch-js)](https://github.com/python-project-templates/hatch-js)
[![PyPI](https://img.shields.io/pypi/v/hatch-js.svg)](https://pypi.python.org/pypi/hatch-js)

## Overview

A simple, extensible JS build plugin for [hatch](https://hatch.pypa.io/latest/).

```toml
[tool.hatch.build.hooks.hatch-js]
path = "js"
install_cmd = "install"
build_cmd = "build"
tool = "pnpm"
targets = ["myproject/extension/cdn/index.js"]
```

See the [test cases](./hatch_js/tests/) for more concrete examples.

`hatch-js` is driven by [pydantic](https://docs.pydantic.dev/latest/) models for configuration and execution of the build.
These models can themselves be overridden by setting `build-config-class` / `build-plan-class`.

## Configuration

```toml
verbose = "false"

path = "path/to/js/root"
tool = "npm" # or pnpm, yarn, jlpm

install_cmd = "" # install command, defaults to `npm install`/`pnpm install`/`yarn`/`jlpm`
build_cmd = "build" # build command, defaults to `npm run build`/`pnpm run build`/`yarn build`/`jlpm build`
targets = [  # outputs to validate after build
    "some/output.js"
]
```

## Dependency licenses

License collection is opt-in and currently supports `tool = "pnpm"`. Install pnpm before building; CI tests use pnpm 10.28.2 with Node 22. No separate license collector or Python dependency is needed.

```toml
[tool.hatch.build.hooks.hatch-js]
path = "js"
tool = "pnpm"

[tool.hatch.build.hooks.hatch-js.licenses]
destination = "myproject/licenses/pnpm.json"
production-only = false
# previous = "js/license-overrides.json"
```

After a successful JavaScript build, hatch-js runs `pnpm licenses list --json` and reads original license and notice files from the listed package paths. The destination must be inside a package directory, without absolute paths, traversal, or collisions with project files and other force-included outputs.

Destinations are wheel-relative. If Hatchling's `sources` configuration would rewrite the destination, collection fails rather than placing the bundle at a different path. Choose a destination that is not itself a mapped source prefix. Existing files in source layouts such as `src/myproject` are also checked for collisions.

The JSON contains `root_name` and a `libraries` list. Each library records `package_name`, `package_version`, the collector's `license` expression, and a `files` list of package-relative `path` and original `text`. Different versions remain separate. No machine-specific absolute paths are packaged.

Collection includes root LICENSE, LICENCE, COPYING, COPYRIGHT, NOTICE, AUTHORS, and third-party notice files, including common suffixes, plus files under license/licence directories and files referenced by `SEE LICENSE IN ...`. UTF-8 contents are retained without changing copyright notices or line endings. A notice or author list alone does not satisfy the requirement for a license text. README files are included only when explicitly referenced by the package's license field; hatch-js does not substitute generic SPDX license templates.

The bundle is force-included in standard and editable wheels, even if an ignore rule would exclude it. Temporary collection files are removed after packaging; no bundle is written into the source package. An editable import points at the source tree, so inspect the installed wheel files rather than expecting the generated bundle under that source package. Source distributions do not run JavaScript installation or license collection. Keep the JS project, lockfile, and any override inputs in the sdist so a wheel built from it can collect licenses.

### Missing texts

A missing, empty, placeholder, or non-UTF-8 license file fails the build. When a dependency's license is stored in an unrecognized location, supply a reviewed JSON bundle through `previous`. The path is relative to the Python project root, not the JS directory.

The override format is the same `libraries` structure as generated output; `root_name` is optional for overrides:

```json
{
    "libraries": [
        {
            "package_name": "dependency",
            "package_version": "1.0.0",
            "license": "MIT",
            "files": [
                {"path": "LICENSE", "text": "Original text reviewed for this exact package version."}
            ]
        }
    ]
}
```

Replace the example text with the dependency's complete original license and required notices. Overrides match exact package name, version, and collected license expression. They fill absent license files, including missing `SEE LICENSE IN ...` targets, retain discovered notices, and cannot replace a conflicting original file. Files named only NOTICE, AUTHORS, COPYRIGHT, or third-party notices do not satisfy the license requirement in an override. Existing unrecognized files referenced by an override must match the original text. Empty or invalid files already present in the package still fail. Dependency updates may require new reviewed overrides.

### Scope

By default, the pnpm listing includes development and optional dependencies as well as runtime dependencies. Bundlers can embed code from dev dependencies, so `production-only = true` is appropriate only when those packages are not shipped. That option passes `--prod` to pnpm; it does not change dependency installation or the JS build.

This is a conservative dependency-graph inventory, not a bundler input trace. It can include build tools, unrelated workspace dependencies, and packages not present in the final output. Workspace and platform selection follow the installed pnpm version; linked workspace packages and dependencies outside the listing need separate review. pnpm must have a lockfile and its installed package/store data available. Python dependencies, separately vendored assets, and native-library notices are outside this collector's scope.

`SKIP_HATCH_JS` also skips license collection. Existing npm, yarn, and jlpm builds are unchanged; enabling `licenses` with those tools fails explicitly. Collected metadata and texts do not establish license compatibility or certify compliance. Review the shipped dependency set and required notices before release.

> [!NOTE]
> This library was generated using [copier](https://copier.readthedocs.io/en/stable/) from the [Base Python Project Template repository](https://github.com/python-project-templates/base).
