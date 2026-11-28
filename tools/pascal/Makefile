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

.PHONY: all build test install clean

all: build

build: $(TARGETS)

$(HW_TARGET): $(SOURCE_DIR)/wsm_hwcheck.pas $(SOURCE_DIR)/wsm_hwcheck_core.pas
	mkdir -p "$(BUILD_DIR)"
	$(FPC) $(FPCFLAGS) -o"$@" "$(SOURCE_DIR)/wsm_hwcheck.pas"

$(CLASSIFY_TARGET): $(SOURCE_DIR)/wsm_classify.pas
	mkdir -p "$(BUILD_DIR)"
	$(FPC) $(FPCFLAGS) -o"$@" "$(SOURCE_DIR)/wsm_classify.pas"

test: build
	"$(HW_TARGET)" --version | grep -Fx "wsm-hwcheck 0.1.0"
	"$(HW_TARGET)" --help >/dev/null
	"$(CLASSIFY_TARGET)" --version | grep -Fx "wsm-classify 0.1.0"
	"$(CLASSIFY_TARGET)" --help >/dev/null

install: build
	mkdir -p "$(PREFIX)/bin"
	install -m 0755 "$(HW_TARGET)" "$(PREFIX)/bin/wsm-hwcheck"
	install -m 0755 "$(CLASSIFY_TARGET)" "$(PREFIX)/bin/wsm-classify"

clean:
	rm -rf "$(BUILD_DIR)"
