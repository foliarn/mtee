"""Application entry point.

``main`` assembles the services, the Qt models and the QML window. A fatal
resource or storage failure returns a non zero exit code with an explanation in
English on the standard error output.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import QCoreApplication, QTimer, QUrl
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from mtee import __version__
from mtee.assets import main_qml, qml_dir
from mtee.cli import AppOptions, parse_arguments
from mtee.fonts import register_fonts, resolve_ui_family
from mtee.models.demo_tracks_model import DemoTracksModel
from mtee.models.demo_workspace import DemoWorkspace
from mtee.models.jobs_model import JobsListModel
from mtee.models.shell_controller import ShellController
from mtee.persistence.database import Database, DatabaseError
from mtee.persistence.settings_repository import SettingsRepository
from mtee.services.app_paths import AppPaths, resolve_app_paths
from mtee.services.jobs import JobService

__all__ = ["EXIT_OK", "create_application", "main", "run"]

ORGANIZATION_NAME = "MTEE"
ORGANIZATION_DOMAIN = "mtee.local"
APPLICATION_NAME = "MTEE"

EXIT_OK = 0
EXIT_STORAGE_ERROR = 3
EXIT_RESOURCE_ERROR = 4
_SHUTDOWN_TIMEOUT_MS = 5_000
_BASE_FONT_POINT_SIZE = 10


@dataclass(slots=True)
class _Runtime:
    """Objects kept alive for the whole run.

    The Qt models are referenced here: the QML context does not own them, and a
    model left to the garbage collector empties its view.
    """

    paths: AppPaths
    database: Database
    jobs: JobService
    engine: QQmlApplicationEngine
    controller: ShellController
    jobs_model: JobsListModel
    tracks_model: DemoTracksModel
    workspace: DemoWorkspace


def create_application(argv: Sequence[str] | None = None) -> QGuiApplication:
    """Return the Qt application, creating it when none exists yet."""
    existing = QCoreApplication.instance()
    if isinstance(existing, QGuiApplication):
        return existing
    QCoreApplication.setOrganizationName(ORGANIZATION_NAME)
    QCoreApplication.setOrganizationDomain(ORGANIZATION_DOMAIN)
    QCoreApplication.setApplicationName(APPLICATION_NAME)
    QCoreApplication.setApplicationVersion(__version__)
    return QGuiApplication(list(argv) if argv is not None else [])


def main(argv: Sequence[str] | None = None) -> int:
    """Run MTEE and return its exit code."""
    arguments = list(argv if argv is not None else sys.argv)
    options = parse_arguments(arguments[1:])
    application = create_application(arguments[:1])

    try:
        runtime = _build_runtime(application, options)
    except DatabaseError as error:
        return _fail(EXIT_STORAGE_ERROR, str(error))
    except OSError as error:
        return _fail(EXIT_STORAGE_ERROR, f"MTEE cannot use its data directory: {error}")

    if runtime is None:
        return EXIT_RESOURCE_ERROR

    if options.smoke_test:
        QTimer.singleShot(0, application.quit)

    exit_code = application.exec()
    _shutdown(runtime)
    return exit_code


def run() -> None:
    """Console entry point declared by the project."""
    raise SystemExit(main(sys.argv))


def _build_runtime(application: QGuiApplication, options: AppOptions) -> _Runtime | None:
    """Create the services, the models and the window; ``None`` on a QML failure."""
    paths = resolve_app_paths(options.data_dir, demo=options.demo).ensure()

    database = Database(paths.database_path)
    database.migrate()
    settings = SettingsRepository(database)

    families = register_fonts()
    font_family = resolve_ui_family(families)
    application.setFont(QFont(font_family, _BASE_FONT_POINT_SIZE))

    jobs = JobService(application)
    jobs_model = JobsListModel(jobs)
    tracks_model = DemoTracksModel()
    workspace = DemoWorkspace(options.scenario if options.demo else "browser")
    controller = ShellController(
        paths=paths,
        settings=settings,
        jobs=jobs,
        demo_mode=options.demo,
        font_family=font_family,
    )

    engine = QQmlApplicationEngine()
    engine.addImportPath(str(qml_dir()))
    context = engine.rootContext()
    context.setContextProperty("shell", controller)
    context.setContextProperty("jobsModel", jobs_model)
    context.setContextProperty("tracksModel", tracks_model)
    context.setContextProperty("workspace", workspace)

    window_file = main_qml()
    if not window_file.is_file():
        _report(f"MTEE cannot find its interface file: {window_file}")
        return None
    engine.load(QUrl.fromLocalFile(str(window_file)))
    if not engine.rootObjects():
        _report(f"MTEE could not load its interface from {window_file}")
        return None

    return _Runtime(
        paths=paths,
        database=database,
        jobs=jobs,
        engine=engine,
        controller=controller,
        jobs_model=jobs_model,
        tracks_model=tracks_model,
        workspace=workspace,
    )


def _shutdown(runtime: _Runtime) -> None:
    """Stop the background work and close the storage before leaving."""
    interrupted = runtime.jobs.shutdown(_SHUTDOWN_TIMEOUT_MS)
    for status in interrupted:
        _report(f"Background task not finished: {status.label} ({status.state.value}).")
    runtime.database.close()


def _report(message: str) -> None:
    """Write an explanation for the user on the standard error output."""
    print(message, file=sys.stderr)


def _fail(exit_code: int, message: str) -> int:
    """Report ``message`` and return ``exit_code``."""
    _report(message)
    return exit_code
