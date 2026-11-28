# SPDX-License-Identifier: LicenseRef-Volnist
#
# Keep the compiler mode explicit.  The source also declares {$mode objfpc}{$H+};
# the flags make the package build independent of the caller's FPC defaults.

FPC ?= fpc
FPCFLAGS ?= -Mobjfpc -Sh -O2 -vewn
TARGET = wsm-hwcheck

all: $(TARGET)

$(TARGET): wsm_hwcheck.pas
	$(FPC) $(FPCFLAGS) -o$(TARGET) wsm_hwcheck.pas

clean:
	rm -f $(TARGET) *.o *.ppu

.PHONY: all clean
