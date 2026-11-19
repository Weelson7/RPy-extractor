# ViWo — capability gaps to consider (parked)

A user-perspective audit (2026-11-19). Not started; the owner decides what to file. Each line
tags my recommendation: **[File-high]**, **[File-medium]**, **[Maybe]**, **[Skip]**.

## 1. "Find the thing I want to change"
- **[File-high] Content/value search across a workspace and inside a binary.** Find a string, a
  number, or a byte pattern anywhere in the extracted files or in an exe/dll. ViWo has no search
  today; SORT is type-only. The #1 entry point for both patching and modding.
- **[File-high] "Change it in the app, then show me what changed."** Snapshot files + registry
  (optionally memory), the user flips a setting in the running app, ViWo diffs and points at the
  file/key/offset that holds it. `viwo diff` only compares two static game versions, not an action.

## 2. "Patch it and keep it working"
- **[File-medium] Intent -> location last mile.** Tie a user's words ("the connection limit") to
  the actual constant/instruction via string-xref (the analysis arm) feeding `patch.sig`. The
  machinery exists (`patch.bytes`/`patch.sig`/disasm); the glue from a name to the immediate is
  manual (the FDM last step). Analysis-heavy.
- **[File-medium] Patch portability and re-apply after update.** Export a patch as an AOB-signature
  recipe; when the app updates, re-locate by signature and re-apply, or warn that it moved.
  `signature()` exists but there is no user flow or update watch.

## 3. "Reach more targets"
- **[Maybe] Mobile (Android APK/OBB, mobile Unity/IL2CPP).** Not a first-class target. Large
  scope, but where many "games I own" now live. Decide if in scope.
- More desktop engines (GameMaker, Wolf RPG, TyranoScript): already in flight, not a gap to file.

## 4. "Understand / trust what happened"
- **[Maybe] A user-facing per-run report.** "Here's what I found, what is editable vs one-way,
  what is patchable, what hit a wall." Partly covered by `survey` + the ASSETS plan + run records,
  but not as one readable summary.

## Not gaps (for trust)
Extraction/decoding breadth, two-way repack, runbooks/workflows/hooks, the three arms, and the
isolation/patcher layer are present. Sharing patches and community scripts tie to the **indexes
repo, which is owner/GitHub-blocked** -> **[Skip]** until it exists.
