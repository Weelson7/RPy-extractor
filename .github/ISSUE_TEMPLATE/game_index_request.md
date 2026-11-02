---
name: Game / index request
about: A game ViWo should know (an index entry), or one it handles badly
title: "[game] "
labels: index
---

**Game, version, store/platform**:

**Engine** (if known) and how to recognize the install (files or folders that always exist):

**What ViWo does today** (`viwo survey <game folder>` output, or 07 SURVEY):

**What is needed** (plugin, options, tools, QuickBMS script with URL + sha256 + license, source
of the knowledge):

Prefer a pull request with the entry under `indexes/games/<slug>/<version>/index.json`,
validated with `python indexes/tools/validate.py` (see CONTRIBUTING.md).
