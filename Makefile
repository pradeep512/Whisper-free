SHELL := /bin/bash
REPO_ROOT := $(shell pwd)
VENV_PY := $(REPO_ROOT)/venv/bin/python
WHISPER_BIN := /usr/local/bin/whisper

.PHONY: run
run:
	@if [ ! -x "$(VENV_PY)" ]; then \
		echo "Virtualenv not found: $(VENV_PY)"; \
		echo "Create it with: python -m venv venv"; \
		exit 1; \
	fi
	PYTHONPATH="$(REPO_ROOT)" "$(VENV_PY)" -m app.main

.PHONY: install
install:
	@if [ ! -f "$(REPO_ROOT)/scripts/whisper" ]; then \
		echo "Missing script: $(REPO_ROOT)/scripts/whisper"; \
		exit 1; \
	fi
	@if [ ! -x "$(REPO_ROOT)/scripts/whisper" ]; then \
		echo "Making script executable: $(REPO_ROOT)/scripts/whisper"; \
		chmod +x "$(REPO_ROOT)/scripts/whisper"; \
	fi
	@echo "Linking $(WHISPER_BIN) -> $(REPO_ROOT)/scripts/whisper"
	sudo ln -sf "$(REPO_ROOT)/scripts/whisper" "$(WHISPER_BIN)"
	@echo "Done. Run: whisper"

.PHONY: uninstall
uninstall:
	@echo "Removing $(WHISPER_BIN)"
	sudo rm -f "$(WHISPER_BIN)"
