# Spécification visuelle MTEE — prototype 02

## Direction

MTEE se comporte visuellement comme un poste de travail musical : une surface
calme, dense et structurée, où l'accent bleu marque l'action ou le morceau en
lecture. Les panneaux portent des zones fonctionnelles ; ils ne sont pas des
cartes décoratives. La vue doit rester utile avec une collection longue, un
chemin accentué ou une métadonnée absente.

## Tokens

| Rôle | Valeur |
|---|---|
| Background | `#080E18` |
| Panel | `#111B2B` |
| Active surface | `#1B2A40` |
| Primary text | `#EDF2FA` |
| Secondary text | `#A5B3C7` |
| Accent / focus | `#80B5FF` |
| Error | `#FF9A8B` |
| Body | 14 px |
| Secondary | 12 px |
| Table row | 36 px |
| Panel radius | 12 px |
| Control radius | 7 px |

La police préférée reste Geist Sans lorsqu'elle sera embarquée avec sa licence.
Le prototype utilise la police système enregistrée par le socle lorsqu'aucun
fichier de police n'est présent.

## Browser

La fenêtre de référence est 1440 × 900. Le Browser place le dossier à gauche,
les onglets au-dessus de la surface de travail, la table au centre et
l'inspecteur à droite lorsqu'il est demandé. Le lecteur commun reste ancré en
bas, sous le panneau des tâches de session.

La table commence par Title, Artist, Genre, BPM et Key. Duration, Format et
Filename sont des colonnes secondaires accessibles par `More columns`. Un clic
sur un en-tête simule le tri et conserve la colonne active visible. La ligne
sélectionnée utilise la surface de sélection ; la ligne en lecture porte un
trait bleu gauche et un titre plus fort. Un double-clic change fictivement le
morceau joué sans déplacer la sélection.

La vue Artwork conserve une entrée par fichier, sans regroupement par album.
Une pochette absente affiche `No artwork`, tandis qu'un artiste ou un genre
manquant reste explicite avec un tiret ou un libellé d'absence.

Sous 1160 px, l'explorateur latéral se replie. Sous 930 px, Library et
Inspector deviennent deux panneaux commutables ; leur sélection reste en
mémoire. Ce comportement est une règle de maquette et devra être repris par
l'explorateur fonctionnel.

## Listening view

Listening view suit le morceau en lecture, même si Browser conserve une autre
sélection. La grande pochette et l'identité occupent la partie supérieure ; la
barre de progression prépare l'emplacement de la waveform du plan 08. Les
commandes de transport sont centrées et la file rappelle que son ordre est
capturé au lancement.

Le lecteur inférieur disparaît dans cet espace. `Back to browser` restaure le
contexte de Browser. La progression est volontairement classique jusqu'à
l'implémentation de la waveform.

Les champs de métadonnée partagent le même composant que l'inspecteur Browser.
Une perte de focus montre Saving puis Saved, ou conserve la saisie et affiche
Could not save avec Retry. Undo remet l'état visuel au repos. En multisélection,
Mixed values est un état d'affichage ; il ne peut pas être écrit comme une
valeur.

## Convert

Convert sépare les fichiers d'entrée et les réglages de sortie. Les commandes
immédiates sont Add files, Add selected tracks et Start conversion. Les choix
fréquents sont visibles ; Sample rate, Channels et Metadata sont regroupés
dans Advanced.

Les combinaisons affichées sont explicitement fictives au stade du prototype.
Une erreur est attachée à l'entrée concernée, garde le fichier source intact et
propose Retry. Open output folder est visible mais simulé.

## Vocabulaire

Les mêmes actions gardent le même libellé d'un écran à l'autre : Browser,
Listening view, Convert, Inspector, Save, Saved, Retry, Undo et Back to browser.
Les messages décrivent l'état et l'action possible ; ils n'exposent pas de
journal technique dans le parcours courant.
