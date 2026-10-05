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
let drafts = {}, rowLimit = 100, searchTimer;
const reviewFor = id => drafts[id] ?? data.reviews[id] ?? {};
const roleGroups = ["Producer / DJ", "Singer", "MC"];
const roleValues = role => role === "Producer / DJ" ? ["Producer", "DJ"] : [role];

function profileLinks(o, r) {
  const links = [{url:r.spotify_url,label:"Spotify"},{url:r.soundcloud_url,label:"SoundCloud"}].filter(l=>l.url);
  return links.map(l=>safeLink(l.url,l.label ?? "Profil","profile")).join("") || '<span class="saved">Aucun profil retenu à ce stade.</span>';
}

function rolesFor(artist) { return reviewFor(artist.artist_id).roles ?? []; }
function attentionFor(artist) { const o = observations[artist.artist_id] ?? {}; return (o.issues ?? []).length > 0 || o.identity_status !== "matched"; }
function updateProgress() {
  const count = Object.keys(drafts).length;
  dirty = count > 0;
  $("progress").textContent = saving ? "Enregistrement…" : count ? `${count} artiste${count > 1 ? "s" : ""} modifié${count > 1 ? "s" : ""}` : "Aucune correction à enregistrer";
  $("save-all").disabled = saving || !count;
}
function renderRows() {
  const query = $("search").value.trim().toLocaleLowerCase("fr"), role = $("role").value;
  filtered = data.artists.filter(a => {
    const o = observations[a.artist_id] ?? {}, r = reviewFor(a.artist_id), roles = rolesFor(a);
    return (!query || [a.display_name, ...a.representative_titles].join(" ").toLocaleLowerCase("fr").includes(query)) &&
      (!role || (role === "unknown" ? !roles.length : roleValues(role).some(value=>roles.includes(value)))) &&
      (!$("proposal").value || (o.interest_proposal ?? "uncertain") === $("proposal").value) &&
      (!$("review").value || ($("review").value === "modified" ? drafts[a.artist_id] || r.saved_at : r.decision === $("review").value)) &&
      (!$("attention").checked || attentionFor(a));
  });
  filtered.sort((a,b) => ($("sort").value === "count" ? b.collection_tracks - a.collection_tracks :
    $("sort").value === "attention" ? Number(attentionFor(b)) - Number(attentionFor(a)) : 0) || a.display_name.localeCompare(b.display_name, "fr"));
  $("rows").innerHTML = filtered.slice(0,rowLimit).map(rowHTML).join("");
  $("more-rows").hidden = rowLimit >= filtered.length;
  $("visible-count").textContent = `${filtered.length} artiste${filtered.length > 1 ? "s" : ""} affiché${filtered.length > 1 ? "s" : ""}`;
  $("empty").hidden = filtered.length !== 0;
}
function rowHTML(a) {
  const o = observations[a.artist_id] ?? {}, r = reviewFor(a.artist_id), roles = rolesFor(a);
  const issues = o.issues ?? [];
  const warning = o.identity_status === "unresolved" ? "Identité introuvable" : issues[0] ?? (o.identity_status !== "matched" ? "Identité à consolider" : "");
  return `<tr data-row="${esc(a.artist_id)}" class="${drafts[a.artist_id] ? "modified" : ""}"><td><button class="artist-button" data-artist="${esc(a.artist_id)}" aria-label="Dossier de ${esc(a.display_name)}">${esc(a.display_name)}</button>${warning ? `<span class="row-warning" title="${esc(issues.join(" · "))}">${esc(warning)}</span>` : ""}<span class="saved row-state">${drafts[a.artist_id] ? "Correction à enregistrer" : r.saved_at ? "Corrigé" : "Accepté par défaut"}</span></td><td class="num">${a.collection_tracks}</td><td class="row-profiles">${profileLinks(o,r)}</td><td><div class="inline-roles">${roleGroups.map(role=>`<label><input type="checkbox" data-field="roles" value="${role}" ${roleValues(role).some(value=>roles.includes(value))?"checked":""} aria-label="${role} — ${esc(a.display_name)}">${role}</label>`).join("")}</div></td><td><select data-field="bass_related" aria-label="Bass-related — ${esc(a.display_name)}"><option value="unknown" ${r.bass_related == null ? "selected" : ""}>Non établi</option><option value="yes" ${r.bass_related === true ? "selected" : ""}>Oui</option><option value="no" ${r.bass_related === false ? "selected" : ""}>Non</option></select></td><td><select data-field="decision" aria-label="Tri — ${esc(a.display_name)}">${Object.entries(labels).filter(([v])=>v!=="pending").map(([v,l])=>`<option value="${v}" ${r.decision === v ? "selected" : ""}>${l}</option>`).join("")}</select><span class="saved">IA : ${esc(proposals[o.interest_proposal ?? "uncertain"])}</span></td></tr>`;
}
function addRows() {
  if(saving) return;
  const previous = rowLimit; rowLimit += 100;
  $("rows").insertAdjacentHTML("beforeend",filtered.slice(previous,rowLimit).map(rowHTML).join(""));
  $("more-rows").hidden = rowLimit >= filtered.length;
}
function setDraft(id, value) {
  drafts[id] = {...reviewFor(id),...value,accepted_by_default:false};
  updateProgress();
  const row = [...$("rows").children].find(row=>row.dataset.row === id);
  if(row) { row.classList.add("modified"); row.querySelector(".row-state").textContent = "Correction à enregistrer"; }
}
function canLeave() { return !saving; }
function selectArtist(id, focus = false) {
  if (id === current || !canLeave()) return;
  current = id; $("detail").hidden = false; renderDetail();
  if (focus) $("detail-title").focus();
}
function renderDetail() {
  const a = data.artists.find(a => a.artist_id === current), o = observations[current] ?? {}, r = reviewFor(current);
  const provider = data.musicbrainz.artists[current] ?? {}, roles = rolesFor(a);
  decision = r.decision ?? "pending";
  const bass = r.bass_related;
  const sampled = data.tracks.filter(t => t.credits.some(c => c.artist_id === current));
  const spotify = r.spotify_url ?? (o.links ?? []).find(l=>l.url.includes("open.spotify.com/artist/"))?.url ?? "";
  const soundcloud = r.soundcloud_url ?? (o.links ?? []).find(l=>l.url.includes("soundcloud.com/"))?.url ?? "";
  $("detail").innerHTML = `<div class="detail-top"><div><h2 id="detail-title" tabindex="-1">${esc(a.display_name)}</h2><p class="detail-sub">${a.collection_tracks} sons en collection · ${sampled.length} dans ce pilote</p></div><button id="close-detail" type="button">Fermer</button></div>
    <div id="profile-links" class="links">${profileLinks(o,r)}</div>
    <p class="detail-sub">${esc(identityLabels[o.identity_status] ?? "Identité à auditer")} · Bass-related : ${o.bass_related === true ? "oui (proposé)" : o.bass_related === false ? "non (proposé)" : "non établi"}</p>
    <p id="human-identity" class="detail-sub">Identité retenue ${r.accepted_by_default ? "par défaut" : "après correction"} : ${esc(humanIdentityLabels[r.identity_decision ?? "pending"])}.</p>
    <h3>Proposition IA : ${esc(proposals[o.interest_proposal ?? "uncertain"])}</h3><p class="reason">${esc(o.reason ?? "Audit non réalisé.")}</p>
    ${(o.issues ?? []).length ? `<div class="issues"><strong>À vérifier</strong>${o.issues.map(i=>`<p>${esc(i)}</p>`).join("")}</div>` : ""}
    <details open><summary>Preuves et sources · ${(o.sources ?? []).length}</summary>${(o.sources ?? []).map(s=>`<p class="source">${safeLink(s.url,s.title)}<small>${esc(s.supports)}</small></p>`).join("")}</details>
    <details><summary>Sons du pilote · ${sampled.length}</summary><ul>${sampled.map(t=>`<li>${esc(t.title)}<br><span class="saved">${esc(t.credits.map(c=>c.name).join(" · "))}</span></li>`).join("")}</ul></details>
    <details><summary>Autres titres de ta collection</summary><ul>${a.representative_titles.map(t=>`<li>${esc(t)}</li>`).join("")}</ul></details>
    <details><summary>Candidats MusicBrainz et genres bruts</summary><p>Le score mesure la pertinence du nom, pas la certitude d’identité. Les genres d’artiste ne classent pas les morceaux.</p>${(provider.details ?? []).map(d=>`<p class="source">${safeLink(`https://musicbrainz.org/artist/${d.id}`,d.name)}<small>${esc(d.disambiguation || "Sans désambiguïsation")} · ${(o.retained_mbids ?? []).includes(d.id) ? "Rapproché par l’IA" : "Non retenu dans l’audit"}</small><small>Genres bruts : ${esc((d.genres ?? []).map(g=>g.name).join(", ") || "aucun")}</small></p>`).join("") || '<p>Aucun détail de candidat.</p>'}<ul>${(provider.candidates ?? []).map(c=>`<li>${esc(c.name)} — score ${esc(c.score)} ${esc(c.disambiguation ?? "")}</li>`).join("")}</ul></details>
    <form id="review-form" class="review-form"><h3>Corrections facultatives</h3><div class="decisions" aria-label="Choix de tri">${Object.entries(labels).filter(([v])=>v!=="pending").map(([v,l])=>`<button type="button" data-decision="${v}" aria-pressed="${decision === v}">${l}</button>`).join("")}</div>
    <label>Revue de l’identité<select id="identity" aria-label="Revue de l’identité"><option value="pending" ${(r.identity_decision ?? "pending") === "pending" ? "selected" : ""}>À vérifier</option><option value="accepted" ${r.identity_decision === "accepted" ? "selected" : ""}>Rapprochement correct</option><option value="rejected" ${r.identity_decision === "rejected" ? "selected" : ""}>Mauvais artiste</option></select></label>
    <label>Profil Spotify retenu<input id="spotify-url" type="url" maxlength="500" value="${esc(spotify)}" placeholder="https://open.spotify.com/artist/…"></label>
    <label>Profil SoundCloud retenu<input id="soundcloud-url" type="url" maxlength="500" value="${esc(soundcloud)}" placeholder="https://soundcloud.com/…"></label>
    <div class="role-checks" role="group" aria-label="Rôles corrigés">${roleGroups.map(role=>`<label><input type="checkbox" name="roles" value="${role}" ${roleValues(role).some(value=>roles.includes(value))?"checked":""}>${role}</label>`).join("")}</div>
    <label>Bass-related<select id="bass"><option value="unknown" ${bass == null ? "selected" : ""}>Non établi</option><option value="yes" ${bass === true ? "selected" : ""}>Oui</option><option value="no" ${bass === false ? "selected" : ""}>Non</option></select></label>
    <label>Notes personnelles<textarea id="notes" maxlength="4000" placeholder="Lien douteux, crédit à revoir, raison de ton choix…">${esc(r.notes ?? "")}</textarea></label>
    <div class="form-actions"><span id="save-state" class="saved">Les corrections rejoignent le lot à enregistrer.</span></div></form>`;
  $("review-form").addEventListener("input", markDirty);
  $("review-form").addEventListener("change", markDirty);
  $("detail").querySelectorAll("[data-decision]").forEach(b=>b.addEventListener("click",()=>{
    decision = b.dataset.decision;
    $("detail").querySelectorAll("[data-decision]").forEach(b=>b.setAttribute("aria-pressed", String(b.dataset.decision === decision)));
    markDirty();
  }));
  $("review-form").addEventListener("submit", e=>e.preventDefault());
  $("close-detail").addEventListener("click",()=>{current=null; $("detail").hidden=true;});
}
function markDirty() {
  const payload = {decision, roles:[...$("review-form").querySelectorAll('[name="roles"]:checked')].flatMap(i=>roleValues(i.value)),
    bass_related: $("bass").value === "unknown" ? null : $("bass").value === "yes", notes:$("notes").value,
    identity_decision:$("identity").value, spotify_url:$("spotify-url").value.trim(), soundcloud_url:$("soundcloud-url").value.trim()};
  setDraft(current,payload); renderRows();
  $("save-state").textContent = "Correction ajoutée au lot";
}
async function saveReview() {
  if(saving || !dirty) return;
  saving = true; updateProgress();
  document.querySelectorAll("main input,main select,main textarea,main button").forEach(c=>c.disabled=true);
  try {
    const response = await fetch("/api/reviews",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(drafts)});
    if (response.status === 400) { $("status").textContent="Aucune correction enregistrée. Vérifie les liens : profil d’artiste Spotify et profil SoundCloud uniquement."; return; }
    if (!response.ok) throw new Error(await response.text());
    Object.assign(data.reviews,await response.json()); drafts = {}; dirty = false;
    $("status").textContent = "Toutes tes corrections sont enregistrées. Le reste est accepté par défaut.";
    renderRows(); if(current) renderDetail();
  } catch { $("status").textContent = "Échec de sauvegarde. Tes corrections sont conservées à l’écran ; réessaie."; }
  finally { saving = false; document.querySelectorAll("main input,main select,main textarea,main button").forEach(c=>c.disabled=false); updateProgress(); }
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
    <div class="report-section"><h3>Ton mode de revue</h3><ul><li>Les valeurs inchangées sont acceptées par défaut. Corrige seulement les exceptions, puis enregistre tes corrections ensemble.</li><li>Écarter ne supprime aucun crédit ni morceau. Producer / DJ, Singer et MC sont cumulables.</li><li>Les identités introuvables restent non résolues ; les champs manquants restent vides. Aucun artiste n’est suivi automatiquement sur Spotify.</li><li>Les images et la taxonomie des genres restent pour la suite.</li></ul></div>
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
  } catch { $("failure").hidden=false; $("context").textContent="Le serveur doit accéder au dossier complet du pilote."; }
}
document.querySelectorAll("[data-tab]").forEach(b=>b.addEventListener("click",()=>showTab(b.dataset.tab)));
for(const id of ["search","role","proposal","review","attention","sort"]) $(id).addEventListener(id==="search"?"input":"change",()=>{clearTimeout(searchTimer); searchTimer=setTimeout(()=>{rowLimit=100; if(data) renderRows();},id==="search"?120:0);});
$("reset").addEventListener("click",()=>{ for(const id of ["search","role","proposal","review"]) $(id).value=""; $("attention").checked=false; $("sort").value="name"; if(data) renderRows(); });
$("rows").addEventListener("click",e=>{const b=e.target.closest("[data-artist]"); if(b) selectArtist(b.dataset.artist);});
$("rows").addEventListener("change",e=>{
  const field=e.target.dataset.field, row=e.target.closest("[data-row]"); if(!field || !row || saving) return;
  const id=row.dataset.row, value=field==="roles" ? [...row.querySelectorAll('[data-field="roles"]:checked')].flatMap(i=>roleValues(i.value)) : field==="bass_related" ? e.target.value==="unknown" ? null : e.target.value==="yes" : e.target.value;
  setDraft(id,{[field]:value}); if(current===id) renderDetail();
});
$("save-all").addEventListener("click",saveReview);
document.querySelector(".export").addEventListener("click",e=>{if(dirty || saving){e.preventDefault(); $("status").textContent="Enregistre tes corrections avant d’exporter.";}});
new IntersectionObserver(entries=>{if(data && entries.some(e=>e.isIntersecting) && rowLimit<filtered.length) addRows();},{rootMargin:"600px"}).observe($("more-rows"));
$("track-table").addEventListener("click",e=>{const b=e.target.closest("[data-track-artist]"); if(b) { selectArtist(b.dataset.trackArtist,true); if(current === b.dataset.trackArtist) showTab("artists"); }});
$("retry").addEventListener("click",load);
document.addEventListener("keydown",e=>{if(e.key==="Escape" && current && !saving){current=null; $("detail").hidden=true;}});
window.addEventListener("beforeunload",e=>{if(dirty || saving){e.preventDefault(); e.returnValue="";}});
load();
