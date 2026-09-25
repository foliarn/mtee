"""Application entry point.

``main`` assembles the services, the Qt models and the QML window. A fatal
resource or storage failure returns a non zero exit code with an explanation in
English on the standard error output.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, QTimer, QUrl
from PySide6.QtGui import QFont, QGuiApplication, QWindow
from PySide6.QtQml import QQmlApplicationEngine

from mtee import __version__
from mtee.assets import main_qml, qml_dir
from mtee.cli import AppOptions, parse_arguments
from mtee.domain.analysis import AnalysisSpec
from mtee.domain.jobs import JobCancelledError
from mtee.domain.tracks import SourceRevision, sha256_of_file
from mtee.fonts import register_fonts, resolve_ui_family
from mtee.models.analysis_model import AnalysisModel
from mtee.models.artwork_provider import ARTWORK_PROVIDER_ID, ArtworkProvider
from mtee.models.conversion_queue_model import ConversionQueueModel
from mtee.models.demo_tracks_model import DemoTracksModel
from mtee.models.demo_workspace import DemoWorkspace
from mtee.models.file_operation_model import FileOperationModel
from mtee.models.icon_provider import ICON_PROVIDER_ID, IconProvider
from mtee.models.jobs_model import JobsListModel
from mtee.models.metadata_editor_model import MetadataEditorModel
from mtee.models.player_model import PlayerModel
from mtee.models.shell_controller import ShellController
from mtee.models.waveform_model import WaveformModel
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.analysis_repository import AnalysisRepository
from mtee.persistence.database import Database, DatabaseError
from mtee.persistence.derivations_repository import DerivationsRepository
from mtee.persistence.file_operation_repository import FileOperationRepository
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.metadata_history_repository import MetadataHistoryRepository
from mtee.persistence.settings_repository import SettingsRepository
from mtee.persistence.workspace_repository import WorkspaceRepository
from mtee.platform.windows_frame import WindowFrame
from mtee.services.analysis_service import AnalysisService
from mtee.services.app_paths import AppPaths, resolve_app_paths
from mtee.services.conversion_service import ConversionService
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.file_operation_service import FileOperationService
from mtee.services.jobs import JobService
from mtee.services.metadata_reader import MetadataReader
from mtee.services.metadata_writer import MetadataEditService
from mtee.services.mpv_backend import MpvBackend
from mtee.services.player_backend import PlayerBackendError
from mtee.services.player_service import PlayerService

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
    player_service: PlayerService | None
    engine: QQmlApplicationEngine
    controller: ShellController
    jobs_model: JobsListModel
    tracks_model: DemoTracksModel
    workspace: QObject
    frame: WindowFrame
    artwork_provider: ArtworkProvider | None


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
    if options.analysis_smoke_test is not None:
        if options.data_dir is None:
            return _fail(
                EXIT_STORAGE_ERROR, "--analysis-smoke-test requires an isolated --data-dir."
            )
        return _analysis_smoke_test(options.analysis_smoke_test, options.data_dir)
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
    artwork_provider = None
    player_service = None
    if options.demo:
        workspace: QObject = DemoWorkspace(options.scenario)
    else:
        library = LibraryRepository(database)
        workspace_repository = WorkspaceRepository(database)
        file_access = FileAccessCoordinator()
        backend = None
        backend_error = ""
        try:
            backend = MpvBackend()
        except PlayerBackendError as error:
            backend_error = str(error)
        player_service = PlayerService(
            library.track,
            file_access,
            backend,
            backend_error=backend_error,
            parent=application,
        )
        waveform_model = WaveformModel(
            player_service, library, jobs, file_access, paths.cache_dir, application
        )
        player_model = PlayerModel(player_service, application, waveform=waveform_model)
        workspace = WorkspaceModel(
            library=library,
            session=workspace_repository,
            jobs=jobs,
            player=player_model,
        )
        analysis_model = AnalysisModel(
            AnalysisService(library, AnalysisRepository(database), file_access),
            jobs,
            workspace.selected_ids_snapshot,
            workspace,
        )
        workspace.attach_analysis_model(analysis_model)
        metadata_writer = MetadataEditService(
            library,
            MetadataHistoryRepository(database),
            file_access,
        )
        metadata_editor = MetadataEditorModel(
            library,
            metadata_writer,
            jobs,
            workspace.selected_ids_snapshot,
            player=player_model,
        )
        workspace.attach_metadata_editor(metadata_editor)
        conversion_model = ConversionQueueModel(
            library,
            jobs,
            ConversionService(),
            file_access,
            DerivationsRepository(database),
            application,
        )
        workspace.attach_conversion_model(conversion_model)
        file_operations = FileOperationModel(
            FileOperationService(
                library,
                FileOperationRepository(database, library),
                file_access,
            ),
            jobs,
            player=player_model,
        )
        workspace.attach_file_operations(file_operations)
        artwork_provider = ArtworkProvider(library)
    frame = WindowFrame()
    controller = ShellController(
        paths=paths,
        settings=settings,
        jobs=jobs,
        demo_mode=options.demo,
        font_family=font_family,
    )

    engine = QQmlApplicationEngine()
    engine.addImportPath(str(qml_dir()))
    engine.addImageProvider(ICON_PROVIDER_ID, IconProvider())
    if artwork_provider is not None:
        engine.addImageProvider(ARTWORK_PROVIDER_ID, artwork_provider)
    context = engine.rootContext()
    context.setContextProperty("shell", controller)
    context.setContextProperty("jobsModel", jobs_model)
    context.setContextProperty("tracksModel", tracks_model)
    context.setContextProperty("workspace", workspace)
    context.setContextProperty("windowFrame", frame)

    window_file = main_qml()
    if not window_file.is_file():
        _report(f"MTEE cannot find its interface file: {window_file}")
        _discard_partial_startup(database, jobs, player_service, engine)
        return None
    engine.load(QUrl.fromLocalFile(str(window_file)))
    if not engine.rootObjects():
        _report(f"MTEE could not load its interface from {window_file}")
        _discard_partial_startup(database, jobs, player_service, engine)
        return None
    window = engine.rootObjects()[0]
    if isinstance(window, QWindow) and not options.diagnostic_no_native_frame:
        frame.attach(window)

    runtime = _Runtime(
        paths=paths,
        database=database,
        jobs=jobs,
        player_service=player_service,
        engine=engine,
        controller=controller,
        jobs_model=jobs_model,
        tracks_model=tracks_model,
        workspace=workspace,
        frame=frame,
        artwork_provider=artwork_provider,
    )
    if isinstance(workspace, WorkspaceModel):
        workspace.resumeRoots()
    return runtime


def _shutdown(runtime: _Runtime) -> None:
    """Stop the background work and close the storage before leaving."""
    runtime.frame.detach()
    _shutdown_services(runtime.database, runtime.jobs, runtime.player_service)


def _discard_partial_startup(
    database: Database,
    jobs: JobService,
    player_service: PlayerService | None,
    engine: QQmlApplicationEngine,
) -> None:
    """Release native services if startup fails before a runtime is returned."""
    _shutdown_services(database, jobs, player_service)
    engine.deleteLater()


def _shutdown_services(
    database: Database,
    jobs: JobService,
    player_service: PlayerService | None,
) -> None:
    if player_service is not None:
        try:
            player_service.close()
        except Exception as error:
            _report(f"The audio player did not close cleanly: {error}")
    interrupted = jobs.shutdown(_SHUTDOWN_TIMEOUT_MS)
    for status in interrupted:
        _report(f"Background task not finished: {status.label} ({status.state.value}).")
    if jobs.wait_for_done(0):
        database.close()
    else:
        # A timed out worker may still use its SQLite connection. Keeping the
        # database open until process exit is safer than invalidating it under
        # that worker; the diagnostic makes this incomplete shutdown visible.
        _report("Background workers are still stopping; SQLite remains open until process exit.")


def _report(message: str) -> None:
    """Write an explanation for the user on the standard error output."""
    if sys.stderr is not None:
        print(message, file=sys.stderr)


def _fail(exit_code: int, message: str) -> int:
    """Report ``message`` and return ``exit_code``."""
    _report(message)
    return exit_code


class _SmokeAnalysisContext:
    is_cancelled = False

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise JobCancelledError("analysis smoke test cancelled")

    def report_progress(self, _progress: float) -> None:
        return


def _analysis_smoke_test(audio_path: Path, data_dir: Path) -> int:
    """Run all packaged analyzers against one explicitly supplied local fixture."""
    from mtee.persistence.analysis_repository import AnalysisRepository
    from mtee.services.analysis_service import AnalysisService

    source = audio_path.expanduser().resolve()
    if not source.is_file():
        return _fail(EXIT_RESOURCE_ERROR, f"Analysis fixture is unavailable: {source}")
    database = Database(resolve_app_paths(data_dir).ensure().database_path)
    try:
        database.migrate()
        library = LibraryRepository(database)
        root = library.add_root(source.parent)
        generation = library.begin_scan(str(root["id"]))
        track_id = library.upsert_location(
            str(root["id"]),
            source.name,
            source,
            SourceRevision.observe(source),
            MetadataReader().read(source),
            generation,
        )
        library.upsert_folders(str(root["id"]), [], generation)
        library.finish_scan(str(root["id"]), generation, complete=True)
        digest_before = sha256_of_file(source)
        service = AnalysisService(library, AnalysisRepository(database), FileAccessCoordinator())
        specs = [
            AnalysisSpec(name) for name in ("technical", "silence", "loudness", "tempo", "key")
        ]
        preview = service.preview([track_id], specs)
        service.execute(preview, _SmokeAnalysisContext())
        results = service.results(track_id)
        digest_after = sha256_of_file(source)
        report = {
            "analyzers": [
                {
                    "name": item["analyzer"],
                    "version": item["analyzer_version"],
                    "status": item["status"],
                    "metrics": item["metrics"],
                    "diagnostics": item["diagnostics"],
                }
                for item in results
            ],
            "source_unchanged": digest_before == digest_after,
        }
        if sys.stdout is not None:
            print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        expected = {spec.analyzer for spec in specs}
        received = {item["analyzer"] for item in results}
        if received != expected or not report["source_unchanged"]:
            return EXIT_RESOURCE_ERROR
        if any(item["status"] in {"failed", "stale"} for item in results):
            return EXIT_RESOURCE_ERROR
        return EXIT_OK
    except Exception as error:
        return _fail(EXIT_RESOURCE_ERROR, f"Audio analysis validation failed: {error}")
    finally:
        database.close()
