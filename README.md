# RegenGIS Analysis Toolbox

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

## Development
- Algorithms live in the `algorithms/` package. Keep that folder intact when editing.
- Subfolders under `algorithms/` are discovered automatically and shown as Processing groups. You do not need to update provider code or add `__init__.py` files for new folders.
- Convert a QGIS Model Designer export into a plugin-ready algorithm module from the QGIS Processing Toolbox:

```text
Processing Toolbox -> Scripts -> Tools -> Convert Model To Plugin Algorithm
```

- Point the tool at a `.model3` file or an exported Processing `.py` script and choose the destination Python file inside `algorithms/`.
- The same converter can also be run from the command line:

```bash
python3 scripts/validate_algorithms.py path/to/model.model3 --subdir hydrology
```

- Review and smoke-test the generated algorithm in QGIS before shipping.
- Use the import checklist in [`docs/ALGORITHM_IMPORT_CHECKLIST.md`](docs/ALGORITHM_IMPORT_CHECKLIST.md) when adding or updating algorithms.

## Support & Contribution
- Tracker / Website: https://www.regengis.com
- Email: info@regengis.com

## License
This project is licensed under the Mozilla Public License 2.0 (see `LICENSE`).
