# SPDX-License-Identifier: LicenseRef-Volnist
#
# FPC is invoked with -Mobjfpc and -Sh so the unit's {$mode objfpc}{$H+}
# directives are honoured; without -Sh the H+ (ANSI strings) is ignored and
# the JSON builder silently truncates on the first byte above 127.

FPC ?= fpc
FPCFLAGS ?= -Mobjfpc -Sh -O2 -vewn
TARGETS = wsm-hwcheck wsm-classify wsm-partition wsm-profile

all: $(TARGETS)

wsm-hwcheck: wsm_hwcheck.pas
	$(FPC) $(FPCFLAGS) -owsw-hwcheck wsm_hwcheck.pas

wsm-classify: wsm_classify.pas
	$(FPC) $(FPCFLAGS) -owsw-classify wsm_classify.pas

wsm-partition: wsm_partition.pas
	$(FPC) $(FPCFLAGS) -owsw-partition wsm_partition.pas

wsm-profile: wsm_profile.pas
	$(FPC) $(FPCFLAGS) -owsw-profile wsm_profile.pas

clean:
	rm -f $(TARGETS) *.o *.ppu

.PHONY: all clean
