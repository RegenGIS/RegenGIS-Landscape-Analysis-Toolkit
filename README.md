# RegenGIS Landscape Analysis Toolkit

A QGIS Processing provider and toolbox with spatial analysis tools to support decision making when designing regenerative landscapes, such as food forests, agroforestry or permaculture systems.

## Features
- A set of offline models and spatial algorithms for hydrology, solar radiation and water flow relevant to agroforestry planning.
- Algorithms are loaded dynamically from the `algorithms/` folder structure and exposed through the QGIS Processing toolbox.

## Requirements
- QGIS 3.16 or newer (adjustable in `metadata.txt`)
- Python 3.7+

## Installation
1. Package the plugin folder as a ZIP for installation in QGIS.
2. In QGIS: Plugins → Manage and Install Plugins → Install from ZIP → choose the generated ZIP file.

## Usage
- After installing, open the Processing Toolbox and search for "Agroforestry" or the individual algorithm names in the `Agroforestry Toolbox` provider.

## Support & Contribution
- Website: https://www.regengis.com
- Email: info@regengis.com

## License
This project is licensed under the Mozilla Public License 2.0 (see `LICENSE`).
