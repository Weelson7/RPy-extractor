**What this changes** (one paragraph; link the issue if there is one)

**Kind**: index entry / script pin / tool pin / plugin / backend / fix / docs

**Checklist**
- [ ] `ruff format`, `ruff check`, `python tools/loc_count.py` and the tests (`python -m unittest discover -s tests -t .`) pass locally
- [ ] committed with `python tools/version.py commit` (version bumped, tag created)
- [ ] pins carry size + sha256 computed from the real asset; URLs are HTTPS
- [ ] no game files, keys or secrets in fixtures, tests or docs
- [ ] fits the README Philosophy (no new boundaries or safeguards in the code)
