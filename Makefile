# SPDX-License-Identifier: GPL-3.0-or-later

PYTHON ?= python3
GUIX ?= guix

.PHONY: check check-docs check-system vm-system

check: check-docs

check-docs:
	$(PYTHON) scripts/check_docs.py

check-system:
	$(GUIX) system build systems/minimal.scm

vm-system:
	$(GUIX) system vm systems/minimal.scm
