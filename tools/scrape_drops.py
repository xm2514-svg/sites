# -*- coding: utf-8 -*-
"""scrape_drops.py — construit _repo/drops.json : QUI droppe QUOI, et a quel TAUX.

    python3 scrape_drops.py            met a jour ce qui manque (reprend ou il s'est arrete)
    python3 scrape_drops.py --reset    repart de zero

A LANCER DEPUIS LE PIXEL (Termux) OU LE PC DE XAVIER — JAMAIS DEPUIS GITHUB ACTIONS.
eqltools.com renvoie 403 aux IP de datacenter : le runner GitHub sera refuse, comme le
sandbox de Claude. Constate le 12/08/2026 sur toutes les zones, y compris celles deja en
cache. Depuis une connexion domestique, tout repond normalement.

SOURCE  https://eqltools.com/atlas/zones/index.json  -> les 122 zones
        https://eqltools.com/atlas/wiki/{zone}.json  -> mobs + items + taux
        Donnees eqlwiki.com, licence CC BY-SA 4.0 — attribution obligatoire dans le guide.

SORTIE  _repo/drops.json, oriente OBJET (c'est la fiche d'objet qui l'affiche) :

    {"Ghoulbane": [{"z":"guktop","m":"the froglok shin lord","lvl":"35","dr":"2.4%"}], ...}

GARDE-FOUS, comme update_items.py :
  - moins de SEUIL_ZONES zones recuperees -> abandon, rien n'est ecrit
  - le nouveau fichier perd plus de 20 % d'objets -> ancien conserve
  - ecriture atomique (.tmp puis os.replace)
  - PAUSE entre chaque zone : le site nous donne ses donnees, on ne le matraque pas
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(HERE)
OUT = os.path.join(RACINE, "drops.json")
CACHE = os.path.join(HERE, ".drops_cache.json")   # reprise entre deux lancements

BASE = "https://eqltools.com/atlas"
UA = {"User-Agent": "EQLegendsGuide/1.0 (+https://xm2514-svg.github.io/sites/)"}
PAUSE = 1.5          # secondes entre deux zones
SEUIL_ZONES = 100    # sur 122 : en dessous, la capture est incomplete


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def zones():
    d = get(BASE + "/zones/index.json")
    z = d.get("zones", d)
    z = z if isinstance(z, list) else list(z.values())
    return [x["key"] for x in z if isinstance(x, dict) and x.get("key")]


def main():
    reset = "--reset" in sys.argv
    cache = {}
    if not reset and os.path.exists(CACHE):
        try:
            cache = json.load(open(CACHE, encoding="utf-8"))
        except Exception:
            cache = {}

    try:
        liste = zones()
    except urllib.error.HTTPError as e:
        sys.exit("ABANDON : l'index des zones renvoie %s. Depuis un datacenter (GitHub Actions, "
                 "sandbox) eqltools refuse les requetes — lancer ce script depuis Termux ou le PC."
                 % e.code)
    print("%d zones a l'index, %d deja en cache" % (len(liste), len(cache)))

    for i, z in enumerate(liste, 1):
        if z in cache:
            continue
        try:
            d = get("%s/wiki/%s.json" % (BASE, z))
        except Exception as e:
            print("  %-16s ignoree (%s)" % (z, type(e).__name__))
            continue
        noms = [x.get("n") for x in d.get("items", [])]
        lignes = []
        for m in d.get("mobs", []):
            drops, taux = m.get("drops") or [], m.get("dr") or []
            for k, idx in enumerate(drops):
                if 0 <= idx < len(noms) and noms[idx]:
                    lignes.append({"o": noms[idx], "m": m.get("n"), "lvl": m.get("lvl"),
                                   "dr": taux[k] if k < len(taux) else None,
                                   "named": bool(m.get("named"))})
        cache[z] = lignes
        json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
        if i % 10 == 0 or i == len(liste):
            print("  %3d/%d  %-16s %d couples objet/mob" % (i, len(liste), z, len(lignes)))
        time.sleep(PAUSE)

    if len(cache) < SEUIL_ZONES:
        sys.exit("ABANDON : seulement %d zones sur %d — fichier precedent conserve"
                 % (len(cache), len(liste)))

    # --- pivot : oriente objet
    par_objet = {}
    for z, lignes in cache.items():
        for l in lignes:
            e = {"z": z, "m": l["m"], "lvl": l["lvl"], "dr": l["dr"]}
            if l["named"]:
                e["named"] = 1
            par_objet.setdefault(l["o"], []).append(e)
    # les named d'abord, puis le meilleur taux connu
    for o in par_objet:
        par_objet[o].sort(key=lambda e: (0 if e.get("named") else 1, e["z"]))
        par_objet[o] = par_objet[o][:8]

    if os.path.exists(OUT):
        try:
            anc = len(json.load(open(OUT, encoding="utf-8")).get("drops", {}))
            if anc and len(par_objet) < anc * 0.8:
                sys.exit("ABANDON : %d objets contre %d avant — fichier conserve"
                         % (len(par_objet), anc))
        except Exception:
            pass

    data = {"source": "eqltools.com / eqlwiki.com", "license": "CC BY-SA 4.0",
            "updated": time.strftime("%Y-%m-%d"), "zones": len(cache), "drops": par_objet}
    tmp = OUT + ".tmp"
    json.dump(data, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, OUT)
    print("drops.json : %d objets, %d zones, %.0f Ko"
          % (len(par_objet), len(cache), os.path.getsize(OUT) / 1024))


if __name__ == "__main__":
    main()
