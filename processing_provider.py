# =============================================================================
# MODULE: processing_provider.py
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import inspect
import logging
import sys
import traceback
from pathlib import Path

from PyQt5.QtGui import QIcon
from qgis.core import QgsProcessingAlgorithm, QgsProcessingProvider

from . import algorithms as algorithms_pkg

logger = logging.getLogger(__name__)
PLUGIN_ICON_PATH = Path(__file__).parent / "icon.png"


@dataclass(frozen=True)
class AlgorithmLoadIssue:
    stage: str
    module_path: str
    module_name: str
    class_name: str | None
    error_type: str
    error_message: str
    traceback_text: str


class ModelToolboxProvider(QgsProcessingProvider):
    """Processing provider that exposes the packaged algorithms."""

    def __init__(self):
        super().__init__()
        self._load_issues: list[AlgorithmLoadIssue] = []

    def id(self) -> str:
        return "regengis_toolbox"

    def name(self) -> str:
        return "Landscape Analysis Toolkit - RegenGIS.com"

    def longName(self) -> str:
        return "Landscape Analysis Toolkit - RegenGIS.com"

    def icon(self) -> QIcon:
        """Return the provider icon from icon.png if available."""
        if PLUGIN_ICON_PATH.exists():
            return QIcon(str(PLUGIN_ICON_PATH))
        return super().icon()

    def _algorithm_icon(self) -> QIcon | None:
        """Return the shared plugin icon for individual processing tools."""
        if not PLUGIN_ICON_PATH.exists():
            return None
        return QIcon(str(PLUGIN_ICON_PATH))

    def loadAlgorithms(self) -> None:
        """Register algorithms shipped with this plugin.

        Recursively discovers QgsProcessingAlgorithm subclasses from Python files
        under the algorithms folder, using folder names as group names.
        """
        self._load_issues = []
        algorithms_dir = Path(algorithms_pkg.__file__).resolve().parent
        for module_path in sorted(self._iter_algorithm_files(algorithms_dir)):
            group_prefix = self._group_prefix_for_path(algorithms_dir, module_path)
            self._load_algorithm_from_path(module_path, group_prefix)

        if self._load_issues:
            logger.warning(
                "RegenGIS Processing provider loaded with %d issue(s). First issue: [%s] %s (%s)",
                len(self._load_issues),
                self._load_issues[0].stage,
                self._load_issues[0].module_path,
                self._load_issues[0].error_message,
            )

    def load_issues(self) -> list[AlgorithmLoadIssue]:
        """Return structured diagnostics for algorithm load failures."""
        return list(self._load_issues)

    def _iter_algorithm_files(self, algorithms_dir: Path):
        """Yield candidate algorithm files from disk."""
        for path in algorithms_dir.rglob("*.py"):
            if path.name == "__init__.py":
                continue
            if "__pycache__" in path.parts:
                continue
            if any(part.startswith(".") for part in path.parts):
                continue
            yield path

    def _group_prefix_for_path(self, algorithms_dir: Path, module_path: Path) -> str:
        """Return the display group derived from the module's relative folder path."""
        relative_parent = module_path.relative_to(algorithms_dir).parent
        if str(relative_parent) == ".":
            return ""

        return "/".join(part.replace("_", " ").title() for part in relative_parent.parts)

    def _record_issue(
        self,
        *,
        stage: str,
        module_path: Path,
        module_name: str,
        exc: Exception,
        class_name: str | None = None,
    ) -> None:
        issue = AlgorithmLoadIssue(
            stage=stage,
            module_path=str(module_path),
            module_name=module_name,
            class_name=class_name,
            error_type=type(exc).__name__,
            error_message=str(exc),
            traceback_text=traceback.format_exc(),
        )
        self._load_issues.append(issue)
        logger.warning(
            "Failed to %s algorithm module '%s'%s: %s: %s",
            stage,
            module_path,
            f" ({class_name})" if class_name else "",
            issue.error_type,
            issue.error_message,
        )
        logger.debug("Algorithm load traceback for %s:\n%s", module_path, issue.traceback_text)

    def _load_algorithm_from_path(self, module_path: Path, group_prefix: str = "") -> None:
        """Load and register algorithms from a single Python file."""
        relative_module = module_path.relative_to(Path(__file__).resolve().parent)
        module_name = ".".join((__package__,) + relative_module.with_suffix("").parts)

        try:
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Could not create import spec for '{module_path}'.")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            try:
                spec.loader.exec_module(module)
            except Exception:
                sys.modules.pop(module_name, None)
                raise
        except Exception as exc:
            self._record_issue(
                stage="import",
                module_path=module_path,
                module_name=module_name,
                exc=exc,
            )
            return

        for _, obj in inspect.getmembers(module, inspect.isclass):
            try:
                if issubclass(obj, QgsProcessingAlgorithm) and obj is not QgsProcessingAlgorithm:
                    alg = obj()
                    if group_prefix:
                        alg.group = lambda: group_prefix
                        alg.groupId = lambda: group_prefix.lower().replace(" ", "_").replace("/", "_")
                    shared_icon = self._algorithm_icon()
                    if shared_icon is not None:
                        alg.icon = lambda shared_icon=shared_icon: shared_icon
                    self.addAlgorithm(alg)
                    logger.debug("Registered algorithm: %s (group: %s)", alg.displayName(), alg.group())
            except Exception as exc:
                self._record_issue(
                    stage="instantiate",
                    module_path=module_path,
                    module_name=module_name,
                    class_name=getattr(obj, "__name__", None),
                    exc=exc,
                )
                continue
