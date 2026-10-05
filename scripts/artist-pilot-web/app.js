"use strict";
const $ = id => document.getElementById(id);
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[c]));
const labels = {keep:"Garder", exclude:"Écarter", uncertain:"Incertain", pending:"À faire"};
const proposals = {keep:"Garder", exclude:"Bloat possible", uncertain:"À déterminer"};
const identityLabels = {matched:"Identité rapprochée par l’IA", provisional:"Identité à consolider", unresolved:"Identité non résolue"};
const humanIdentityLabels = {pending:"À vérifier", accepted:"Rapprochement correct", rejected:"Mauvais artiste"};
const badge = (value, text = labels[value] ?? value) => `<span class="badge ${esc(value)}">${esc(text)}</span>`;
const safeLink = (url, title, className = "") => {
  try { const parsed = new URL(url); if (parsed.protocol !== "https:" || parsed.username || parsed.password) return esc(title); }
  catch { return esc(title); }
  return `<a class="${esc(className)}" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(title)}</a>`;
};
let data, observations = {}, current = null, filtered = [], dirty = false, decision = "pending", saving = false;

function profileLinks(o, r) {
  const links = r.saved_at ? [{url:r.spotify_url,label:"Spotify"},{url:r.soundcloud_url,label:"SoundCloud"}].filter(l=>l.url) : o.links ?? [];
  return links.map(l=>safeLink(l.url,l.label ?? "Profil","profile")).join("") || '<span class="saved">Aucun profil retenu à ce stade.</span>';
}

function rolesFor(artist) { return data.reviews[artist.artist_id]?.roles ?? observations[artist.artist_id]?.roles ?? []; }
function attentionFor(artist) { const o = observations[artist.artist_id] ?? {}; return (o.issues ?? []).length > 0 || o.identity_status !== "matched"; }
function updateProgress() {
  const done = data.artists.filter(a => (data.reviews[a.artist_id]?.decision ?? "pending") !== "pending").length;
  $("progress").textContent = `${done} / ${data.artists.length}`;
  $("meter").max = data.artists.length; $("meter").value = done;
}
function renderRows() {
  const query = $("search").value.trim().toLocaleLowerCase("fr"), role = $("role").value;
  filtered = data.artists.filter(a => {
    const o = observations[a.artist_id] ?? {}, r = data.reviews[a.artist_id] ?? {}, roles = rolesFor(a);
    return (!query || [a.display_name, ...a.representative_titles].join(" ").toLocaleLowerCase("fr").includes(query)) &&
      (!role || (role === "unknown" ? !roles.length : roles.includes(role))) &&
      (!$("proposal").value || (o.interest_proposal ?? "uncertain") === $("proposal").value) &&
      (!$("review").value || (r.decision ?? "pending") === $("review").value) &&
      (!$("attention").checked || attentionFor(a));
  });
  filtered.sort((a,b) => ($("sort").value === "count" ? b.collection_tracks - a.collection_tracks :
    $("sort").value === "attention" ? Number(attentionFor(b)) - Number(attentionFor(a)) : 0) || a.display_name.localeCompare(b.display_name, "fr"));
  $("rows").innerHTML = filtered.map(a => {
    const o = observations[a.artist_id] ?? {}, r = data.reviews[a.artist_id] ?? {}, roles = rolesFor(a);
    return `<tr class="${current === a.artist_id ? "selected" : ""}"><td><button class="artist-button" data-artist="${esc(a.artist_id)}" aria-label="Examiner ${esc(a.display_name)}" aria-pressed="${current === a.artist_id}">${esc(a.display_name)}</button>${attentionFor(a) ? '<span class="row-warning">À vérifier</span>' : ""}</td><td>${roles.length ? roles.map(role => badge("role",role)).join("") : '<span class="saved">Non établi</span>'}</td><td class="num">${a.collection_tracks}</td><td>${badge(o.interest_proposal ?? "uncertain",proposals[o.interest_proposal ?? "uncertain"])}</td><td>${badge(r.decision ?? "pending")}</td></tr>`;
  }).join("");
  $("visible-count").textContent = `${filtered.length} artiste${filtered.length > 1 ? "s" : ""} affiché${filtered.length > 1 ? "s" : ""}`;
  $("empty").hidden = filtered.length !== 0;
}
function canLeave() { return !saving && (!dirty || window.confirm("Abandonner les modifications non enregistrées de ce dossier ?")); }
function selectArtist(id, focus = false) {
  if (id === current || !canLeave()) return;
  current = id; dirty = false; renderRows(); renderDetail();
  if (focus) $("detail-title").focus();
}
function renderDetail() {
  const a = data.artists.find(a => a.artist_id === current), o = observations[current] ?? {}, r = data.reviews[current] ?? {};
  const provider = data.musicbrainz.artists[current] ?? {}, roles = rolesFor(a);
  decision = r.decision ?? "pending";
  const bass = r.saved_at ? r.bass_related : o.bass_related;
  const sampled = data.tracks.filter(t => t.credits.some(c => c.artist_id === current));
  const spotify = r.spotify_url ?? (o.links ?? []).find(l=>l.url.includes("open.spotify.com/artist/"))?.url ?? "";
  const soundcloud = r.soundcloud_url ?? (o.links ?? []).find(l=>l.url.includes("soundcloud.com/"))?.url ?? "";
  $("detail").innerHTML = `<div class="detail-top"><div><h2 id="detail-title" tabindex="-1">${esc(a.display_name)}</h2><p class="detail-sub">${a.collection_tracks} sons en collection · ${sampled.length} dans ce pilote</p></div><button id="next" class="text-button" type="button">Suivant →</button></div>
    <div id="profile-links" class="links">${profileLinks(o,r)}</div>
    <p class="detail-sub">${esc(identityLabels[o.identity_status] ?? "Identité à auditer")} · Bass-related : ${o.bass_related === true ? "oui (proposé)" : o.bass_related === false ? "non (proposé)" : "non établi"}</p>
    <p id="human-identity" class="detail-sub">Ta revue de l’identité : ${esc(humanIdentityLabels[r.identity_decision ?? "pending"])}.</p>
    <h3>Proposition IA : ${esc(proposals[o.interest_proposal ?? "uncertain"])}</h3><p class="reason">${esc(o.reason ?? "Audit non réalisé.")}</p>
    ${(o.issues ?? []).length ? `<div class="issues"><strong>À vérifier</strong>${o.issues.map(i=>`<p>${esc(i)}</p>`).join("")}</div>` : ""}
    <details open><summary>Preuves et sources · ${(o.sources ?? []).length}</summary>${(o.sources ?? []).map(s=>`<p class="source">${safeLink(s.url,s.title)}<small>${esc(s.supports)}</small></p>`).join("")}</details>
    <details><summary>Sons du pilote · ${sampled.length}</summary><ul>${sampled.map(t=>`<li>${esc(t.title)}<br><span class="saved">${esc(t.credits.map(c=>c.name).join(" · "))}</span></li>`).join("")}</ul></details>
    <details><summary>Autres titres de ta collection</summary><ul>${a.representative_titles.map(t=>`<li>${esc(t)}</li>`).join("")}</ul></details>
    <details><summary>Candidats MusicBrainz et genres bruts</summary><p>Le score mesure la pertinence du nom, pas la certitude d’identité. Les genres d’artiste ne classent pas les morceaux.</p>${(provider.details ?? []).map(d=>`<p class="source">${safeLink(`https://musicbrainz.org/artist/${d.id}`,d.name)}<small>${esc(d.disambiguation || "Sans désambiguïsation")} · ${(o.retained_mbids ?? []).includes(d.id) ? "Rapproché par l’IA" : "Non retenu dans l’audit"}</small><small>Genres bruts : ${esc((d.genres ?? []).map(g=>g.name).join(", ") || "aucun")}</small></p>`).join("") || '<p>Aucun détail de candidat.</p>'}<ul>${(provider.candidates ?? []).map(c=>`<li>${esc(c.name)} — score ${esc(c.score)} ${esc(c.disambiguation ?? "")}</li>`).join("")}</ul></details>
    <form id="review-form" class="review-form"><h3>Ma décision</h3><div class="decisions" aria-label="Choix de tri">${Object.entries(labels).map(([v,l])=>`<button type="button" data-decision="${v}" aria-pressed="${decision === v}">${l}</button>`).join("")}</div>
    <label>Revue de l’identité<select id="identity" aria-label="Revue de l’identité"><option value="pending" ${(r.identity_decision ?? "pending") === "pending" ? "selected" : ""}>À vérifier</option><option value="accepted" ${r.identity_decision === "accepted" ? "selected" : ""}>Rapprochement correct</option><option value="rejected" ${r.identity_decision === "rejected" ? "selected" : ""}>Mauvais artiste</option></select></label>
    <label>Profil Spotify retenu<input id="spotify-url" type="url" maxlength="500" value="${esc(spotify)}" placeholder="https://open.spotify.com/artist/…"></label>
    <label>Profil SoundCloud retenu<input id="soundcloud-url" type="url" maxlength="500" value="${esc(soundcloud)}" placeholder="https://soundcloud.com/…"></label>
    <div class="role-checks" role="group" aria-label="Rôles corrigés">${["Producer","DJ","Singer","MC"].map(role=>`<label><input type="checkbox" name="roles" value="${role}" ${roles.includes(role)?"checked":""}>${role}</label>`).join("")}</div>
    <label>Bass-related<select id="bass"><option value="unknown" ${bass == null ? "selected" : ""}>Non établi</option><option value="yes" ${bass === true ? "selected" : ""}>Oui</option><option value="no" ${bass === false ? "selected" : ""}>Non</option></select></label>
    <label>Notes personnelles<textarea id="notes" maxlength="4000" placeholder="Lien douteux, crédit à revoir, raison de ton choix…">${esc(r.notes ?? "")}</textarea></label>
    <div class="form-actions"><span id="save-state" class="saved">${r.saved_at ? "Décision enregistrée" : "Aucune décision enregistrée"}</span><button class="primary" id="save" type="submit">Enregistrer</button></div></form>`;
  $("review-form").addEventListener("input", markDirty);
  $("review-form").addEventListener("change", markDirty);
  $("detail").querySelectorAll("[data-decision]").forEach(b=>b.addEventListener("click",()=>{
    decision = b.dataset.decision;
    $("detail").querySelectorAll("[data-decision]").forEach(b=>b.setAttribute("aria-pressed", String(b.dataset.decision === decision)));
    markDirty();
  }));
  $("review-form").addEventListener("submit", saveReview);
  $("next").addEventListener("click",()=>{
    const index = filtered.findIndex(a=>a.artist_id === current);
    const next = filtered[(index+1)%filtered.length];
    if (next) selectArtist(next.artist_id,true);
  });
}
function markDirty() { dirty = true; $("save-state").textContent = "Modifications non enregistrées"; }
async function saveReview(event) {
  event.preventDefault(); if (saving) return;
  saving = true;
  $("review-form").querySelectorAll("input,select,textarea,button").forEach(control=>control.disabled=true);
  $("save-state").textContent = "Enregistrement…";
  const payload = {decision, roles:[...$("review-form").querySelectorAll('[name="roles"]:checked')].map(i=>i.value),
    bass_related: $("bass").value === "unknown" ? null : $("bass").value === "yes", notes:$("notes").value,
    identity_decision:$("identity").value, spotify_url:$("spotify-url").value.trim(), soundcloud_url:$("soundcloud-url").value.trim()};
  try {
    const response = await fetch(`/api/review/${current}`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
    if (response.status === 400) { $("save-state").textContent="Vérifie les liens : profil d’artiste Spotify et profil SoundCloud uniquement."; return; }
    if (!response.ok) throw new Error(await response.text());
    data.reviews[current] = await response.json(); dirty = false;
    $("profile-links").innerHTML = profileLinks(observations[current] ?? {},data.reviews[current]);
    $("human-identity").textContent = `Ta revue de l’identité : ${humanIdentityLabels[data.reviews[current].identity_decision]}.`;
    $("save-state").textContent = "Décision enregistrée"; $("status").textContent = `${data.artists.find(a=>a.artist_id===current).display_name} : revue enregistrée localement.`;
    updateProgress(); renderRows();
  } catch { $("save-state").textContent = "Échec : tes modifications sont conservées à l’écran. Réessaie."; $("status").textContent = "La décision n’a pas été enregistrée."; }
  finally { saving = false; $("review-form").querySelectorAll("input,select,textarea,button").forEach(control=>control.disabled=false); }
}
function renderTracks() {
  $("track-table").innerHTML = `<table><caption class="sr-only">50 morceaux sélectionnés</caption><thead><tr><th>#</th><th>Titre confirmé local</th><th>Artistes</th><th>Catégories de sélection</th></tr></thead><tbody>${data.tracks.map((t,i)=>`<tr><td class="num">${i+1}</td><td>${esc(t.title)}<br><span class="saved">${esc(t.format)}${t.observed_genres.length ? " · tags bruts : "+esc(t.observed_genres.join(", ")) : ""}</span></td><td>${t.credits.map(c=>`<button type="button" class="artist-button" data-track-artist="${esc(c.artist_id)}">${esc(c.name)}</button>`).join(" · ")}</td><td>${t.selection_categories.map(c=>badge("category",c)).join("")}</td></tr>`).join("")}</tbody></table>`;
}
function renderReport() {
  const s=data.summary, runs=s.provider_runs ?? [], requests=runs.reduce((n,r)=>n+r.http_requests,0), seconds=runs.reduce((n,r)=>n+r.seconds,0);
  const links=data.observations.flatMap(o=>o.links ?? []), spotify=links.filter(l=>l.url.includes("open.spotify.com/artist/")), soundcloud=links.filter(l=>l.url.includes("soundcloud.com/"));
  const counts = s.proposed_interest ?? {};
  $("report").innerHTML = `<h2>Ce que l’essai permet de juger</h2><p>Échantillon ciblé pour tester les catégories et les ambiguïtés. Ces résultats ne prédisent pas la couverture des 1 976 artistes.</p><div class="report-grid">
    <div class="report-section"><h3>Résultats du rapprochement</h3><dl><dt>Morceaux distincts</dt><dd>${s.tracks}</dd><dt>Artistes examinés par l’IA</dt><dd>${s.web_audited} / ${s.artists}</dd><dt>Profils Spotify proposés</dt><dd>${spotify.length}</dd><dt>Profils SoundCloud proposés</dt><dd>${soundcloud.length}</dd><dt>Identités non résolues</dt><dd>${data.observations.filter(o=>o.identity_status === "unresolved").length}</dd><dt>Garder / bloat possible / à déterminer</dt><dd>${counts.keep ?? 0} / ${counts.exclude ?? 0} / ${counts.uncertain ?? 0}</dd></dl></div>
    <div class="report-section"><h3>Coût réellement observé</h3><dl><dt>Appels HTTP MusicBrainz</dt><dd>${requests}</dd><dt>Durée de collecte MusicBrainz</dt><dd>${seconds.toFixed(1)} s</dd><dt>Tokens IA</dt><dd>Non exposés</dd><dt>Prix total</dt><dd>Non mesuré</dd></dl><p>La recherche web et l’audit ont été réalisés dans cette session. Le script automatisé couvre MusicBrainz, son cache et sa reprise.</p></div>
    <div class="report-section"><h3>Ce qui reste à décider</h3><ul><li>Le tri dépend de ton intérêt personnel. « Bloat possible » est une suggestion, jamais une suppression.</li><li>Producer, DJ, Singer et MC sont cumulables. Bass-related décrit le contexte de carrière quand les preuves suffisent.</li><li>Les profils documentés restent à valider par toi. Aucun artiste n’est suivi automatiquement sur Spotify.</li><li>Les images et la taxonomie des genres ne sont pas validées dans cet essai.</li></ul></div>
    <div class="report-section"><h3>Couverture de l’échantillon</h3><p>Les catégories servent à composer le test ; elles ne sont pas une taxonomie de genres.</p><dl>${Object.entries(s.coverage.structural ?? {}).map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl><p>Catégories structurelles manquantes : ${esc((s.coverage.missing_structural ?? []).join(", ") || "aucune")}.</p></div>
  </div>`;
}
function showTab(name) {
  for (const tab of ["artists","tracks","report"]) $(tab).hidden=tab!==name;
  document.querySelectorAll("[data-tab]").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.tab===name)));
}
async function load() {
  $("failure").hidden=true;
  try {
    const response=await fetch("/api/data"); if(!response.ok) throw new Error("load");
    data=await response.json(); observations=Object.fromEntries(data.observations.map(o=>[o.artist_id,o]));
    $("artist-count").textContent=data.artists.length; $("track-count").textContent=data.tracks.length;
    $("context").textContent=`${data.tracks.length} morceaux · ${data.artists.length} artistes · Propositions IA avec sources · Tes décisions restent séparées des crédits locaux.`;
    updateProgress(); renderRows(); renderTracks(); renderReport();
    if(!current && filtered.length) selectArtist(filtered[0].artist_id);
  } catch { $("failure").hidden=false; $("context").textContent="Le serveur doit accéder au dossier complet du pilote."; }
}
document.querySelectorAll("[data-tab]").forEach(b=>b.addEventListener("click",()=>showTab(b.dataset.tab)));
for(const id of ["search","role","proposal","review","attention","sort"]) $(id).addEventListener(id==="search"?"input":"change",()=>data&&renderRows());
$("reset").addEventListener("click",()=>{ for(const id of ["search","role","proposal","review"]) $(id).value=""; $("attention").checked=false; $("sort").value="name"; if(data) renderRows(); });
$("rows").addEventListener("click",e=>{const b=e.target.closest("[data-artist]"); if(b) selectArtist(b.dataset.artist);});
$("track-table").addEventListener("click",e=>{const b=e.target.closest("[data-track-artist]"); if(b) { selectArtist(b.dataset.trackArtist,true); if(current === b.dataset.trackArtist) showTab("artists"); }});
$("retry").addEventListener("click",load);
window.addEventListener("beforeunload",e=>{if(dirty || saving){e.preventDefault(); e.returnValue="";}});
load();
