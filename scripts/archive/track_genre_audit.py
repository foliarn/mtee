"""Track tag policy; artist context can reject a suspect tag, never supply a genre."""

import re

GENERIC = {
    "alternative",
    "dance",
    "pop",
    "electronic",
    "electronica",
    "electronique",
    "electronics",
    "music",
    "other",
    "unknown",
    "misc",
    "unclassified",
}


def audit_track(track: dict, rules: dict) -> dict:
    retained, ignored, alerts = [], [], []
    override = rules.get("tracks", {}).get(track.get("track_id"), {})
    contexts = rules.get("artists", {})
    for raw in track.get("observed_genres", []):
        for genre in re.split(r"[,;/|]", raw):
            genre = genre.strip()
            if not genre:
                continue
            if genre.casefold() in GENERIC:
                ignored.append(genre)
                continue
            conflict = override.get("rejected_tags", {}).get(genre.casefold())
            if genre.casefold() == "house" and not conflict:
                # Only explicit, sourced context may reject House. Missing context
                # is not evidence, and genre breadth is never reduced to one style.
                for credit in track.get("credits", []):
                    context = contexts.get(credit["artist_id"], {})
                    if context.get("house_unlikely") and context.get("source"):
                        conflict = f"House peu probable pour {credit['name']} : {context['source']}"
                        break
            if conflict:
                alerts.append({"tag": genre, "reason": conflict})
            elif genre.casefold() not in {g.casefold() for g in retained}:
                retained.append(genre)
    # Corrections identify this particular recording, not all its artists' work.
    if "genres" in override:
        retained = list(override["genres"])
    return {
        "retained": retained,
        "ignored": ignored,
        "alerts": alerts,
        "source": override.get("source", "Tags du morceau" if retained else ""),
    }
