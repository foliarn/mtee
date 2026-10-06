"use strict";
const $ = id => document.getElementById(id);
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[c]));
const labels = {keep:"Garder", exclude:"Écarter"};
const proposals = {keep:"Garder", exclude:"Bloat possible", uncertain:"Garder"};
const identityLabels = {matched:"Identité rapprochée par l’IA", provisional:"Identité à consolider", unresolved:"Identité non résolue"};
const humanIdentityLabels = {pending:"À vérifier", accepted:"Rapprochement correct", rejected:"Mauvais artiste"};
const badge = (value, text = labels[value] ?? value) => `<span class="badge ${esc(value)}">${esc(text)}</span>`;
const safeLink = (url, title, className = "") => {
  try { const parsed = new URL(url); if (parsed.protocol !== "https:" || parsed.username || parsed.password) return esc(title); }
  catch { return esc(title); }
  return `<a class="${esc(className)}" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(title)}</a>`;
};
let data, observations = {}, current = null, filtered = [], dirty = false, decision = "pending", saving = false;
let drafts = {}, page = 1, searchTimer;
const pageArtists = () => filtered.slice((page-1)*100,page*100);
const triFor = r => r.decision === "exclude" ? "exclude" : "keep";
const reviewFor = id => drafts[id] ?? data.reviews[id] ?? {};
const roleGroups = ["Producer", "DJ", "Singer", "MC"];

function profileLinks(o, r) {
  const links = [{url:r.spotify_url,label:"Spotify"},{url:r.soundcloud_url,label:"SoundCloud"}].filter(l=>l.url);
  return links.map(l=>safeLink(l.url,l.label ?? "Profil","profile")).join("") || '<span class="saved">Aucun profil retenu à ce stade.</span>';
}

function rolesFor(artist) { return reviewFor(artist.artist_id).roles ?? []; }
function attentionFor(artist) { const o = observations[artist.artist_id] ?? {}; return (o.issues ?? []).length > 0 || o.identity_status !== "matched"; }
function updateProgress() {
  const count = Object.keys(drafts).length;
  dirty = count > 0;
  $("progress").textContent = saving ? "Enregistrement…" : count ? `${count} modification${count > 1 ? "s" : ""}` : "";
  $("save-all").textContent = `Valider cette page (${pageArtists().length})`;
  $("save-all").disabled = saving || !pageArtists().length;
}
function matchesRecap(a) {
  const value=$("recap-filter").value, r=reviewFor(a.artist_id), o=observations[a.artist_id] ?? {};
  if(!value) return true;
  if(value === "bass") return r.bass_related === true;
  if(value === "spotify" || value === "soundcloud") return Boolean(r[`${value}_url`]);
  if(value === "unresolved") return o.identity_status === "unresolved";
  return data.tracks.some(t=>t.credits.some(c=>c.artist_id === a.artist_id) && t.selection_categories?.includes(value));
}
function renderRows() {
  const query = $("search").value.trim().toLocaleLowerCase("fr"), role = $("role").value;
  filtered = data.artists.filter(a => {
    const o = observations[a.artist_id] ?? {}, r = reviewFor(a.artist_id), roles = rolesFor(a);
    return (!query || [a.display_name, ...a.representative_titles].join(" ").toLocaleLowerCase("fr").includes(query)) &&
      (!role || (role === "unknown" ? !roles.length : roles.includes(role))) &&
      (!$("proposal").value || (o.interest_proposal === "exclude" ? "exclude" : "keep") === $("proposal").value) &&
      (!$("review").value || ($("review").value === "modified" ? drafts[a.artist_id] || r.saved_at : triFor(r) === $("review").value)) && matchesRecap(a) &&
      (!$("attention").checked || attentionFor(a));
  });
  filtered.sort((a,b) => ($("sort").value === "count" ? b.collection_tracks - a.collection_tracks :
    $("sort").value === "attention" ? Number(attentionFor(b)) - Number(attentionFor(a)) : 0) || a.display_name.localeCompare(b.display_name, "fr"));
  const pages=Math.max(1,Math.ceil(filtered.length/100)); page=Math.min(page,pages);
  $("rows").innerHTML = pageArtists().map(rowHTML).join("");
  $("visible-count").textContent = filtered.length ? `${(page-1)*100+1}–${Math.min(page*100,filtered.length)} / ${filtered.length}` : "0";
  $("page-number").innerHTML = Array.from({length:pages},(_,i)=>`<option value="${i+1}" ${page===i+1 ? "selected" : ""}>${i+1}</option>`).join("");
  $("page-count").textContent=`/ ${pages}`;
  $("previous-page").disabled=page===1 || saving; $("next-page").disabled=page===pages || saving;
  $("empty").hidden = filtered.length !== 0;
  updateProgress();
}
function rowHTML(a) {
  const o = observations[a.artist_id] ?? {}, r = reviewFor(a.artist_id), roles = rolesFor(a);
  const issues = o.issues ?? [];
  const warning = o.identity_status === "unresolved" ? "Identité introuvable" : issues[0] ?? (o.identity_status !== "matched" ? "Identité à consolider" : "");
  return `<tr data-row="${esc(a.artist_id)}" class="${drafts[a.artist_id] ? "modified" : ""}"><td><button class="artist-button" data-artist="${esc(a.artist_id)}" aria-label="Dossier de ${esc(a.display_name)}">${esc(a.display_name)}</button>${warning ? `<span class="row-warning" title="${esc(issues.join(" · "))}">${esc(warning)}</span>` : ""}<span class="saved row-state">${drafts[a.artist_id] ? "Correction à enregistrer" : r.saved_at ? "Corrigé" : "Accepté par défaut"}</span></td><td class="num">${a.collection_tracks}</td><td class="row-profiles">${profileLinks(o,r)}</td><td><div class="inline-roles">${roleGroups.map(role=>`<label><input type="checkbox" data-field="roles" value="${role}" ${roles.includes(role)?"checked":""} aria-label="${role} — ${esc(a.display_name)}">${role}</label>`).join("")}</div></td><td><select data-field="bass_related" aria-label="Bass-related — ${esc(a.display_name)}"><option value="yes" ${r.bass_related === true ? "selected" : ""}>Oui</option><option value="no" ${r.bass_related !== true ? "selected" : ""}>Non</option></select></td><td><select data-field="decision" aria-label="Tri — ${esc(a.display_name)}">${Object.entries(labels).filter(([v])=>v!=="pending").map(([v,l])=>`<option value="${v}" ${triFor(r) === v ? "selected" : ""}>${l}</option>`).join("")}</select><span class="saved">IA : ${esc(proposals[o.interest_proposal ?? "uncertain"])}</span></td></tr>`;
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
  decision = triFor(r);
  const bass = r.bass_related;
  const sampled = data.tracks.filter(t => t.credits.some(c => c.artist_id === current));
  const spotify = r.spotify_url ?? (o.links ?? []).find(l=>l.url.includes("open.spotify.com/artist/"))?.url ?? "";
  const soundcloud = r.soundcloud_url ?? (o.links ?? []).find(l=>l.url.includes("soundcloud.com/"))?.url ?? "";
  $("detail").innerHTML = `<div class="detail-top"><div><h2 id="detail-title" tabindex="-1">${esc(a.display_name)}</h2><p class="detail-sub">${a.collection_tracks} sons en collection · ${sampled.length} dans ce pilote</p></div><button id="close-detail" type="button">Fermer</button></div>
    <div id="profile-links" class="links">${profileLinks(o,r)}</div>
    <p class="detail-sub">${esc(identityLabels[o.identity_status] ?? "Identité à auditer")}</p>
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
    <div class="role-checks" role="group" aria-label="Rôles corrigés">${roleGroups.map(role=>`<label><input type="checkbox" name="roles" value="${role}" ${roles.includes(role)?"checked":""}>${role}</label>`).join("")}</div>
    <label>Bass-related<select id="bass"><option value="yes" ${bass === true ? "selected" : ""}>Oui</option><option value="no" ${bass !== true ? "selected" : ""}>Non</option></select></label>
    <label>Notes personnelles<textarea id="notes" maxlength="4000" placeholder="Lien douteux, crédit à revoir, raison de ton choix…">${esc(r.notes ?? "")}</textarea></label>
    <div class="form-actions"><span id="save-state" class="saved"></span></div></form>`;
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
function markDirty(event) {
  if(event?.target.name === "roles" && event.target.value === "Producer" && event.target.checked) $("review-form").querySelector('[name="roles"][value="DJ"]').checked = true;
  const payload = {decision, roles:[...$("review-form").querySelectorAll('[name="roles"]:checked')].map(i=>i.value),
    bass_related: $("bass").value === "unknown" ? null : $("bass").value === "yes", notes:$("notes").value,
    identity_decision:$("identity").value, spotify_url:$("spotify-url").value.trim(), soundcloud_url:$("soundcloud-url").value.trim()};
  setDraft(current,payload); renderRows();
  $("save-state").textContent = "Correction ajoutée au lot";
}
async function saveReview() {
  if(saving || !pageArtists().length) return;
  const changes=Object.fromEntries(pageArtists().map(a=>{const r=reviewFor(a.artist_id); return [a.artist_id,{...r,decision:triFor(r),bass_related:r.bass_related === true}];}));
  saving = true; updateProgress();
  document.querySelectorAll("main input,main select,main textarea,main button").forEach(c=>c.disabled=true);
  try {
    const response = await fetch("/api/page",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(changes)});
    if (response.status === 400) { $("status").textContent="Aucune correction enregistrée. Vérifie les liens : profil d’artiste Spotify et profil SoundCloud uniquement."; return; }
    if (!response.ok) throw new Error(await response.text());
    Object.assign(data.reviews,await response.json()); Object.keys(changes).forEach(id=>delete drafts[id]);
    $("status").textContent = "Page validée.";
    renderRows(); renderReport(); if(current) renderDetail();
  } catch { $("status").textContent = "Échec de sauvegarde. Tes corrections sont conservées à l’écran ; réessaie."; }
  finally { saving = false; document.querySelectorAll("main input,main select,main textarea,main button").forEach(c=>c.disabled=false); renderRows(); }
}
function renderTracks() {
  $("track-table").innerHTML = `<table><caption class="sr-only">Morceaux sélectionnés</caption><thead><tr><th>#</th><th>Titre</th><th>Artistes</th><th>Genres retenus</th><th>Tags ignorés / à vérifier</th></tr></thead><tbody>${data.tracks.map((t,i)=>{
    const g=t.genre_audit ?? {retained:[],ignored:[],alerts:[]};
    return `<tr id="track-${esc(t.track_id)}"><td class="num">${i+1}</td><td>${esc(t.title)}<br><span class="saved">Tags : ${esc((t.observed_genres ?? []).join(", ") || "—")}</span></td><td>${t.credits.map(c=>`<button type="button" class="artist-button" data-track-artist="${esc(c.artist_id)}">${esc(c.name)}</button>`).join(" · ")}</td><td title="${esc(g.source)}">${esc(g.retained.join(", ") || "—")}</td><td><span class="saved">${esc(g.ignored.join(", "))}</span>${g.alerts.map(a=>`<p class="genre-alert">${esc(a.tag)} : ${esc(a.reason)}</p>`).join("")}</td></tr>`;
  }).join("")}</tbody></table>`;
}
function renderReport() {
  const runs=data.summary.provider_runs ?? [], requests=runs.reduce((n,r)=>n+r.http_requests,0), seconds=runs.reduce((n,r)=>n+r.seconds,0);
  const metrics=[...roleGroups.map(role=>({label:role,kind:"role",value:role,test:a=>rolesFor(a).includes(role)})),
    {label:"Garder",kind:"review",value:"keep",test:a=>triFor(reviewFor(a.artist_id)) === "keep"},
    {label:"Écarter · idgaf",kind:"review",value:"exclude",test:a=>triFor(reviewFor(a.artist_id)) === "exclude"},
    ...["bass","spotify","soundcloud","unresolved"].map((value,i)=>({label:["Bass-related","Spotify","SoundCloud","Identités non résolues"][i],kind:"recap",value,test:a=>{
      const r=reviewFor(a.artist_id); return value === "bass" ? r.bass_related === true : value === "unresolved" ? observations[a.artist_id]?.identity_status === "unresolved" : Boolean(r[`${value}_url`]);
    }}))];
  const categories=[...new Set(data.tracks.flatMap(t=>t.selection_categories ?? []))];
  const categoryLabels={producer_bass:"Producer bass",mc_bass_context:"MC · collaborations bass",singer_bass_context:"Singer · collaborations bass",original_remixed_possible_bloat:"Original remixé",less_documented_producer:"Producer peu documenté",short_or_ambiguous_name:"Nom court / ambigu",bootleg_flip_edit:"Bootleg / flip / edit",additional:"Complément",producer_dnb:"Producer DnB",producer_dubstep:"Producer dubstep",producer_ukg:"Producer UKG",singer:"Singer",mc:"MC",original_remixed:"Original remixé",remix:"Remix",bootleg:"Bootleg / edit",collaboration:"Collaboration",single_credit:"Un seul crédit",solo:"Solo",short_name:"Nom court",combined_roles:"Rôles combinés",ambiguous:"Identité ambiguë"};
  const button=(label,kind,value,count)=>`<button class="recap-link" data-filter-kind="${esc(kind)}" data-filter-value="${esc(value)}"><span>${esc(label)}</span><strong>${count}</strong></button>`;
  const recapValue=$("recap-filter").value;
  $("recap-filter").innerHTML='<option value="">Tous</option>'+[...metrics.filter(m=>m.kind==="recap").map(m=>({value:m.value,label:m.label})),...categories.map(value=>({value,label:categoryLabels[value] ?? value.replaceAll("_"," ")}))].map(m=>`<option value="${esc(m.value)}">${esc(m.label)}</option>`).join("");
  $("recap-filter").value=recapValue;
  const alerts=data.tracks.filter(t=>t.genre_audit?.alerts.length);
  $("report").innerHTML=`<div class="report-grid"><section class="report-section"><h3>Artistes</h3>${metrics.map(m=>button(m.label,m.kind,m.value,data.artists.filter(m.test).length)).join("")}</section>
    <section class="report-section"><h3>Catégories du test</h3>${categories.map(value=>button(categoryLabels[value] ?? value.replaceAll("_"," "),"recap",value,data.artists.filter(a=>data.tracks.some(t=>t.selection_categories?.includes(value) && t.credits.some(c=>c.artist_id===a.artist_id))).length)).join("")}</section>
    <section class="report-section genre-report"><h3>Genres à vérifier · ${alerts.length}</h3>${alerts.length ? alerts.map(t=>`<div><button class="artist-button" data-track="${esc(t.track_id)}">${esc(t.title)}</button><span class="saved">${esc(t.credits.map(c=>c.name).join(" · "))}</span>${t.genre_audit.alerts.map(a=>`<p class="genre-alert">${esc(a.tag)} écarté : ${esc(a.reason)}</p>`).join("")}</div>`).join("") : '<span class="saved">Aucun tag contradictoire détecté.</span>'}</section>
    <section class="report-section"><h3>Coût observé</h3><dl><dt>Appels MusicBrainz</dt><dd>${requests}</dd><dt>Collecte</dt><dd>${seconds.toFixed(1)} s</dd><dt>Tokens IA</dt><dd>Non exposés</dd><dt>Prix</dt><dd>Non mesuré</dd></dl></section></div>`;
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

    renderReport(); renderRows(); renderTracks();
  } catch { $("failure").hidden=false;  }
}
document.querySelectorAll("[data-tab]").forEach(b=>b.addEventListener("click",()=>{if(b.dataset.tab==="report" && data) renderReport(); showTab(b.dataset.tab);}));
for(const id of ["search","role","proposal","review","attention","sort","recap-filter"]) $(id).addEventListener(id==="search"?"input":"change",()=>{clearTimeout(searchTimer); searchTimer=setTimeout(()=>{page=1; if(data) renderRows();},id==="search"?120:0);});
$("reset").addEventListener("click",()=>{ for(const id of ["search","role","proposal","review"]) $(id).value=""; $("attention").checked=false; $("sort").value="name"; page=1; $("recap-filter").value=""; $("recap-filter-label").hidden=true; if(data) renderRows(); });
$("rows").addEventListener("click",e=>{const b=e.target.closest("[data-artist]"); if(b) selectArtist(b.dataset.artist);});
$("rows").addEventListener("change",e=>{
  const field=e.target.dataset.field, row=e.target.closest("[data-row]"); if(!field || !row || saving) return;
  if(field === "roles" && e.target.value === "Producer" && e.target.checked) row.querySelector('[data-field="roles"][value="DJ"]').checked = true;
  const id=row.dataset.row, value=field==="roles" ? [...row.querySelectorAll('[data-field="roles"]:checked')].map(i=>i.value) : field==="bass_related" ? e.target.value==="unknown" ? null : e.target.value==="yes" : e.target.value;
  setDraft(id,{[field]:value}); if(current===id) renderDetail();
});
$("save-all").addEventListener("click",saveReview);
$("previous-page").addEventListener("click",()=>{page--; renderRows();});
$("next-page").addEventListener("click",()=>{page++; renderRows();});
$("page-number").addEventListener("change",()=>{page=Number($("page-number").value); renderRows();});
$("report").addEventListener("click",e=>{
  const filter=e.target.closest("[data-filter-kind]"), track=e.target.closest("[data-track]");
  if(filter){current=null; $("detail").hidden=true; $("reset").click(); const kind=filter.dataset.filterKind; $(kind==="recap"?"recap-filter":kind).value=filter.dataset.filterValue; $("recap-filter-label").hidden=kind!=="recap"; renderRows(); showTab("artists");}
  if(track){showTab("tracks"); document.getElementById(`track-${track.dataset.track}`).scrollIntoView({block:"center"});}
});
document.querySelector(".export").addEventListener("click",e=>{if(dirty || saving){e.preventDefault(); $("status").textContent="Enregistre tes corrections avant d’exporter.";}});

$("track-table").addEventListener("click",e=>{const b=e.target.closest("[data-track-artist]"); if(b && !saving) { $("reset").click(); page=Math.floor(filtered.findIndex(a=>a.artist_id===b.dataset.trackArtist)/100)+1; renderRows(); current=null; selectArtist(b.dataset.trackArtist,true); showTab("artists"); }});
$("retry").addEventListener("click",load);
document.addEventListener("keydown",e=>{if(e.key==="Escape" && current && !saving){current=null; $("detail").hidden=true;}});
window.addEventListener("beforeunload",e=>{if(dirty || saving){e.preventDefault(); e.returnValue="";}});
load();
