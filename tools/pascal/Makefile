# SPDX-License-Identifier: LicenseRef-Volnist
#
# Build both native WSM tools with Free Pascal. FPC and its FCL units are
# build-time inputs only; installed binaries do not invoke Python.

FPC ?= fpc
PREFIX ?= /usr/local
SOURCE_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ROOT_DIR := $(abspath $(SOURCE_DIR)/../..)
BUILD_DIR ?= $(ROOT_DIR)/build/pascal
FPCFLAGS ?= -B -O2 -Mobjfpc -Sh -Fu"$(SOURCE_DIR)" -FU"$(BUILD_DIR)" -FE"$(BUILD_DIR)"

HW_TARGET := $(BUILD_DIR)/wsm-hwcheck
CLASSIFY_TARGET := $(BUILD_DIR)/wsm-classify
TARGETS := $(HW_TARGET) $(CLASSIFY_TARGET)

.PHONY: all build build-hwcheck build-classify test test-hwcheck test-classify install install-hwcheck install-classify clean

all: build

build: build-hwcheck build-classify

build-hwcheck: $(HW_TARGET)

build-classify: $(CLASSIFY_TARGET)

$(HW_TARGET): $(SOURCE_DIR)/wsm_hwcheck.pas $(SOURCE_DIR)/wsm_hwcheck_core.pas
	mkdir -p "$(BUILD_DIR)"
	$(FPC) $(FPCFLAGS) -o"$@" "$(SOURCE_DIR)/wsm_hwcheck.pas"

$(CLASSIFY_TARGET): $(SOURCE_DIR)/wsm_classify.pas
	mkdir -p "$(BUILD_DIR)"
	$(FPC) $(FPCFLAGS) -o"$@" "$(SOURCE_DIR)/wsm_classify.pas"

test: test-hwcheck test-classify

test-hwcheck: build-hwcheck
	"$(HW_TARGET)" --version | grep -Fx "wsm-hwcheck 0.1.0"
	"$(HW_TARGET)" --help >/dev/null

test-classify: build-classify
	"$(CLASSIFY_TARGET)" --version | grep -Fx "wsm-classify 0.1.0"
	"$(CLASSIFY_TARGET)" --help >/dev/null

install: install-hwcheck install-classify

install-hwcheck: build-hwcheck
	mkdir -p "$(PREFIX)/bin"
	install -m 0755 "$(HW_TARGET)" "$(PREFIX)/bin/wsm-hwcheck"

install-classify: build-classify
	mkdir -p "$(PREFIX)/bin"
	install -m 0755 "$(CLASSIFY_TARGET)" "$(PREFIX)/bin/wsm-classify"

clean:
	rm -rf "$(BUILD_DIR)"
