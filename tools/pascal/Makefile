# SPDX-License-Identifier: LicenseRef-Volnist
#
# FPC is invoked with -Mobjfpc and -Sh so the unit's {$mode objfpc}{$H+}
# directives are honoured; without -Sh the H+ (ANSI strings) is ignored and
# the JSON builder silently truncates on the first byte above 127.

FPC ?= fpc
FPCFLAGS ?= -Mobjfpc -Sh -O2 -vewn
TARGETS = wsm-hwcheck wsm-classify wsm-partition wsm-profile wsm-preflight wsm-install

all: $(TARGETS)

wsm-hwcheck: wsm_hwcheck.pas
	$(FPC) $(FPCFLAGS) -owsw-hwcheck wsm_hwcheck.pas

wsm-classify: wsm_classify.pas
	$(FPC) $(FPCFLAGS) -owsw-classify wsm_classify.pas

wsm-partition: wsm_partition.pas
	$(FPC) $(FPCFLAGS) -owsw-partition wsm_partition.pas

wsm-profile: wsm_profile.pas
	$(FPC) $(FPCFLAGS) -owsw-profile wsm_profile.pas

wsm-preflight: wsm_preflight.pas
	$(FPC) $(FPCFLAGS) -owsw-preflight wsm_preflight.pas

wsm-install: wsm_install.pas
	$(FPC) $(FPCFLAGS) -owsw-install wsm_install.pas

PASCAL_DIR := $(patsubst %/,%,$(dir $(lastword $(MAKEFILE_LIST))))

wsm-install-fpc: $(PASCAL_DIR)/wsm_install_cli.lpr $(PASCAL_DIR)/wsmjson.pas
	$(FPC) $(FPCFLAGS) \
		-Fu$(PASCAL_DIR) -FU$(PASCAL_DIR) -FE$(PASCAL_DIR) \
		-o$(PASCAL_DIR)/wsm-install-fpc $(PASCAL_DIR)/wsm_install_cli.lpr

clean:
	rm -f $(TARGETS) *.o *.ppu

.PHONY: all clean
