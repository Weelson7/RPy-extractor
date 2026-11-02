# 10. Third-party tools as sparse submodules (proposal + open problems)

Your direction: every third-party tool or library lives in the repository as
a **sparsely checked-out git submodule**. This doc describes how that could
work and, more importantly, where it **doesn't fit cleanly yet**. Several
points need your decision before anything here can be locked.

## 10.1 What it gives us

- **Pinned versions:** every tool is fixed to a known commit. Output that differs because of tool versions becomes reproducible.
- **Provenance:** we know exactly which code we run, and licenses sit next to the code.
- **Fewer install surprises:** less depends on `pip install` at startup, or winget/choco (v1 `startup.py`).
- **The kernel can find tools in a known place:** the ToolLocator (doc 1.2) gets a "vendored" step.

## 10.2 Proposed layout

```
third_party/
  manifest.ini              # one section per tool: repo, pinned commit, sparse paths, license, build
  unitypy/                  # submodule (sparse)
  unrpa/
  py7zr/
  ...
  _build/<kernel>/<tool>/   # build outputs for compiled tools (gitignored)
```

```ini
; third_party/manifest.ini (sketch)
[unitypy]
repo     = https://github.com/K0lb3/UnityPy
commit   = <sha>
sparse   = UnityPy/
license  = MIT              ; to verify
kind     = python           ; python | native | dotnet | java | rust
build    = none

[ghidra]
repo     = https://github.com/NationalSecurityAgency/ghidra
commit   = <sha>
sparse   = <to define>
license  = Apache-2.0       ; to verify
kind     = java
build    = gradle (heavy)   ; see 10.4
```

Notes on mechanics:

- `.gitmodules` can record `shallow = true`, but **it cannot record sparse-checkout paths.** The sparse paths have to live in our own file (`manifest.ini` above). A sync script would then run `git submodule update --init --filter=blob:none` followed by `git -C third_party/<x> sparse-checkout set <paths>`. In other words, sparse checkout needs tooling of our own; plain git won't do it.
- The ToolLocator search order (doc 1.2) would become: config override → env var → **vendored (`third_party/`, `_build/<kernel>/`)** → PATH → known install dirs. Should vendored come before or after a system install? I lean towards vendored first (reproducibility), but there's a case for system first (the user's own newer tool). ❓

## 10.3 The tools, sorted by how well they fit

> Research update: the verified repository and license facts are in doc 13.5. Confirmed so far: `.gitmodules` can't hold sparse paths; unrar has **no official git**; 7-Zip's GitHub repository looks official but has RAR-restricted parts; FFmpeg's canonical repository is git.ffmpeg.org. GPL tools must run as subprocesses.


The repository locations and licenses below come from memory and **still
need to be checked** one by one.

| Fit | Tools | Why |
|-----|-------|-----|
| **Good:** pure Python, usable straight from source | unrpa, unrpyc, py7zr (?) | can be added to `sys.path` from the submodule |
| **Partial:** Python with compiled dependencies | UnityPy | its texture/audio decoders are native extensions (wheels). The submodule pins UnityPy itself, but pip or prebuilt wheels are still needed for those dependencies ❓ |
| **Source only:** needs a build toolchain for each kernel | repak (Rust), GodotPckTool (C++), umodel (C++), Il2CppDumper / Cpp2IL / AssetRipper / ILSpy (.NET), Ghidra (Java/Gradle), ffmpeg (C) | a submodule gives us **source, not a runnable tool**. Each would need a build step for each kernel, and some builds are heavy (Ghidra, ffmpeg) |
| **Doesn't fit plain git** | unrar (source is shipped as a tarball from RARLAB, not git, as far as I know), 7-Zip (official git hosting to verify) | would need a mirror repository we maintain |

## 10.4 Open problems

1. **Source vs. runnable.** For compiled tools, what does the submodule really give us? The options:
   - (a) build from source per kernel (correct, but slow, and needs Rust/.NET/JDK/C toolchains on every dev machine and in CI);
   - (b) the submodule pins the version and license, and a script downloads the matching **release binary**, verified by checksum;
   - (c) a separate binaries repository (with git LFS) as the submodule.
   My suggestion is (b) for heavy native tools and plain source for pure-Python ones. I'd like your call. ❓
2. **Licenses.** Shipping GPL source (AssetRipper, and possibly unrpa; to verify) inside the repository affects how the combined app can be distributed. The unrar license has its own restrictions. The project doesn't have a LICENSE file yet, so a license decision should come before vendoring. ❓
3. **Repository size.** Ghidra and ffmpeg are very large repositories. Sparse checkout plus a blobless clone helps, but CI and first-time cloning still pay a real cost.
4. **Updates.** Bumping a pinned commit should rerun the combination test matrix (doc 3.6) and the slot failover tests (doc 8). That gives us a reason to keep fixtures small and synthetic.
5. **The ini overlap.** `third_party/manifest.ini` (what's vendored) and `startup.ini [tools]` (what's used) are two separate files. Is that the split you want, or should vendoring also be described in `startup.ini`? ❓

## 10.5 Effect on the other documents (once decided)

- doc 1.2: add the vendored step to the search order.
- doc 2.6 / 8: `DependencySpec` gains `vendored: <manifest section>`.
- doc 9: `[tools]` entries can point to `vendored:<name>`.
- `auto_install` becomes a fallback for anything that isn't vendored.
