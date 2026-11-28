# SPDX-License-Identifier: LicenseRef-Volnist
#
# FPC is invoked with -Mobjfpc and -Sh so {$mode objfpc}{$H+} is honoured.
# Build outputs stay under build/ and never pollute the source tree.

FPC ?= fpc
FPCFLAGS ?= -Mobjfpc -Sh -O2 -vewn
BUILD_DIR ?= build

all: wsm-hwcheck wsm-classify wsm-partition

wsm-hwcheck: $(BUILD_DIR)/wsm-hwcheck

wsm-classify: $(BUILD_DIR)/wsm-classify

wsm-partition: $(BUILD_DIR)/wsm-partition

$(BUILD_DIR)/wsm-hwcheck: wsm_hwcheck.pas
	mkdir -p $(BUILD_DIR)
	$(FPC) $(FPCFLAGS) -FE$(BUILD_DIR) -FU$(BUILD_DIR) -o$(BUILD_DIR)/wsm-hwcheck wsm_hwcheck.pas

$(BUILD_DIR)/wsm-classify: wsm_classify.pas
	mkdir -p $(BUILD_DIR)
	$(FPC) $(FPCFLAGS) -FE$(BUILD_DIR) -FU$(BUILD_DIR) -o$(BUILD_DIR)/wsm-classify wsm_classify.pas

$(BUILD_DIR)/wsm-partition: wsm_partition.pas
	mkdir -p $(BUILD_DIR)
	$(FPC) $(FPCFLAGS) -FE$(BUILD_DIR) -FU$(BUILD_DIR) -o$(BUILD_DIR)/wsm-partition wsm_partition.pas

clean:
	rm -rf $(BUILD_DIR) *.o *.ppu

.PHONY: all wsm-hwcheck wsm-classify wsm-partition clean
