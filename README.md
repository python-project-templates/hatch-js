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

> [!NOTE]
> This library was generated using [copier](https://copier.readthedocs.io/en/stable/) from the [Base Python Project Template repository](https://github.com/python-project-templates/base).
