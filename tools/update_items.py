# -*- coding: utf-8 -*-
"""
Met a jour items.json a partir d'eqlwiki. Concu pour tourner chez GitHub (Actions),
donc sans aucune dependance et sans toucher au HTML du site.

Fonctionnement :
  1. recupere la liste des titres de Category:Items (~22 requetes, titres seuls)
  2. garde uniquement les noms d'objets reellement cites dans index.html
  3. telecharge la fiche de ces objets-la (~3 requetes)
  4. recupere la fiche des EFFETS cites par ces objets (pages Spellpage du wiki)
  5. ecrit items.json seulement si les garde-fous passent

Les effets : la fiche objet ne donne que le NOM du proc ("Effect: Ykesha"), jamais ce
qu'il fait. La description vit sur une page a part. On la recupere pour pouvoir afficher
"Ykesha - DD proc, interrompt les sorts, 475 de haine" au lieu d'un nom seul.
Cette partie ne doit JAMAIS faire echouer la mise a jour des objets : en cas de pepin
on garde les effets precedents.

GARDE-FOUS (le site ne doit jamais casser a cause d'une mise a jour de donnees) :
  - la categorie doit renvoyer au moins 5000 titres, sinon on abandonne
  - le nouveau fichier doit garder au moins 80 % des objets du precedent, sinon on abandonne
  - ecriture atomique
  - index.html et eq-legends.html ne sont JAMAIS modifies
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date

def _nettoie(t):
    """Retire le HTML du wiki. Sans ca, l'infobulle affichait en clair
    "Effect: <span class='itemeff'>Ykesha</span>" au lieu de "Effect: Ykesha"."""
    t = re.sub(r"<[Bb][Rr]\s*/?>", " ", t)
    t = re.sub(r"<[^>]+>", "", t)
    return re.sub(r"[ \t]{2,}", " ", t).strip()


API = "https://eqlwiki.com/api.php"
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(RACINE, "index.html")
OUT = os.path.join(RACINE, "items.json")
# Base complete (~10 900 objets) pour la barre de recherche du site. Elle n'est PAS
# chargee au demarrage : la page ne la telecharge que si le lecteur tape une recherche.
# 331 Ko compresses, mis en cache par le navigateur ensuite.
OUT_ALL = os.path.join(RACINE, "items-all.json")
# Les effets ont leur propre base, independante des objets : un fichier, une chose.
OUT_EFF = os.path.join(RACINE, "effects.json")
SEUIL_ALL = 5000
UA = {"User-Agent": "EQLegendsGuide/1.0 (+https://xm2514-svg.github.io/sites/)"}
SEUIL_TITRES = 5000

ALIAS = {
    "FBSS": "Flowing Black Silk Sash",
    "Sword of Ykesha": "Short Sword of the Ykesha",
    "Executioner's Axe": "An Executioners Axe",
    "Executioner's Hood": "Executioners Hood",
    "Dark Reaver": "A Dark Reaver",
    "Clawed Knuckle Ring": "Clawed Knuckle-Ring",
}


def api(params):
    url = API + "?" + urllib.parse.urlencode(params)
    for essai in range(4):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40))
        except Exception:
            if essai == 3:
                raise
            time.sleep(3 * (essai + 1))


def titres():
    out, cont = [], None
    while True:
        p = {"action": "query", "list": "categorymembers", "cmtitle": "Category:Items",
             "cmlimit": "500", "format": "json"}
        if cont:
            p["cmcontinue"] = cont
        d = api(p)
        out += [m["title"] for m in d["query"]["categorymembers"]]
        cont = d.get("continue", {}).get("cmcontinue")
        if not cont:
            return [t for t in out if not t.startswith("Category:")]


def champ(w, nom):
    m = re.search(r"\|\s*" + nom + r"\s*=([\s\S]*?)(?=\n\|[a-zA-Z_]+\s*=|\}\})", w)
    return m.group(1).strip() if m else ""


def nettoie(s):
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"\[\[([^\]|]*\|)?([^\]]*)\]\]", r"\2", s)
    s = re.sub(r"'''?", "", s)
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n{2,}", "\n", s).strip()



def champ_sort(w, nom):
    """Champ d'une page Spellpage. Le separateur y est "\n| nom = " AVEC espaces,
    que champ() ne reconnait pas : elle capturait alors toute la fin de la page."""
    m = re.search(r"\n\|\s*" + nom + r"\s*=([\s\S]*?)(?=\n\|\s*[a-zA-Z_]+\s*=|\n\}\})", w)
    return m.group(1).strip() if m else ""



def effets(items, anciens):
    """Fiches des effets cites par les objets. Le wiki les publie sur des pages
    Spellpage separees : la fiche objet ne porte que le nom du proc."""
    noms = set()
    for v in items.values():
        for m in re.finditer(r"Effect:\s*([^(\n]+?)\s*\(", v["s"]):
            n = m.group(1).strip()
            if 2 < len(n) < 60:
                noms.add(n)
    if not noms:
        return anciens
    print("effets cites par les objets : %d" % len(noms))
    out = {}
    noms = sorted(noms)
    for i in range(0, len(noms), 50):
        try:
            d = api({"action": "query", "prop": "revisions", "rvprop": "content",
                     "rvslots": "main", "format": "json", "titles": "|".join(noms[i:i + 50])})
        except Exception as e:
            print("  effets : lot ignore (%s)" % e)
            continue
        for p in d["query"]["pages"].values():
            if "revisions" not in p:
                continue
            w = p["revisions"][0]["slots"]["main"].get("*", "")
            if "Spellpage" not in w:
                continue
            desc = _nettoie(nettoie(champ_sort(w, "description")))
            slots = [_nettoie(nettoie(m.group(1))) for m in
                     re.finditer(r"\{\{SpellSlotRow\s*\|\s*\d+\s*\|([^}]*)\}\}", w)]
            fiche = {"d": desc, "e": [x for x in slots if x]}
            for cle, champ_wiki in (("r", "recast_time"), ("t", "duration"), ("s", "resist")):
                v = _nettoie(nettoie(champ_sort(w, champ_wiki)))
                if v:
                    fiche[cle] = v
            if desc or fiche["e"]:
                out[p["title"]] = fiche
    if len(out) < len(anciens) * 0.8:
        print("  effets : chute suspecte (%d contre %d), on garde les precedents"
              % (len(out), len(anciens)))
        return anciens
    print("effets recuperes : %d" % len(out))
    return out


def main():
    page = open(PAGE, encoding="utf-8").read()
    texte = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ",
                   re.sub(r"<script.*?</script>", "", page, flags=re.S)))

    tous = titres()
    if len(tous) < SEUIL_TITRES:
        sys.exit("ABANDON : seulement %d titres recuperes" % len(tous))
    print("titres dans la categorie Items : %d" % len(tous))

    vises = [t for t in tous if len(t) >= 6 and t in texte]
    for a, vrai in ALIAS.items():
        if (a in texte or vrai in texte) and vrai in tous and vrai not in vises:
            vises.append(vrai)
    print("objets cites dans le guide : %d" % len(vises))

    items = {}
    for i in range(0, len(vises), 50):
        d = api({"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
                 "format": "json", "titles": "|".join(vises[i:i + 50])})
        for p in d["query"]["pages"].values():
            if "revisions" not in p:
                continue
            w = p["revisions"][0]["slots"]["main"].get("*", "")
            s = nettoie(champ(w, "statsblock"))
            if s:
                items[p["title"]] = {"s": _nettoie(s), "d": _nettoie(nettoie(champ(w, "dropsfrom")))[:200]}

    if os.path.exists(OUT):
        try:
            ancien = json.load(open(OUT, encoding="utf-8")).get("items", {})
            if ancien and len(items) < len(ancien) * 0.8:
                sys.exit("ABANDON : %d objets contre %d avant, fichier conserve" % (len(items), len(ancien)))
        except Exception:
            pass

    # --- base complete pour la recherche du site
    tous_items = {}
    for i in range(0, len(tous), 50):
        try:
            d = api({"action": "query", "prop": "revisions", "rvprop": "content",
                     "rvslots": "main", "format": "json", "titles": "|".join(tous[i:i + 50])})
        except Exception as e:
            print("  base complete : lot ignore (%s)" % e)
            continue
        for p in d["query"]["pages"].values():
            if "revisions" not in p:
                continue
            w = p["revisions"][0]["slots"]["main"].get("*", "")
            st = nettoie(champ(w, "statsblock"))
            if st:
                tous_items[p["title"]] = {"s": _nettoie(st),
                                          "d": _nettoie(nettoie(champ(w, "dropsfrom")))[:200]}
        if (i // 50) % 20 == 0:
            print("  base complete : %d/%d" % (i, len(tous)))

    if len(tous_items) >= SEUIL_ALL:
        anc_all = 0
        if os.path.exists(OUT_ALL):
            try:
                anc_all = len(json.load(open(OUT_ALL, encoding="utf-8")).get("items", {}))
            except Exception:
                pass
        if anc_all and len(tous_items) < anc_all * 0.8:
            print("base complete : chute suspecte (%d contre %d), fichier conserve"
                  % (len(tous_items), anc_all))
        else:
            tmp = OUT_ALL + ".tmp"
            json.dump({"source": "eqlwiki.com", "updated": date.today().isoformat(),
                       "items": tous_items}, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
            os.replace(tmp, OUT_ALL)
            print("items-all.json : %d objets, %.0f Ko"
                  % (len(tous_items), os.path.getsize(OUT_ALL) / 1024))
    else:
        print("base complete : seulement %d objets, fichier precedent conserve" % len(tous_items))

    # --- base des effets, independante (couvre les objets du guide ET la base complete)
    anciens_eff = {}
    if os.path.exists(OUT_EFF):
        try:
            anciens_eff = json.load(open(OUT_EFF, encoding="utf-8")).get("effects", {})
        except Exception:
            pass
    source_eff = dict(items)
    source_eff.update(tous_items)
    try:
        eff = effets(source_eff, anciens_eff)
    except Exception as e:
        print("effets : echec, on garde les precedents (%s)" % e)
        eff = anciens_eff
    if eff:
        tmp_e = OUT_EFF + ".tmp"
        json.dump({"source": "eqlwiki.com", "updated": date.today().isoformat(), "effects": eff},
                  open(tmp_e, "w", encoding="utf-8"), ensure_ascii=False)
        os.replace(tmp_e, OUT_EFF)
        print("effects.json : %d effets, %.0f Ko" % (eff and len(eff), os.path.getsize(OUT_EFF) / 1024))

    data = {"source": "eqlwiki.com", "updated": date.today().isoformat(),
            "alias": ALIAS, "items": items}
    tmp = OUT + ".tmp"
    json.dump(data, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, OUT)
    print("items.json : %d objets, %d effets, %.1f Ko, %s"
          % (len(items), len(eff), os.path.getsize(OUT) / 1024, data["updated"]))


if __name__ == "__main__":
    main()
