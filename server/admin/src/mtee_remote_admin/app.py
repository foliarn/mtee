"""The terminal interface of a MTEE Remote server: status, settings, accounts, devices, libraries.

It runs on the server host. Everything that touches Docker or the server runs in a worker thread
(`_background`), so the screen never freezes; the result comes back on the interface thread.
Without a settings file, the setup screen comes first (`SetupScreen`).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Log,
    Static,
    Switch,
    TabbedContent,
    TabPane,
)
from textual.worker import Worker, WorkerState

from . import __version__
from .compose import Compose, ComposeError, docker_available, health
from .envfile import BUILD_KEYS, FIELD_BY_KEY, FIELDS, EnvFile, problems
from .paths import Layout, read_origin
from .screens import ConfirmScreen, PasswordScreen, TextScreen, check_password
from .updater import UpdateError, update

GIB = 1024**3
HEALTH_WAIT_S = 90


def show(widget: Static, text: str) -> None:
    """Set the text of a problem or warning line, and hide the line while it is empty."""
    widget.update(text)
    widget.display = bool(text)


def size_text(value: int | None) -> str:
    if value is None:
        return "no limit"
    if value >= GIB:
        return f"{value / GIB:.1f} GB"
    return f"{value / 1024**2:.0f} MB"


class AdminApp(App[None]):
    """`mtee-remote-admin`."""

    TITLE = "MTEE Remote"
    SUB_TITLE = f"server admin {__version__}"
    CSS = """
    .dialog { width: 72; height: auto; border: round $accent; padding: 1 2; background: $panel; }
    ModalScreen { align: center middle; }
    .question { margin-bottom: 1; }
    .buttons { height: auto; align-horizontal: right; margin-top: 1; }
    .buttons Button { margin-left: 1; }
    .problem { color: $error; height: auto; display: none; }
    .warning { color: $warning; height: auto; display: none; }
    .help { color: $text-muted; height: auto; }
    .field { height: auto; margin-bottom: 1; }
    .row { height: auto; }
    .row Button { margin-right: 1; }
    #status-text { height: auto; margin-bottom: 1; }
    #message { height: auto; color: $text-muted; padding: 0 1; }
    DataTable { height: 1fr; }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("s", "start", "Start"),
        Binding("x", "stop", "Stop"),
        Binding("r", "restart", "Restart"),
        Binding("u", "update", "Update"),
        Binding("f5", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, where: Layout, compose: Compose | None = None) -> None:
        super().__init__()
        self.where = where
        self.docker = compose or Compose(where)
        self.users: list[dict[str, Any]] = []
        self.devices: list[dict[str, Any]] = []

    # -- layout -------------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(initial="status"):
            with TabPane("Status", id="status"):
                yield Static("", id="status-text")
                yield DataTable(id="roots", cursor_type="row")
            with TabPane("Settings", id="settings"), VerticalScroll():
                for field in FIELDS:
                    with Vertical(classes="field"):
                        yield Label(f"{field.label}  [dim]{field.key}[/]")
                        yield Input(id=f"env-{field.key}")
                        yield Static(field.help, classes="help")
                        yield Static("", id=f"problem-{field.key}", classes="problem")
                        yield Static("", id=f"warning-{field.key}", classes="warning")
                yield Button("Save settings", id="save-settings", variant="primary")
            with TabPane("Users", id="users"):
                with Horizontal(classes="row"):
                    yield Button("Add", id="user-add", variant="primary")
                    yield Button("Password", id="user-password")
                    yield Button("Quota", id="user-quota")
                    yield Button("Disable / enable", id="user-disable")
                    yield Button("Admin on / off", id="user-admin")
                    yield Button("Delete", id="user-delete", variant="error")
                yield DataTable(id="user-table", cursor_type="row")
            with TabPane("Devices", id="devices"):
                with Horizontal(classes="row"):
                    yield Button("Sign out device", id="device-revoke", variant="error")
                yield DataTable(id="device-table", cursor_type="row")
            with TabPane("Libraries", id="libraries"):
                with Horizontal(classes="row"):
                    yield Button("Adopt a folder", id="root-adopt", variant="primary")
                    yield Button("Scan all", id="root-scan")
                yield DataTable(id="root-table", cursor_type="row")
            with TabPane("Streaming", id="streaming"), VerticalScroll():
                yield Label("Transcodes at once (1 to 8)")
                yield Input(id="stream-max_transcodes")
                yield Label("Transcode cache (GB, 1 to 1000)")
                yield Input(id="stream-cache_limit_gb")
                yield Label("Send WAV as FLAC")
                yield Switch(id="stream-wav_to_flac")
                yield Label('Lossless cap: none, or JSON such as {"sample_rate": 48000}')
                yield Input(id="stream-lossless_cap")
                yield Static("Applied by the server when it restarts.", classes="help")
                yield Button("Save streaming", id="save-streaming", variant="primary")
            with TabPane("Logs", id="logs"):
                yield Button("Read the logs again", id="logs-refresh")
                yield Log(id="log-view")
        yield Static("", id="message")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#roots", DataTable).add_columns(
            "Owner", "Library", "Folder", "Tracks", "Size", "To hash"
        )
        self.query_one("#user-table", DataTable).add_columns(
            "Name", "Admin", "Disabled", "Quota", "Used", "Devices"
        )
        self.query_one("#device-table", DataTable).add_columns(
            "Owner", "Device", "Kind", "Last seen", "Active"
        )
        self.query_one("#root-table", DataTable).add_columns(
            "Owner", "Library", "Folder", "Tracks", "Size", "To hash"
        )
        if not self.where.configured:
            self.push_screen(SetupScreen(self.where, self.docker), self._after_setup)
            return
        self.load_settings()
        self.action_refresh()

    def _after_setup(self, done: bool | None) -> None:
        if not done:
            self.exit()
            return
        self.load_settings()
        self.action_refresh()

    def say(self, text: str) -> None:
        self.query_one("#message", Static).update(text)

    # -- work in the background ---------------------------------------------------------
    @work(thread=True, exclusive=False)
    def _background(
        self, label: str, task: Callable[[], Any], done: Callable[[Any], None] | None = None
    ) -> None:
        self.call_from_thread(self.say, f"{label}…")
        try:
            result = task()
        except (ComposeError, UpdateError, OSError) as error:
            self.call_from_thread(self.say, f"{label} failed: {error}")
            return
        if done is not None:
            self.call_from_thread(done, result)

    # -- status -------------------------------------------------------------------------
    def action_refresh(self) -> None:
        self._background("Reading the server", self._read_all, self._show_all)

    def _read_all(self) -> dict[str, Any]:
        env = EnvFile.read(self.where.env_file).values() if self.where.configured else {}
        state = self.docker.state()
        reached, version = health(env.get("BIND_ADDRESS", ""), env.get("PORT", "8080"))
        result: dict[str, Any] = {"state": state, "reached": reached, "version": version}
        if state == "running":
            result["status"] = self.docker.admin("status")
            result["users"] = self.docker.admin("users")["users"]
            result["devices"] = self.docker.admin("devices")["devices"]
            result["roots"] = self.docker.admin("roots")["roots"]
            result["streaming"] = self.docker.admin("settings")["streaming"]
        return result

    def _show_all(self, found: dict[str, Any]) -> None:
        env = EnvFile.read(self.where.env_file).values() if self.where.configured else {}
        lines = [
            f"Container: [b]{found['state']}[/]   "
            + (
                f"Answers on port {env.get('PORT', '8080')}"
                if found["reached"]
                else "Not answering"
            )
            + (f" (version {found['version']})" if found["version"] else ""),
            f"Listens on {env.get('BIND_ADDRESS', '127.0.0.1')}:{env.get('PORT', '8080')}"
            + (f" · public address {env['PUBLIC_URL']}" if env.get("PUBLIC_URL") else ""),
            f"Music {env.get('MUSIC_DIR', '?')} · data {env.get('DATA_DIR', '?')}",
            f"Source {self.where.source} · {read_origin(self.where).repo}"
            f" ({read_origin(self.where).ref})",
        ]
        status = found.get("status")
        if status:
            hashes = status["hashes"]
            lines.append(
                f"{status['users']} accounts · {status['devices']} devices · {status['items']:,}"
                f" tracks ({size_text(status['library_bytes'])}) · hashing: {hashes['pending']:,}"
                f" waiting, {hashes['error']:,} errors · database"
                f" {size_text(status['database_bytes'])}"
            )
        elif found["state"] != "running":
            lines.append("Press s to start the server.")
        self.query_one("#status-text", Static).update("\n".join(lines))
        self.users = found.get("users", [])
        self.devices = found.get("devices", [])
        self._fill_users()
        self._fill_devices()
        roots = found.get("roots", [])
        for table_id in ("#roots", "#root-table"):
            table = self.query_one(table_id, DataTable)
            table.clear()
            for root in roots:
                table.add_row(
                    root["username"],
                    root["name"],
                    root["relative_dir"] or "(whole folder)",
                    f"{root['items']:,}",
                    size_text(root["bytes"]),
                    f"{root['pending']:,}",
                    key=root["root_id"],
                )
        streaming = found.get("streaming")
        if streaming:
            self._fill_streaming(streaming)
        self.say("Up to date." if found["state"] == "running" else "The server is not running.")

    # -- settings -----------------------------------------------------------------------
    def load_settings(self) -> None:
        values = EnvFile.read(self.where.env_file).values()
        for field in FIELDS:
            self.query_one(f"#env-{field.key}", Input).value = values.get(
                field.key, field.default()
            )
            self._show_warning(field.key, values.get(field.key, ""))

    def _show_warning(self, key: str, value: str) -> None:
        warning = FIELD_BY_KEY[key].warning(value) or ""
        show(self.query_one(f"#warning-{key}", Static), warning)

    @on(Input.Changed)
    def _setting_changed(self, event: Input.Changed) -> None:
        if event.input.id and event.input.id.startswith("env-"):
            self._show_warning(event.input.id.removeprefix("env-"), event.value)

    @on(Button.Pressed, "#save-settings")
    def save_settings(self) -> None:
        values = {f.key: self.query_one(f"#env-{f.key}", Input).value.strip() for f in FIELDS}
        found = problems(values)
        for field in FIELDS:
            show(self.query_one(f"#problem-{field.key}", Static), found.get(field.key, ""))
        if found:
            self.say(f"{len(found)} settings need a change; nothing was saved.")
            return
        env = EnvFile.read(self.where.env_file)
        before = env.values()
        changed = {key for key, value in values.items() if before.get(key, "") != value}
        if not changed:
            self.say("Nothing changed.")
            return
        for key in changed:
            env.set(key, values[key])
        env.write(self.where.env_file)
        rebuild = bool(changed & BUILD_KEYS)

        def apply(answer: bool | None) -> None:
            if not answer:
                self.say("Saved. Restart the server (r) to apply.")
                return
            if rebuild:
                self._background(
                    "Rebuilding and restarting",
                    lambda: (self.docker.build(), self.docker.restart()),
                    lambda _r: self.action_refresh(),
                )
            else:
                self._background(
                    "Restarting", self.docker.restart, lambda _r: self.action_refresh()
                )

        what = "rebuild and restart" if rebuild else "restart"
        self.push_screen(
            ConfirmScreen(
                f"Saved {', '.join(sorted(changed))}. {what.capitalize()} the server now?",
                what.capitalize(),
            ),
            apply,
        )

    # -- the container ------------------------------------------------------------------
    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """The container keys work once the server is set up (not on the setup screen)."""
        if action in ("start", "stop", "restart", "update", "refresh"):
            return self.where.configured and not isinstance(self.screen, SetupScreen)
        return True

    def action_start(self) -> None:
        self._background("Starting", self.docker.up, lambda _r: self.action_refresh())

    def action_stop(self) -> None:
        def stop(answer: bool | None) -> None:
            if answer:
                self._background("Stopping", self.docker.stop, lambda _r: self.action_refresh())

        self.push_screen(
            ConfirmScreen(
                "Stop the server? Your devices cannot sync until it runs again.",
                "Stop",
                danger=True,
            ),
            stop,
        )

    def action_restart(self) -> None:
        self._background("Restarting", self.docker.restart, lambda _r: self.action_refresh())

    def action_update(self) -> None:
        origin = read_origin(self.where)

        def run(answer: bool | None) -> None:
            if not answer:
                return

            def task() -> None:
                update(self.where, origin)
                self.docker.build()
                self.docker.up()

            self._background("Updating", task, lambda _r: self.action_refresh())

        self.push_screen(
            ConfirmScreen(
                f"Download {origin.repo} ({origin.ref}), rebuild the image and restart? "
                "Your settings and data stay; the current source is kept as source.previous.",
                "Update",
            ),
            run,
        )

    # -- users --------------------------------------------------------------------------
    def _fill_users(self) -> None:
        table = self.query_one("#user-table", DataTable)
        table.clear()
        for user in self.users:
            table.add_row(
                user["username"],
                "yes" if user["is_admin"] else "",
                "yes" if user["disabled"] else "",
                size_text(user["quota_bytes"]),
                size_text(user["used_bytes"]),
                str(user["devices"]),
                key=user["username"],
            )

    def selected_user(self) -> dict[str, Any] | None:
        table = self.query_one("#user-table", DataTable)
        if not self.users or table.cursor_row < 0 or table.cursor_row >= len(self.users):
            self.say("Choose an account in the list first.")
            return None
        return self.users[table.cursor_row]

    def _admin_then_refresh(self, label: str, *args: str, password: str | None = None) -> None:
        def done(answer: dict[str, Any]) -> None:
            self.say(str(answer.get("message", "Done.")))
            self.action_refresh()

        self._background(label, lambda: self.docker.admin(*args, password=password), done)

    @on(Button.Pressed, "#user-add")
    def add_user(self) -> None:
        def named(name: str | None) -> None:
            if not name:
                return

            def with_password(password: str | None) -> None:
                if password:
                    self._admin_then_refresh(
                        "Creating the account", "user-create", "--username", name,
                        "--password-stdin", password=password,
                    )  # fmt: skip

            self.push_screen(PasswordScreen(f"Password of {name}"), with_password)

        self.push_screen(TextScreen("Name of the new account", placeholder="ana"), named)

    @on(Button.Pressed, "#user-password")
    def set_password(self) -> None:
        user = self.selected_user()
        if user is None:
            return

        def chosen(password: str | None) -> None:
            if password:
                self._admin_then_refresh(
                    "Changing the password", "user-password", "--username", user["username"],
                    "--password-stdin", password=password,
                )  # fmt: skip

        self.push_screen(
            PasswordScreen(f"New password of {user['username']} (signs its devices out)"), chosen
        )

    @on(Button.Pressed, "#user-quota")
    def set_quota(self) -> None:
        user = self.selected_user()
        if user is None:
            return
        current = "none" if user["quota_bytes"] is None else f"{user['quota_bytes'] / GIB:g}"

        def chosen(value: str | None) -> None:
            if value is not None:
                self._admin_then_refresh(
                    "Changing the quota", "user-set", "--username", user["username"],
                    "--quota-gb", value.strip() or "none",
                )  # fmt: skip

        self.push_screen(TextScreen("Quota in GB, or none", current), chosen)

    @on(Button.Pressed, "#user-disable")
    def toggle_disabled(self) -> None:
        user = self.selected_user()
        if user is not None:
            self._admin_then_refresh(
                "Changing the account", "user-set", "--username", user["username"],
                "--disabled", "no" if user["disabled"] else "yes",
            )  # fmt: skip

    @on(Button.Pressed, "#user-admin")
    def toggle_admin(self) -> None:
        user = self.selected_user()
        if user is not None:
            self._admin_then_refresh(
                "Changing the account", "user-set", "--username", user["username"],
                "--admin", "no" if user["is_admin"] else "yes",
            )  # fmt: skip

    @on(Button.Pressed, "#user-delete")
    def delete_user(self) -> None:
        user = self.selected_user()
        if user is None:
            return
        name = user["username"]

        def typed(value: str | None) -> None:
            if value is None:
                return
            self._admin_then_refresh(
                "Deleting the account", "user-delete", "--username", name, "--confirm", value
            )

        self.push_screen(
            TextScreen(f"Delete {name}? Its music folder is kept. Type {name} to confirm."), typed
        )

    # -- devices ------------------------------------------------------------------------
    def _fill_devices(self) -> None:
        table = self.query_one("#device-table", DataTable)
        table.clear()
        for device in self.devices:
            table.add_row(
                device["username"],
                device["name"],
                device["kind"],
                (device["last_seen_utc"] or "never")[:16].replace("T", " "),
                "yes" if device["active"] else "signed out",
                key=device["device_id"],
            )

    @on(Button.Pressed, "#device-revoke")
    def revoke_device(self) -> None:
        table = self.query_one("#device-table", DataTable)
        if not self.devices or not 0 <= table.cursor_row < len(self.devices):
            self.say("Choose a device in the list first.")
            return
        device = self.devices[table.cursor_row]

        def answer(yes: bool | None) -> None:
            if yes:
                self._admin_then_refresh(
                    "Signing the device out", "device-revoke", "--device-id", device["device_id"]
                )

        self.push_screen(
            ConfirmScreen(
                f"Sign out {device['name']} of {device['username']}? It can sign in again with "
                "the account's password.",
                "Sign out",
                danger=True,
            ),
            answer,
        )

    # -- libraries ----------------------------------------------------------------------
    @on(Button.Pressed, "#root-adopt")
    def adopt_root(self) -> None:
        env = EnvFile.read(self.where.env_file).values()
        owner = env.get("ADMIN_USER", "")

        def folder(path: str | None) -> None:
            if not path:
                return
            name = Path(path.rstrip("/")).name or "music"
            self._background(
                "Adopting the folder (the first scan can take a while)",
                lambda: self.docker.server_command(
                    "adopt-root", "--user", owner, "--path", path, "--name", name
                ),
                lambda text: (self.say(text or "Adopted."), self.action_refresh()),
            )

        self.push_screen(
            TextScreen(
                f"Folder to adopt, as the container sees it (inside /music/{owner})",
                f"/music/{owner}",
            ),
            folder,
        )

    @on(Button.Pressed, "#root-scan")
    def scan_all(self) -> None:
        owners = sorted({user["username"] for user in self.users})

        def task() -> str:
            return "\n".join(
                self.docker.server_command("scan", "--user", owner) for owner in owners
            )

        self._background(
            "Scanning", task, lambda text: (self.say(text or "Scanned."), self.action_refresh())
        )

    # -- streaming ----------------------------------------------------------------------
    def _fill_streaming(self, values: dict[str, Any]) -> None:
        self.query_one("#stream-max_transcodes", Input).value = str(values["max_transcodes"])
        self.query_one("#stream-cache_limit_gb", Input).value = str(values["cache_limit_gb"])
        self.query_one("#stream-wav_to_flac", Switch).value = bool(values["wav_to_flac"])
        cap = values.get("lossless_cap")
        self.query_one("#stream-lossless_cap", Input).value = "none" if cap is None else _json(cap)

    @on(Button.Pressed, "#save-streaming")
    def save_streaming(self) -> None:
        cap = self.query_one("#stream-lossless_cap", Input).value.strip()
        wav = "true" if self.query_one("#stream-wav_to_flac", Switch).value else "false"
        pairs = [
            f"max_transcodes={self.query_one('#stream-max_transcodes', Input).value.strip()}",
            f"cache_limit_gb={self.query_one('#stream-cache_limit_gb', Input).value.strip()}",
            f"wav_to_flac={wav}",
            f"lossless_cap={'null' if cap.lower() in ('', 'none') else cap}",
        ]
        self._admin_then_refresh("Saving the streaming settings", "settings-set", *pairs)

    # -- logs ---------------------------------------------------------------------------
    @on(TabbedContent.TabActivated)
    def _tab(self, event: TabbedContent.TabActivated) -> None:
        if event.pane.id == "logs":
            self.read_logs()

    @on(Button.Pressed, "#logs-refresh")
    def read_logs(self) -> None:
        def show(text: str) -> None:
            view = self.query_one("#log-view", Log)
            view.clear()
            view.write(text)
            self.say("Logs read.")

        self._background("Reading the logs", self.docker.logs, show)


def _json(value: Any) -> str:
    return json.dumps(value)


class SetupScreen(Screen[bool]):
    """The first run: the settings that matter, the admin password, then build and start."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", "Quit")]
    FIRST = ("ADMIN_USER", "MUSIC_DIR", "DATA_DIR", "PORT", "BIND_ADDRESS")

    def __init__(self, where: Layout, compose: Compose) -> None:
        super().__init__()
        self.where = where
        self.docker = compose

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Static(
                "[b]Set up MTEE Remote[/]\nThe settings below go to "
                f"{self.where.env_file}. Everything can be changed later in Settings.",
            )
            for key in self.FIRST:
                field = FIELD_BY_KEY[key]
                with Vertical(classes="field"):
                    yield Label(field.label)
                    default = str(self.where.default_data_dir) if key == "DATA_DIR" else ""
                    yield Input(default or field.default(), id=f"setup-{key}")
                    yield Static(field.help, classes="help")
                    yield Static("", id=f"setup-problem-{key}", classes="problem")
                    warning = field.warning(field.default()) or ""
                    yield Static(warning, classes="warning", id=f"setup-warning-{key}")
            yield Label("Password of the admin account")
            yield Input(password=True, id="setup-password", placeholder="8 characters or more")
            yield Input(password=True, id="setup-password-again", placeholder="The same again")
            yield Static("", id="setup-problem-password", classes="problem")
            yield Button("Install and start", id="setup-go", variant="primary")
            yield Log(id="setup-log")
        yield Footer()

    def action_cancel(self) -> None:
        self.dismiss(False)

    @on(Input.Changed)
    def _changed(self, event: Input.Changed) -> None:
        key = (event.input.id or "").removeprefix("setup-")
        if key in self.FIRST:
            warning = FIELD_BY_KEY[key].warning(event.value) or ""
            show(self.query_one(f"#setup-warning-{key}", Static), warning)

    def values(self) -> dict[str, str]:
        found = {f.key: f.default() for f in FIELDS}
        for key in self.FIRST:
            found[key] = self.query_one(f"#setup-{key}", Input).value.strip()
        return found

    @on(Button.Pressed, "#setup-go")
    def go(self) -> None:
        values = self.values()
        found = {key: text for key, text in problems(values).items() if key in self.FIRST}
        data_dir = values["DATA_DIR"]
        if "DATA_DIR" not in found:
            try:
                Path(data_dir).expanduser().mkdir(parents=True, exist_ok=True)
            except OSError as error:
                found["DATA_DIR"] = f"Cannot create this folder: {error.strerror}."
        for key in self.FIRST:
            show(self.query_one(f"#setup-problem-{key}", Static), found.get(key, ""))
        password = self.query_one("#setup-password", Input).value
        problem = check_password(password, self.query_one("#setup-password-again", Input).value)
        show(self.query_one("#setup-problem-password", Static), problem)
        if found or problem:
            return
        missing = docker_available()
        if missing:
            show(self.query_one("#setup-problem-password", Static), missing)
            return
        self.query_one("#setup-go", Button).disabled = True
        self.install(values, password)

    @work(thread=True, name="install")
    def install(self, values: dict[str, str], password: str) -> bool:
        """Write the settings, build, start, create the admin, adopt the music; True when done.

        The screen closes when the worker has finished (``on_worker_state_changed``): closing it
        from inside the worker would cancel the worker.
        """
        log = self.query_one("#setup-log", Log)

        def say(text: str) -> None:
            self.app.call_from_thread(log.write_line, text)

        try:
            env = EnvFile.read(self.where.env_file) if self.where.configured else EnvFile()
            for key, value in values.items():
                env.set(key, value)
            env.write(self.where.env_file)
            say(f"Settings written to {self.where.env_file}.")
            say("Building the image (a few minutes the first time)…")
            self.docker.build()
            say("Starting the server…")
            self.docker.up()
            if not self._wait_healthy(values):
                say("The server did not answer in time. See the logs: docker compose logs.")
                self.app.call_from_thread(self._enable)
                return False
            user = values["ADMIN_USER"]
            try:
                self.docker.admin(
                    "user-create", "--username", user, "--admin", "--password-stdin",
                    password=password,
                )  # fmt: skip
                say(f"Admin account {user} created.")
            except ComposeError as error:
                if "already" not in str(error).lower():
                    raise
                say(f"The account {user} exists already; it is kept as it is.")
            say("Adopting your music folder (the first scan can take a while)…")
            try:
                say(self.docker.server_command(
                    "adopt-root", "--user", user, "--path", f"/music/{user}", "--name", "music"
                ))  # fmt: skip
            except ComposeError as error:
                if "already" not in str(error).lower():
                    raise
                say("This folder is a library already; it is kept as it is.")
            say("Done. The tracks are hashed in the background; see Status.")
        except (ComposeError, OSError) as error:
            say(f"Stopped: {error}")
            self.app.call_from_thread(self._enable)
            return False
        return True

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if (
            event.worker.name == "install"
            and event.state == WorkerState.SUCCESS
            and event.worker.result is True
        ):
            self.dismiss(True)

    def _wait_healthy(self, values: dict[str, str]) -> bool:
        deadline = time.monotonic() + HEALTH_WAIT_S
        while time.monotonic() < deadline:
            if health(values["BIND_ADDRESS"], values["PORT"])[0]:
                return True
            time.sleep(1)
        return False

    def _enable(self) -> None:
        self.query_one("#setup-go", Button).disabled = False
