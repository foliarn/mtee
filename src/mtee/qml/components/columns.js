// Column fitting and column resizing for the track list (plan 133.1 to 133.4).
//
// Plain JavaScript without QML types, so that tests/ui/test_columns_js_133.py can run it through a
// QJSEngine. All widths and gaps are in pixels.
//
// Rules (decision 130, plan 133):
// - Title and Artist are always kept.
// - The other visible columns are kept in display order while they fit. The first one that does
//   not fit, and every one after it, is hidden for this render only (not saved).
// - Artist shrinks to ARTIST_MIN before Title shrinks below TITLE_MIN.
// - Title always absorbs the room left over, whether it has a stored width or not, so the last
//   column (or the action cell) ends at the right edge. The stored width is not changed by this.
// - Dragging the border of column k changes column k; the opposite change goes to the columns on
//   its right, nearest first, each down to its minimum (resizeBoundary). The total never grows, so
//   the table never runs past the right edge while dragging.

var TITLE_MIN = 140
var ARTIST_MIN = 44
// Ordinary columns cannot be dragged below this (the same bound as the saved widths).
var COLUMN_MIN = 44
// Title never shrinks below this, even when the window is narrower than the minimums.
var TITLE_FLOOR = 40
var TITLE_MAX = 2400
var COLUMN_MAX = 640

function isTitle(key) {
    return key === "title"
}

function isArtist(key) {
    return key === "artist"
}

function isMandatory(key) {
    return isTitle(key) || isArtist(key)
}

// Columns whose text is a number: they are anchored right in the cells and in the header (U19).
// Every other column is text and is anchored left.
var NUMERIC_KEYS = ["bpm", "duration", "bitrate", "playCount", "fileSize", "trackNumber", "discNumber"]

function isNumeric(key) {
    return NUMERIC_KEYS.indexOf(key) >= 0
}

// The width a column needs for the drop decision. Title needs its minimum, since it absorbs the
// room left over; Artist needs its own width, but never less than its minimum.
function minimumOf(column) {
    if (isTitle(column.key))
        return TITLE_MIN
    if (isArtist(column.key))
        return Math.max(ARTIST_MIN, column.width)
    return column.width
}

// columns: [{key, width}] in display order. A width of 0 on "title" means automatic.
// available: the room between the play slot and the action cell, the cell gaps included.
// gap: the space between two cells.
// Returns {items: [{key, width}] kept in display order, hidden: [key] hidden for this render}.
function fitColumns(columns, available, gap) {
    // The gap after the play slot, then one gap after every cell: (cells + 1) gaps in all.
    let used = gap
    for (const column of columns) {
        if (isMandatory(column.key))
            used += minimumOf(column) + gap
    }

    const kept = []
    const hidden = []
    let dropping = false
    for (const column of columns) {
        if (isMandatory(column.key)) {
            kept.push(column)
            continue
        }
        if (!dropping && used + column.width + gap <= available) {
            kept.push(column)
            used += column.width + gap
        } else {
            dropping = true
            hidden.push(column.key)
        }
    }

    // Room left for the mandatory columns once the other kept columns have their widths.
    let others = 0
    let cells = 0
    for (const column of kept) {
        if (!isMandatory(column.key)) {
            others += column.width
        }
        cells += 1
    }
    const room = available - (cells + 1) * gap - others

    const title = kept.find((column) => isTitle(column.key))
    const artist = kept.find((column) => isArtist(column.key))
    let artistWidth = 0
    if (artist) {
        // Artist gives way first: it shrinks down to ARTIST_MIN before Title shrinks.
        artistWidth = title
            ? Math.max(ARTIST_MIN, Math.min(artist.width, room - TITLE_MIN))
            : artist.width
    }
    const titleRoom = room - artistWidth

    const items = kept.map((column) => {
        if (isTitle(column.key))
            return { key: column.key, width: Math.max(TITLE_FLOOR, titleRoom) }
        if (isArtist(column.key))
            return { key: column.key, width: artistWidth }
        return { key: column.key, width: column.width }
    })
    return { items: items, hidden: hidden }
}

// The room that keeps every column of the list: the fit with this room drops nothing.
function neededWidth(columns, gap) {
    let total = gap
    for (const column of columns)
        total += minimumOf(column) + gap
    return total
}

// The narrowest and the widest a column can be dragged to (plan 133.3).
function resizeMinimum(key) {
    if (isTitle(key))
        return TITLE_MIN
    if (isArtist(key))
        return ARTIST_MIN
    return COLUMN_MIN
}

function resizeMaximum(key) {
    return isTitle(key) ? TITLE_MAX : COLUMN_MAX
}

// Drag of the border on the right of column k (plan 133.3).
// columns: [{key, width}] in display order, the widths drawn now (no hidden column).
// k: the index of the column whose right border is dragged.
// delta: the pixels the border moves (positive to the right).
// available: the room the column widths share, the gaps excluded.
// Returns a new [{key, width}] in the same order. Column k changes by as much as its own limits and
// the room allow. Growing it takes the same amount from the columns on its right, nearest first,
// each down to its minimum, then the next; when they are all at minimum the growth stops (the hard
// right limit). Shrinking it gives the freed room to the nearest column on its right.
function resizeBoundary(columns, k, delta, available) {
    const items = columns.map((column) => ({ key: column.key, width: Number(column.width) }))
    if (k < 0 || k >= items.length - 1)
        return items

    const current = items[k].width
    // A column already below its minimum may still grow, but it is not shrunk further.
    const lowest = Math.min(current, resizeMinimum(items[k].key))
    const highest = Math.max(current, resizeMaximum(items[k].key))
    let change = Math.max(lowest - current, Math.min(highest - current, Number(delta)))

    if (change > 0) {
        // Room the widths do not use yet (none when the title absorbs the rest) is free to take.
        let total = 0
        for (const item of items)
            total += item.width
        const free = Math.max(0, available - total)
        let need = Math.max(0, change - free)
        let taken = 0
        for (let j = k + 1; j < items.length && need > 0; ++j) {
            const give = Math.min(need, Math.max(0, items[j].width - resizeMinimum(items[j].key)))
            items[j].width -= give
            need -= give
            taken += give
        }
        change = Math.min(change, free + taken)
    }

    items[k].width = current + change
    if (change < 0)
        items[k + 1].width -= change
    return items
}

// The left edge of the action cell (heart, add, info). It sits after the last column, and at the
// right edge of the table in every other case. With only Title and Artist left it follows Artist.
function actionsLeft(items, viewWidth, padding, playSlot, actions, gap) {
    let natural = padding + playSlot + gap
    for (const item of items)
        natural += item.width + gap
    const onlyTitleAndArtist = items.length === 2
        && items.some((item) => isTitle(item.key))
        && items.some((item) => isArtist(item.key))
    return onlyTitleAndArtist ? natural : viewWidth - padding - actions
}
