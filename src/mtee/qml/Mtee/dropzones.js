.pragma library

// Drop zones of a center window while a tab or a folder is dragged over it (plan 130, P3).
// The outer 25 % of each side is a split zone and the middle is "center" (add here). In a
// corner the nearer side wins. A zone that is not in ``allowed`` is not offered: the pointer then
// falls back to "center" when that is allowed, else to "" (no drop). ``allowed`` null means all.
const OUTER = 0.25

function zoneAt(x, y, width, height, allowed) {
    if (width <= 0 || height <= 0 || x < 0 || y < 0 || x > width || y > height)
        return ""
    const fx = x / width
    const fy = y / height
    const distances = {
        "left": fx,
        "right": 1 - fx,
        "top": fy,
        "bottom": 1 - fy
    }
    let best = "center"
    let bestDistance = OUTER
    for (const name of ["left", "right", "top", "bottom"]) {
        const distance = distances[name]
        if (distance < bestDistance && (allowed === null || allowed === undefined || allowed.indexOf(name) >= 0)) {
            best = name
            bestDistance = distance
        }
    }
    if (best === "center" && allowed !== null && allowed !== undefined && allowed.indexOf("center") < 0)
        return ""
    return best
}

// The zones a window of this size can offer without a child under the minimum size.
function allowedFor(width, height, minWidth, minHeight, gap) {
    const zones = ["center"]
    if (width >= 2 * minWidth + gap)
        zones.push("left", "right")
    if (height >= 2 * minHeight + gap)
        zones.push("top", "bottom")
    return zones
}

// The rectangle a zone covers inside a window.
function rectOf(zone, width, height) {
    if (zone === "left") return { "x": 0, "y": 0, "width": width / 2, "height": height }
    if (zone === "right") return { "x": width / 2, "y": 0, "width": width / 2, "height": height }
    if (zone === "top") return { "x": 0, "y": 0, "width": width, "height": height / 2 }
    if (zone === "bottom") return { "x": 0, "y": height / 2, "width": width, "height": height / 2 }
    if (zone === "center") return { "x": 0, "y": 0, "width": width, "height": height }
    return { "x": 0, "y": 0, "width": 0, "height": 0 }
}
