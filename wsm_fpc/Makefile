# SPDX-License-Identifier: LicenseRef-Volnist
#
# Build recipe for the FPC slices of wsm-install.
#
# Guix's gnu-build-system runs `make`, `make check` and `make install` and passes
# the strings of its #:make-flags to all three. The variables below are the only
# knobs it needs:
#
#   FPC       path to the fpc binary from the store
#   PREFIX    installation prefix (Guix passes its output directory)
#   FPCFLAGS  optimisation and warning switches
#
# FPC 3.2.2 - the version Guix packages - has no sha256 unit, which is why
# wsm_sha256.pas exists here instead of a `uses sha256`.

FPC      ?= fpc
PREFIX   ?= /usr/local
FPCFLAGS ?= -O2 -Sh -vw

# Every program in this directory is built from its own source file; the units are
# pulled in by the compiler as they are referenced.
PROGRAMS = plan-digest schema-vectors

SOURCES = wsm_sha256.pas plan_digest.pas wsmcpufacts.pas wsmsteps.pas \
          wsmschema.pas wsmschema_vectors.pas

.PHONY: all check install clean

all: $(PROGRAMS)

plan-digest: plan_digest.pas wsm_sha256.pas
	$(FPC) $(FPCFLAGS) -o$@ $<

# The schema slice carries 36 vectors captured from the Python validator.
schema-vectors: wsmschema_vectors.pas wsmschema.pas
	$(FPC) $(FPCFLAGS) -o$@ $<

# Each program carries its own vectors and exits non-zero when one differs, so
# `check` is the same run as `all` - which is the point: the first compile on a
# machine with FPC is also the verification.
check: $(PROGRAMS)
	./plan-digest
	./schema-vectors

install: $(PROGRAMS)
	install -d $(DESTDIR)$(PREFIX)/bin
	install -m 0755 plan-digest $(DESTDIR)$(PREFIX)/bin/plan-digest

clean:
	rm -f $(PROGRAMS) *.o *.ppu
