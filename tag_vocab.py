#!/usr/bin/env python3
"""
tag_vocab.py — tags du paquet Vocabulaire (#189) : la nature du mot (nom,
verbe, adjectif…) et un thème pour les noms (animaux, nourriture, corps…),
pour filtrer dans 🔍 (menu 🏷).

Le thème vient du premier sens français du nom, comparé à des listes faites
à la main ci-dessous ; les couleurs et les nombres viennent du mot espagnol.
Le Vocabolario italien reçoit les mêmes tags, traduits.

« transparent » (#198) : le mot espagnol se devine depuis le français
(la capacidad = capacité, reservado = réservé) — après les terminaisons
régulières (-ción → -tion, -dad → -té, -ar → -er…), au moins 80 % de
ressemblance ; jamais un faux ami. Le Vocabolario le compare à l'italien
(« trasparente »).

Appelé à la fin de build_vocab.py ; se lance aussi seul :
    python3 tag_vocab.py
"""
import difflib
import json
import os
import re
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))

# nature (enrich_es.py) → tag
POS = {"nom": "nom", "verbe": "verbe", "adjectif": "adjectif", "adverbe": "adverbe",
       "expression": "expression", "préposition": "mot-outil", "conjonction": "mot-outil",
       "pronom": "mot-outil", "interjection": "interjection"}

THEMES = {
    "animaux": """abeille agneau aigle animal|animal de compagnie araignée baleine bestiole canard cerf chameau chat chaton cheval
        chien chiot chèvre coq corbeau crabe dauphin dinde dinosaure faucon femelle fourmi girafe gorille grenouille homard insecte
        lapin lion loup mouche moustique mouton mulet nid oiseau ours panda papillon patte pigeon poisson poule renard requin
        saumon serpent singe souris taupe taureau thon tigre tortue troupeau vache ver zèbre écureuil éléphant âne griffe corne
        laisse zoo""",
    "nourriture": """ail aliment banane beurre biscuit bière boisson bonbon bonbons cacahuète café champagne champignon chocolat
        citron citronnade citrouille cocktail cognac confiture crème cuisine cuisinier déjeuner dessert dîner farine fast-food
        fromage fruit gelée gâteau hamburger haricot huile jambon jus lait lard liqueur légumes maïs malbouffe menthe menu miel
        noix|noix de coco oeuf oignon olive omelette orange pain pâtes petit déjeuner pique-nique plat principal poivre pomme
        pomme de terre pop-corn porc poulet recette repas riz rôti salade sandwich sauce saucisse sel soda soupe steak sucre
        taco tequila thé tomate vermicelle viande vin|vin blanc|vin rouge restaurant boulangerie boulanger boucher assiette
        cuillère fourchette tasse verre bouteille marmite appétit faim soif goût gorgée ingrédient blé graine canette""",
    "corps": """bouche bras cerveau cheveux cheville coeur corps cou coude dent doigt dos foie genou gorge hanche jambe joue
        lèvre main muscle mâchoire nez oeil ongle oreille organe os paume peau pied poignet poing poitrine pouce poumon rein
        sang tête veine ventre visage épaule artère barbe moustache larme sueur souffle respiration pouls nerfs""",
    "santé": """accouchement addiction allergie ambulance anesthésiques antibiotiques antidote blessure brancard brûlure
        cancer chirurgie chirurgien cicatrice clinique diagnostic docteur dose douleur dépression fièvre fracture grippe
        grossesse hémorragie hôpital infarctus infection infirmerie infirmière maladie médicament overdose patient pharmacie
        pilule piqûre remède rhume rééducation santé symptôme syndrome thérapeute thérapie toux traitement tumeur virus
        vétérinaire bloc opératoire dentiste rétablissement drogues gueule de bois""",
    "famille": """beau-frère beau-père bébé cousin cousine enfance famille femme fille fils frère gendre grand-mère grand-père
        grands-parents jumeau maman mari mariage mère neveu nom de famille oncle papa parent parents petit-fils petite-fille
        père soeur tante veuve divorce ancêtre parrain héritier petit copain petite copine amant couple fiancé""",
    "métiers": """acteur actrice administrateur agriculteur architecte avocat berger boucher boulanger capitaine chauffeur|chauffeur de taxi
        chef chercheur chirurgien coiffeur colonel commandant comptable concierge conducteur conseiller cuisinier danseur
        dentiste docteur détective écrivain facteur fermier flic gardien infirmière ingénierie jardinier journaliste lieutenant
        magicien maire majordome marin mécanicien peintre photographe pilote pompier poète prêtre producteur professeur
        reporter secrétaire sergent serveur serveuse spécialiste technicien vendeur vétérinaire éditeur métier profession
        travailleur ouvrier employés gérant superviseur assistant moine évêque soldat avocate""",
    "maison": """appartement armoire baignoire balcon berceau bougie canapé cave chaise chambre cheminée clé commode
        couette couloir couverture cuisine domicile douche drap escalier fauteuil fenêtre four grenier immeuble jardin lampe
        lit logement loyer maison matelas meubles miroir mur oreiller placard plafond porte poubelle rideau salle à manger salon
        serrure serviette sous-sol tapis terrasse tiroir toilettes toit toit-terrasse étagère réfrigérateur congélateur savon
        sonnette ménage déménagement voisin voisinage interrupteur ascenseur garage""",
    "vêtements": """bague bijou bottes botte boucles d'oreilles bracelet caleçon casque casquette ceinture chapeau chaussettes
        chaussures chemise chemisier collier costume cravate culotte déguisement gants gilet imperméable jupe lunettes
        maquillage manteau peignoir perruque poche pull pyjama robe short t-shirt uniforme veste vêtements écharpe
        coiffure parfum mode""",
    "ville": """aéroport ambassade auberge|auberge de jeunesse autoroute avenue banlieue banque bar bibliothèque boutique bureau
        café cimetière cinéma commissariat église gare hôpital hôtel kiosque laverie librairie magasin mairie marché musée parc
        parking pharmacie place pont port prison quartier restaurant route rue ruelle stade station-service supermarché
        théâtre trottoir usine village ville zoo pâté de maisons capitale circulation croisement école université
        piscine bâtiment""",
    "transports": """automobile avion barque bateau bus camion camionnette caravane chemin de fer frein hélicoptère moto
        motocyclette navire passager pneu taxi train transport vaisseau vaisseau spatial vélo voiture volant wagon yacht
        véhicule carburant essence atterrissage décollage croisière voyage valise passeport billet bagage visa
        sous-marin fusée parachute""",
    "nature": """air arbre aube averse baie bois boue branche brise brouillard cascade champ ciel climat colline coucher du soleil
        désert eau étang étoile feu feuille fleur forêt|forêt tropicale galaxie glace grotte herbe horizon île jungle lac lave
        lune marais marée marguerite mer montagne mont nature neige nuage océan orage ouragan paysage pierre plage planète
        plante pluie racine rive rivière roche rose ruisseau sable soleil sommet tempête terre tremblement de terre univers
        vague vallée vent volcan éclair arc-en-ciel environnement espace orbite pôle nord sud est ouest""",
    "temps": """après-midi année|année dernière anniversaire aube automne calendrier date début décennie fin heure hiver
        horaire instant jour lundi matin minute mois moment nuit printemps saison seconde semaine semestre siècle soir soirée
        temps été époque retard vacances week-end futur passé présent petit matin petit moment""",
    "loisirs": """album badminton ballet ballon base-ball basket-ball billard boxe cartes cinéma cirque club|club de sport concert
        danse divertissement échecs festival film football golf guitare gymnastique jeu|jeu vidéo jouet loterie marathon
        musique opéra orchestre piano poker puzzle randonnée sport stade surf tennis théâtre tournoi trophée vacances violon
        yoga chanson chant chanteur concours championnat champion coupe du monde mélodie spectacle peinture photo
        photographie roman livre lecture poésie poème excursion fête soirée pique-nique salle de sport""",
    "école": """cahier classe cours crayon devoirs école élève étudiant étude études examen exercice gomme leçon livre
        maternelle professeur stylo université diplôme remise des diplômes biologie chimie géographie histoire latin
        mathématiques philosophie physique psychologie science littérature internat académie bibliothèque tuteur""",
    "travail": """affaire agence argent banque bénéfice bourse budget bureau carrière centime chèque client collègue
        commerce comptabilité compte contrat coût coûts dette dollar emploi entreprise entretien euro facture faillite finances
        impôts investissement licenciement marché monnaie paiement patron pourboires prêt|prêt immobilier
        prix profit réunion revenu salaire stocks syndicat taxes travail vente|vente aux enchères démission retraite
        promotion acheteur consommateur marchandise industrie économie richesse pauvreté portefeuille reçu virement
        distributeur automatique""",
    "crime": """alibi arme|arme du crime arnaque arrestation assassin bandit braquage butin cadavre chantage commissariat
        complice complot condamnation à perpétuité contrebande crime cachot délinquant délit détective enlèvement escroc
        flic fraude fugitif gâchette interrogatoire juge jugement justice loi mafia meurtre otage pistolet police
        pot-de-vin preuve prison prisonnier procès revolver témoignage tribunal trafiquant tuerie verdict victime
        voleur avocat fusil de chasse tireur|tireur d'élite munition menace violence corruption suspect enquête""",
    "guerre": """armée armure artillerie bataille bataillon bombe bombardement bouclier brigade canon cavalerie combat
        défaite défense embuscade ennemi épée escorte guerre guerrier invasion missile munition offensive paix peloton
        régiment renfort soldat troupes trêve victoire dague sergent colonel commandant lieutenant capitaine char
        dynamite explosion""",
    "sentiments": """affection amitié amour angoisse anxiété bonheur chagrin colère compassion confiance courage crainte
        culpabilité déception dégoût désespoir émotion embarras enthousiasme envie espoir fierté frayeur fureur gratitude
        haine honte humiliation inquiétude jalousie joie larme mépris nostalgie passion peur pitié plaisir rage rancune
        regret sentiment solitude soulagement souffrance stress surprise terreur tristesse""",
}

COLOURS = {"rojo", "roja", "azul", "verde", "amarillo", "amarilla", "negro", "negra", "blanco", "blanca", "gris",
           "rosa", "rosado", "marrón", "morado", "naranja", "color", "dorado", "plateado"}
NUMBERS = {"cero", "uno", "una", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once",
           "doce", "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve", "veinte",
           "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa", "cien", "ciento", "mil",
           "millón", "primero", "primera", "segundo", "tercero", "tercera", "cuarto", "quinto", "medio", "mitad",
           "docena", "número"}

IT = {"nom": "nome", "verbe": "verbo", "adjectif": "aggettivo", "adverbe": "avverbio", "expression": "espressione",
      "mot-outil": "parola grammaticale", "interjection": "interiezione", "animaux": "animali", "nourriture": "cibo",
      "corps": "corpo", "santé": "salute", "famille": "famiglia", "métiers": "mestieri", "maison": "casa",
      "vêtements": "vestiti", "ville": "città", "transports": "trasporti", "nature": "natura", "temps": "tempo",
      "loisirs": "svago", "école": "scuola", "travail": "lavoro e soldi", "crime": "crimine e giustizia",
      "guerre": "guerra", "sentiments": "sentimenti", "couleurs": "colori", "nombres": "numeri",
      "transparent": "trasparente"}

# « transparent » (#198): Spanish endings → French / Italian ones
ENDINGS = {
    "fr": [("ciones", "tions"), ("cion", "tion"), ("dad", "te"), ("tad", "te"), ("osa", "euse"), ("oso", "eux"),
           ("mente", "ment"), ("ista", "iste"), ("ismo", "isme"), ("ica", "ique"), ("ico", "ique"), ("ia", "ie"),
           ("ario", "aire"), ("aria", "aire"), ("ivo", "if"), ("iva", "ive"), ("encia", "ence"), ("ancia", "ance"),
           ("ante", "ant"), ("ente", "ent"), ("ar", "er"), ("er", "re"), ("o", ""), ("a", "e"), ("e", "")],
    "it": [("ciones", "zioni"), ("cion", "zione"), ("dad", "ta"), ("tad", "ta"), ("mente", "mente"), ("encia", "enza"),
           ("ancia", "anza"), ("ar", "are"), ("er", "ere"), ("ir", "ire"), ("o", "o"), ("e", "e")],
}
ART = {"es": re.compile(r"^(el|la|los|las|un|una|unos|unas|lo) "),
       "fr": re.compile(r"^(le |la |les |l'|un |une |des |du |de la |se |s')"),
       "it": re.compile(r"^(il |lo |la |i |gli |le |l'|un |uno |una |un')")}


def _bare(s, lang):
    s = s.split(",")[0].split(";")[0].lower().strip()
    s = "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")
    s = re.sub(r"\(.*?\)", "", s).strip()
    return ART[lang].sub("", s).strip()


def transparent(es, meaning, lang="fr"):
    e, m = _bare(es, "es"), _bare(meaning, lang)
    if len(e) < 3 or not m or " " in e or " " in m:
        return False
    forms = {e} | {e[:-len(a)] + b for a, b in ENDINGS[lang] if e.endswith(a)}
    return max(difflib.SequenceMatcher(None, f, m).ratio() for f in forms) >= .8


MULTI = ["animal de compagnie", "pomme de terre", "noix de coco", "petit déjeuner", "plat principal", "bloc opératoire",
         "gueule de bois", "nom de famille", "petit copain", "petite copine", "salle à manger", "chauffeur de taxi",
         "auberge de jeunesse", "pâté de maisons", "chemin de fer", "vaisseau spatial", "coucher du soleil",
         "forêt tropicale", "tremblement de terre", "année dernière", "petit matin", "petit moment", "club de sport",
         "jeu vidéo", "coupe du monde", "salle de sport", "remise des diplômes", "prêt immobilier", "vente aux enchères",
         "distributeur automatique", "arme du crime", "condamnation à perpétuité", "fusil de chasse", "tireur d'élite",
         "vin blanc", "vin rouge", "boucles d'oreilles"]


def themes_of(fr):
    head = re.split(r"[,;]", fr)[0]
    head = re.sub(r"\([^)]*\)?", "", head).strip().lower()
    head = re.sub(r"^(le |la |les |l'|l’|un |une |des |du )", "", head).strip()
    if head in MULTI_THEMES:
        return MULTI_THEMES[head]
    return LEX.get(head, set())


def build_lex():
    lex, multi = {}, {}
    for theme, text in THEMES.items():
        flat = " " + " ".join(text.split()) + " "
        for m in MULTI:
            if " " + m + " " in flat or "|" + m + " " in flat or " " + m + "|" in flat or "|" + m + "|" in flat:
                multi.setdefault(m, set()).add(theme)
                flat = flat.replace(m, " ")
        for chunk in flat.split():
            for word in chunk.split("|"):
                if word:
                    lex.setdefault(word, set()).add(theme)
    return lex, multi


LEX, MULTI_THEMES = build_lex()


def tags_for(c):
    tags = []
    pos = (c.get("pos") or "").split(" ")[0]
    if POS.get(pos):
        tags.append(POS[pos])
    elif not pos and " " in c["es"].strip():
        tags.append("expression")
    if pos == "nom":
        tags += sorted(themes_of(c["fr"]))
    core = re.sub(r"^(el|la|los|las|un|una) ", "", c["es"].strip().lower())
    if core in COLOURS:
        tags.append("couleurs")
    if core in NUMBERS:
        tags.append("nombres")
    return tags


def main():
    path = os.path.join(HERE, "vocabulaire.json")
    fr = json.load(open(path, encoding="utf-8"))
    by_key, counts = {}, {}
    for deck in fr["decks"]:
        for c in deck["cards"]:
            keep = [t for t in c.get("tags", []) if t not in IT]  # « vocabulaire », « faux ami »… stay
            new = tags_for(c)
            by_key[(c.get("key"), c["es"])] = list(new)
            if "faux ami" not in keep and transparent(c["es"], c["fr"]):
                new.append("transparent")
            c["tags"] = keep + new
            for t in new:
                counts[t] = counts.get(t, 0) + 1
    with open(path, "w", encoding="utf-8") as f:
        json.dump(fr, f, ensure_ascii=False, separators=(",", ":"))
    path_it = os.path.join(HERE, "vocabolario.json")
    if os.path.exists(path_it):
        it = json.load(open(path_it, encoding="utf-8"))
        for deck in it["decks"]:
            for c in deck["cards"]:
                keep = [t for t in c.get("tags", []) if t not in IT.values()]
                c["tags"] = keep + [IT[t] for t in by_key.get((c.get("key"), c["es"]), [])]
                if not {"faux ami", "falso amico"} & set(keep) and transparent(c["es"], c["fr"], "it"):
                    c["tags"].append("trasparente")  # compared with the Italian meaning
                    counts["trasparente (it)"] = counts.get("trasparente (it)", 0) + 1
        with open(path_it, "w", encoding="utf-8") as f:
            json.dump(it, f, ensure_ascii=False, separators=(",", ":"))
    print("tags du Vocabulaire : " + ", ".join(f"{t} {n}" for t, n in sorted(counts.items(), key=lambda x: -x[1])))


if __name__ == "__main__":
    main()
