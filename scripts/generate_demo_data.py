"""
generate_demo_data.py -- Genere des donnees de demonstration avec HC/HP
========================================================================

Utilisez ce script pour tester le tableau de bord HTML avant
d'avoir configure le scraping reel.

Les heures creuses sont typiquement la nuit (22h-6h) et representent
environ 35-45% de la consommation totale.

Usage :
    python scripts/generate_demo_data.py
"""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

RAW_FILE = DATA_DIR / "conso_raw.json"


def generate():
    """Genere 365+ jours de donnees fictives avec HC/HP."""
    records = []
    start = datetime(2025, 1, 12)
    end = datetime(2026, 3, 11)

    current = start
    while current <= end:
        month = current.month

        # Consommation totale simulee : base saisonniere + bruit
        if month in (12, 1, 2):
            base = 18.0  # hiver = chauffage
        elif month in (3, 11):
            base = 14.0
        elif month in (4, 10):
            base = 10.0
        elif month in (6, 7, 8):
            base = 8.0   # ete = moins de conso
        else:
            base = 11.0

        # Weekend = un peu plus (presence maison)
        if current.weekday() >= 5:
            base += 2.0

        noise = random.gauss(0, 2.5)
        total_kwh = max(1.0, round(base + noise, 1))

        # Repartition HC / HP
        # HC represente environ 35-45% du total (plage variable)
        hc_ratio = random.uniform(0.35, 0.45)
        hc_kwh = round(total_kwh * hc_ratio, 1)
        hp_kwh = round(total_kwh - hc_kwh, 1)

        records.append({
            "date": current.strftime("%Y-%m-%d"),
            "consommation_kwh": total_kwh,
            "hp_kwh": hp_kwh,
            "hc_kwh": hc_kwh,
        })

        current += timedelta(days=1)

    with open(RAW_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"Donnees de demo generees : {len(records)} jours -> {RAW_FILE}")

    # Lancer le traitement
    from process_data import process_data
    process_data()
    print("Traitement termine. Vous pouvez ouvrir le tableau de bord.")


if __name__ == "__main__":
    generate()
