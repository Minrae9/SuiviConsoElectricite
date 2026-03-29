"""
mint_scraper.py — Scraper automatique pour Mint-Énergie
========================================================

Se connecte à l'espace client Mint-Énergie (client.mint-energie.com),
récupère les données de consommation mensuelles HC/HP depuis les champs
hidden de la page consommation (HF_COLUMN_CATEGORIES_MONTH / HF_COLUMN_SERIES_MONTH),
ainsi que les données hebdo et journalières si disponibles.

Sauvegarde dans data/conso_raw.json puis lance process_data.py.
"""

import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ============================================================
# Configuration et chemins
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = PROJECT_ROOT / "config"
ENV_FILE = CONFIG_DIR / ".env"

DATA_DIR.mkdir(exist_ok=True)

if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
else:
    load_dotenv(PROJECT_ROOT / ".env")

MINT_EMAIL = os.getenv("MINT_EMAIL")
MINT_PASSWORD = os.getenv("MINT_PASSWORD")
MINT_BASE_URL = os.getenv("MINT_BASE_URL", "https://client.mint-energie.com")
MINT_HEADLESS = os.getenv("MINT_HEADLESS", "true").lower() == "true"

RAW_DATA_FILE = DATA_DIR / "conso_raw.json"

# ============================================================
# Logging
# ============================================================

LOG_FILE = DATA_DIR / "scraper.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger("mint_scraper")

# ============================================================
# Utilitaires
# ============================================================


def load_existing_raw_data() -> dict:
    if RAW_DATA_FILE.exists():
        try:
            with open(RAW_DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Migration: ancien format = liste, nouveau = dict
                if isinstance(data, list):
                    return {"format": "monthly_periods", "monthly": [], "daily": data}
                return data
        except (json.JSONDecodeError, IOError):
            logger.warning("Fichier conso_raw.json corrompu, il sera recréé.")
    return {"format": "monthly_periods", "monthly": [], "daily": []}


def save_raw_data(data: dict) -> None:
    # Merge avec les données existantes (préserver les entrées manuelles)
    existing = load_existing_raw_data()
    existing_monthly = {m["period_start"]: m for m in existing.get("monthly", [])}

    for m in data.get("monthly", []):
        existing_monthly[m["period_start"]] = m  # scraped override manual

    merged_monthly = sorted(existing_monthly.values(), key=lambda m: m["period_start"])

    # Merge invoices : par date
    existing_invoices = {i["date"]: i for i in existing.get("invoices", [])}
    for inv in data.get("invoices", []):
        existing_invoices[inv["date"]] = inv
    merged_invoices = sorted(existing_invoices.values(), key=lambda i: i["date"])

    merged = {
        "format": "monthly_periods",
        "fetched_at": data.get("fetched_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "monthly": merged_monthly,
        "weekly": data.get("weekly", existing.get("weekly", [])),
        "daily": data.get("daily", existing.get("daily", [])),
        "invoices": merged_invoices,
    }

    with open(RAW_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    nb = len(merged["monthly"])
    nb_inv = len(merged["invoices"])
    logger.info(f"Données brutes sauvegardées : {nb} périodes mensuelles, {nb_inv} factures -> {RAW_DATA_FILE}")


# ============================================================
# Login sur client.mint-energie.com
# ============================================================


def login(page) -> bool:
    login_url = f"{MINT_BASE_URL}/Pages/Connexion/connexion.aspx"
    logger.info(f"Navigation vers {login_url}...")

    page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)

    try:
        # Chercher le champ email
        email_field = None
        for sel in ['input[type="email"]:visible', 'input[type="text"]:visible']:
            try:
                fields = page.locator(sel)
                if fields.count() > 0:
                    email_field = fields.first
                    break
            except Exception:
                continue

        if not email_field:
            all_inputs = page.locator('input:visible:not([type="password"]):not([type="hidden"]):not([type="submit"]):not([type="button"])')
            if all_inputs.count() > 0:
                email_field = all_inputs.first

        if not email_field:
            logger.error("Impossible de trouver le champ email.")
            page.screenshot(path=str(DATA_DIR / "debug_login_no_email.png"))
            return False

        email_field.fill(MINT_EMAIL)
        logger.info("Email rempli.")

        pw_field = page.locator('input[type="password"]:visible').first
        pw_field.fill(MINT_PASSWORD)
        logger.info("Mot de passe rempli.")

        for sel in ['#BT_Connexion', 'input[type="submit"]:visible', 'button[type="submit"]:visible']:
            try:
                btn = page.locator(sel)
                if btn.count() > 0 and btn.first.is_visible():
                    btn.first.click()
                    logger.info(f"Bouton de connexion cliqué ({sel})")
                    break
            except Exception:
                continue

        page.wait_for_timeout(3000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except PlaywrightTimeout:
            pass

        logger.info(f"URL après login : {page.url}")

        if "connexion" in page.url.lower():
            logger.error("Connexion échouée (toujours sur page login).")
            page.screenshot(path=str(DATA_DIR / "debug_login_failed.png"))
            return False

        logger.info("Connexion réussie !")
        return True

    except Exception as e:
        logger.error(f"Erreur lors de la connexion : {e}", exc_info=True)
        page.screenshot(path=str(DATA_DIR / "debug_login_error.png"))
        return False


# ============================================================
# Extraction des données depuis les champs hidden
# ============================================================


def parse_categories(raw: str) -> list[dict]:
    """
    Parse HF_COLUMN_CATEGORIES_MONTH.
    Format: 'du 12/02/25 au 11/03/25','du 12/03/25 au 11/04/25',...
    Retourne une liste de {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "label": "..."}.
    """
    categories = []
    # Extraire chaque entrée entre quotes
    for match in re.finditer(r"'([^']*)'", raw):
        label = match.group(1)
        # Parser "du DD/MM/YY au DD/MM/YY"
        dates = re.findall(r"(\d{2}/\d{2}/\d{2})", label)
        if len(dates) == 2:
            try:
                start = datetime.strptime(dates[0], "%d/%m/%y").strftime("%Y-%m-%d")
                end = datetime.strptime(dates[1], "%d/%m/%y").strftime("%Y-%m-%d")
                categories.append({"start": start, "end": end, "label": label})
            except ValueError as e:
                logger.warning(f"Date invalide dans catégorie '{label}': {e}")
    return categories


def parse_series(raw: str) -> dict[str, list[int]]:
    """
    Parse HF_COLUMN_SERIES_MONTH.
    Format: { name:'HP', color:'#2D2155', data:[607,556,...] },{ name:'HC', color:'#8ED0DA', data:[292,231,...] },
    Retourne {"HP": [607, 556, ...], "HC": [292, 231, ...]}.
    """
    series = {}
    # Trouver chaque bloc { name:'...', ..., data:[...] }
    for match in re.finditer(r"name\s*:\s*'([^']*)'[^}]*data\s*:\s*\[([^\]]*)\]", raw):
        name = match.group(1).upper()
        data_str = match.group(2)
        values = []
        for num in re.findall(r"[\d.]+", data_str):
            try:
                values.append(float(num))
            except ValueError:
                values.append(0)
        series[name] = values
    return series


def extract_hidden_fields(page) -> dict:
    """Extrait tous les champs hidden HF_* de la page."""
    fields = page.evaluate("""
        () => {
            const result = {};
            const inputs = document.querySelectorAll('input[type="hidden"]');
            for (const inp of inputs) {
                if (inp.id && inp.id.indexOf('HF_') === 0) {
                    result[inp.id] = inp.value;
                }
            }
            return result;
        }
    """)
    return fields


def scrape_consumption(page) -> dict | None:
    """
    Navigue vers la page de consommation et extrait les données
    depuis les champs hidden HF_COLUMN_CATEGORIES_MONTH / HF_COLUMN_SERIES_MONTH.
    """
    conso_url = f"{MINT_BASE_URL}/Pages/Compte/consommation.aspx"
    logger.info(f"Navigation vers {conso_url}...")

    try:
        page.goto(conso_url, wait_until="domcontentloaded", timeout=30000)
    except PlaywrightTimeout:
        logger.warning("Timeout page consommation (on continue).")

    page.wait_for_timeout(5000)

    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except PlaywrightTimeout:
        pass

    # Extraire les champs hidden
    fields = extract_hidden_fields(page)
    logger.info(f"Champs hidden trouvés : {list(fields.keys())}")

    for key, value in fields.items():
        preview = value[:200] if value else "(vide)"
        logger.info(f"  {key} = {preview}")

    # Parser les données mensuelles
    cat_month = fields.get("HF_COLUMN_CATEGORIES_MONTH", "")
    ser_month = fields.get("HF_COLUMN_SERIES_MONTH", "")

    if not cat_month or not ser_month:
        logger.error("Champs HF_COLUMN_CATEGORIES_MONTH ou HF_COLUMN_SERIES_MONTH introuvables/vides.")
        page.screenshot(path=str(DATA_DIR / "debug_conso_no_data.png"))
        return None

    categories = parse_categories(cat_month)
    series = parse_series(ser_month)

    logger.info(f"Catégories mensuelles : {len(categories)} périodes")
    logger.info(f"Séries mensuelles : {list(series.keys())}")

    hp_data = series.get("HP", [])
    hc_data = series.get("HC", [])

    if not categories:
        logger.error("Aucune catégorie parsée.")
        return None

    # Construire les enregistrements mensuels
    monthly = []
    for i, cat in enumerate(categories):
        hp = hp_data[i] if i < len(hp_data) else 0
        hc = hc_data[i] if i < len(hc_data) else 0
        total = hp + hc

        monthly.append({
            "period_start": cat["start"],
            "period_end": cat["end"],
            "label": cat["label"],
            "hp_kwh": round(hp, 1),
            "hc_kwh": round(hc, 1),
            "total_kwh": round(total, 1),
        })

        logger.info(f"  {cat['label']}: HP={hp} HC={hc} Total={total} kWh")

    # Aussi récupérer les données par semaine et par jour si dispo
    weekly = []
    cat_week = fields.get("HF_COLUMN_CATEGORIES_WEEK", "")
    ser_week = fields.get("HF_COLUMN_SERIES_WEEK", "")
    if cat_week and ser_week:
        w_categories = parse_categories(cat_week)
        w_series = parse_series(ser_week)
        w_hp = w_series.get("HP", [])
        w_hc = w_series.get("HC", [])
        for i, cat in enumerate(w_categories):
            hp = w_hp[i] if i < len(w_hp) else 0
            hc = w_hc[i] if i < len(w_hc) else 0
            weekly.append({
                "period_start": cat["start"],
                "period_end": cat["end"],
                "label": cat["label"],
                "hp_kwh": round(hp, 1),
                "hc_kwh": round(hc, 1),
                "total_kwh": round(hp + hc, 1),
            })
        logger.info(f"Données hebdo : {len(weekly)} périodes")

    daily = []
    cat_day = fields.get("HF_COLUMN_CATEGORIES_DAY", "")
    ser_day = fields.get("HF_COLUMN_SERIES_DAY", "")
    if cat_day and ser_day:
        d_categories = parse_categories(cat_day)
        d_series = parse_series(ser_day)
        d_hp = d_series.get("HP", [])
        d_hc = d_series.get("HC", [])
        for i, cat in enumerate(d_categories):
            hp = d_hp[i] if i < len(d_hp) else 0
            hc = d_hc[i] if i < len(d_hc) else 0
            daily.append({
                "period_start": cat["start"],
                "period_end": cat["end"],
                "label": cat["label"],
                "hp_kwh": round(hp, 1),
                "hc_kwh": round(hc, 1),
                "total_kwh": round(hp + hc, 1),
            })
        logger.info(f"Données journalières : {len(daily)} points")

    # Aussi cliquer sur les onglets semaine/jour pour charger les données
    # (les champs hidden sont peut-être vides tant qu'on n'a pas cliqué)
    if not weekly:
        weekly = try_load_tab(page, "BT_CONSO_WEEK", "HF_COLUMN_CATEGORIES_WEEK", "HF_COLUMN_SERIES_WEEK", "Semaine")
    if not daily:
        daily = try_load_tab(page, "BT_CONSO_DAY", "HF_COLUMN_CATEGORIES_DAY", "HF_COLUMN_SERIES_DAY", "Jour")

    return {
        "format": "monthly_periods",
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "monthly": monthly,
        "weekly": weekly,
        "daily": daily,
    }


def try_load_tab(page, tab_id: str, cat_field: str, ser_field: str, label: str) -> list:
    """Clique un onglet et récupère les données qui se chargent."""
    try:
        tab = page.locator(f"#{tab_id}")
        if tab.count() > 0 and tab.first.is_visible():
            logger.info(f"Clic sur onglet '{label}'...")
            tab.first.click()
            page.wait_for_timeout(3000)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except PlaywrightTimeout:
                pass
            page.wait_for_timeout(2000)

            fields = extract_hidden_fields(page)
            cat_raw = fields.get(cat_field, "")
            ser_raw = fields.get(ser_field, "")

            if cat_raw and ser_raw:
                categories = parse_categories(cat_raw)
                series = parse_series(ser_raw)
                hp_data = series.get("HP", [])
                hc_data = series.get("HC", [])
                records = []
                for i, cat in enumerate(categories):
                    hp = hp_data[i] if i < len(hp_data) else 0
                    hc = hc_data[i] if i < len(hc_data) else 0
                    records.append({
                        "period_start": cat["start"],
                        "period_end": cat["end"],
                        "label": cat["label"],
                        "hp_kwh": round(hp, 1),
                        "hc_kwh": round(hc, 1),
                        "total_kwh": round(hp + hc, 1),
                    })
                logger.info(f"Données '{label}' : {len(records)} entrées")
                return records
            else:
                logger.info(f"Onglet '{label}' : pas de données dans les champs hidden.")
    except Exception as e:
        logger.warning(f"Erreur chargement onglet '{label}': {e}")

    return []


# ============================================================
# Scraping des factures (page informations_paiement.aspx)
# ============================================================


def scrape_invoices(page) -> list[dict]:
    """
    Navigue vers la page des factures et extrait date + montant.
    La page factures_liste.aspx contient des blocs avec :
      <div>Date : <b>DD/MM/YYYY</b></div>
      <div>Montant : <b>XXX,XX€</b></div>
    """
    # On essaie d'abord factures_liste.aspx (page "Toutes vos factures"),
    # sinon informations_paiement.aspx
    for url_path in ["factures_liste.aspx", "informations_paiement.aspx"]:
        invoice_url = f"{MINT_BASE_URL}/Pages/Compte/{url_path}"
        logger.info(f"Navigation vers {invoice_url}...")

        try:
            page.goto(invoice_url, wait_until="domcontentloaded", timeout=30000)
        except PlaywrightTimeout:
            logger.warning(f"Timeout {url_path} (on continue).")
            continue

        page.wait_for_timeout(3000)

        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except PlaywrightTimeout:
            pass

        # Verifier qu'on est sur une page avec des factures
        has_factures = page.evaluate("() => document.body.innerText.indexOf('Montant') !== -1")
        if has_factures:
            logger.info(f"Page factures trouvée : {url_path}")
            break
    else:
        logger.warning("Aucune page factures accessible.")
        return []

    # Sauvegarder le HTML pour debug
    try:
        html = page.content()
        with open(DATA_DIR / "debug_factures_page.html", "w", encoding="utf-8") as f:
            f.write(html)
    except Exception:
        pass

    # Extraire les factures : chercher les paires Date/Montant dans les <b>
    invoices = page.evaluate(r"""
        () => {
            const results = [];
            // Trouver tous les <b> contenant une date DD/MM/YYYY
            const bolds = document.querySelectorAll('b');
            const dates = [];
            const montants = [];

            for (const b of bolds) {
                const txt = (b.textContent || '').trim();
                // Date: DD/MM/YYYY
                if (/^\d{2}\/\d{2}\/\d{4}$/.test(txt)) {
                    // Verifier que le parent contient "Date"
                    const parent = b.parentElement;
                    if (parent && (parent.textContent || '').indexOf('Date') !== -1) {
                        dates.push(txt);
                    }
                }
                // Montant: XXX,XX€
                if (/[\d.,]+€$/.test(txt)) {
                    const parent = b.parentElement;
                    if (parent && (parent.textContent || '').indexOf('Montant') !== -1) {
                        montants.push(txt);
                    }
                }
            }

            // Les dates et montants sont dans le meme ordre
            const count = Math.min(dates.length, montants.length);
            for (let i = 0; i < count; i++) {
                const montantStr = montants[i].replace(/[€\s]/g, '').replace(',', '.');
                results.push({
                    date: dates[i],
                    montant: parseFloat(montantStr),
                });
            }

            return results;
        }
    """)

    logger.info(f"Factures trouvées : {len(invoices)}")
    for inv in invoices:
        logger.info(f"  {inv['date']} : {inv['montant']}€")

    return invoices


def run_scraper() -> bool:
    if not MINT_EMAIL or not MINT_PASSWORD:
        logger.error(
            "Identifiants manquants ! Créez le fichier config/.env à partir de "
            "config/config.example.env et renseignez MINT_EMAIL et MINT_PASSWORD."
        )
        return False

    logger.info("=" * 60)
    logger.info(f"Démarrage du scraping Mint-Énergie — {datetime.now():%Y-%m-%d %H:%M}")
    logger.info(f"Mode headless : {MINT_HEADLESS}")
    logger.info("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=MINT_HEADLESS)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        try:
            if not login(page):
                return False

            result = scrape_consumption(page)

            if not result or not result.get("monthly"):
                logger.error("Aucune donnée mensuelle extraite.")
                page.screenshot(path=str(DATA_DIR / "debug_error.png"))
                return False

            # Scraper les factures
            invoices = scrape_invoices(page)
            result["invoices"] = invoices

            save_raw_data(result)
            return True

        except Exception as e:
            logger.error(f"Erreur inattendue : {e}", exc_info=True)
            try:
                page.screenshot(path=str(DATA_DIR / "debug_error.png"))
            except Exception:
                pass
            return False

        finally:
            browser.close()
            logger.info("Navigateur fermé.")


# ============================================================
# Point d'entrée
# ============================================================

if __name__ == "__main__":
    success = run_scraper()

    if success:
        logger.info("Lancement du traitement des données...")
        from process_data import process_data
        process_data()
        logger.info("Terminé avec succès.")
    else:
        logger.error("Le scraping a échoué.")
        sys.exit(1)
