"""Application entry point.

``main`` assembles the services, the Qt models and the QML window. A fatal
resource or storage failure returns a non zero exit code with an explanation in
English on the standard error output.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QTimer, QUrl
from PySide6.QtGui import QFont, QGuiApplication, QWindow
from PySide6.QtQml import QQmlApplicationEngine

from mtee import __version__
from mtee.assets import main_qml, qml_dir
from mtee.cli import AppOptions, parse_arguments
from mtee.fonts import register_fonts, resolve_ui_family
from mtee.models.analysis_model import AnalysisModel
from mtee.models.analysis_settings_model import AnalysisSettingsModel
from mtee.models.artist_manager_model import ArtistManagerModel
from mtee.models.artwork_provider import ARTWORK_PROVIDER_ID, ArtworkProvider
from mtee.models.conversion_queue_model import ConversionQueueModel
from mtee.models.cover_accent_model import CoverAccentModel
from mtee.models.demo_tracks_model import DemoTracksModel
from mtee.models.demo_workspace import DemoWorkspace
from mtee.models.file_move_model import FileMoveModel
from mtee.models.icon_provider import ICON_PROVIDER_ID, IconProvider
from mtee.models.jobs_model import JobsListModel
from mtee.models.metadata_editor_model import MetadataEditorModel
from mtee.models.player_model import PlayerModel
from mtee.models.playlists_model import PlaylistsModel
from mtee.models.shell_controller import ShellController
from mtee.models.tag_conflicts_model import TagConflictsModel
from mtee.models.trash_model import TrashModel
from mtee.models.waveform_model import WaveformModel
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.analysis_repository import AnalysisRepository
from mtee.persistence.artist_repository import ArtistRepository
from mtee.persistence.database import Database, DatabaseError
from mtee.persistence.derivations_repository import DerivationsRepository
from mtee.persistence.library_repository import LibraryRepository
from mtee.persistence.metadata_history_repository import MetadataHistoryRepository
from mtee.persistence.play_log_repository import PlayLogRepository, load_or_create_device_id
from mtee.persistence.playback_repository import (
    PlaybackRepository,
    PlaybackSessionError,
)
from mtee.persistence.playlists_repository import PlaylistsRepository
from mtee.persistence.settings_repository import SettingsRepository
from mtee.persistence.trash_repository import TrashRepository
from mtee.persistence.workspace_repository import WorkspaceRepository
from mtee.platform.windows_frame import WindowFrame
from mtee.plugins.registry import load_plugin
from mtee.services.analysis_service import AnalysisService
from mtee.services.app_paths import AppPaths, resolve_app_paths
from mtee.services.artist_file_service import ArtistFileService
from mtee.services.artist_identification_service import ArtistIdentificationService
from mtee.services.artist_manager_service import ArtistManagerService
from mtee.services.audio_analyzer import AudioAnalyzer
from mtee.services.conversion_service import ConversionService
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.file_move_service import FileMoveService
from mtee.services.jobs import JobService
from mtee.services.media_decode_service import MediaDecodeService
from mtee.services.metadata_writer import MetadataEditService
from mtee.services.mpv_backend import MpvBackend
from mtee.services.player_backend import PlayerBackendError
from mtee.services.player_service import PlayerService
from mtee.services.playlist_exchange import PlaylistExchange
from mtee.services.playlist_service import PlaylistService
from mtee.services.trash_service import TrashService

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
    _destroy_windows(runtime)
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
    analysis_settings = AnalysisSettingsModel(settings, application)

    families = register_fonts()
    font_family = resolve_ui_family(families)
    application.setFont(QFont(font_family, _BASE_FONT_POINT_SIZE))

    jobs = JobService(application)
    jobs_model = JobsListModel(jobs)
    tracks_model = DemoTracksModel()
    artwork_provider = None
    player_service = None
    workspace: QObject | None = None
    if options.demo:
        workspace = DemoWorkspace(options.scenario)
        workspace.attach_analysis_settings(analysis_settings, TagConflictsModel(parent=application))
    else:
        library = LibraryRepository(database)
        analysis_repository = AnalysisRepository(database)
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
        playback_repository = PlaybackRepository(database)
        try:
            saved_playback = playback_repository.load()
        except PlaybackSessionError as error:
            _report(str(error))
            saved_playback = None
        player_service.attach_settings(settings)
        player_service.attach_session(playback_repository, saved_playback)
        player_service.attach_play_log(
            PlayLogRepository(database), load_or_create_device_id(settings)
        )
        waveform_model = WaveformModel(
            player_service, library, jobs, file_access, analysis_repository, application
        )
        accent_model = CoverAccentModel(player_service, library, application)
        player_model = PlayerModel(
            player_service, application, waveform=waveform_model, accent=accent_model
        )
        workspace = WorkspaceModel(
            library=library,
            session=workspace_repository,
            jobs=jobs,
            player=player_model,
        )
        workspace.attach_genre_manager_factory(
            lambda: load_plugin(
                "genre_manager", database, library, PlaylistsRepository(database), file_access
            )
        )
        playlist_service = PlaylistService(PlaylistsRepository(database), library)
        playlists_model = PlaylistsModel(
            playlist_service, settings, jobs, paths.database_path.parent
        )
        playlists_model.exchange = PlaylistExchange(
            playlist_service, file_access, paths.database_path.parent
        )
        playlists_model.refresh()
        workspace.attach_playlists(playlists_model)
        artist_repository = ArtistRepository(database)
        identification = ArtistIdentificationService(library, artist_repository)
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
            analysis=analysis_repository,
            analysis_settings=lambda: analysis_settings.settings,
            artists=identification,
        )
        workspace.attach_metadata_editor(metadata_editor)
        analysis_service = AnalysisService(
            library,
            analysis_repository,
            AudioAnalyzer(MediaDecodeService(file_access), file_access),
            metadata_writer,
            identification,
        )
        analysis_model = AnalysisModel(
            library,
            analysis_service,
            jobs,
            analysis_settings,
            application,
            identification=identification,
        )
        workspace.attach_analysis(
            analysis_settings,
            analysis_model,
            TagConflictsModel(jobs, analysis_service.resolve_tag_conflict, application),
        )
        workspace.attach_artist_manager(
            ArtistManagerModel(
                ArtistManagerService(
                    artist_repository,
                    ArtistFileService(
                        database, library, artist_repository, metadata_writer, file_access
                    ),
                ),
                jobs,
                analysis_model,
            )
        )
        conversion_model = ConversionQueueModel(
            library,
            jobs,
            ConversionService(),
            file_access,
            DerivationsRepository(database),
            application,
        )
        workspace.attach_conversion_model(conversion_model)
        trash_model = TrashModel(
            library,
            jobs,
            TrashService(),
            file_access,
            TrashRepository(database),
            player=player_model,
        )
        workspace.attach_trash_model(trash_model)
        workspace.attach_file_move_model(
            FileMoveModel(FileMoveService(database, library, file_access), jobs)
        )
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
    qml_diagnostics: list[str] = []

    def capture_qml_diagnostics(warnings: Sequence) -> None:
        qml_diagnostics.extend(error.toString() for error in warnings)

    engine.warnings.connect(capture_qml_diagnostics)
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
        _discard_partial_startup(database, jobs, player_service, engine, workspace)
        return None
    engine.load(QUrl.fromLocalFile(str(window_file)))
    engine.warnings.disconnect(capture_qml_diagnostics)
    if not engine.rootObjects():
        for diagnostic in qml_diagnostics:
            _report(diagnostic)
        _report(f"MTEE could not load its interface from {window_file}")
        _discard_partial_startup(database, jobs, player_service, engine, workspace)
        return None
    window = engine.rootObjects()[0]
    if isinstance(window, QWindow) and isinstance(workspace, WorkspaceModel):
        window.installEventFilter(workspace)
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


def _destroy_windows(runtime: _Runtime) -> None:
    """Delete the QML windows while the context still holds the models.

    Letting the engine tear everything down at exit nulls the context properties first,
    so the bindings of the still living window log a TypeError each.
    """
    for window in runtime.engine.rootObjects():
        window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _shutdown(runtime: _Runtime) -> None:
    """Stop the background work and close the storage before leaving."""
    if isinstance(runtime.workspace, WorkspaceModel):
        playlist_model = runtime.workspace.playlistModel
        if isinstance(playlist_model, PlaylistsModel):
            playlist_model.flush_pending()
        runtime.workspace.flush_session()
    runtime.jobs.begin_shutdown()
    runtime.frame.detach()
    _shutdown_services(runtime.database, runtime.jobs, runtime.player_service)


def _discard_partial_startup(
    database: Database,
    jobs: JobService,
    player_service: PlayerService | None,
    engine: QQmlApplicationEngine,
    workspace: QObject | None = None,
) -> None:
    """Release native services if startup fails before a runtime is returned."""
    if isinstance(workspace, WorkspaceModel):
        workspace.flush_session()
    _shutdown_services(database, jobs, player_service)
    engine.deleteLater()


def _shutdown_services(
    database: Database,
    jobs: JobService,
    player_service: PlayerService | None,
) -> None:
    jobs.begin_shutdown()
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
