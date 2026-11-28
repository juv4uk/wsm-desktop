# SPDX-License-Identifier: LicenseRef-Volnist

FPC ?= fpc
PREFIX ?= /usr/local
BUILD_DIR ?= build/fpc
PROGRAM := $(BUILD_DIR)/wsm-hwcheck
SOURCE_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

.PHONY: all build test install clean

all: build

build:
	mkdir -p "$(BUILD_DIR)"
	$(FPC) -B -O2 -Mobjfpc -Sh -Fu"$(SOURCE_DIR)" -FU"$(BUILD_DIR)" -FE"$(BUILD_DIR)" -o"$(PROGRAM)" "$(SOURCE_DIR)/wsm_hwcheck.pas"

test: build
	"$(PROGRAM)" --version | grep -Fx "wsm-hwcheck 0.1.0"
	"$(PROGRAM)" --help >/dev/null

install: build
	mkdir -p "$(PREFIX)/bin"
	install -m 0755 "$(PROGRAM)" "$(PREFIX)/bin/wsm-hwcheck"

clean:
	rm -rf "$(BUILD_DIR)"
