# SPDX-License-Identifier: LicenseRef-Volnist
#
# FPC is invoked with -Mobjfpc and -Sh so the unit's {$mode objfpc}{$H+}
# directives are honoured; without -Sh the H+ (ANSI strings) is ignored and
# the JSON builder silently truncates on the first byte above 127.

FPC ?= fpc
FPCFLAGS ?= -Mobjfpc -Sh -O2 -vewn
TARGETS = wsm-hwcheck wsm-classify

# Where this Makefile lives, so a recipe works when make is started from the
# repository root (`make -f tools/pascal/Makefile …`), which is how the Guix
# packages invoke it.
PASCAL_DIR := $(patsubst %/,%,$(dir $(lastword $(MAKEFILE_LIST))))

all: $(TARGETS)

wsm-hwcheck: wsm_hwcheck.pas
	$(FPC) $(FPCFLAGS) -owsw-hwcheck wsm_hwcheck.pas

wsm-classify: wsm_classify.pas
	$(FPC) $(FPCFLAGS) -owsw-classify wsm_classify.pas

# The read-only installer front end. It is a program (`.lpr`) plus the JSON unit
# `wsmjson.pas` beside it, so the unit search path is set explicitly: this
# recipe must work from the repository root, not only from this directory.
# Deliberately not part of `all`: it has its own Guix package
# (wsm/packages/wsm-install-fpc.scm) and its own parity workflow.
wsm-install-fpc: $(PASCAL_DIR)/wsm_install_cli.lpr $(PASCAL_DIR)/wsmjson.pas
	$(FPC) $(FPCFLAGS) \
		-Fu$(PASCAL_DIR) -FU$(PASCAL_DIR) -FE$(PASCAL_DIR) \
		-o$(PASCAL_DIR)/wsm-install-fpc $(PASCAL_DIR)/wsm_install_cli.lpr

clean:
	rm -f $(TARGETS) wsm-install-fpc *.o *.ppu

.PHONY: all clean
