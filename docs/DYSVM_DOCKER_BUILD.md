# DYSVM Docker Build: Problem Analysis & Status

## Goal

Run `make dysvm` inside the Docker container (via `docker-compose`) to produce
a Linux `dysond` binary without needing Docker-in-Docker.

## What works

- `docker compose build` succeeds (Dockerfile.dev builds a container with
  pyenv Python 3.12.11, goenv Go 1.24.6, nodeenv Node 22.12.0, plus
  build-essential, gcc, etc.)
- `docker compose run --rm build` enters the container and runs
  `make dysvm dashboard build`
- `docker compose run --rm test` runs `make test` inside the container
- `docker compose run --rm shell "bash"` opens an interactive shell

## Fixes already applied

### 1. VENV path collision (Makefile + docker-compose.yml)

**Problem:** The Makefile hardcoded `VENV := $(CURDIR)/.venv`. The host's macOS
`.venv` directory gets mounted into the container at `/workspace/.venv` (via
`volumes: .:/workspace`), containing macOS-native binaries that can't run on
Linux. Result: `/workspace/.venv/bin/python: No module named pip`.

**Fix:** Changed `VENV := ...` to `VENV ?= ...` in the Makefile, and set
`VENV=/tmp/venv` in docker-compose.yml environment. The container creates a
fresh Linux venv at `/tmp/venv`.

### 2. docker-compose command quoting (docker-compose.yml)

**Problem:** With `entrypoint: ["/bin/bash", "-c"]` and
`command: make dysvm dashboard build`, Docker produces:

    /bin/bash -c make dysvm dashboard build

`bash -c` treats only the first word (`make`) as the command string. The rest
(`dysvm`, `dashboard`, `build`) become positional parameters $0, $1, $2 and are
ignored. So it ran `make` with no targets (defaulting to `dev-venv`), installed
pip, and exited.

**Fix:** Changed to `command: ["make dysvm dashboard build"]` so the entire
string is passed as a single argument to `bash -c`.

### 3. Makefile dependency not guarded (dysvm/pbs-patch)

**Problem:** In `cpython-unix/Makefile` line 82, the binutils target
unconditionally depends on a Docker image tar file. When `PYBUILD_NO_DOCKER`
is set, the rule to BUILD that tar is guarded (lines 77-80), but the DEPENDENCY
is not. Make fails with "No rule to make target 'image-gcc.debian9...tar'".

```makefile
# Line 69: PYTHON_DEP_DEPENDS correctly excludes docker image
PYTHON_DEP_DEPENDS := \
    $(if $(PYBUILD_NO_DOCKER),,$(OUTDIR)/image-$(DOCKER_IMAGE_BUILD).$(HOST_PLATFORM).tar) \

# Lines 77-80: Build rule correctly excluded
ifndef PYBUILD_NO_DOCKER
$(OUTDIR)/image-%.$(HOST_PLATFORM).tar: $(OUTDIR)/%.Dockerfile
    $(RUN_BUILD) --toolchain image-$*
endif

# Line 82: BUG -- binutils UNCONDITIONALLY depends on docker image tar
$(OUTDIR)/binutils-...: $(OUTDIR)/image-$(DOCKER_IMAGE_GCC).$(HOST_PLATFORM).tar ...
```

**Fix:** Build-time patch (`dysvm/pbs-patch`) wraps the dependency with
`$(if $(PYBUILD_NO_DOCKER),,...)`, same pattern as line 69. Applied by
`dysvm-patch.sh` before each build.

This bug exists upstream on the main branch as of 2026-03-17.

### 4. Build scripts hardcode Docker container paths (dysvm/pbs-patch)

**Problem:** Shell scripts assume they're running inside a Docker container:

- `build-binutils.sh` line 8: `cd /build` (absolute path only exists in
  containers)
- `build-binutils.sh` line 30: `DESTDIR=/build/out` (same)
- `build-musl.sh` lines 8, 106: same pattern

`TempdirContext` copies files to a random temp dir (e.g. `/tmp/tmpXXXXXX`) and
sets `cwd` to it, but the scripts ignore cwd and `cd` to `/build` which doesn't
exist.

**Fix:** Build-time patch (`dysvm/pbs-patch`) modifies `pythonbuild/buildenv.py`:

- `build_environment()` uses fixed `/build` directory instead of
  `tempfile.TemporaryDirectory()`, cleaning it between build steps
- `TempdirContext.tools_path` set to `/tools` (matching shell scripts'
  `--prefix=/tools/host`) when using `/build`
- `install_toolchain_archive` and `install_artifact_archive` extract to
  `self.tools_path` instead of `self.td / "tools"`

### 5. Container paths pre-created (Dockerfile.dev)

**Fix:** Added `RUN mkdir -p /build /tools` to Dockerfile.dev so the paths
exist when the build starts.

### 6. Dirty submodule tolerance (verify_requirements.sh)

**Problem:** After `dysvm-patch.sh` modifies submodules, `verify_requirements.sh`
detects dirty submodules and fails in non-interactive mode (Docker).

**Fix:** Split the check into commit-mismatch vs dirty-only. Dirty submodules
(expected after patching) warn but don't block. Only commit mismatches (`+`)
and merge conflicts (`U`) require resolution.

### 7. Non-interactive prompts (docker-compose.yml)

**Fix:** Set `YES=1` in docker-compose.yml environment to auto-approve prompts
like the `dysvm-assets` consent check in the Makefile.

## Options considered (for Bug 1 & 2)

| Option | Description | Status |
|--------|-------------|--------|
| Docker-in-Docker (socket mount) | Mount `/var/run/docker.sock` into container | Rejected -- not secure, gives container full host Docker access |
| PYBUILD_NO_DOCKER + stub files | Touch empty docker image tars to satisfy make | Rejected -- only fixes Bug 1, not Bug 2 (`cd /build`) |
| Fork the submodule | Fix both bugs in a fork | Rejected -- maintenance burden of keeping fork in sync |
| **Build-time patches** | Patch submodule at build time via `dysvm-patch.sh` | **Implemented** -- same pattern as existing cpython patches |

## How the DYSVM build works

1. `make dysvm` -> `scripts/dysvm.sh` -> `dysvm-patch.sh`, `dysvm-build.sh`,
   `dysvm-embed.sh`
2. `dysvm-patch.sh` resets and patches both `cpython` and
   `python-build-standalone` submodules
3. `dysvm-build.sh` on Linux calls `build-linux.py` in the
   `dysvm/python-build-standalone` submodule
4. `build-linux.py` bootstraps a venv, then calls `build-main.py`
5. `build-main.py` runs `make` in `cpython-unix/` which orchestrates the entire
   CPython build
6. `cpython-unix/build.py` is the build orchestrator -- with `PYBUILD_NO_DOCKER=1`,
   it uses `TempdirContext` (patched to use `/build` and `/tools`) instead of
   spawning nested Docker containers

## Key code paths

### TempdirContext vs ContainerContext (pythonbuild/buildenv.py)

| | ContainerContext (Docker) | TempdirContext (patched, no Docker) |
|---|---|---|
| Files copied to | `/build` | `/build` |
| Tools installed to | `/tools` | `/tools` |
| Scripts run with cwd | `/` (container root) | `/build` |
| Output collected from | `/build/out/tools` | `/build/out/tools` |

After patching, both contexts use identical paths and all shell scripts work
unmodified.

### get_image() (pythonbuild/docker.py line 71-75)

When `client=None` (no Docker), `get_image()` returns `None`. The Python
orchestration code already handles this -- it passes `None` to
`build_environment()` which uses `TempdirContext`. The Docker image tars are
never loaded. The Makefile just needs to not require them as dependencies.

## Files involved

| File | Role |
|------|------|
| `Makefile` | Top-level, defines `dysvm` target, `VENV` variable |
| `docker-compose.yml` | Defines `build`, `test`, and `shell` services |
| `Dockerfile.dev` | Dev container with pyenv/goenv/nodeenv, `/build`, `/tools` |
| `scripts/dysvm.sh` | Orchestrates patch -> build -> embed |
| `scripts/dysvm-patch.sh` | Patches cpython and python-build-standalone |
| `scripts/dysvm-build.sh` | Calls build-linux.py or build-macos.py |
| `scripts/verify_requirements.sh` | Pre-flight checks (tolerates dirty submodules) |
| `dysvm/patch` | CPython determinism patch |
| `dysvm/pbs-patch` | python-build-standalone no-Docker-on-Linux patch |
| `dysvm/python-build-standalone/` | Submodule (astral-sh/python-build-standalone @ 20250918) |
| `dysvm/python-build-standalone/cpython-unix/Makefile` | Inner Makefile (patched) |
| `dysvm/python-build-standalone/pythonbuild/buildenv.py` | TempdirContext (patched) |
| `dysvm/python-build-standalone/cpython-unix/build-binutils.sh` | Hardcodes `cd /build` |
