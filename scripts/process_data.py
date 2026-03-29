"""
process_data.py -- Traitement des donnees de consommation Mint-Energie
======================================================================

Ce script :
1. Lit les donnees brutes depuis data/conso_raw.json (format periodes mensuelles)
2. Determine le mois comptable de chaque periode (basé sur date de debut)
3. Produit data/conso_processed.json utilise par le dashboard HTML

Les donnees viennent directement du site Mint-Energie qui fournit deja
des periodes du 12 au 11 (ex: "du 12/02/25 au 11/03/25").
"""

import json
import logging
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

# ============================================================
# Configuration et chemins
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

RAW_DATA_FILE = DATA_DIR / "conso_raw.json"
PROCESSED_DATA_FILE = DATA_DIR / "conso_processed.json"

logger = logging.getLogger("process_data")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


# ============================================================
# Logique de mois comptable
# ============================================================


def get_billing_month_from_period(period_start: str) -> str:
    """
    Determine le mois comptable depuis la date de debut de periode.
    Les periodes commencent le 12 du mois, donc le mois comptable
    est simplement le mois de la date de debut.
    Ex: 2025-02-12 -> "2025-02" (fevrier 2025)
    """
    dt = datetime.strptime(period_start, "%Y-%m-%d")
    return dt.strftime("%Y-%m")


def get_billing_month_label(billing_month: str) -> str:
    """Convertit "YYYY-MM" en libelle lisible (ex : "Fevrier 2025")."""
    mois_fr = {
        "01": "Janvier", "02": "Fevrier", "03": "Mars",
        "04": "Avril", "05": "Mai", "06": "Juin",
        "07": "Juillet", "08": "Aout", "09": "Septembre",
        "10": "Octobre", "11": "Novembre", "12": "Decembre",
    }
    parts = billing_month.split("-")
    return f"{mois_fr.get(parts[1], parts[1])} {parts[0]}"


def get_billing_month_from_invoice_date(invoice_date_str: str) -> str:
    """
    Mappe une date de facture au mois comptable correspondant.
    La facture du 13/MM/YYYY correspond a la periode qui vient de finir le 11/MM,
    donc le mois comptable est (MM-1)/YYYY.
    Ex: 13/03/2026 -> periode du 12/02 au 11/03 -> mois comptable 2026-02
        19/12/2025 -> periode du 12/11 au 11/12 -> mois comptable 2025-11
    """
    try:
        dt = datetime.strptime(invoice_date_str, "%d/%m/%Y")
    except ValueError:
        try:
            dt = datetime.strptime(invoice_date_str, "%Y-%m-%d")
        except ValueError:
            return ""

    # La facture arrive apres le 11 du mois, elle couvre le mois precedent
    if dt.month == 1:
        return f"{dt.year - 1:04d}-12"
    else:
        return f"{dt.year:04d}-{dt.month - 1:02d}"


def get_billing_month_for_date(date: datetime) -> str:
    """
    Pour les donnees journalieres legacy.
    jour >= 12 -> mois courant, jour < 12 -> mois precedent.
    """
    if date.day >= 12:
        return date.strftime("%Y-%m")
    else:
        if date.month == 1:
            return f"{date.year - 1:04d}-12"
        else:
            return f"{date.year:04d}-{date.month - 1:02d}"


# ============================================================
# Traitement principal
# ============================================================


def process_data() -> None:
    if not RAW_DATA_FILE.exists():
        logger.error(f"Fichier introuvable : {RAW_DATA_FILE}")
        return

    with open(RAW_DATA_FILE, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    # Detecter le format
    if isinstance(raw_data, dict) and raw_data.get("format") == "monthly_periods":
        process_monthly_periods(raw_data)
    elif isinstance(raw_data, list):
        process_daily_legacy(raw_data)
    else:
        logger.error("Format de données inconnu dans conso_raw.json.")


def process_monthly_periods(raw_data: dict) -> None:
    """Traite les donnees au format periodes mensuelles (depuis le scraper)."""
    monthly_raw = raw_data.get("monthly", [])
    weekly_raw = raw_data.get("weekly", [])
    daily_raw = raw_data.get("daily", [])
    invoices_raw = raw_data.get("invoices", [])

    if not monthly_raw:
        logger.warning("Aucune donnée mensuelle.")
        return

    logger.info(f"Données mensuelles : {len(monthly_raw)} périodes")
    if invoices_raw:
        logger.info(f"Factures : {len(invoices_raw)}")

    # Mapper les factures par mois comptable
    invoice_by_month = {}
    for inv in invoices_raw:
        bm = get_billing_month_from_invoice_date(inv["date"])
        if bm:
            invoice_by_month[bm] = {
                "date": inv["date"],
                "montant_euros": inv["montant"],
            }
            logger.info(f"  Facture {inv['date']} ({inv['montant']}€) -> mois {bm}")
    if weekly_raw:
        logger.info(f"Données hebdo : {len(weekly_raw)} périodes")
    if daily_raw:
        logger.info(f"Données journalières : {len(daily_raw)} points")

    # Construire monthly_data
    monthly_data = []
    for m in monthly_raw:
        billing_month = get_billing_month_from_period(m["period_start"])
        hp = m.get("hp_kwh", 0)
        hc = m.get("hc_kwh", 0)
        total = m.get("total_kwh", hp + hc)

        # Estimer nb jours depuis les dates de periode
        try:
            start = datetime.strptime(m["period_start"], "%Y-%m-%d")
            end = datetime.strptime(m["period_end"], "%Y-%m-%d")
            nb_jours = (end - start).days + 1
        except (ValueError, KeyError):
            nb_jours = 30

        avg_daily = round(total / nb_jours, 2) if nb_jours > 0 else 0

        monthly_data.append({
            "billing_month": billing_month,
            "label": get_billing_month_label(billing_month),
            "period_start": m.get("period_start"),
            "period_end": m.get("period_end"),
            "period_label": m.get("label", ""),
            "total_kwh": round(total, 2),
            "hp_kwh": round(hp, 2),
            "hc_kwh": round(hc, 2),
            "avg_daily_kwh": avg_daily,
            "min_daily_kwh": avg_daily,
            "max_daily_kwh": avg_daily,
            "hc_ratio": round(hc / total * 100, 1) if total > 0 else 0,
            "hp_ratio": round(hp / total * 100, 1) if total > 0 else 0,
            "nb_jours": nb_jours,
            "montant_euros": invoice_by_month.get(billing_month, {}).get("montant_euros"),
            "prix_kwh": round(
                invoice_by_month[billing_month]["montant_euros"] / total, 4
            ) if billing_month in invoice_by_month and total > 0 else None,
        })

    monthly_data.sort(key=lambda m: m["billing_month"])

    # Calculs globaux
    global_total = round(sum(m["total_kwh"] for m in monthly_data), 2)
    global_hp = round(sum(m["hp_kwh"] for m in monthly_data), 2)
    global_hc = round(sum(m["hc_kwh"] for m in monthly_data), 2)
    global_avg_monthly = round(global_total / len(monthly_data), 2) if monthly_data else 0

    # Top 3
    sorted_months = sorted(monthly_data, key=lambda m: m["total_kwh"], reverse=True)
    top3 = [
        {"label": m["label"], "total_kwh": m["total_kwh"], "hp_kwh": m["hp_kwh"], "hc_kwh": m["hc_kwh"]}
        for m in sorted_months[:3]
    ]

    # Comparaison annuelle
    year_data = defaultdict(lambda: {"total": 0.0, "hp": 0.0, "hc": 0.0})
    for m in monthly_data:
        year = m["billing_month"][:4]
        year_data[year]["total"] += m["total_kwh"]
        year_data[year]["hp"] += m["hp_kwh"]
        year_data[year]["hc"] += m["hc_kwh"]

    yearly_comparison = []
    for year in sorted(year_data.keys()):
        yearly_comparison.append({
            "year": year,
            "total_kwh": round(year_data[year]["total"], 2),
            "hp_kwh": round(year_data[year]["hp"], 2),
            "hc_kwh": round(year_data[year]["hc"], 2),
        })

    # Construire les "daily" pour la vue journaliere du dashboard
    # On genere un point par jour estime a partir des donnees mensuelles
    daily_records = []
    for m in monthly_data:
        try:
            start = datetime.strptime(m["period_start"], "%Y-%m-%d")
            end = datetime.strptime(m["period_end"], "%Y-%m-%d")
            nb_days = (end - start).days + 1
            hp_per_day = m["hp_kwh"] / nb_days if nb_days > 0 else 0
            hc_per_day = m["hc_kwh"] / nb_days if nb_days > 0 else 0
            total_per_day = hp_per_day + hc_per_day
            for d in range(nb_days):
                current_date = start + timedelta(days=d)
                daily_records.append({
                    "date": current_date.strftime("%Y-%m-%d"),
                    "consommation_kwh": round(total_per_day, 2),
                    "hp_kwh": round(hp_per_day, 2),
                    "hc_kwh": round(hc_per_day, 2),
                    "billing_month": m["billing_month"],
                })
        except (ValueError, KeyError):
            pass

    # Total factures
    total_factures = round(sum(
        m["montant_euros"] for m in monthly_data if m.get("montant_euros")
    ), 2)
    nb_factures = sum(1 for m in monthly_data if m.get("montant_euros"))

    # Determiner dates
    date_debut = monthly_data[0]["period_start"] if monthly_data else None
    date_fin = monthly_data[-1]["period_end"] if monthly_data else None

    processed = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "billing_rule": "Mois comptable : du 12 au 11. Periodes fournies directement par Mint-Energie.",
        "has_hc_hp": True,
        "data_source": "mint-energie-scraper",
        "summary": {
            "total_kwh": global_total,
            "hp_kwh": global_hp,
            "hc_kwh": global_hc,
            "hc_ratio": round(global_hc / global_total * 100, 1) if global_total > 0 else 0,
            "hp_ratio": round(global_hp / global_total * 100, 1) if global_total > 0 else 0,
            "avg_monthly_kwh": global_avg_monthly,
            "nb_months": len(monthly_data),
            "date_debut": date_debut,
            "date_fin": date_fin,
            "top3_months": top3,
            "yearly_comparison": yearly_comparison,
            "total_factures_euros": total_factures,
            "nb_factures": nb_factures,
            "avg_prix_kwh": round(total_factures / global_total, 4) if global_total > 0 and total_factures > 0 else None,
        },
        "monthly": monthly_data,
        "daily": daily_records,
    }

    with open(PROCESSED_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(processed, f, ensure_ascii=False, indent=2)

    logger.info(f"Données traitées sauvegardées : {PROCESSED_DATA_FILE}")
    logger.info(f"  - {len(monthly_data)} mois comptables")
    logger.info(f"  - Total: {global_total} kWh | HP: {global_hp} kWh | HC: {global_hc} kWh")


def process_daily_legacy(raw_data: list) -> None:
    """Traite les donnees au format journalier legacy (donnees demo)."""
    if not raw_data:
        logger.warning("Aucune donnée dans conso_raw.json.")
        return

    logger.info(f"Données brutes (format legacy) : {len(raw_data)} enregistrements.")

    daily_records = []
    has_hc_hp = False

    for record in raw_data:
        try:
            date = datetime.strptime(record["date"], "%Y-%m-%d")
            kwh = float(record["consommation_kwh"])
            hp = float(record.get("hp_kwh", 0))
            hc = float(record.get("hc_kwh", 0))
            billing_month = get_billing_month_for_date(date)

            if hp > 0 or hc > 0:
                has_hc_hp = True
            if kwh == 0 and (hp or hc):
                kwh = hp + hc

            daily_records.append({
                "date": record["date"],
                "consommation_kwh": kwh,
                "hp_kwh": hp,
                "hc_kwh": hc,
                "billing_month": billing_month,
            })
        except (ValueError, KeyError) as e:
            logger.warning(f"Enregistrement ignoré : {record} -- {e}")

    daily_records.sort(key=lambda r: r["date"])

    # Agregation par mois comptable
    monthly_buckets = defaultdict(lambda: {"total": [], "hp": [], "hc": []})
    for rec in daily_records:
        bm = rec["billing_month"]
        monthly_buckets[bm]["total"].append(rec["consommation_kwh"])
        monthly_buckets[bm]["hp"].append(rec["hp_kwh"])
        monthly_buckets[bm]["hc"].append(rec["hc_kwh"])

    monthly_data = []
    for month_key in sorted(monthly_buckets.keys()):
        bucket = monthly_buckets[month_key]
        totals = bucket["total"]
        hps = bucket["hp"]
        hcs = bucket["hc"]
        count = len(totals)

        monthly_data.append({
            "billing_month": month_key,
            "label": get_billing_month_label(month_key),
            "total_kwh": round(sum(totals), 2),
            "avg_daily_kwh": round(sum(totals) / count, 2) if count else 0,
            "min_daily_kwh": round(min(totals), 2) if totals else 0,
            "max_daily_kwh": round(max(totals), 2) if totals else 0,
            "hp_kwh": round(sum(hps), 2),
            "avg_daily_hp_kwh": round(sum(hps) / count, 2) if count else 0,
            "hc_kwh": round(sum(hcs), 2),
            "avg_daily_hc_kwh": round(sum(hcs) / count, 2) if count else 0,
            "hc_ratio": round(sum(hcs) / sum(totals) * 100, 1) if sum(totals) > 0 else 0,
            "hp_ratio": round(sum(hps) / sum(totals) * 100, 1) if sum(totals) > 0 else 0,
            "nb_jours": count,
        })

    global_total = round(sum(m["total_kwh"] for m in monthly_data), 2)
    global_hp = round(sum(m["hp_kwh"] for m in monthly_data), 2)
    global_hc = round(sum(m["hc_kwh"] for m in monthly_data), 2)
    global_avg_monthly = round(global_total / len(monthly_data), 2) if monthly_data else 0

    sorted_months = sorted(monthly_data, key=lambda m: m["total_kwh"], reverse=True)
    top3 = [
        {"label": m["label"], "total_kwh": m["total_kwh"], "hp_kwh": m["hp_kwh"], "hc_kwh": m["hc_kwh"]}
        for m in sorted_months[:3]
    ]

    year_data = defaultdict(lambda: {"total": 0.0, "hp": 0.0, "hc": 0.0})
    for m in monthly_data:
        year = m["billing_month"][:4]
        year_data[year]["total"] += m["total_kwh"]
        year_data[year]["hp"] += m["hp_kwh"]
        year_data[year]["hc"] += m["hc_kwh"]

    yearly_comparison = [
        {"year": y, "total_kwh": round(year_data[y]["total"], 2),
         "hp_kwh": round(year_data[y]["hp"], 2), "hc_kwh": round(year_data[y]["hc"], 2)}
        for y in sorted(year_data.keys())
    ]

    processed = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "billing_rule": "Mois comptable : du 12 au 11. Jour >= 12 = mois courant, jour < 12 = mois precedent.",
        "has_hc_hp": has_hc_hp,
        "summary": {
            "total_kwh": global_total,
            "hp_kwh": global_hp,
            "hc_kwh": global_hc,
            "hc_ratio": round(global_hc / global_total * 100, 1) if global_total > 0 else 0,
            "hp_ratio": round(global_hp / global_total * 100, 1) if global_total > 0 else 0,
            "avg_monthly_kwh": global_avg_monthly,
            "nb_months": len(monthly_data),
            "date_debut": daily_records[0]["date"] if daily_records else None,
            "date_fin": daily_records[-1]["date"] if daily_records else None,
            "top3_months": top3,
            "yearly_comparison": yearly_comparison,
        },
        "monthly": monthly_data,
        "daily": daily_records,
    }

    with open(PROCESSED_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(processed, f, ensure_ascii=False, indent=2)

    logger.info(f"Données traitées sauvegardées : {PROCESSED_DATA_FILE}")
    logger.info(f"  - {len(monthly_data)} mois comptables")
    logger.info(f"  - {len(daily_records)} jours")
    logger.info(f"  - Total: {global_total} kWh | HP: {global_hp} kWh | HC: {global_hc} kWh")


# ============================================================
# Point d'entree
# ============================================================

if __name__ == "__main__":
    process_data()
