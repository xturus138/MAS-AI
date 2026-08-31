# Packaging the MAS AI Orchestrator .exe

## One-time setup

1. Download Android `platform-tools` for Windows from Google's official
   distribution (`https://developer.android.com/tools/releases/platform-tools`).
2. Extract it, then copy `adb.exe` and every `.dll` next to it into
   `desktop_app/vendor/platform-tools/` in this repo (this directory is
   gitignored on purpose — these are redistributable third-party binaries,
   not source code this repo tracks).
3. Install packaging dependencies: `pip install -r requirements.txt`
   (this already includes `pyinstaller` as of the desktop-app work).

## Building

From the repo root:

```
pyinstaller desktop_app/packaging/mas_ai_orchestrator.spec
```

Output: `desktop_app/packaging/dist/MAS AI Orchestrator/MAS AI Orchestrator.exe`

## Verifying

See Task 24 in `docs/superpowers/plans/2026-08-31-mas-ai-desktop-app.md` for
the manual smoke-test checklist that must pass before distributing a build.
