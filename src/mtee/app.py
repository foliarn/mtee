"""Application entry point.

``main`` assembles the services, the Qt models and the QML window. A fatal
resource or storage failure returns a non zero exit code with an explanation in
English on the standard error output.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QTimer, QUrl
from PySide6.QtGui import QFont, QGuiApplication, QWindow
from PySide6.QtQml import QQmlApplicationEngine

from mtee import __version__
from mtee.assets import main_qml, qml_dir
from mtee.cli import AppOptions, parse_arguments
from mtee.fonts import register_fonts, resolve_ui_family
from mtee.models.analysis_model import AnalysisModel
from mtee.models.analysis_settings_model import AnalysisSettingsModel
from mtee.models.artist_rules_model import ArtistRulesModel
from mtee.models.artwork_provider import ARTWORK_PROVIDER_ID, ArtworkProvider
from mtee.models.conversion_queue_model import ConversionQueueModel
from mtee.models.cover_accent_model import CoverAccentModel
from mtee.models.data_privacy_model import DataPrivacyModel
from mtee.models.demo_workspace import DemoWorkspace
from mtee.models.file_move_model import FileMoveModel
from mtee.models.icon_provider import ICON_PROVIDER_ID, IconProvider
from mtee.models.jobs_model import JobsListModel
from mtee.models.metadata_editor_model import MetadataEditorModel
from mtee.models.playback_settings_model import PlaybackSettingsModel
from mtee.models.player_model import PlayerModel
from mtee.models.playlists_model import PlaylistsModel
from mtee.models.profile_model import PROFILE_PROVIDER_ID, ProfileAvatarProvider, ProfileModel
from mtee.models.shell_controller import ShellController
from mtee.models.statistics_model import StatisticsModel
from mtee.models.tag_conflicts_model import TagConflictsModel
from mtee.models.trash_model import TrashModel
from mtee.models.waveform_model import WaveformModel
from mtee.models.workspace_model import WorkspaceModel
from mtee.persistence.analysis_repository import AnalysisRepository
from mtee.persistence.credit_override_repository import CreditOverrideRepository
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
from mtee.platform.media_transport import create_media_transport
from mtee.platform.windows_frame import WindowFrame
from mtee.plugins.registry import load_plugin, plugin_ui_enabled
from mtee.services.analysis_service import AnalysisService
from mtee.services.app_paths import AppPaths, resolve_app_paths
from mtee.services.artist_index_service import ArtistIndexService
from mtee.services.audio_analyzer import AudioAnalyzer
from mtee.services.conversion_service import ConversionService
from mtee.services.data_privacy import RestoreLayout, apply_pending_restore
from mtee.services.file_access import FileAccessCoordinator
from mtee.services.file_move_service import FileMoveService
from mtee.services.jobs import JobService
from mtee.services.main_thread_gc import install_main_thread_gc
from mtee.services.media_controls import MediaControls
from mtee.services.media_decode_service import MediaDecodeService
from mtee.services.metadata_writer import MetadataEditService
from mtee.services.mpv_backend import MpvBackend
from mtee.services.player_backend import PlayerBackendError
from mtee.services.player_service import PlayerService
from mtee.services.playlist_exchange import PlaylistExchange
from mtee.services.playlist_service import PlaylistService
from mtee.services.profile_service import PROFILE_DIRECTORY_NAME, ProfileService
from mtee.services.trash_service import TrashService

if TYPE_CHECKING:
    from mtee.plugins.artist_manager.identification import ArtistIdentificationService

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
    workspace: QObject
    frame: WindowFrame
    artwork_provider: ArtworkProvider | None
    media_controls: MediaControls | None


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
    # Before any worker starts: a Qt object freed by a collection on a worker thread
    # leaves dangling registrations in the event dispatcher of this thread.
    install_main_thread_gc(application)
    paths = resolve_app_paths(options.data_dir, demo=options.demo).ensure()

    database = Database(paths.database_path)
    _apply_scheduled_restore(paths, database)
    database.migrate()
    settings = SettingsRepository(database)
    analysis_settings = AnalysisSettingsModel(settings, application)
    playback_settings = PlaybackSettingsModel(settings, application)

    families = register_fonts()
    font_family = resolve_ui_family(families)
    application.setFont(QFont(font_family, _BASE_FONT_POINT_SIZE))

    jobs = JobService(application)
    jobs_model = JobsListModel(jobs)
    artwork_provider = None
    media_controls: MediaControls | None = None
    player_service = None
    workspace: QObject | None = None
    profile_model: ProfileModel | None = None
    profile_avatar: ProfileAvatarProvider | None = None
    statistics_model: StatisticsModel | None = None
    data_privacy_model: DataPrivacyModel | None = None
    artist_rules_model: ArtistRulesModel | None = None
    if options.demo:
        workspace = DemoWorkspace(options.scenario)
        workspace.attach_analysis_settings(analysis_settings, TagConflictsModel(parent=application))
        workspace.attach_playback_settings(playback_settings)
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
        # The normalization choices are in place before a restored track is opened.
        player_service.set_normalization(playback_settings.settings)
        playback_settings.changed.connect(
            lambda: player_service.set_normalization(playback_settings.settings)
        )
        player_service.attach_session(playback_repository, saved_playback)
        play_log = PlayLogRepository(database)
        player_service.attach_play_log(play_log, load_or_create_device_id(settings))
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
        workspace.attach_playback_settings(playback_settings)
        # The core artist index: the Artists view, the artist links, the tag editor and the
        # top artists cut credits with the same rules. It is rebuilt off the graphical thread
        # after each library change, and the statistics follow each finished build.
        artist_index = ArtistIndexService(
            library, CreditOverrideRepository(database), jobs, parent=workspace
        )
        workspace.attach_artist_index(artist_index)
        workspace.libraryChanged.connect(artist_index.refresh)
        workspace.scanFinished.connect(lambda *_arguments: artist_index.refresh())
        artist_index.refresh()
        # Plugins load only when the plugin switch is on; v0.1 builds none of them.
        plugins_enabled = plugin_ui_enabled()
        if plugins_enabled:
            workspace.attach_genre_manager_factory(
                lambda: load_plugin(
                    "genre_manager", database, library, PlaylistsRepository(database), file_access
                )
            )
        # The profile first: its constructor moves the former playlist creator name.
        profile = ProfileService(settings, paths.data_dir / PROFILE_DIRECTORY_NAME)
        profile_model = ProfileModel(profile, jobs, application)
        profile_avatar = ProfileAvatarProvider(profile)
        profile_avatar.setParent(application)
        statistics_model = StatisticsModel(
            play_log,
            jobs,
            application,
            artist_rules=artist_index.rules,
        )
        artist_index.indexChanged.connect(statistics_model.followArtistRules)
        data_privacy_model = DataPrivacyModel(
            database,
            RestoreLayout(paths.data_dir),
            play_log,
            jobs,
            application,
        )
        # A stored listening updates the Profile statistics and the listening columns.
        player_service.playLogWritten.connect(
            lambda: _refresh_after_listening(statistics_model, jobs)
        )
        player_service.playLogWritten.connect(workspace.refreshPlayStats)
        # Reset statistics (and any other privacy action) ends with a fresh read.
        data_privacy_model.finished.connect(lambda _message: statistics_model.refresh())
        workspace.attach_play_log(play_log)
        playlist_service = PlaylistService(PlaylistsRepository(database), library)
        playlists_model = PlaylistsModel(
            playlist_service, settings, jobs, paths.database_path.parent
        )
        playlists_model.exchange = PlaylistExchange(
            playlist_service, file_access, paths.database_path.parent
        )
        profile_model.nameChanged.connect(lambda _name: playlists_model.refresh())
        playlists_model.refresh()
        workspace.attach_playlists(playlists_model)
        identification = _artist_identification(database, library) if plugins_enabled else None
        metadata_writer = MetadataEditService(
            library,
            MetadataHistoryRepository(database),
            file_access,
        )
        artist_rules_model = ArtistRulesModel(artist_index, application)
        metadata_editor = MetadataEditorModel(
            library,
            metadata_writer,
            jobs,
            workspace.selected_ids_snapshot,
            player=player_model,
            analysis=analysis_repository,
            analysis_settings=lambda: analysis_settings.settings,
            artist_rules=artist_index,
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
        if plugins_enabled:
            _attach_artist_manager(
                workspace,
                database,
                library,
                metadata_writer,
                file_access,
                jobs,
                analysis_model,
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
        # Never fatal: without the system controls the application keeps working.
        media_controls = MediaControls(
            player_service, library, create_media_transport(), application
        )
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
    if profile_avatar is not None:
        engine.addImageProvider(PROFILE_PROVIDER_ID, profile_avatar)
    context = engine.rootContext()
    context.setContextProperty("shell", controller)
    context.setContextProperty("jobsModel", jobs_model)
    context.setContextProperty("workspace", workspace)
    context.setContextProperty("windowFrame", frame)
    # Models of the Profile and Settings pages (plans 114-115). Demo mode has none of them.
    for name, model in (
        ("profile", profile_model),
        ("statistics", statistics_model),
        ("dataPrivacy", data_privacy_model),
        ("artistRules", artist_rules_model),
    ):
        if model is not None:
            context.setContextProperty(name, model)

    window_file = main_qml()
    if not window_file.is_file():
        _report(f"MTEE cannot find its interface file: {window_file}")
        _discard_partial_startup(database, jobs, player_service, engine, workspace, media_controls)
        return None
    engine.load(QUrl.fromLocalFile(str(window_file)))
    engine.warnings.disconnect(capture_qml_diagnostics)
    if not engine.rootObjects():
        for diagnostic in qml_diagnostics:
            _report(diagnostic)
        _report(f"MTEE could not load its interface from {window_file}")
        _discard_partial_startup(database, jobs, player_service, engine, workspace, media_controls)
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
        workspace=workspace,
        frame=frame,
        artwork_provider=artwork_provider,
        media_controls=media_controls,
    )
    if isinstance(workspace, WorkspaceModel):
        workspace.resumeRoots()
    return runtime


def _refresh_after_listening(statistics: StatisticsModel, jobs: JobService) -> None:
    """Read the statistics again after a listening was stored, unless the application is closing.

    The last listening is often stored while the player shuts down: then no job may start.
    """
    if jobs.accepting:
        statistics.refresh()


def _apply_scheduled_restore(paths: AppPaths, database: Database) -> None:
    """Apply a restore scheduled on the Data & privacy page, before the database opens."""
    try:
        outcome = apply_pending_restore(
            RestoreLayout(paths.data_dir),
            database_path=database.path,
            supported_version=database.supported_version,
            migrations=database.migrations,
            now=datetime.now(UTC),
        )
    except OSError as error:
        _report(
            f"The scheduled restore did not finish: {error}. Its files are in the restore folder."
        )
        return
    if outcome is not None:
        _report(outcome.message)


def _artist_identification(
    database: Database, library: LibraryRepository
) -> ArtistIdentificationService:
    """Build the artist phase of the analysis. Only the artist manager plugin uses it."""
    from mtee.plugins.artist_manager.identification import ArtistIdentificationService
    from mtee.plugins.artist_manager.repository import ArtistRepository

    return ArtistIdentificationService(library, ArtistRepository(database))


def _attach_artist_manager(
    workspace: WorkspaceModel,
    database: Database,
    library: LibraryRepository,
    metadata_writer: MetadataEditService,
    file_access: FileAccessCoordinator,
    jobs: JobService,
    analysis_model: AnalysisModel,
) -> None:
    """Attach the artist manager plugin; called only while the plugin switch is on."""
    from mtee.plugins.artist_manager.file_service import ArtistFileService
    from mtee.plugins.artist_manager.models import ArtistManagerModel
    from mtee.plugins.artist_manager.repository import ArtistRepository
    from mtee.plugins.artist_manager.service import ArtistManagerService

    repository = ArtistRepository(database)
    files = ArtistFileService(database, library, repository, metadata_writer, file_access)
    workspace.attach_artist_manager(
        ArtistManagerModel(ArtistManagerService(repository, files), jobs, analysis_model)
    )


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
    if runtime.media_controls is not None:
        runtime.media_controls.close()
    runtime.jobs.begin_shutdown()
    runtime.frame.detach()
    _shutdown_services(runtime.database, runtime.jobs, runtime.player_service)


def _discard_partial_startup(
    database: Database,
    jobs: JobService,
    player_service: PlayerService | None,
    engine: QQmlApplicationEngine,
    workspace: QObject | None = None,
    media_controls: MediaControls | None = None,
) -> None:
    """Release native services if startup fails before a runtime is returned."""
    if isinstance(workspace, WorkspaceModel):
        workspace.flush_session()
    if media_controls is not None:
        media_controls.close()
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
