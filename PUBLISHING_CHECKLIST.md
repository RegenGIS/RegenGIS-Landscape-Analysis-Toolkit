# RegenGIS QGIS Plugin Publishing Checklist

This checklist covers:
1. preparing the source repository for public GitHub publication
2. preparing the plugin package for the QGIS plugin repository
3. publishing with Visual Studio Code + Git

## 1. GitHub source repository checklist

- [ ] Repository contains only source, documentation and assets that belong in the public plugin project.
- [ ] Local-only folders are not tracked: `.hermes/`, `.autocrs-cache/`, `dist/`, `__pycache__/`, virtualenv folders.
- [ ] Generated or temporary packaging files are not tracked: `*.zip`, `*.tgz`, `*.b64`.
- [ ] `README.md` explains what the plugin does, requirements, installation and support.
- [ ] `LICENSE` is present.
- [ ] `CHANGELOG.md` reflects the current public release.
- [ ] `metadata.txt` points to the public GitHub repo, issue tracker and homepage.
- [ ] The repo does not rely on unpublished local files.

## 2. QGIS plugin repository checklist

- [ ] Build the release zip with `bash scripts/build_zip.sh`.
- [ ] Upload the generated file from `dist/regengis_processing_plugin.zip`.
- [ ] The zip contains exactly one top-level folder: `regengis_processing_plugin/`.
- [ ] `regengis_processing_plugin/metadata.txt` exists inside the zip root.
- [ ] `metadata.txt` includes: `name`, `version`, `description`, `about`, `tracker`, `repository`, `homepage`, `license`.
- [ ] `metadata.txt` clearly states external dependencies and restrictions.
- [ ] The plugin zip does not include tests, scripts, caches, `.git`, `.DS_Store`, `__MACOSX` or local work folders.
- [ ] The plugin zip is well below the QGIS upload size limit.
- [ ] Public documentation is available from the homepage / README.
- [ ] `Height Contours` memory-first output limitation is documented clearly in README / release notes.
- [ ] Direct `.gpkg` output from `Height Contours` is not presented as production-safe until the provider/runtime lock bug is resolved.
- [ ] Source code on GitHub matches the uploaded zip contents.

## 3. Visual Studio Code publishing flow

### A. Review changes locally
- Open the repo in VS Code.
- Open the Source Control panel.
- Review all changed files before staging.
- Make sure no local-only files are about to be committed.

### B. Commit the cleanup and release-prep changes
Suggested commit sequence:
1. plugin/source improvements
2. publish/packaging cleanup

Example commit messages:
- `feat: improve RegenGIS plugin tools and UX`
- `chore: prepare plugin for GitHub and QGIS publication`

### C. Push to GitHub
- In Source Control, stage the files you want public.
- Commit from VS Code.
- Push to `main` or to a release branch, depending on your preference.

### D. Create the QGIS upload package
Run in the VS Code terminal:

```bash
bash scripts/build_zip.sh
```

Then upload:

- `dist/regengis_processing_plugin.zip`

## Recommended release decision

Do **not** delete the existing GitHub repository by default.

Prefer this order:
1. clean the current repo
2. commit the publication-ready state
3. push the cleaned history forward
4. only replace/delete the repo if the current public repo is irreparably confusing or contains material that should never have been public

Deleting and recreating the repo is usually unnecessary and breaks links, issues and continuity.

## Current known good release artifact

- Built file: `dist/regengis_processing_plugin.zip`
- Expected root folder inside zip: `regengis_processing_plugin/`
- `metadata.txt` is present at the correct level inside the zip.

## Current release blocker / workaround

- `Height Contours` is currently reliable as a **temporary memory output**.
- Direct provider output from `Height Contours` to `.gpkg` remains a reproducible runtime lock issue in headless testing.
- Safe user workflow for now:
  1. run `Height Contours`
  2. keep the result as the temporary output layer
  3. export the resulting layer afterwards from QGIS if a file on disk is needed
- Production publication should treat direct `.gpkg` output for this tool as an open limitation until a real provider-side fix exists.
