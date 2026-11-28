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
PROFILE_TARGET := $(BUILD_DIR)/wsm-profile
PREFLIGHT_TARGET := $(BUILD_DIR)/wsm-preflight
TARGETS := $(HW_TARGET) $(CLASSIFY_TARGET) $(ISA_TARGET) $(PARTITION_TARGET) $(PROFILE_TARGET) $(PREFLIGHT_TARGET)

.PHONY: all build build-hwcheck build-classify build-isa build-partition build-profile build-preflight test test-hwcheck test-classify test-isa test-partition test-profile test-preflight install install-hwcheck install-classify install-isa install-partition install-profile install-preflight clean

all: build

build: build-hwcheck build-classify build-isa build-partition build-profile build-preflight

build-isa: $(ISA_TARGET)

$(ISA_TARGET): $(SOURCE_DIR)/wsm_cpu_isa.pas $(SOURCE_DIR)/wsm_cpu_isa_core.pas
	mkdir -p "$(BUILD_DIR)"
	$(FPC) $(FPCFLAGS) -o"$@" "$(SOURCE_DIR)/wsm_cpu_isa.pas"

build-partition: $(PARTITION_TARGET)

build-profile: $(PROFILE_TARGET)

$(PROFILE_TARGET): $(SOURCE_DIR)/wsm_profile.pas
	mkdir -p "$(BUILD_DIR)"
	$(FPC) $(FPCFLAGS) -o"$@" "$(SOURCE_DIR)/wsm_profile.pas"

build-preflight: $(PREFLIGHT_TARGET)

$(PREFLIGHT_TARGET): $(SOURCE_DIR)/wsm_preflight.pas
	mkdir -p "$(BUILD_DIR)"
	$(FPC) $(FPCFLAGS) -o"$@" "$(SOURCE_DIR)/wsm_preflight.pas"

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

test: test-hwcheck test-classify test-isa test-partition test-profile test-preflight

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
	@output="$$($(PARTITION_TARGET) --disk /dev/sdz --size 20000000000 --firmware uefi --ack /dev/sdz)"; \
	 printf '%s\n' "$$output" | grep -F '"executed":false' >/dev/null; \
	 printf '%s\n' "$$output" | grep -F '"typecode":"ef00"' >/dev/null
	@set +e; "$(PARTITION_TARGET)" --disk /dev/sdz1 --size 20000000000 --firmware uefi --ack /dev/sdz1 >/dev/null 2>&1; status=$$?; set -e; test "$$status" -eq 10

test-profile: build-profile
	@tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT; \
	 printf '%s\n' '{"schema":"wsm-profile-evidence/2","verified_functions":[{"status":"pass"}],"artifacts":[]}' > "$tmp/evidence.json"; \
	 output="$("$(PROFILE_TARGET)" "$tmp/evidence.json")"; \
	 printf '%s\n' "$output" | grep -F '"ok":true' >/dev/null; \
	 printf '%s\n' "$output" | grep -F '"digest_verification":"delegated"' >/dev/null

test-preflight: build-preflight
	@tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT; \
	 printf '%s\n' '(operating-system)' > "$tmp/desktop.scm"; \
	 set +e; output="$("$(PREFLIGHT_TARGET)" --mount-point "$tmp" --system-file "$tmp/desktop.scm")"; status=$?; set -e; \
	 test "$status" -eq 1 -o "$status" -eq 6; \
	 printf '%s\n' "$output" | grep -F '"schema":"wsm-preflight/1"' >/dev/null; \
	 printf '%s\n' "$output" | grep -F '"id":"report","status":"not-run"' >/dev/null

install: install-hwcheck install-classify install-isa install-partition install-profile install-preflight

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

install-profile: build-profile
	mkdir -p "$(PREFIX)/bin"
	install -m 0755 "$(PROFILE_TARGET)" "$(PREFIX)/bin/wsm-profile"

install-preflight: build-preflight
	mkdir -p "$(PREFIX)/bin"
	install -m 0755 "$(PREFLIGHT_TARGET)" "$(PREFIX)/bin/wsm-preflight"

clean:
	rm -rf "$(BUILD_DIR)"
