# SPDX-License-Identifier: LicenseRef-Volnist
#
# FPC is invoked with -Mobjfpc and -Sh so the unit's {$mode objfpc}{$H+}
# directives are honoured; without -Sh the H+ (ANSI strings) is ignored and
# the JSON builder silently truncates on the first byte above 127.

FPC ?= fpc
FPCFLAGS ?= -Mobjfpc -Sh -O2 -vewn
TARGET = wsm-hwcheck

all: $(TARGET)

$(TARGET): wsm_hwcheck.pas
	$(FPC) $(FPCFLAGS) -o$(TARGET) wsm_hwcheck.pas

clean:
	rm -f $(TARGET) *.o *.ppu

.PHONY: all clean
