# SPDX-License-Identifier: LicenseRef-Volnist
#
# Native WSM utilities. Each target builds one executable under BUILD_DIR.
# The tools only read their evidence inputs; the partition planner emits data.

FPC ?= fpc
PREFIX ?= /usr/local
BUILD_DIR ?= build
FPCFLAGS ?= -Mobjfpc -Sh -O2 -vewn
TARGETS = wsm-hwcheck wsm-classify wsm-cpu-isa wsm-partition wsm-profile wsm-preflight wsm-install

.PHONY: all clean $(TARGETS)

all: $(TARGETS)

$(BUILD_DIR):
	mkdir -p "$(BUILD_DIR)"

wsm-hwcheck: $(BUILD_DIR)/wsm-hwcheck
$(BUILD_DIR)/wsm-hwcheck: wsm_hwcheck.pas | $(BUILD_DIR)
	$(FPC) $(FPCFLAGS) -FE"$(BUILD_DIR)" -FU"$(BUILD_DIR)" -o"$(BUILD_DIR)/wsm-hwcheck" wsm_hwcheck.pas

wsm-classify: $(BUILD_DIR)/wsm-classify
$(BUILD_DIR)/wsm-classify: wsm_classify.pas | $(BUILD_DIR)
	$(FPC) $(FPCFLAGS) -FE"$(BUILD_DIR)" -FU"$(BUILD_DIR)" -o"$(BUILD_DIR)/wsm-classify" wsm_classify.pas

wsm-cpu-isa: $(BUILD_DIR)/wsm-cpu-isa
$(BUILD_DIR)/wsm-cpu-isa: wsm_cpu_isa.pas wsm_cpu_isa_core.pas | $(BUILD_DIR)
	$(FPC) $(FPCFLAGS) -FE"$(BUILD_DIR)" -FU"$(BUILD_DIR)" -Fu. -o"$(BUILD_DIR)/wsm-cpu-isa" wsm_cpu_isa.pas

wsm-partition: $(BUILD_DIR)/wsm-partition
$(BUILD_DIR)/wsm-partition: wsm_partition.pas | $(BUILD_DIR)
	$(FPC) $(FPCFLAGS) -FE"$(BUILD_DIR)" -FU"$(BUILD_DIR)" -o"$(BUILD_DIR)/wsm-partition" wsm_partition.pas

wsm-profile: $(BUILD_DIR)/wsm-profile
$(BUILD_DIR)/wsm-profile: wsm_profile.pas | $(BUILD_DIR)
	$(FPC) $(FPCFLAGS) -FE"$(BUILD_DIR)" -FU"$(BUILD_DIR)" -o"$(BUILD_DIR)/wsm-profile" wsm_profile.pas

wsm-preflight: $(BUILD_DIR)/wsm-preflight
$(BUILD_DIR)/wsm-preflight: wsm_preflight.pas | $(BUILD_DIR)
	$(FPC) $(FPCFLAGS) -FE"$(BUILD_DIR)" -FU"$(BUILD_DIR)" -o"$(BUILD_DIR)/wsm-preflight" wsm_preflight.pas

wsm-install: $(BUILD_DIR)/wsm-install
$(BUILD_DIR)/wsm-install: wsm_install.pas | $(BUILD_DIR)
	$(FPC) $(FPCFLAGS) -FE"$(BUILD_DIR)" -FU"$(BUILD_DIR)" -o"$(BUILD_DIR)/wsm-install" wsm_install.pas

clean:
	rm -rf "$(BUILD_DIR)" *.o *.ppu
