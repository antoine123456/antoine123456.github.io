#!/usr/bin/env python3
"""
build_helmholtz.py — Paquet « Helmholtz » façon Refold, avec animations.

Une note par notion : la notion en grand + une question au recto ; au verso
la réponse courte (celle qu'on tape dans l'appli), la formule, une
explication et une animation en boucle (WebP animé) à la place de l'image.

Sorties :
  helmholtz_media/*.webp   les animations (régénérées si numpy, scipy et
                           Pillow sont installés ; sinon celles déjà là servent)
  helmholtz.json           paquet pour l'appli (＋ Importer un fichier .json)
  Helmholtz.apkg           à importer dans Anki (mêmes ids de cartes que
                           l'appli, pour ankisync) — il faut le paquet 'anki'

Usage :
    trainervenv/bin/python build_helmholtz.py
Convention : dépendance en temps e^(−iωt), donc onde sortante e^(+ikr).
"""
import html
import json
import math
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = "helmholtz_media"
MEDIA = os.path.join(HERE, MEDIA_DIR)
DECK = "🌊 Helmholtz"
MODEL = "Helmholtz (Refold)"
ID_BASE = 1_106_000_000_000  # ids dans le passé, hors des autres paquets (cf. build_vocab.py)
# Sous-paquets : des lettres, pas des numéros, pour ne pas déclencher le verrou par étapes.
SUBS = {
    "A": "A · Régime harmonique",
    "B": "B · Onde plane",
    "C": "C · Sources et rayonnement",
    "D": "D · Cavités et modes propres",
}

# (clé, notion, question, réponse courte à taper, formule, nature, explication, animation)
# La clé fixe l'id de la carte : ne pas la changer, ajouter les nouvelles cartes avec une clé libre.
CARDS = [
    # ── A · Régime harmonique : forme générale, constantes, complexes ──────────
    ("A", 101, "Équation d’onde", "Quelles variables ses dérivées secondes relient-elles ?", "temps et espace",
     "∂²p/∂t² = c² ∇²p", "forme générale",
     "La dérivée seconde en temps vaut c² fois le laplacien. C’est le point de départ, ici pour une pression p.", None),
    ("A", 102, "Régime harmonique", "Que suppose-t-on sur la dépendance en temps ?", "une seule pulsation",
     "p(x, t) = Re[ u(x) e<sup>−iωt</sup> ]", "régime harmonique",
     "Tout le champ oscille à la même pulsation ω. Le temps se factorise et il ne reste que l’amplitude complexe u(x).", "onde_progressive"),
    ("A", 103, "Équation de Helmholtz", "Quel opérateur porte-t-elle, et quel est son seul paramètre ?", "laplacien et nombre d'onde",
     "∇²u + k²u = 0", "forme générale",
     "Forme homogène, sans source. On l’obtient en injectant le régime harmonique dans l’équation d’onde.", "onde_plane"),
    ("A", 104, "Du temps à la fréquence", "Par quoi remplace-t-on ∂²/∂t² en régime harmonique ?", "moins oméga carré",
     "∂²/∂t² → −ω²", "régime harmonique",
     "Dériver deux fois e<sup>−iωt</sup> donne (−iω)² = −ω². D’où −ω²u = c²∇²u, soit ∇²u + (ω/c)²u = 0.", None),
    ("A", 105, "Nombre d’onde k", "Comment s’écrit-il avec ω et c ?", "oméga sur c",
     "k = ω/c = 2π/λ", "constantes",
     "En rad/m. C’est la pulsation spatiale : la phase tourne de k radians par mètre parcouru.", "onde_progressive"),
    ("A", 106, "Longueur d’onde λ", "Comment se déduit-elle de c et de f ?", "c sur f",
     "λ = c/f = 2π/k", "constantes",
     "En mètres. Dans l’air, 430 Hz donne λ ≈ 0,80 m.", "onde_progressive"),
    ("A", 107, "Pulsation ω", "Quel est son lien avec la fréquence f ?", "deux pi f",
     "ω = 2πf = ck", "constantes",
     "En rad/s. La période vaut T = 1/f = 2π/ω.", None),
    ("A", 108, "Célérité c", "Que vaut-elle pour le son dans l’air, en m/s ?", "343",
     "c ≈ 343 m/s (air, 20 °C)", "constantes",
     "Elle relie pulsation et nombre d’onde : ω = ck. Dans l’eau, environ 1 480 m/s.", None),
    ("A", 109, "Amplitude complexe u", "Que donnent son module et son argument ?", "amplitude et phase",
     "u = |u| e<sup>iφ</sup>", "parties complexes",
     "|u| est l’amplitude de l’oscillation au point x, φ = arg u son déphasage.", "onde_stationnaire"),
    ("A", 110, "Retour au champ physique", "Quelle partie du produit u e<sup>−iωt</sup> garde-t-on ?", "la partie réelle",
     "p = Re[ u e<sup>−iωt</sup> ] = |u| cos(ωt − φ)", "parties complexes",
     "Le calcul se fait en complexe, la grandeur mesurée est la partie réelle.", None),
    ("A", 111, "Re u et Im u", "Re u est le champ à t = 0. Quand le champ vaut-il Im u ?", "un quart de période plus tard",
     "Im u = p à ωt = π/2", "parties complexes",
     "Car Re[ u e<sup>−iπ/2</sup> ] = Re[ −iu ] = Im u. Les deux parties sont deux instantanés du même champ.", None),
    ("A", 112, "Convention e<sup>−iωt</sup>", "Avec elle, vers où se propage e<sup>ikx</sup> ?", "vers les x croissants",
     "Re[ e<sup>i(kx − ωt)</sup> ] = cos(kx − ωt)", "parties complexes",
     "Avec la convention opposée e<sup>+iωt</sup>, tous les signes s’inversent : l’onde sortante devient e<sup>−ikr</sup>.", "onde_progressive"),
    ("A", 113, "Onde progressive", "Comment est son enveloppe |u| ?", "constante",
     "u = e<sup>ikx</sup>, |u| = 1", "régime harmonique",
     "La crête avance, l’amplitude est la même partout : seule la phase kx change d’un point à l’autre.", "onde_progressive"),
    ("A", 114, "Onde stationnaire", "Que font ses nœuds au cours du temps ?", "ils restent fixes",
     "u = cos kx = ½ (e<sup>ikx</sup> + e<sup>−ikx</sup>)", "régime harmonique",
     "Somme de deux ondes progressives de sens opposés. Les nœuds sont espacés de λ/2.", "onde_stationnaire"),
    ("A", 115, "Linéarité", "Qu’est la somme de deux solutions ?", "encore une solution",
     "∇²(u₁ + u₂) + k²(u₁ + u₂) = 0", "forme générale",
     "C’est le principe de superposition : il explique les interférences et permet de sommer des sources.", "deux_ondes_planes"),
    ("A", 116, "Équation avec source", "Que devient le second membre pour une source s ?", "moins s",
     "∇²u + k²u = −s", "forme générale",
     "Forme inhomogène. Le signe moins est une convention : il rend la fonction de Green positive près de la source.", "monopole"),
    ("A", 117, "Problème bien posé", "Que faut-il ajouter à l’équation pour avoir une solution unique ?", "des conditions aux limites",
     None, "conditions aux limites",
     "Au bord : Dirichlet, Neumann ou Robin. En domaine infini : la condition de rayonnement de Sommerfeld.", None),

    # ── B · Onde plane ─────────────────────────────────────────────────────────
    ("B", 201, "Onde plane", "Comment sont ses surfaces de phase constante ?", "des plans parallèles",
     "u(x) = A e<sup>i k·x</sup>", "onde plane",
     "Solution élémentaire en espace libre. Les plans sont perpendiculaires au vecteur d’onde k.", "onde_plane"),
    ("B", 202, "Vecteur d’onde k", "Que fixent sa direction et sa norme ?", "sens et longueur d'onde",
     "‖k‖ = k = 2π/λ", "onde plane",
     "Sa direction est celle de la propagation ; sa norme est le nombre d’onde.", "onde_plane"),
    ("B", 203, "Relation de dispersion", "Que doit valoir k<sub>x</sub>² + k<sub>y</sub>² + k<sub>z</sub>² ?", "k carré",
     "k<sub>x</sub>² + k<sub>y</sub>² + k<sub>z</sub>² = ω²/c²", "onde plane",
     "C’est la condition pour que A e<sup>i k·x</sup> vérifie l’équation de Helmholtz.", None),
    ("B", 204, "Fronts d’onde", "Quelle distance sépare deux crêtes successives ?", "une longueur d'onde",
     "k·x = constante", "onde plane",
     "Mesurée le long de k. Perpendiculairement à k, le champ ne varie pas.", "onde_plane"),
    ("B", 205, "Vitesse de phase", "À quelle vitesse avancent les crêtes ?", "oméga sur k",
     "v = ω/k = c", "onde plane",
     "Le milieu est non dispersif : toutes les fréquences avancent à la même célérité c.", "onde_plane"),
    ("B", 206, "Deux ondes planes croisées", "Que dessine leur superposition ?", "des franges",
     "interfrange = λ / (2 sin(θ/2))", "onde plane",
     "θ est l’angle entre les deux directions. Les franges sont parallèles à la bissectrice des deux vecteurs d’onde.", "deux_ondes_planes"),

    # ── C · Sources et rayonnement ─────────────────────────────────────────────
    ("C", 301, "Source ponctuelle", "Par quelle distribution la modélise-t-on ?", "un Dirac",
     "s(x) = δ(x − x₀)", "source ponctuelle",
     "Toute la source est concentrée au point x₀. C’est la brique de base de n’importe quelle source étendue.", "monopole"),
    ("C", 302, "Fonction de Green G", "De quoi est-elle la réponse ?", "une source ponctuelle",
     "∇²G + k²G = −δ(x − x₀)", "fonction de Green",
     "C’est le champ créé en x par une source unité placée en x₀, avec la condition de rayonnement à l’infini.", "monopole"),
    ("C", 303, "Fonction de Green en 3D", "Comment décroît son amplitude ?", "en un sur r",
     "G = e<sup>ikr</sup> / (4πr)", "fonction de Green",
     "Onde sphérique sortante. r = ‖x − x₀‖ est la distance à la source.", None),
    ("C", 304, "Fonction de Green en 2D", "Quelle fonction spéciale y apparaît ?", "Hankel",
     "G = (i/4) H₀<sup>(1)</sup>(kr)", "fonction de Green",
     "Onde cylindrique sortante : la source est une ligne infinie vue en coupe.", "monopole"),
    ("C", 305, "Fonction de Green en 1D", "Comment varie son amplitude avec la distance ?", "elle reste constante",
     "G = (i/2k) e<sup>ik|x − x₀|</sup>", "fonction de Green",
     "Deux ondes planes qui partent de part et d’autre de la source, sans s’étaler.", None),
    ("C", 306, "Source étendue", "Par quelle opération obtient-on son champ à partir de G ?", "une convolution",
     "u(x) = ∫ G(x, x′) s(x′) dx′", "fonction de Green",
     "Par linéarité, on somme les contributions de tous les points de la source.", "deux_sources_en_phase"),
    ("C", 307, "Fonction de Hankel H₀<sup>(1)</sup>", "De quelles fonctions de Bessel est-elle faite ?", "J0 et Y0",
     "H₀<sup>(1)</sup> = J₀ + i Y₀", "fonction de Green",
     "Onde cylindrique sortante avec la convention e<sup>−iωt</sup>. H₀<sup>(2)</sup> = J₀ − i Y₀ est l’onde entrante.", "monopole"),
    ("C", 308, "Champ lointain", "Quelle condition porte sur kr ?", "kr grand devant un",
     "kr ≫ 1", "champ lointain",
     "À plusieurs longueurs d’onde de la source. L’onde y ressemble localement à une onde plane.", "monopole"),
    ("C", 309, "Hankel en champ lointain", "Comment décroît l’amplitude en 2D ?", "un sur racine de r",
     "H₀<sup>(1)</sup>(kr) ≈ √(2/(πkr)) e<sup>i(kr − π/4)</sup>", "champ lointain",
     "Une phase qui avance comme kr, une amplitude qui s’étale sur un cercle de plus en plus grand.", "monopole"),
    ("C", 310, "Décroissance géométrique", "Pourquoi 1/√r en 2D et 1/r en 3D ?", "conservation de l'énergie",
     "|u|² × 2πr = cste (2D), |u|² × 4πr² = cste (3D)", "champ lointain",
     "La même puissance traverse un cercle ou une sphère de plus en plus grands.", None),
    ("C", 311, "Condition de Sommerfeld", "Quelle onde garde-t-elle à l’infini ?", "l'onde sortante",
     "lim<sub>r→∞</sub> r<sup>(d−1)/2</sup> (∂u/∂r − iku) = 0", "Sommerfeld",
     "Condition de rayonnement, d étant la dimension. Elle rend unique la solution en domaine infini.", "monopole"),
    ("C", 312, "Sommerfeld en 2D et en 3D", "Quel facteur multiplie (∂u/∂r − iku) dans chaque cas ?", "racine de r puis r",
     "2D : √r (∂u/∂r − iku) → 0 · 3D : r (∂u/∂r − iku) → 0", "Sommerfeld",
     "Le facteur compense exactement la décroissance géométrique de l’onde.", None),
    ("C", 313, "Onde entrante", "Pourquoi l’écarte-t-on ?", "elle vient de l'infini",
     "e<sup>−ikr</sup> / r", "Sommerfeld",
     "Elle vérifie l’équation, mais son énergie convergerait de l’infini vers la source.", None),
    ("C", 314, "Monopôle", "Vers où rayonne une source ponctuelle seule ?", "dans toutes les directions",
     "u = G(x, x₀)", "source ponctuelle",
     "Rayonnement isotrope : des fronts d’onde circulaires (2D) ou sphériques (3D).", "monopole"),
    ("C", 315, "Dipôle", "De quoi est-il fait ?", "deux sources en opposition",
     "u = G(x, x₊) − G(x, x₋)", "dipôle",
     "Deux sources ponctuelles proches, déphasées de 180°. Ici elles sont écartées de λ/2.", "dipole"),
    ("C", 316, "Directivité du dipôle", "Sur quelle droite ne rayonne-t-il pas ?", "la médiatrice",
     "champ lointain ∝ cos θ (pour kd ≪ 1)", "dipôle",
     "θ est l’angle avec l’axe du dipôle. Sur la médiatrice les deux contributions arrivent en opposition et s’annulent.", "dipole"),
    ("C", 317, "Deux sources en phase", "Sur quelle droite le champ est-il toujours renforcé ?", "la médiatrice",
     "r₂ − r₁ = 0", "source ponctuelle",
     "Les deux ondes y parcourent la même distance et arrivent en phase. Ici les sources sont écartées de 2λ.", "deux_sources_en_phase"),
    ("C", 318, "Différence de marche", "Pour deux sources en phase, quel écart donne une interférence destructive ?", "une demi longueur d'onde",
     "r₂ − r₁ = (n + ½) λ", "source ponctuelle",
     "À un nombre entier de longueurs d’onde près. Avec r₂ − r₁ = nλ, l’interférence est constructive.", "deux_sources_en_phase"),

    # ── D · Cavités et modes propres ───────────────────────────────────────────
    ("D", 401, "Cavité", "Que deviennent les fréquences possibles dans un domaine fermé ?", "elles sont discrètes",
     "k ∈ { k₁, k₂, k₃, … }", "cavités",
     "Sans source, seule une suite de valeurs de k admet une solution non nulle.", "mode_3_2"),
    ("D", 402, "Problème aux valeurs propres", "Quel opérateur, et quelle valeur propre ?", "moins laplacien et k carré",
     "−∇²u = k²u dans Ω · u = 0 sur ∂Ω", "modes propres",
     "La même équation de Helmholtz, lue autrement : k² est l’inconnue, avec u.", None),
    ("D", 403, "Mode propre", "Que décrit u<sub>mn</sub> ?", "une forme de vibration",
     "p = u<sub>mn</sub>(x) cos(ω<sub>mn</sub>t)", "modes propres",
     "Une onde stationnaire de la cavité : tous les points vibrent en phase ou en opposition.", "mode_3_2"),
    ("D", 404, "Fréquence propre", "Comment se déduit-elle de k<sub>mn</sub> ?", "c k sur deux pi",
     "f<sub>mn</sub> = c k<sub>mn</sub> / 2π", "modes propres",
     "Pour 1,5 m × 1 m dans l’air, le mode (3, 2) est à 485 Hz.", "mode_3_2"),
    ("D", 405, "Condition de Dirichlet", "Qu’impose-t-elle sur le bord ?", "u nul",
     "u = 0 sur ∂Ω", "conditions aux limites",
     "Membrane fixée sur son cadre, ou paroi qui impose une pression nulle.", "mode_3_2"),
    ("D", 406, "Condition de Neumann", "Qu’impose-t-elle sur le bord ?", "dérivée normale nulle",
     "∂u/∂n = 0 sur ∂Ω", "conditions aux limites",
     "Paroi rigide d’une salle : la vitesse normale est nulle, la pression est maximale contre le mur.", "mode_neumann_3_2"),
    ("D", 407, "Condition de Robin", "Que relie-t-elle sur le bord ?", "u et sa dérivée normale",
     "∂u/∂n + αu = 0 sur ∂Ω", "conditions aux limites",
     "Condition d’impédance : une paroi qui absorbe une partie de l’onde. α = 0 redonne Neumann, α → ∞ Dirichlet.", None),
    ("D", 408, "Modes du rectangle, bord u = 0", "Quelle forme ont-ils ?", "produit de deux sinus",
     "u<sub>mn</sub> = sin(mπx/a) sin(nπy/b)", "modes propres",
     "Rectangle a × b avec Dirichlet. Les sinus s’annulent sur les quatre bords.", "mode_3_2"),
    ("D", 409, "Modes du rectangle, bord rigide", "Quelle forme ont-ils ?", "produit de deux cosinus",
     "u<sub>mn</sub> = cos(mπx/a) cos(nπy/b)", "modes propres",
     "Rectangle a × b avec Neumann. Les cosinus ont une pente nulle sur les quatre bords.", "mode_neumann_3_2"),
    ("D", 410, "Nombre d’onde propre k<sub>mn</sub>", "Comment combine-t-on les deux directions ?", "somme des carrés",
     "k<sub>mn</sub>² = π² (m²/a² + n²/b²)", "modes propres",
     "k<sub>x</sub> = mπ/a et k<sub>y</sub> = nπ/b. La formule est la même en Dirichlet et en Neumann.", "mode_3_2"),
    ("D", 411, "Indices m et n", "Que comptent-ils ?", "les demi longueurs d'onde",
     "a = m λ<sub>x</sub>/2, b = n λ<sub>y</sub>/2", "indices m et n",
     "m selon x, n selon y. Entiers à partir de 1 en Dirichlet, à partir de 0 en Neumann.", "mode_3_2"),
    ("D", 412, "Lignes nodales", "Combien de lignes nodales intérieures a le mode (3, 2) en Dirichlet ?", "3",
     "(m − 1) + (n − 1)", "indices m et n",
     "2 verticales et 1 horizontale. Le champ y reste nul et change de signe en les traversant.", "mode_3_2"),
    ("D", 413, "Mode fondamental", "Quels sont ses indices en Dirichlet ?", "1 et 1",
     "k₁₁ = π √(1/a² + 1/b²)", "indices m et n",
     "La fréquence propre la plus basse : une seule bosse. Pour 1,5 m × 1 m dans l’air, 206 Hz.", "mode_1_1"),
    ("D", 414, "Mode (0, 0) en Neumann", "Que vaut-il ?", "une constante",
     "u₀₀ = 1, k₀₀ = 0", "indices m et n",
     "Pression uniforme, fréquence nulle. Il n’existe pas en Dirichlet, où le champ serait nul partout.", None),
    ("D", 415, "Modes dégénérés", "Dans quelle cavité (1, 2) et (2, 1) ont-ils la même fréquence ?", "une cavité carrée",
     "a = b ⟹ k₁₂ = k₂₁", "modes propres",
     "Deux formes différentes pour une même valeur propre ; toute combinaison des deux est encore un mode.", "mode_1_2"),
    ("D", 416, "Orthogonalité des modes", "Que vaut ∫ u<sub>mn</sub> u<sub>pq</sub> pour deux modes différents ?", "zéro",
     "∫<sub>Ω</sub> u<sub>mn</sub> u<sub>pq</sub> dx = 0", "modes propres",
     "Les modes forment une base : tout champ de la cavité se décompose sur eux.", None),
    ("D", 417, "Résonance", "Sans amortissement, que fait l’amplitude si on excite la cavité à k = k<sub>mn</sub> ?", "elle diverge",
     "u = Σ s<sub>mn</sub> u<sub>mn</sub> / (k<sub>mn</sub>² − k²)", "cavités",
     "Décomposition modale de la réponse à une source s. Le dénominateur s’annule à chaque fréquence propre.", None),
    ("D", 418, "Cavité 3D", "Combien d’indices pour les modes d’une salle ?", "trois",
     "k<sub>lmn</sub>² = π² (l²/L<sub>x</sub>² + m²/L<sub>y</sub>² + n²/L<sub>z</sub>²)", "cavités",
     "Un indice par direction. Avec des murs rigides, les modes sont des produits de trois cosinus.", None),
    ("D", 419, "Cavité 1D", "Quelles longueurs d’onde tiennent dans une longueur L ?", "deux L sur n",
     "λ<sub>n</sub> = 2L/n, f<sub>n</sub> = n c / 2L", "cavités",
     "Corde fixée ou tuyau : un nombre entier de demi-longueurs d’onde entre les deux extrémités.", "onde_stationnaire"),
]


# ── Comment chaque carte est demandée (#209 à #213) ─────────────────────────
# Comme un paquet Anki de physique : la notion au recto, et l'on donne
#   eq    : la formule, tapée en mode équation (#212) — « lambda = c/f »,
#           les variantes acceptées ; l'appli ignore espaces, ×, parenthèses,
#           accepte lambda / omega / pi / sqrt / ^2 et les deux côtés inversés ;
#   flip  : une formule trop longue à taper : la carte se retourne et on se note ;
#   sinon : la réponse courte, les nombres en chiffres (#210 : « 2 », pas « deux »).
# ask remplace la question ; pre = les cartes à avoir vues avant (#213) : la
# carte attend qu'elles soient connues, et son verso dit sur quoi elle s'appuie.
ASK = {
    101: {"ask": "Écris-la pour une pression p.", "flip": True},
    102: {"ask": "Comment s’écrit p(x, t) ?", "flip": True},
    103: {"ask": "Écris-la, sans source.", "eq": ["∇²u + k²u = 0", "Δu + k²u = 0", "∇²u = −k²u", "Δu = −k²u"], "pre": [101, 102]},
    104: {"ask": "Par quoi remplace-t-on ∂²/∂t² ?", "eq": ["−ω²"], "pre": [102]},
    105: {"ask": "Écris k en fonction de ω et c.", "eq": ["k = ω/c"], "pre": [107]},
    106: {"ask": "Écris λ en fonction de c et f.", "eq": ["λ = c/f"]},
    107: {"ask": "Écris ω en fonction de f.", "eq": ["ω = 2πf", "ω = 2fπ"]},
    108: {"short": "343"},
    111: {"short": "1/4 de période plus tard", "pre": [110]},
    110: {"pre": [109]},
    112: {"pre": [102]},
    113: {"pre": [112]},
    114: {"pre": [113, 115]},
    115: {"pre": [103]},
    116: {"ask": "Écris-la avec une source s.", "eq": ["∇²u + k²u = −s", "Δu + k²u = −s"], "pre": [103]},
    117: {"pre": [103]},
    201: {"ask": "Écris-la avec son amplitude A et son vecteur d’onde k.", "flip": True, "pre": [103]},
    202: {"ask": "Que vaut sa norme ?", "eq": ["‖k‖ = 2π/λ", "k = 2π/λ", "‖k‖ = ω/c", "k = ω/c"], "pre": [201, 105]},
    203: {"ask": "Que vaut k<sub>x</sub>² + k<sub>y</sub>² + k<sub>z</sub>² ?", "eq": ["ω²/c²", "k²", "(ω/c)²"], "pre": [202]},
    204: {"ask": "Quelle distance sépare deux crêtes successives ?", "eq": ["λ"], "pre": [201, 106]},
    205: {"ask": "Écris v en fonction de ω et k.", "eq": ["v = ω/k"], "pre": [201, 105]},
    206: {"pre": [201, 115]},
    301: {"pre": [116]},
    302: {"pre": [301]},
    303: {"ask": "Écris G en 3D.", "eq": ["G = e^(ikr)/(4πr)", "G = e^(ikr)/(4rπ)"], "pre": [302]},
    304: {"pre": [302]},
    305: {"pre": [302]},
    306: {"pre": [302, 115]},
    307: {"ask": "Écris H₀<sup>(1)</sup> avec J₀ et Y₀.", "eq": ["H0 = J0 + iY0", "H0(1) = J0 + iY0"], "pre": [304]},
    308: {"ask": "Quelle condition porte sur kr ?", "eq": ["kr ≫ 1", "kr >> 1"], "pre": [105]},
    309: {"ask": "Comment décroît l’amplitude en 2D ?", "eq": ["1/√r", "1/√(r)", "r^(−1/2)"], "pre": [307, 308]},
    310: {"pre": [303, 309]},
    311: {"pre": [303]},
    312: {"ask": "Quel facteur multiplie (∂u/∂r − iku) en 2D, puis en 3D ?", "eq": ["√r, r", "√r puis r", "√r et r"], "pre": [311, 310]},
    313: {"pre": [311]},
    314: {"pre": [301]},
    315: {"short": "2 sources en opposition", "pre": [314]},
    316: {"pre": [315]},
    317: {"short": "la médiatrice", "pre": [314, 115]},
    318: {"ask": "Pour 2 sources en phase, quelle différence de marche r₂ − r₁ donne une interférence destructive ?",
          "eq": ["λ/2", "(n + 1/2)λ", "(n + ½)λ"], "pre": [317, 106]},
    401: {"pre": [117]},
    402: {"ask": "Écris l’équation : quel opérateur, quelle valeur propre ?",
          "eq": ["−∇²u = k²u", "−Δu = k²u", "∇²u = −k²u", "Δu = −k²u"], "pre": [103, 401]},
    403: {"pre": [402]},
    404: {"ask": "Écris f<sub>mn</sub> avec k<sub>mn</sub>.", "eq": ["f = ck/2π", "f = kc/2π", "fmn = c kmn/2π", "fmn = kmn c/2π"], "pre": [403, 107]},
    405: {"ask": "Qu’impose-t-elle sur le bord ?", "eq": ["u = 0"], "pre": [117]},
    406: {"ask": "Qu’impose-t-elle sur le bord ?", "eq": ["∂u/∂n = 0", "du/dn = 0"], "pre": [117]},
    407: {"ask": "Écris-la, avec un coefficient α.", "eq": ["∂u/∂n + αu = 0", "du/dn + αu = 0", "∂u/∂n = −αu", "du/dn = −αu"], "pre": [405, 406]},
    408: {"short": "produit de 2 sinus", "pre": [405, 402]},
    409: {"short": "produit de 2 cosinus", "pre": [406, 408]},
    410: {"ask": "Écris k<sub>mn</sub>² pour un rectangle a × b.", "eq": ["kmn² = π²(m²/a² + n²/b²)", "k² = π²(m²/a² + n²/b²)",
          "kmn² = (mπ/a)² + (nπ/b)²", "k² = (mπ/a)² + (nπ/b)²"], "pre": [408, 409]},
    411: {"pre": [410]},
    412: {"pre": [411]},
    413: {"short": "1 et 1", "pre": [411]},
    414: {"pre": [411, 406]},
    415: {"pre": [410]},
    416: {"ask": "Que vaut ∫ u<sub>mn</sub> u<sub>pq</sub> pour 2 modes différents ?", "eq": ["0"], "pre": [403]},
    417: {"pre": [416]},
    418: {"short": "3", "pre": [410]},
    419: {"ask": "Écris λ<sub>n</sub> pour une longueur L.", "eq": ["λn = 2L/n", "λ = 2L/n"], "pre": [114, 401]},
}
# formules : une équation par ligne (#214) — séparées par « , » ou « · » quand
# chaque morceau est une équation (k ∈ { k₁, k₂, … } reste sur une ligne)
EQ_SIGN = re.compile(r"[=≈→∝<>≫≪]")


def formula_lines(f):
    if not f:
        return []
    parts, depth, cur = [], 0, ""
    for i, ch in enumerate(f):
        depth += 1 if ch in "([{" else -1 if ch in ")]}" else 0
        if depth == 0 and (f[i:i + 2] == ", " or f[i:i + 3] == " · "):
            parts.append(cur)
            cur = ""
            continue
        cur += ch
    parts.append(cur)
    parts = [p.strip(" ·,") for p in parts if p.strip(" ·,")]
    return parts if len(parts) > 1 and all(EQ_SIGN.search(re.sub(r"<[^>]+>", "", p)) for p in parts) else [f]


# ── Animations (WebP animés, une période en boucle) ──────────────────────────
NF, MS = 24, 60                       # images par période, durée d'une image
BG, POS, NEG = (255, 255, 255), (217, 115, 26), (29, 95, 194)   # fond, crête, creux
INK, GREY, LINE = (23, 33, 44), (120, 132, 145), (213, 219, 226)
FW, FH, DW, DH = 420, 262, 4.0, 2.5   # cartes de champ : pixels, mètres


def build_animations():
    try:
        import numpy as np
        from PIL import Image, ImageDraw, ImageFont
        from scipy.special import hankel1
    except ImportError:
        print("  (numpy, scipy ou Pillow absent : les animations existantes sont gardées)")
        return
    os.makedirs(MEDIA, exist_ok=True)
    phases = [2 * math.pi * i / NF for i in range(NF)]

    def font(size, italic=False):
        for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf" if italic else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                  "/System/Library/Fonts/Supplemental/Times New Roman Italic.ttf" if italic else "/System/Library/Fonts/Supplemental/Arial.ttf"):
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
        return ImageFont.load_default()

    def colour(v):
        v = np.clip(v, -1, 1)
        a = np.abs(v)[..., None]
        col = np.where((v >= 0)[..., None], np.array(POS, float), np.array(NEG, float))
        return Image.fromarray((np.array(BG, float) + (col - np.array(BG, float)) * a).astype(np.uint8), "RGB")

    def save(name, frames):
        path = os.path.join(MEDIA, name + ".webp")
        frames[0].save(path, save_all=True, append_images=frames[1:], duration=MS, loop=0, quality=72, method=4)
        print(f"  {name}.webp ({os.path.getsize(path) // 1024} Ko)")

    def arrow(d, x0, y0, x1, y1, col, w=3):
        a = math.atan2(y1 - y0, x1 - x0)
        d.line([x0, y0, x1 - 6 * math.cos(a), y1 - 6 * math.sin(a)], fill=col, width=w)
        d.polygon([(x1, y1), (x1 - 12 * math.cos(a - .45), y1 - 12 * math.sin(a - .45)),
                   (x1 - 12 * math.cos(a + .45), y1 - 12 * math.sin(a + .45))], fill=col)

    def scale_bar(d):
        x, y, m = 12, FH - 12, FW / DW
        d.rectangle([x - 5, y - 22, x + m + 5, y + 6], fill=BG)
        d.line([x, y - 5, x, y, x + m, y, x + m, y - 5], fill=INK, width=2)
        d.text((x + 4, y - 19), "1 m", fill=INK, font=font(12))

    X, Y = np.meshgrid((np.arange(FW) + .5) / FW * DW, (1 - (np.arange(FH) + .5) / FH) * DH)

    # Ondes planes
    def plane(name, lam, angles):
        k, frames = 2 * math.pi / lam, []
        for ph in phases:
            v = sum(np.cos(k * (X * math.cos(math.radians(a)) + Y * math.sin(math.radians(a))) - ph) for a in angles)
            im = colour(v * (.85 if len(angles) == 1 else .5))
            d = ImageDraw.Draw(im)
            for j, a in reversed(list(enumerate(angles))):
                r = math.radians(a)
                arrow(d, FW / 2, FH / 2, FW / 2 + 56 * math.cos(r), FH / 2 - 56 * math.sin(r), INK if j == 0 else GREY)
            r = math.radians(angles[0])
            d.text((FW / 2 + 72 * math.cos(r) - 5, FH / 2 - 72 * math.sin(r) - 10), "k", fill=INK, font=font(17, True))
            scale_bar(d)
            frames.append(im)
        save(name, frames)

    plane("onde_plane", .6, [25])
    plane("deux_ondes_planes", .6, [25, 150])

    # Sources ponctuelles : la vraie fonction de Green 2D, (i/4) H0(1)(kr)
    def sources(name, lam, pts, gain):
        k = 2 * math.pi / lam
        u = sum(s * .25j * hankel1(0, k * np.maximum(np.hypot(X - x, Y - y), 1e-3)) for x, y, s in pts)
        frames = []
        for ph in phases:
            v = np.real(u * np.exp(-1j * ph)) * gain
            im = colour(np.sign(v) * np.abs(v) ** .8)
            d = ImageDraw.Draw(im)
            for x, y, s in pts:
                cx, cy = x / DW * FW, (1 - y / DH) * FH
                d.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=BG, outline=INK, width=2)
            scale_bar(d)
            frames.append(im)
        save(name, frames)

    sources("monopole", .4, [(2, 1.25, 1)], 11)
    sources("deux_sources_en_phase", .4, [(1.6, 1.25, 1), (2.4, 1.25, 1)], 7)
    sources("dipole", .4, [(1.9, 1.25, 1), (2.1, 1.25, -1)], 7)

    # Modes propres du rectangle 1,5 m × 1 m
    def mode(name, m, n, neumann=False):
        w, h = 420, 280
        x, y = np.meshgrid((np.arange(w) + .5) / w, 1 - (np.arange(h) + .5) / h)
        f = np.cos if neumann else np.sin
        shape, frames = f(m * math.pi * x) * f(n * math.pi * y), []
        for ph in phases:
            im = colour(shape * math.cos(ph))
            d = ImageDraw.Draw(im)
            t = 6 if neumann else 2
            d.rectangle([0, 0, w - 1, h - 1], outline=INK if neumann else GREY, width=t)
            frames.append(im)
        save(name, frames)

    mode("mode_1_1", 1, 1)
    mode("mode_1_2", 1, 2)
    mode("mode_3_2", 3, 2)
    mode("mode_neumann_3_2", 3, 2, neumann=True)

    # Ondes 1D : 2 m, λ = 0,8 m (430 Hz dans l'air), dessinées en double taille puis réduites
    def wave1d(name, standing):
        S, w, h, L, lam = 2, 420, 190, 2.0, .8
        k = 2 * math.pi / lam
        ml, mr, mt, mb = 14 * S, 14 * S, 34 * S, 30 * S
        pw, hh = w * S - ml - mr, h * S - mt - mb
        y0, A = mt + hh / 2, hh * .44
        xs = np.linspace(0, L, 400)
        env = np.abs(np.cos(k * xs)) if standing else np.ones_like(xs)
        frames = []
        for ph in phases:
            im = Image.new("RGB", (w * S, h * S), BG)
            d = ImageDraw.Draw(im)
            for i in range(5):
                gx = ml + pw * i / 4
                d.line([gx, mt, gx, mt + hh], fill=LINE, width=S)
                label = f"{i * .5:.1f} m".replace(".", ",")
                tw = d.textlength(label, font=font(12 * S))
                d.text((min(max(gx - tw / 2, ml), ml + pw - tw), mt + hh + 6 * S), label, fill=GREY, font=font(12 * S))
            d.line([ml, y0, ml + pw, y0], fill=LINE, width=S)
            for s in (1, -1):  # enveloppe ±|u| en pointillés
                pts = [(ml + x / L * pw, y0 - s * e * A) for x, e in zip(xs, env)]
                for i in range(0, len(pts) - 4, 8):
                    d.line(pts[i:i + 5], fill=GREY, width=S + 1)
            val = np.cos(k * xs) * math.cos(ph) if standing else np.cos(k * xs - ph)
            d.line([(ml + x / L * pw, y0 - v * A) for x, v in zip(xs, val)], fill=NEG, width=3 * S, joint="curve")
            lw, yb = lam / L * pw, 15 * S
            d.line([ml, yb, ml + lw, yb], fill=INK, width=S + 1)
            for gx in (ml, ml + lw):
                d.line([gx, yb - 5 * S, gx, yb + 5 * S], fill=INK, width=S + 1)
            d.text((ml + lw + 7 * S, yb - 11 * S), "λ", fill=INK, font=font(16 * S, True))
            frames.append(im.resize((w, h), Image.LANCZOS))
        save(name, frames)

    wave1d("onde_progressive", False)
    wave1d("onde_stationnaire", True)


# ── Cartes ───────────────────────────────────────────────────────────────────
STYLE = """<style>
.rf-word{font-size:36px;font-weight:600;margin:4px 0 10px;line-height:1.15}
.rf-sent{font-size:19px;line-height:1.5;opacity:.9}
.rf-mean{font-size:24px;font-weight:600;margin:2px 0}
.rf-form{font-family:"STIX Two Math","Cambria Math","Times New Roman",serif;font-size:22px;margin:10px 0 4px}
.rf-pos{font-size:11px;opacity:.55;text-transform:uppercase;letter-spacing:.8px;margin:4px 0 10px}
.rf-tr{font-size:15px;opacity:.75;line-height:1.45;max-width:34em;margin:0 auto}
.rf-img img{max-width:100%;max-height:280px;border-radius:10px;margin-top:12px}
.rf-pre{font-size:13px;opacity:.6;margin:8px auto 0;max-width:34em}
</style>"""
FRONT = """<div class="rf-word">{{Notion}}</div>
<div class="rf-sent">{{Question}}</div>"""
BACK = """{{FrontSide}}
<hr id=answer>
<div class="rf-mean">{{Réponse}}</div>
{{#Formule}}<div class="rf-form">{{Formule}}</div>{{/Formule}}
<div class="rf-pos">{{Nature}}</div>
{{#Explication}}<div class="rf-tr">{{Explication}}</div>{{/Explication}}
{{#Animation}}<div class="rf-img">{{Animation}}</div>{{/Animation}}"""
CSS = ('.card { font-family: -apple-system, "Segoe UI", sans-serif; text-align: center; font-size: 18px; }\n'
       + STYLE.replace("<style>\n", "").replace("\n</style>", ""))
FIELDS = ["Clé", "Notion", "Question", "Réponse", "Formule", "Nature", "Explication", "Animation"]


def words_of(short):
    """Les mots à taper : la réponse courte, sans ponctuation (comme #90)."""
    return [w for w in re.split(r"\s+", re.sub(r"[,;.!?]", " ", short)) if w]


def cards():
    out = []
    for sub, key, notion, question, short, formule, nature, expl, anim in CARDS:
        if anim and not os.path.exists(os.path.join(MEDIA, anim + ".webp")):
            print(f"  animation manquante : {anim}.webp (carte {key})")
            anim = None
        a = ASK.get(key, {})
        out.append({"sub": sub, "key": key, "id": str(ID_BASE + key * 10 + 1), "notion": notion,
                    "question": a.get("ask", question), "short": a.get("short", short), "eq": a.get("eq"),
                    "flip": a.get("flip", False), "pre": a.get("pre", []),
                    "formule": formule or "", "nature": nature, "expl": expl, "anim": anim})
    by_key = {c["key"]: c for c in out}
    for c in out:
        assert all(k in by_key for k in c["pre"]), f"carte {c['key']} : prérequis inconnu"
    # the order of the cards: a prerequisite always before (#213), else the order of CARDS
    order, seen = [], set()
    def visit(c, path=()):
        assert c["key"] not in path, f"prérequis en boucle : {path + (c['key'],)}"
        if c["key"] in seen:
            return
        for k in c["pre"]:
            visit(by_key[k], path + (c["key"],))
        seen.add(c["key"])
        order.append(c)
    for c in out:
        visit(c)
    return order


def build_json(cs):
    by_key = {c["key"]: c for c in cs}
    decks = []
    for sub, name in SUBS.items():
        deck = {"id": f"helmholtz-{sub.lower()}", "name": f"{DECK}::{name}", "cards": []}
        for c in (c for c in cs if c["sub"] == sub):
            # the answer asked: the formula itself for an equation or a turned card
            back = "" if (c["eq"] or c["flip"]) else f'<div class="rf-mean">{html.escape(c["short"])}</div>'
            for line in formula_lines(c["formule"]):
                back += f'<div class="rf-form">{line}</div>'
            if c["eq"] and not c["formule"]:
                back += f'<div class="rf-form">{html.escape(c["eq"][0])}</div>'
            back += f'<div class="rf-pos">{c["nature"]}</div><div class="rf-tr">{c["expl"]}</div>'
            if c["pre"]:
                names = " · ".join(by_key[k]["notion"] for k in c["pre"])
                back += f'<div class="rf-pre">s’appuie sur : {names}</div>'
            if c["anim"]:
                back += f'<div class="rf-img"><img src="{MEDIA_DIR}/{c["anim"]}.webp" alt=""></div>'
            card = {
                "id": c["id"],
                "question": STYLE + f'<div class="rf-word">{c["notion"]}</div><div class="rf-sent">{c["question"]}</div>',
                "answer": STYLE + back,
                "words": [c["eq"][0]] if c["eq"] else words_of(c["short"]),
                "tags": [c["nature"]],
            }
            if c["eq"]: card["eq"] = c["eq"]
            if c["flip"]: card["flip"] = True
            if c["pre"]: card["pre"] = [by_key[k]["id"] for k in c["pre"]]
            deck["cards"].append(card)
        decks.append(deck)
    path = os.path.join(HERE, "helmholtz.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "source": DECK, "decks": decks}, f, ensure_ascii=False, indent=1)
    print(f"{len(cs)} cartes → helmholtz.json")


def build_apkg(cs):
    try:
        from anki.collection import Collection, DeckIdLimit, ExportAnkiPackageOptions
    except ImportError:
        print("  (paquet 'anki' absent : pas de .apkg — lancer avec trainervenv/bin/python)")
        return
    import shutil
    import tempfile
    out_path = os.path.join(HERE, "Helmholtz.apkg")
    with tempfile.TemporaryDirectory() as tmp:
        col = Collection(os.path.join(tmp, "collection.anki2"))
        try:
            mm = col.models
            m = mm.new(MODEL)
            for name in FIELDS:
                mm.add_field(m, mm.new_field(name))
            t = mm.new_template("Notion → réponse")
            t["qfmt"], t["afmt"] = FRONT, BACK
            mm.add_template(m, t)
            m["css"] = CSS
            m["sortf"] = 0
            mm.add(m)
            m = mm.by_name(MODEL)
            did = col.decks.id(DECK)
            dids = {sub: col.decks.id(f"{DECK}::{name}") for sub, name in SUBS.items()}
            media = col.media.dir()
            for c in cs:
                n = col.new_note(m)
                n["Clé"] = str(c["key"])
                n["Notion"] = c["notion"]
                n["Question"] = c["question"]
                n["Réponse"] = html.escape(c["eq"][0] if c["eq"] else "" if c["flip"] else c["short"])
                n["Formule"] = "<br>".join(formula_lines(c["formule"]))
                n["Nature"] = c["nature"]
                n["Explication"] = c["expl"]
                if c["anim"]:
                    fn = f"helmholtz_{c['anim']}.webp"
                    shutil.copy(os.path.join(MEDIA, c["anim"] + ".webp"), os.path.join(media, fn))
                    n["Animation"] = f'<img src="{fn}">'
                n.tags = ["helmholtz", c["nature"].replace(" ", "_")]
                col.add_note(n, dids[c["sub"]])
                # Mêmes ids que dans l'appli (ankisync fait le lien après import).
                cid = col.db.scalar("select id from cards where nid = ?", n.id)
                col.db.execute("update cards set id = ? where id = ?", int(c["id"]), cid)
                col.db.execute("update notes set id = ? where id = ?", int(c["id"]) - 1, n.id)
                col.db.execute("update cards set nid = ? where nid = ?", int(c["id"]) - 1, n.id)
            opts = ExportAnkiPackageOptions(with_scheduling=False, with_deck_configs=False, with_media=True, legacy=False)
            col.export_anki_package(out_path=out_path, options=opts, limit=DeckIdLimit(did))
        finally:
            col.close()
    print(f"  → {out_path} ({os.path.getsize(out_path) // 1024} Ko)")


def main():
    assert len({c[1] for c in CARDS}) == len(CARDS), "deux cartes ont la même clé"
    build_animations()
    cs = cards()
    build_json(cs)
    build_apkg(cs)


if __name__ == "__main__":
    main()
