# SPDX-License-Identifier: LicenseRef-Volnist
FPC ?= fpc

.PHONY: all clean

all: wsm_pe_exports

wsm_pe_exports: wsm_pe_exports.lpr
	$(FPC) -Mobjfpc -FE. -FU. $<

clean:
	$(RM) wsm_pe_exports wsm_pe_exports.exe *.o *.ppu
