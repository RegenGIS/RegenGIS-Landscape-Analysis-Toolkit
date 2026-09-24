# Changelog

All notable changes to this plugin will be documented in this file.

## 0.5
- Prepared a new upload package after the blocked 0.4 scan result; the release preflight now runs Bandit, detect-secrets, Flake8, package file analysis and approval-link checks.
- Excluded development tooling, diagnostics and binary assets from the upload ZIP.

## 0.4
- Verified functional Processing output and GUI behavior in QGIS 3.44 and QGIS 4.2.
- Added QGIS 4-safe analysis extent handling to prevent empty output rasters outside the input coverage.
- Fixed GRASS batch execution in the regression runtime and strengthened raster-output checks to reject NoData-only results.
- Corrected Height Contours output handling in QGIS 4 and the TWI completion layer name.
- Raised the declared minimum QGIS version to 3.44, the earliest runtime verified for this release.

## 0.3
- Bumped plugin version to 0.3 for the updated release package.
- Community join link points to the direct RegenGIS account registration page.

## 0.1
- Initial public packaging of the RegenGIS QGIS plugin.
- Processing provider with bundled RegenGIS tools.
- Shared AutoCRS modules and raster-preparation workflows.
- Hydrology, landscape and microclimate processing algorithms.
- Community dialog, About RegenGIS entry points and plugin-wide tool icons.
- Release packaging cleaned for GitHub and QGIS plugin repository upload.

