# SPDX-License-Identifier: LicenseRef-Volnist
#
# Build native WSM tools with Free Pascal. FPC and its FCL units are
# build-time inputs only; installed binaries do not invoke Python.

FPC ?= fpc
PREFIX ?= /usr/local
SOURCE_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ROOT_DIR := $(abspath $(SOURCE_DIR)/../..)
BUILD_DIR ?= $(ROOT_DIR)/build/pascal
FPCFLAGS ?= -B -O2 -Mobjfpc -Sh -Fu"$(SOURCE_DIR)" -FU"$(BUILD_DIR)" -FE"$(BUILD_DIR)"

HW_TARGET := $(BUILD_DIR)/wsm-hwcheck
CLASSIFY_TARGET := $(BUILD_DIR)/wsm-classify
ISA_TARGET := $(BUILD_DIR)/wsm-cpu-isa
PARTITION_TARGET := $(BUILD_DIR)/wsm-partition
TARGETS := $(HW_TARGET) $(CLASSIFY_TARGET) $(ISA_TARGET) $(PARTITION_TARGET)

.PHONY: all build build-hwcheck build-classify build-isa test test-hwcheck test-classify test-isa install install-hwcheck install-classify install-isa build-partition test-partition install-partition clean

all: build

build: build-hwcheck build-classify build-isa build-partition

build-isa: $(ISA_TARGET)

$(ISA_TARGET): $(SOURCE_DIR)/wsm_cpu_isa.pas $(SOURCE_DIR)/wsm_cpu_isa_core.pas
	mkdir -p "$(BUILD_DIR)"
	$(FPC) $(FPCFLAGS) -o"$@" "$(SOURCE_DIR)/wsm_cpu_isa.pas"

build-partition: $(PARTITION_TARGET)

$(PARTITION_TARGET): $(SOURCE_DIR)/wsm_partition.pas
	mkdir -p "$(BUILD_DIR)"
	$(FPC) $(FPCFLAGS) -o"$@" "$(SOURCE_DIR)/wsm_partition.pas"

build-hwcheck: $(HW_TARGET)

build-classify: $(CLASSIFY_TARGET)

$(HW_TARGET): $(SOURCE_DIR)/wsm_hwcheck.pas $(SOURCE_DIR)/wsm_hwcheck_core.pas
	mkdir -p "$(BUILD_DIR)"
	$(FPC) $(FPCFLAGS) -o"$@" "$(SOURCE_DIR)/wsm_hwcheck.pas"

$(CLASSIFY_TARGET): $(SOURCE_DIR)/wsm_classify.pas
	mkdir -p "$(BUILD_DIR)"
	$(FPC) $(FPCFLAGS) -o"$@" "$(SOURCE_DIR)/wsm_classify.pas"

test: test-hwcheck test-classify test-isa test-partition

test-hwcheck: build-hwcheck
	"$(HW_TARGET)" --version | grep -Fx "wsm-hwcheck 0.1.0"
	"$(HW_TARGET)" --help >/dev/null

test-classify: build-classify
	"$(CLASSIFY_TARGET)" --version | grep -Fx "wsm-classify 0.1.0"
	"$(CLASSIFY_TARGET)" --help >/dev/null

test-isa: build-isa
	"$(ISA_TARGET)" --version | grep -Fx "wsm-cpu-isa 0.1.2"
	"$(ISA_TARGET)" --help >/dev/null

test-partition: build-partition
	@output="$("$(PARTITION_TARGET)" --disk /dev/sdz --size 20000000000 --firmware uefi --ack /dev/sdz)"; \
	 printf '%s\n' "$output" | grep -F '"executed":false' >/dev/null; \
	 printf '%s\n' "$output" | grep -F '"typecode":"ef00"' >/dev/null
	@set +e; "$(PARTITION_TARGET)" --disk /dev/sdz1 --size 20000000000 --firmware uefi --ack /dev/sdz1 >/dev/null 2>&1; status=$?; set -e; test "$status" -eq 10

install: install-hwcheck install-classify install-isa install-partition

install-hwcheck: build-hwcheck
	mkdir -p "$(PREFIX)/bin"
	install -m 0755 "$(HW_TARGET)" "$(PREFIX)/bin/wsm-hwcheck"

install-classify: build-classify
	mkdir -p "$(PREFIX)/bin"
	install -m 0755 "$(CLASSIFY_TARGET)" "$(PREFIX)/bin/wsm-classify"

install-isa: build-isa
	mkdir -p "$(PREFIX)/bin"
	install -m 0755 "$(ISA_TARGET)" "$(PREFIX)/bin/wsm-cpu-isa"

install-partition: build-partition
	mkdir -p "$(PREFIX)/bin"
	install -m 0755 "$(PARTITION_TARGET)" "$(PREFIX)/bin/wsm-partition"

clean:
	rm -rf "$(BUILD_DIR)"
