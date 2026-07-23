# RegenGIS Landscape Analysis Toolkit

A QGIS Processing provider and toolbox with spatial analysis tools to support decision making when designing regenerative landscapes, such as food forests, agroforestry or permaculture systems.

## Features

- A set of offline models and spatial algorithms for hydrology, solar radiation and water flow relevant to agroforestry planning.
- Algorithms are loaded dynamically from the `algorithms/` folder structure and exposed through the QGIS Processing toolbox.

## Requirements

- QGIS 3.16 or newer (adjustable in `metadata.txt`)
- Python 3.7+
- GRASS processing provider is available (this depends on the platform you're using and the QGIS version. For more information see below)

## Installation

1. Package the plugin folder as a ZIP for installation in QGIS.
2. In QGIS: Plugins → Manage and Install Plugins → Install from ZIP → choose the generated ZIP file.

## Usage

- After installing, open the Processing Toolbox and search for "RegenGIS" or the individual algorithm names in the `RegenGIS Landscape Analysis Toolkit` provider.
- `Height Contours` currently uses a **memory-first output workflow** to avoid reproducible GeoPackage transaction locks in headless/provider execution.
- Recommended workflow for `Height Contours`:
  1. run the algorithm and keep the result as a temporary memory layer
  2. inspect the result in QGIS
  3. export the layer afterwards to GeoPackage, Shapefile or another file format if needed
- Do **not** rely on direct `.gpkg` output from `Height Contours` as a production-safe path until this provider/runtime issue is resolved.

## Support & Contribution

- Website: https://www.regengis.com
- Email: info@regengis.com

## License

This project is licensed under the Mozilla Public License 2.0 (see `LICENSE`).

## GRASS Processing Provider Support

This plugin requires the **QGIS GRASS Processing Provider**.

Support depends on a combination of:

- **QGIS LTR version**
- **platform**: Windows, Linux, Mac Intel/Apple Silicon
- **installation/package variant**

For that reason, support is defined as follows.

#### Windows

- **QGIS LTR versions:** Supported in principle across LTR releases
- **GRASS included by default:** Not always
- **Requirement:** Install a QGIS build that includes the GRASS component/plugin
- **Support status:** Supported when the GRASS provider is installed and available

#### Linux

- **QGIS LTR versions:** Supported in principle across LTR releases
- **GRASS included by default:** Usually not in the base `qgis` package alone
- **Requirement:** Install the GRASS package for the distribution, typically `qgis-grass` or `qgis-plugin-grass`
- **Support status:** Supported when the GRASS provider package is installed

#### macOS Intel

- **QGIS 3.40 LTR:** Supported
- **QGIS 3.44 LTR:** Not supported
- **Reason:** Open QGIS issues report that recent macOS 3.44 builds do not properly provide working GRASS integration
- **Support status:** Support macOS Intel on **QGIS 3.40 LTR**, do **not** support **3.44 LTR** for GRASS-dependent workflows

#### macOS Apple Silicon

- **QGIS 3.40 LTR:** Provisionally supported
- **QGIS 3.44 LTR:** Not supported
- **Reason:** Open QGIS issues show unresolved macOS GRASS problems, including Apple Silicon-specific GISBASE/provider issues
- **Support status:** Support Apple Silicon on **QGIS 3.40 LTR** only if GRASS is confirmed working locally; do **not** support **3.44 LTR** for GRASS-dependent workflows

### Recommended minimum combinations

- **Windows:** QGIS LTR with GRASS component installed
- **Linux:** QGIS LTR with `qgis-grass` or `qgis-plugin-grass` installed
- **macOS Intel:** **QGIS 3.40 LTR**
- **macOS Apple Silicon:** **QGIS 3.40 LTR**, with local verification of GRASS availability