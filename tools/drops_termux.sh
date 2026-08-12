#!/data/data/com.termux/files/usr/bin/bash
# drops_termux.sh — capture hebdomadaire des taux de drop, depuis le Pixel.
#
# POURQUOI LE TELEPHONE : eqltools.com refuse les IP de datacenter (403). Le workflow
# GitHub ne peut donc pas faire ce travail, contrairement a update-items.yml. Une
# connexion domestique ou mobile passe sans probleme.
#
# INSTALLATION, une seule fois :
#   pkg install python git
#   cd ~ && git clone https://github.com/xm2514-svg/sites.git
#   cp ~/sites/tools/drops_termux.sh ~/ && chmod +x ~/drops_termux.sh
#   crontab -e   puis la ligne :   30 5 * * 1  ~/drops_termux.sh >> ~/drops.log 2>&1
#   (lundi 5h30 — les taux de drop bougent avec les patchs, pas tous les jours)
#
# Le jeton GitHub est lu depuis ~/.github_token (le meme que pour QUINTE).

set -e
cd ~/sites || { echo "depot absent : git clone https://github.com/xm2514-svg/sites.git"; exit 1; }

echo "=== $(date '+%Y-%m-%d %H:%M') ==="
git pull -q --rebase || { echo "git pull a echoue"; exit 1; }

python tools/scrape_drops.py || { echo "scraping interrompu — fichier precedent conserve"; exit 1; }

if git diff --quiet -- drops.json; then
  echo "aucun changement, rien a pousser"
  exit 0
fi

T=$(tr -d ' \r\n' < ~/.github_token)
git -c user.email="xm2514@gmail.com" -c user.name="Xavier" add drops.json
git -c user.email="xm2514@gmail.com" -c user.name="Xavier" \
    commit -q -m "Auto: drop rates refreshed from eqltools"
git push -q "https://$T@github.com/xm2514-svg/sites.git" HEAD:main
unset T
echo "drops.json pousse : $(python -c "import json;d=json.load(open('drops.json'));print(len(d['drops']),'objets,',d['zones'],'zones')")"
