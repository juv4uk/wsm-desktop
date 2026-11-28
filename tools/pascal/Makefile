# SPDX-License-Identifier: LicenseRef-Volnist
#
# Each program has an explicit target. Compiler and unit outputs stay under
# BUILD_DIR; generated binaries never pollute the Pascal source directory.

FPC ?= fpc
FPCFLAGS ?= -Mobjfpc -Sh -O2 -vewn
BUILD_DIR ?= build

all: wsm-hwcheck wsm-classify wsm-partition wsm-profile wsm-preflight wsm-install

wsm-hwcheck: $(BUILD_DIR)/wsm-hwcheck

wsm-classify: $(BUILD_DIR)/wsm-classify

wsm-partition: $(BUILD_DIR)/wsm-partition

wsm-profile: $(BUILD_DIR)/wsm-profile

wsm-preflight: $(BUILD_DIR)/wsm-preflight

wsm-install: $(BUILD_DIR)/wsm-install

$(BUILD_DIR)/wsm-hwcheck: wsm_hwcheck.pas
	mkdir -p $(BUILD_DIR)
	$(FPC) $(FPCFLAGS) -FE$(BUILD_DIR) -FU$(BUILD_DIR) -o$(BUILD_DIR)/wsm-hwcheck wsm_hwcheck.pas

$(BUILD_DIR)/wsm-classify: wsm_classify.pas
	mkdir -p $(BUILD_DIR)
	$(FPC) $(FPCFLAGS) -FE$(BUILD_DIR) -FU$(BUILD_DIR) -o$(BUILD_DIR)/wsm-classify wsm_classify.pas

$(BUILD_DIR)/wsm-partition: wsm_partition.pas
	mkdir -p $(BUILD_DIR)
	$(FPC) $(FPCFLAGS) -FE$(BUILD_DIR) -FU$(BUILD_DIR) -o$(BUILD_DIR)/wsm-partition wsm_partition.pas

$(BUILD_DIR)/wsm-profile: wsm_profile.pas
	mkdir -p $(BUILD_DIR)
	$(FPC) $(FPCFLAGS) -FE$(BUILD_DIR) -FU$(BUILD_DIR) -o$(BUILD_DIR)/wsm-profile wsm_profile.pas

$(BUILD_DIR)/wsm-preflight: wsm_preflight.pas
	mkdir -p $(BUILD_DIR)
	$(FPC) $(FPCFLAGS) -FE$(BUILD_DIR) -FU$(BUILD_DIR) -o$(BUILD_DIR)/wsm-preflight wsm_preflight.pas

$(BUILD_DIR)/wsm-install: wsm_install.pas
	mkdir -p $(BUILD_DIR)
	$(FPC) $(FPCFLAGS) -FE$(BUILD_DIR) -FU$(BUILD_DIR) -o$(BUILD_DIR)/wsm-install wsm_install.pas

clean:
	rm -rf $(BUILD_DIR) *.o *.ppu

.PHONY: all wsm-hwcheck wsm-classify wsm-partition wsm-profile wsm-preflight wsm-install clean
