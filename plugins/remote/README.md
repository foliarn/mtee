# MTEE Remote plugin

## What it does

Connects MTEE to your MTEE Remote server. In Settings > Remote you enter the server address, your
user name and your password once. MTEE signs this computer in as a named device and keeps the
connection: the cloud icon in the header of the window shows **Connected** on hover, or turns to
**Offline** when the server cannot be reached, and MTEE checks the connection every minute, with
longer waits after repeated failures. Settings also list the devices of your account, and you can
revoke another device from there (MTEE asks first). Disconnect signs this computer out and revokes
its device on the server.

Where things are (MTEE 0.3.0):

- **Remote** window, the cloud button of the left bar (Alt+4 when it is the fourth window): the
  changes waiting to be sent (Apply in Manual mode, **Retry** when one failed), the open conflicts,
  the newest backups and the activity log, with **Sync now** and **Fetch** in its header. Its foot
  says whether this computer is connected and what waits. The button carries the number of
  conflicts and blocked changes. Changes and Conflicts list 50 rows (failed and blocked changes
  first), then one row for the rest; for the conflicts it opens **Remote conflicts**, a tab that
  lists every one of them.
- **Explorer > Server**: the folders of the server, each opening its tracks in a tab.
- **Settings > Remote**: the connection, the devices, the sync, playback and backup choices, the
  settings that travel and the folder links.
- The **bell** of the header lists the conflicts under "Remote conflicts" (Waiting for you), and
  each finished task of the plugin (a sync, a fetch, a backup, a download) leaves one sentence
  there that says what it did, or why it failed. The Tasks window keeps their record.

The **first match** links each watched folder to a server folder (Settings > Remote > Folders). A
mapping can start at a subfolder on either side (**Local subfolder**, **Server subfolder**), so a
first run can be tried on one small folder before the whole library. MTEE compares the tracks by
their audio, not by name or tags, and shows a summary before anything moves: **Matched**, **To
upload**, **Server only**, **Same audio, different file** and **Not matched**. For the same-audio
group one choice applies to all of them: **This computer wins** (default) gives the server's copies
this computer's tags, names and folders; **Server wins** does the reverse; **Decide one by one**
leaves each in Conflicts. When this computer wins and both files hold the same audio bytes, only
the tag parts of the file are sent (FLAC, MP3, WAV, AIFF, M4A): the server rebuilds the file from
them and its own audio, and keeps it only if its SHA-256 equals this computer's; otherwise the whole
file is sent. A track that waits for a decision is never sent.

Once the first match is done (Settings > Remote, Folders), the plugin sends this computer's changes
to the server: new tracks, tag edits (a replacement of the same server item), renames and moves
(the same item at its new path). Files are read only; nothing on this computer is written, moved or
deleted. Settings > Remote > Sync chooses the mode:

- **Auto** (default) sends a change once its file has not changed for the idle delay (120 seconds
  by default, 0 to 3600 in the setting), checked every 60 seconds and after each library scan.
- **Manual** only queues the changes, and the Apply pending changes button sends them.

A large upload is sent in 8 MiB chunks. If MTEE stops or the connection drops, the next run resumes
the upload from the bytes the server holds. A path already taken on the server, or a replacement
from an out-of-date revision, is held as a blocked operation with a conflict row (resolved by the
Conflicts section, plan 126.6). A full quota fails the operation with the server's sentence.

Changes made on your other devices come in with **Fetch** (Settings > Remote > Sync), or on their
own when **Auto pull** is on (a long poll that wakes as the server reports a change). A track added
on another device shows as **Server only** in the lists, and plays after a download (checked by its
SHA-256); with **Download new server tracks** on, it is downloaded into its mapped folder and linked
once the library has scanned it. A replaced track is replaced here only when this computer's copy
is still the one that was synced; if both changed, a conflict is recorded. A move on the server
moves the file here. A deletion on the server never deletes the local file: it is a conflict.

Freeing space keeps the tracks on the server. For a track that has a copy on the server, the
Recycle Bin confirmation (Delete, or **Free up space** in the track menu) offers **Remove from this
computer**, the default: its file goes to the Recycle Bin only when the server copy and the file
both still have the SHA-256 of the last sync. The track stays in the library, under the same id,
and shows as **Server only**. A track that changed since the last sync is skipped and nothing moves.
**Delete everywhere** (red) sends the file to the Recycle Bin and the server copy to the server
trash, which the administrator empties. A track that exists only on the server offers only
**Delete everywhere**. A selection with a track that is on this computer alone gets the Recycle Bin
confirmation as before. **Download** (track menu, for a Server only track) puts the original back
in its mapped folder under the same id, checked by its SHA-256; a copy kept from playing it is
reused. Nothing is deleted permanently.

**Conflicts** are the cases the sync cannot settle alone. They wait in the bell under "Remote
conflicts" and in the Conflicts section of the Remote window, and the header icon turns to the
warning colour (**N conflicts** on hover; a click opens the first one) while any wait. A conflict
opens in a tab with this computer's copy and the server's copy side by side (title,
artists, album, genre, year, size, modified time, revision); the values that differ are in the
warning colour. Nothing changes until you choose:

- **Both changed** (a file changed here and on the server since the last sync), **stale revision**
  (a replacement sent from an out-of-date revision) and **Tags differ** (the same audio, other
  tags): **Keep this computer's** uploads this file as a replacement of the server copy, on the
  revision the server has now; **Keep the server's** downloads the server copy and puts it in place
  of this file, which goes to the Recycle Bin; **Keep both** uploads this file as
  `<name> (<device name>)<ext>` and the server copy stays, as a server only track.
- **A file with this name exists on the server**: **Use another name on the server** uploads this
  file under the next free name (`<name> (2)<ext>`); **Link to the existing file** links this track
  to the server file, only when that file has the same audio (no upload; a different tag set stays
  in Conflicts); **Skip** leaves the track out of the sync.
- **Deleted on the server**: **Upload it again** sends the file back at its path as a new item;
  **Remove from this computer** asks the Recycle Bin confirmation for the file (the conflict closes
  when the file has left this computer); **Keep only on this computer** unlinks the track and leaves
  it out of the sync.

Choices that would overwrite a server file on a changed revision are refused by the server, not
guessed. A choice whose situation no longer holds (the file is gone from the library, or the server
has the file again) closes the conflict as obsolete. A failed choice keeps the conflict open with
the reason. **Dismiss** in the bell (the cross) keeps a conflict for later: it is hidden from the
bell until a change on either side reopens it.

## Requirements and external tools

- Windows. The token is protected with Windows DPAPI, which exists only on Windows.
- A MTEE Remote server, reached over `https://`. Plain `http://` is accepted only for
  `127.0.0.1` and `localhost`, which the tests use.
- No library is added: the plugin uses the Python standard library (`http.client`, `ssl`,
  `ctypes`), and PySide6, which MTEE already ships.
- The tests start the server project in `server/` with `uv`, which must be installed.

## Data it stores and where

- `<data-dir>/plugin-data/remote/token.bin`: the device token, encrypted with DPAPI for the
  current Windows account. Disconnect deletes it.
- The plugin settings `plugins.remote.server_url`, `plugins.remote.username`,
  `plugins.remote.device_id` and `plugins.remote.device_name`, and the sync settings (mode, idle
  delay, Auto pull, Download new server tracks). The password is never stored, and the token is
  never in the settings or in a log.
- The table `remote_conflicts` of the database: one row per conflict, its state (open, decide later,
  resolved), the kind and both versions as JSON, and after a choice the action and the sentence
  that says what was done. The conflict is never deleted; it stays as the record of the choice.
- Housekeeping, at start and once a day: the operations sent more than 7 days ago, the activity
  log beyond its newest 1,000 lines, and the cached hashes of files that left the library are
  deleted. Nothing else is.
- `<data-dir>/plugin-data/remote/incoming` (downloads on their way into a folder) and
  `<data-dir>/plugin-data/remote/cache` (the originals of server-only tracks, kept while they play,
  checked by SHA-256 and removed least recently used above the size setting). Both hold copies
  only; the library's own files are never written here.

## How to test it

- Automated: `uv run pytest tests/plugins/remote`. The connection tests start a real MTEE Remote
  server on `127.0.0.1` for the session, with temporary data and music folders. The conflict tests
  (`test_conflicts.py`) make each kind of conflict for real with a second device, run each choice,
  and check the server, the local calls, the link and the queue; one test opens the conflict tab
  in the real window.
- By hand: `uv run python -m mtee --data-dir .local/dev --plugin-dir plugins`, switch the plugin
  on in Settings > Plugins, restart, then connect in Settings > Remote to a test server.

## Known limits

- The device name is set when the computer connects. Once connected, it cannot be changed without
  disconnecting first.
- A connection interrupted while it is being made can leave a device on the server that this
  computer no longer holds a token for; revoke it from the device list.
- A second copy of audio that the first match left out as a duplicate is never sent. A copy added
  later is not a duplicate of anything known, so it is sent as a new item.
- Server-only tracks are not in the Explorer. Playing one at the Original level (Settings > Remote
  > Playback) first downloads it for up to 1.5 s: on a fast network it then plays from the cache,
  so it crosses the network once. Otherwise it streams, and the copy goes on in the background
  from the bytes already received. The copy is checked by its SHA-256 once, and kept for the next
  play and for offline play; a lossy level streams and is not kept. Their cover is read from the
  server once and kept.
- A link made by a fetch or by a download is kept, but the playlists that held a server-only track
  keep pointing to it; they do not move to the local file.
- Availability is read from the hash cache: a file changed a moment ago shows as synced until the
  next pass hashes it.
- A failed operation (for example a full quota) is not retried by itself: **Retry** in the Changes
  section sends the failed ones again. A blocked one (a path taken, a stale revision) waits in
  Conflicts until you choose.
- **Keep both** and **Use another name** upload this file under the new name; the server's own copy
  keeps its name. This computer keeps the path it has, so the push does not send a move back.
- **Keep this computer's** on a server copy that changed since the conflict was read is refused by
  the server (the revision is checked when the upload opens), and the conflict stays open.
- The tags shown in a conflict are read from the file with mutagen (title, artist, album, genre,
  date); a format without those fields shows them empty. The server's tags are the ones it stored
  at its last read, shown as last seen when the server cannot be reached.
- **Remove from this computer** closes its conflict only after the core's Recycle Bin confirmation
  has removed the file from the library; until then the conflict stays open.
- The folder, backup and settings-that-travel groups are not built yet.
- A click on the header icon opens the first open conflict; with none it does nothing, since a
  plugin cannot open its own tool window yet.
- A track is adopted as a server-only track under the key of its server copy. When that key is
  already the key of another track of this plugin (a track that was server-only earlier and got a
  local file by a fetch), **Remove from this computer** skips the track before anything moves: the
  core's adopt does not accept a key that a removed track still holds (a core limit, reported).
- A track whose link exists but whose file is missing gets no delete choice; the Recycle Bin
  confirmation stays as it is for it.
- Delete everywhere stops at the first connection failure; the server copies after it are left as
  they are. A server copy whose trash fails keeps its link, and the failure is in the activity log.
