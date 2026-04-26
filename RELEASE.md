# Release process

iobox is published to [PyPI](https://pypi.org/project/iobox/) automatically by
`.github/workflows/release.yml` on every `v*` tag push, via PyPI Trusted
Publishing (OIDC, no API token in the repo).

## Versioning

iobox follows [SemVer](https://semver.org/), but is **pre-1.0**, so:

- `0.x.y` → minor bumps may include breaking changes when the upside is large
  enough. Document them in `CHANGELOG.md` under the new version.
- `1.0.0` will be the first release that promises backwards compatibility for
  the public API (CLI, `Workspace`, `GoogleAuth` / `MicrosoftAuth`,
  `TokenStore`).

## Cutting a release

1. **Pick the version.** Edit `pyproject.toml` `version = "X.Y.Z"`. Match it
   to a new top entry in `CHANGELOG.md` summarising what changed.
2. **Run CI checks locally** to catch obvious problems before burning a tag:
   ```bash
   ruff check src tests && ruff format --check src tests
   pytest --cov=src --cov-fail-under=80
   ```
   Tests that simulate "extra not installed" (e.g. `O365` missing) will fail
   locally if the corresponding extra is installed in your venv. CI installs
   only `[dev]`, so those pass there.
3. **Land everything on `main`** — version bump, CHANGELOG, code. The release
   workflow runs `ci.yml` first via `needs: test`; if anything is broken on
   `main`, the publish step is skipped and the tag becomes a phantom.
4. **Tag and push:**
   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```
5. **Watch the workflow:**
   ```bash
   gh run watch -R timainge/iobox
   ```
6. **Verify on PyPI:** `pip index versions iobox` should show the new version
   within a few minutes of the workflow finishing.

## Recovering from a failed release

The workflow's `publish` job runs only if `test` passes. If the tag is pushed
but the workflow fails, the tag exists but no artifact is published — a
"phantom tag". Two paths:

- **Fix forward.** Bump to the next patch version, land the fix, tag again.
  Phantom tag stays; tagging policy makes it harmless.
- **Delete and retry** (only safe if no one has pulled the tag yet):
  ```bash
  git push origin :refs/tags/vX.Y.Z
  git tag -d vX.Y.Z
  ```
  Then fix the issue, land it, and re-tag.

## Why no manual `python -m build && twine upload`?

The Trusted Publishing flow ties releases to `main` history and a tagged commit
without any long-lived API token. Don't add one — it weakens the security
posture and provides no benefit over the workflow.
