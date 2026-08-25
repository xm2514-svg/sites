# -*- coding: utf-8 -*-
"""build_items_calc.py — fabrique items-calc.json a partir de items-all.json.

items-all.json garde le bloc de stats brut du wiki (champ "s") et la liste des droppeurs
("d"). Le calculateur d'objets, lui, a besoin de champs deja decoupes : c'est ce fichier-la.

Ecrit le 25/08/2026 parce qu'il n'existait plus : items-calc.json etait fige au 19 aout et
aucun script du depot ne savait le regenerer. Il tourne apres update_items.py, sans reseau.

    python3 tools/build_items_calc.py

Sortie : items-calc.json, memes cles qu'avant — source, regle, items.
Chaque objet : st (dict de stats), dly, wt, slot, cl, race, eff, skill, haste, zone, mobs, g.
"""
import json
import os
import re

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(RACINE, "items-all.json")
EXTRAIT = os.path.join(RACINE, "items.json")
OUT = os.path.join(RACINE, "items-calc.json")

REGLE = "+10 % cumule par tier, minimum +1, arrondi bas ; haste +1/tier ; delay fixe"

# Les resistances s'ecrivent « SV FIRE: +20 » dans le wiki et « SV Fire » dans le calculateur.
SV = {"FIRE": "SV Fire", "COLD": "SV Cold", "MAGIC": "SV Magic",
      "POISON": "SV Poison", "DISEASE": "SV Disease", "VOID": "SV Void"}
ATTRS = ("STR", "STA", "AGI", "DEX", "WIS", "INT", "CHA", "HP", "MANA", "AC", "DMG", "ENDUR")


def stats(s):
    """Le bloc brut -> dict de stats. Les lignes sont libres, on cherche les motifs."""
    d = {}
    for cle, val in re.findall(r"\b([A-Z]{2,5}):\s*([+-]?\d+)", s):
        if cle in ATTRS:
            d[cle] = int(val)
    for cle, val in re.findall(r"\bSV\s+([A-Z]+):\s*([+-]?\d+)", s):
        if cle in SV:
            d[SV[cle]] = int(val)
    return d


def un(s, motif, conv=str):
    m = re.search(motif, s, re.M)
    if not m:
        return None
    try:
        return conv(m.group(1).strip())
    except ValueError:
        return None


def convertit(nom, v, dans_guide):
    s = v.get("s") or ""
    o = {}
    st = stats(s)
    if st:
        o["st"] = st
    for cle, motif, conv in (
            ("dly", r"Atk Delay:\s*(\d+)", int),
            ("haste", r"Haste:\s*\+?(\d+)\s*%", int),
            ("wt", r"WT:\s*([\d.]+)", float),
            ("slot", r"Slot:\s*([A-Za-z][A-Za-z ]*)", str),
            ("cl", r"Class:\s*([A-Za-z][A-Za-z ]*)", str),
            ("skill", r"Skill:[ \t]*([A-Za-z0-9 ]+?)[ \t]*(?:Atk Delay|$)", str),
            ("eff", r"Effect:\s*([^(\n]+?)\s*(?:\(|at Level|\n|$)", str)):
        x = un(s, motif, conv)
        if x not in (None, ""):
            o[cle] = x
    race = un(s, r"Race:\s*([A-Za-z][A-Za-z ]*)")
    if race and race.strip() != "ALL":
        o["race"] = race.strip()
    # « Zone\n* mob\n* mob\nAutre zone\n* mob » : on garde la premiere zone et tous les mobs
    d = v.get("d") or ""
    if d:
        lignes = [x.strip() for x in d.split("\n") if x.strip()]
        zones = [x for x in lignes if not x.startswith("*")]
        mobs = [x.lstrip("* ").strip() for x in lignes if x.startswith("*")]
        if zones:
            o["zone"] = zones[0]      # la premiere zone citee
        if mobs:
            o["mobs"] = mobs[:4]      # quatre droppeurs au plus, comme la base d'origine
    if dans_guide:
        o["g"] = 1
    return o


def main():
    src = json.load(open(SRC, encoding="utf-8"))
    tous = src["items"]
    guide = set()
    if os.path.exists(EXTRAIT):
        guide = set(json.load(open(EXTRAIT, encoding="utf-8")).get("items", {}))
    out = {n: convertit(n, v, n in guide) for n, v in tous.items()}

    ancien = 0
    if os.path.exists(OUT):
        try:
            ancien = len(json.load(open(OUT, encoding="utf-8")).get("items", {}))
        except Exception:
            pass
    # garde-fou : on ne remplace jamais une base saine par une base amputee
    if ancien and len(out) < ancien * 0.9:
        raise SystemExit("REFUS : %d objets contre %d avant, la source est suspecte"
                         % (len(out), ancien))

    tmp = OUT + ".tmp"
    json.dump({"source": src.get("source", "eqlwiki.com"), "regle": REGLE, "items": out},
              open(tmp, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, OUT)
    avec = sum(1 for v in out.values() if v.get("st"))
    print("items-calc.json : %d objets, %d avec des stats, %d Ko"
          % (len(out), avec, os.path.getsize(OUT) / 1024))


if __name__ == "__main__":
    main()
