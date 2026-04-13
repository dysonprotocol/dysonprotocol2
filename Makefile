#!/usr/bin/make -f

VERSION ?= $(shell git symbolic-ref -q --short HEAD || git describe --tags --exact-match)
COMMIT ?= $(shell git rev-parse --short HEAD)
BUILDDIR ?= $(CURDIR)/build
CURRENT_DIR = $(shell pwd)

###############################################################################
###                                Build Tags                               ###
###############################################################################

# Build tags
build_tags = netgo

ifeq ($(LEDGER_ENABLED),true)
  ifeq ($(OS),Windows_NT)
    GCCEXE = $(shell where gcc.exe 2> NUL)
    ifeq ($(GCCEXE),)
      $(error gcc.exe not installed for ledger support, please install or set LEDGER_ENABLED=false)
    else
      build_tags += ledger
    endif
  else
    UNAME_S = $(shell uname -s)
    ifeq ($(UNAME_S),OpenBSD)
      $(warning OpenBSD detected, disabling ledger support (https://github.com/cosmos/cosmos-sdk/issues/1988))
    else
      GCC = $(shell command -v gcc 2> /dev/null)
      ifeq ($(GCC),)
        $(error gcc not installed for ledger support, please install or set LEDGER_ENABLED=false)
      else
        build_tags += ledger
      endif
    endif
  endif
endif

# Handle rocksdb
ifeq ($(ROCKSDB_ENABLED),true)
  CGO_ENABLED=1
  build_tags += rocksdb
endif


build_tags += $(BUILD_TAGS)
build_tags := $(strip $(build_tags))


# look for depinject in BUILD_TAGS or add app_v1
ifeq ($(findstring app_v2,$(BUILD_TAGS)),)
  ifeq ($(findstring app_v1,$(BUILD_TAGS)),)
    build_tags += app_v1
  endif
endif

whitespace :=
whitespace += $(whitespace)
comma := ,
build_tags_comma_sep := $(subst $(whitespace),$(comma),$(build_tags))

# Linker flags
ldflags = -X github.com/cosmos/cosmos-sdk/version.Name=dyson \
		  -X github.com/cosmos/cosmos-sdk/version.AppName=dysond \
		  -X github.com/cosmos/cosmos-sdk/version.Version=$(VERSION) \
		  -X github.com/cosmos/cosmos-sdk/version.Commit=$(COMMIT) \
		  -X "github.com/cosmos/cosmos-sdk/version.BuildTags=$(build_tags_comma_sep)"

ifeq ($(LINK_STATICALLY),true)
	ldflags += -linkmode=external -extldflags "-Wl,-z,muldefs -static"
endif
ldflags := $(strip $(ldflags))

BUILD_FLAGS := -tags "$(build_tags)" -ldflags '$(ldflags)'
# check for nostrip option
ifeq (,$(findstring nostrip,$(COSMOS_BUILD_OPTIONS)))
  BUILD_FLAGS += -trimpath
endif

  

# Check for debug option
ifeq (debug,$(findstring debug,$(COSMOS_BUILD_OPTIONS)))
  BUILD_FLAGS += -gcflags "all=-N -l"
endif

###############################################################################
###                          Development (Python)                           ###
###############################################################################

# Virtual environment for Python dev/test dependencies
VENV ?= $(CURDIR)/.venv
PY := $(VENV)/bin/python
PATH := $(VENV)/bin:$(PATH)


dev-venv:
	@test -d $(VENV) || $$(command -v pyenv >/dev/null 2>&1 && echo "$$(pyenv root)/shims/python" || echo python3) -m venv $(VENV)
	@$(PY) -m pip install -U pip

dev-install: dev-venv
	@$(PY) -m pip install -r requirements.txt

###############################################################################
###                                Building                                 ###
###############################################################################


verify-requirements:
	@echo "Verifying build/install requirements..."
	@bash ./scripts/verify_requirements.sh

build: verify-requirements dysvm-assets
	@echo "Building dysond binary..."
	@mkdir -p $(BUILDDIR)
	@go build -mod=readonly $(BUILD_FLAGS) -o $(BUILDDIR)/dysond ./dysond
	@chmod +x $(BUILDDIR)/dysond || true

install: verify-requirements dysvm-assets
	@echo "Installing dysond binary..."
	@go install -mod=readonly $(BUILD_FLAGS) ./dysond
	@dysond version --long | tail -n 8

###############################################################################
###                                 Linting                                 ###
###############################################################################

# Build tags must match what the binary uses so app.go (//go:build app_v1)
# is included and generated /api/ packages (pulsar) are excluded.
BUILD_TAGS_LINT := netgo app_v1

vet:
	@go vet -tags "$(BUILD_TAGS_LINT)" $$(go list -tags "$(BUILD_TAGS_LINT)" ./... | grep -v '/api/')

mod-tidy-check:
	@go mod tidy
	@git diff --exit-code go.mod go.sum

###############################################################################
###                                Testing                                  ###
###############################################################################

# CLEAN_COVERAGE: Set to non-empty (e.g., CLEAN_COVERAGE=1) to remove existing
# coverage files before running tests. By default, coverage files are cleaned up.
CLEAN_COVERAGE ?= 1

# Coverage: if COVERAGE_PACKAGES is non-empty, coverage is enabled
# Comma-separated list of packages to include in coverage (can be overridden)
COVERAGE_PACKAGES ?= dysonprotocol.com/x/crontask/keeper,dysonprotocol.com/x/nameservice/keeper,dysonprotocol.com/x/nft/keeper,dysonprotocol.com/x/script/keeper,dysonprotocol.com/x/storage/keeper,dysonprotocol.com/x/whaleswap/keeper,dysonprotocol.com/dysond/server/dwapp


test: verify-requirements

	@mkdir -p $(BUILDDIR)
	@if [ -n "$(COVERAGE_PACKAGES)" ]; then \
		echo "--> building dysond with coverage instrumentation"; \
		go build -mod=readonly $(BUILD_FLAGS) -cover -o $(BUILDDIR)/dysond ./dysond; \
	elif [ ! -f "$(BUILDDIR)/dysond" ]; then \
		echo "--> building dysond binary for tests"; \
		go build -mod=readonly $(BUILD_FLAGS) -o $(BUILDDIR)/dysond ./dysond; \
	else \
		echo "✓ using existing $(BUILDDIR)/dysond"; \
	fi
	@chmod +x $(BUILDDIR)/dysond || true

	@echo "--> running pytest"
	@TMP_ROOT=$$(mktemp -d /tmp/dyson-test.XXXXXX); \
	PATH="$(BUILDDIR):$$PATH"; \
	export PATH; \
	echo "Using temporary directory: $$TMP_ROOT"; \
	if [ -n "$(COVERAGE_PACKAGES)" ]; then \
		GOCOVERDIR="$(CURDIR)/coverage"; \
		if [ -n "$(CLEAN_COVERAGE)" ]; then \
			echo "Removing $$GOCOVERDIR"; \
			rm -rf "$$GOCOVERDIR"; \
		fi; \
		echo "Creating $$GOCOVERDIR"; \
		mkdir -p "$$GOCOVERDIR"; \
		export GOCOVERDIR; \
		echo "Go coverage enabled. Writing to $$GOCOVERDIR"; \
	fi; \
	GOCOVERDIR=$$GOCOVERDIR DYSON_BASE_DIR=$$TMP_ROOT/test-dysonchains python -u -m pytest --ff -x --capture=fd --showlocals --durations=0 $(PYTEST_ARGS); \
	TEST_EXIT_CODE=$$?; \
	if [ -n "$(COVERAGE_PACKAGES)" ] && [ -d "$$GOCOVERDIR" ]; then \
		echo "Generating go coverage reports from $$GOCOVERDIR"; \
		PKG_FLAG="-pkg=$(COVERAGE_PACKAGES)"; \
		go tool covdata textfmt -i="$$GOCOVERDIR" $$PKG_FLAG -o=coverage.out; \
		go tool cover -func=coverage.out -o=coverage.txt; \
		go tool cover -html=coverage.out -o=coverage.html; \
		echo "Coverage reports written: coverage.out, coverage.txt, coverage.html"; \
		echo "Generating line-by-line coverage reports..."; \
		python3 scripts/print_coverage.py coverage.out "$$GOCOVERDIR"; \
	fi; \
	echo "Cleaning up temporary directory"; \
	rm -rf $$TMP_ROOT; \
	exit $$TEST_EXIT_CODE; \

clean-coverage:
	@echo "Removing coverage directory..."
	@rm -rf "$(CURDIR)/coverage"
	@rm -f coverage.out coverage.txt coverage.html
	@echo "Coverage files removed."

###############################################################################
###                                Scripts                                  ###
###############################################################################


start: install
	@echo "--> Installing and then Starting dyson"
	dysond start


# The 'watch' target monitors .go files then installs and restarts the application on changes.
watch:
	@echo "Watching for changes in Go files..."
	@while sleep 1; do \
		find . -name '*.go' | entr -r -c -n -d make start; \
	done

init-localnet: 
	@echo "--> Initializing dyson local chain"
	@$(PY) ./scripts/chainnet.py generate --chains 1 --nodes 2 --hermes-config --base-dir $${DYSON_BASE_DIR:-$$HOME/.dysonchains}
	@$(PY) ./scripts/chainnet.py setup --force --config-file $${DYSON_BASE_DIR:-$$HOME/.dysonchains}/chains.json


start-localnet: 
	@echo "--> Starting dyson local net"
	@LOG_MODULE_FLAG=""; \
	if [ -n "$(LOG_MODULE)" ]; then \
		LOG_MODULE_FLAG="--log-module $(LOG_MODULE)"; \
	fi; \
	$(PY) ./scripts/chainnet.py start --block-speed 500ms --logs --no-blocks-timeout 10 $$LOG_MODULE_FLAG --config-file $${DYSON_BASE_DIR:-$$HOME/.dysonchains}/chains.json

###############################################################################
###                               Dashboard                                 ###
###############################################################################

dashboard:
	@echo "--> Building dashboard (client/docs/dysonprotocol2-dashboard)"
	npx npm --prefix=./client/docs/dysonprotocol2-dashboard run build

###############################################################################
###                                Protobuf                                 ###
###############################################################################
DOCKER := $(shell which docker)

protoVer=0.16.0
protoImageName=ghcr.io/cosmos/proto-builder:$(protoVer)
protoImage=$(DOCKER) run --rm -v $(CURDIR):/workspace --workdir /workspace $(protoImageName)

# Custom protobuf image with jsonschema support
customProtoImageName=dyson-proto-builder:$(protoVer)
customProtoImage=$(DOCKER) run --rm -v $(CURDIR):/workspace --workdir /workspace $(customProtoImageName)

proto-all: proto-format proto-lint proto-gen

# Build custom protobuf Docker image with jsonschema support
proto-build-image:
	@echo "Building custom protobuf Docker image with jsonschema support"
	@$(DOCKER) build -t $(customProtoImageName) -f Dockerfile.protobuf .

proto-gen: proto-build-image
	@echo "Generating Protobuf files"
	@$(customProtoImage) sh ./scripts/protocgen.sh

proto-update:
	@echo "Updating dependencies in ./proto"
	@$(protoImage) sh -c "buf dep update ./proto"

# Remove custom protobuf Docker image
proto-clean-image:
	@echo "Removing custom protobuf Docker image"
	@$(DOCKER) rmi $(customProtoImageName) 2>/dev/null || true

###############################################################################
###                                DYSVM                                    ###
###############################################################################

# DYSVM related paths
DYSVM_SCRIPTS_DIR := $(CURRENT_DIR)/scripts

# Main DYSVM target - runs patch, build, and embed in sequence
dysvm: dev-install
	@echo "Running complete DYSVM process..."
	@$(DYSVM_SCRIPTS_DIR)/dysvm.sh

# Ensure DYSVM embedded assets exist.
# In CI the assets are baked into the image at /opt/dysvm-data/ and copied here.
# Locally, prompts to run 'make dysvm' if missing.
dysvm-assets:
	@echo "Checking for DYSVM embedded assets..."
	@if [ -d ./dysvm/internal/data ] && ls -A ./dysvm/internal/data >/dev/null 2>&1; then \
	  echo "✓ DYSVM assets present"; \
	elif [ -d /opt/dysvm-data ] && ls -A /opt/dysvm-data >/dev/null 2>&1; then \
	  echo "Copying pre-built DYSVM assets from image..."; \
	  mkdir -p ./dysvm/internal/data; \
	  cp -r /opt/dysvm-data/. ./dysvm/internal/data/; \
	  echo "✓ DYSVM assets ready"; \
	else \
	  echo "⚠️  DYSVM assets missing (./dysvm/internal/data)."; \
	  if [ -t 0 ]; then \
	    printf "Run 'make dysvm' now? [y/N]: "; \
	    read ans; \
	    case "$$ans" in \
	      y|Y|yes|YES) $(MAKE) dysvm ;; \
	      *) echo "Declined. Please run 'make dysvm' first."; exit 1 ;; \
	    esac; \
	  else \
	    echo "Non-interactive shell. Run 'make dysvm' manually or rebuild the CI image."; exit 1; \
	  fi; \
	fi

# Apply patch to CPython submodule
dysvm-patch:
	@echo "Running DYSVM patch operation..."
	@$(DYSVM_SCRIPTS_DIR)/dysvm-patch.sh

# Build custom Python distributions
dysvm-build:
	@echo "Running DYSVM build operation..."
	@$(DYSVM_SCRIPTS_DIR)/dysvm-build.sh

# Prepare Python for go-embed-python
dysvm-embed:
	@echo "Running DYSVM embed operation..."
	@$(DYSVM_SCRIPTS_DIR)/dysvm-embed.sh

# Clean DYSVM build artifacts
dysvm-clean:
	@echo "Running DYSVM clean operation..."
	@$(DYSVM_SCRIPTS_DIR)/dysvm-clean.sh


.PHONY: build install test clean-coverage vet mod-tidy-check init localnet start watch dashboard proto-all proto-gen proto-format proto-lint proto-update proto-build-image proto-clean-image dysvm dysvm-patch dysvm-build dysvm-embed dysvm-clean verify-requirements dysvm-assets
