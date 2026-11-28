# SPDX-License-Identifier: LicenseRef-Volnist
#
# Native FPC executables. Build outputs never enter the source tree's Git paths.

FPC ?= fpc
PREFIX ?= /usr/local
BUILD_DIR ?= build
FPCFLAGS ?= -B -O2 -Mobjfpc -Sh -vewn

HW_BINARY := $(BUILD_DIR)/wsm-hwcheck
CLASSIFY_BINARY := $(BUILD_DIR)/wsm-classify

.PHONY: all build-wsm-hwcheck test-wsm-hwcheck install-wsm-hwcheck \
        build-wsm-classify test-wsm-classify install-wsm-classify clean

all: build-wsm-hwcheck build-wsm-classify

build-wsm-hwcheck: $(HW_BINARY)

$(HW_BINARY): wsm_hwcheck.pas wsm_hwcheck_core.pas
	mkdir -p "$(BUILD_DIR)"
	$(FPC) $(FPCFLAGS) -Fu. -FU"$(abspath $(BUILD_DIR))" \
		-FE"$(abspath $(BUILD_DIR))" -o"$(abspath $(HW_BINARY))" wsm_hwcheck.pas

build-wsm-classify: $(CLASSIFY_BINARY)

$(CLASSIFY_BINARY): wsm_classify.pas
	mkdir -p "$(BUILD_DIR)"
	$(FPC) $(FPCFLAGS) -Fu. -FU"$(abspath $(BUILD_DIR))" \
		-FE"$(abspath $(BUILD_DIR))" -o"$(abspath $(CLASSIFY_BINARY))" wsm_classify.pas

test-wsm-hwcheck: build-wsm-hwcheck
	"$(HW_BINARY)" --version | grep -Fx "wsm-hwcheck 0.1.0"
	"$(HW_BINARY)" --help >/dev/null

test-wsm-classify: build-wsm-classify
	"$(CLASSIFY_BINARY)" --version | grep -Fx "wsm-classify 0.2.0"
	"$(CLASSIFY_BINARY)" --help >/dev/null

install-wsm-hwcheck: build-wsm-hwcheck
	install -D -m 0755 "$(HW_BINARY)" "$(PREFIX)/bin/wsm-hwcheck"

install-wsm-classify: build-wsm-classify
	install -D -m 0755 "$(CLASSIFY_BINARY)" "$(PREFIX)/bin/wsm-classify"

clean:
	rm -rf "$(BUILD_DIR)" *.o *.ppu
