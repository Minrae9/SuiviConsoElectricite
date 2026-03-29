# Mint-Énergie — Suivi automatique de consommation électrique

Projet local (Windows) pour récupérer automatiquement vos données de consommation électrique depuis votre espace client Mint-Énergie, les stocker en local et les afficher dans un tableau de bord HTML.

---

## Table des matières

1. [Architecture du projet](#architecture-du-projet)
2. [Prérequis](#prérequis)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Premier lancement (test manuel)](#premier-lancement-test-manuel)
6. [Adaptation au site Mint-Énergie](#adaptation-au-site-mint-énergie)
7. [Automatisation (Planificateur de tâches Windows)](#automatisation-planificateur-de-tâches-windows)
8. [Visualiser le tableau de bord](#visualiser-le-tableau-de-bord)
9. [Logique des mois comptables (12→11)](#logique-des-mois-comptables-1211)
10. [Dépannage](#dépannage)
11. [Avertissement légal](#avertissement-légal)

---

## Architecture du projet

```
MintEnergie/
├── config/
│   ├── config.example.env    # Exemple de configuration (à copier vers .env)
│   └── .env                  # Vos identifiants (NON versionné, à créer)
├── data/
│   ├── conso_raw.json        # Données brutes (généré automatiquement)
│   ├── conso_processed.json  # Données traitées (généré automatiquement)
│   └── scraper.log           # Journal d'exécution
├── scripts/
│   ├── mint_scraper.py       # Script principal : scraping + lancement du traitement
│   └── process_data.py       # Traitement des données (logique 12→11, agrégation)
├── web/
│   ├── index.html            # Page du tableau de bord
│   ├── style.css             # Styles CSS
│   └── app.js                # Logique JavaScript + graphiques Chart.js
├── requirements.txt          # Dépendances Python
├── .gitignore
└── README.md                 # Ce fichier
```

---

## Prérequis

- **Windows 10 ou 11**
- **Python 3.10+** installé et accessible dans le PATH
  - Vérifiez avec : `python --version`
  - Téléchargement : https://www.python.org/downloads/
- **Connexion internet** (pour le scraping et le CDN Chart.js)
- **Navigateur web** (Chrome, Edge, Firefox...) pour visualiser le tableau de bord

---

## Installation

### 1. Ouvrir un terminal

Ouvrez **PowerShell** ou **Invite de commandes** et naviguez vers le dossier du projet :

```powershell
cd C:\Users\NicolasBERGER\MintEnergie
```

### 2. Créer un environnement virtuel Python (recommandé)

```powershell
python -m venv .venv
.venv\Scripts\activate
```

### 3. Installer les dépendances

```powershell
pip install -r requirements.txt
```

### 4. Installer le navigateur Playwright

Playwright télécharge un navigateur Chromium embarqué :

```powershell
playwright install chromium
```

> Cette commande télécharge ~150 Mo. Elle ne doit être exécutée qu'une seule fois.

---

## Configuration

### 1. Créer le fichier d'identifiants

Copiez le fichier exemple :

```powershell
copy config\config.example.env config\.env
```

### 2. Renseigner vos identifiants

Ouvrez `config/.env` dans un éditeur de texte et remplissez :

```env
MINT_EMAIL=votre_email@exemple.com
MINT_PASSWORD=votre_mot_de_passe
MINT_BASE_URL=https://espace-client.mint-energie.com
MINT_HEADLESS=true
```

> **Sécurité** : le fichier `config/.env` est exclu du versionnement Git via `.gitignore`. Ne le partagez jamais.

> **Mode debug** : mettez `MINT_HEADLESS=false` pour voir le navigateur s'ouvrir (utile pour adapter les sélecteurs).

---

## Premier lancement (test manuel)

Avant d'automatiser, lancez le script à la main pour vérifier que tout fonctionne :

```powershell
cd C:\Users\NicolasBERGER\MintEnergie
.venv\Scripts\activate
python scripts/mint_scraper.py
```

**Résultat attendu** :
- Le script se connecte à Mint-Énergie
- Il récupère vos données de consommation
- Il crée `data/conso_raw.json` (données brutes)
- Il crée `data/conso_processed.json` (données traitées)

**Si ça ne fonctionne pas** : voir la section [Adaptation au site Mint-Énergie](#adaptation-au-site-mint-énergie).

---

## Adaptation au site Mint-Énergie

Le script fait des **hypothèses** sur la structure du site. Vous devrez probablement adapter certains éléments après inspection du site réel.

### Comment inspecter le site

1. Ouvrez votre navigateur sur l'espace client Mint-Énergie
2. Connectez-vous manuellement
3. Allez sur la page de consommation
4. Appuyez sur **F12** pour ouvrir les DevTools

### Ce qu'il faut adapter dans `scripts/mint_scraper.py`

| Élément | Où dans le code | Comment trouver la bonne valeur |
|---|---|---|
| **URL de login** | Variable `login_url` (~ligne 175) | Regardez l'URL dans la barre d'adresse |
| **Sélecteur champ email** | Liste `email_selectors` (~ligne 180) | Inspectez le champ email (clic droit > Inspecter) |
| **Sélecteur champ mot de passe** | Liste `password_selectors` (~ligne 188) | Idem pour le champ mot de passe |
| **Sélecteur bouton connexion** | Liste `submit_selectors` (~ligne 193) | Idem pour le bouton de connexion |
| **URL page consommation** | Variable `conso_url` dans `try_intercept_network()` (~ligne 83) | Naviguez manuellement vers la page de conso |
| **Filtre requêtes réseau** | Mots-clés dans `handle_response()` (~ligne 72) | Onglet Network des DevTools : filtrez XHR, cherchez les requêtes JSON |
| **Format JSON de l'API** | Parsing dans `handle_response()` (~ligne 78) | Cliquez sur la requête dans Network > onglet Response |
| **Sélecteur tableau HTML** | Variable `table_selector` dans `try_parse_html_table()` (~ligne 104) | Inspectez le tableau de consommation |
| **Colonnes du tableau** | Indices `cells[0]`, `cells[1]` (~ligne 117) | Comptez les colonnes du tableau |
| **Format de date** | Liste `fmt` dans les fonctions de parsing | Regardez le format affiché (JJ/MM/AAAA, etc.) |
| **Sélecteur export CSV** | Liste `export_selectors` dans `try_download_csv()` (~ligne 145) | Cherchez un bouton "Exporter" ou "Télécharger" |
| **Colonnes du CSV** | Parsing dans `try_download_csv()` (~ligne 170) | Ouvrez le CSV téléchargé manuellement |

### Astuce : mode debug

Mettez `MINT_HEADLESS=false` dans `config/.env` pour voir le navigateur. Le script prend aussi des captures d'écran en cas d'erreur dans `data/debug_*.png`.

---

## Automatisation (Planificateur de tâches Windows)

Une fois le script fonctionnel en mode manuel, automatisez-le pour qu'il se lance tous les jours.

### Étape 1 : Créer un fichier batch de lancement

Créez un fichier `run_scraper.bat` à la racine du projet avec ce contenu :

```bat
@echo off
cd /d C:\Users\NicolasBERGER\MintEnergie
call .venv\Scripts\activate.bat
python scripts\mint_scraper.py
```

### Étape 2 : Ouvrir le Planificateur de tâches

1. Appuyez sur **Win + R**, tapez `taskschd.msc`, puis **Entrée**
2. Ou cherchez **"Planificateur de tâches"** dans le menu Démarrer

### Étape 3 : Créer une nouvelle tâche

1. Dans le panneau de droite, cliquez sur **"Créer une tâche..."** (pas "tâche de base")

2. **Onglet Général** :
   - **Nom** : `MintEnergie - Scraping consommation`
   - **Description** : `Récupère les données de consommation depuis Mint-Énergie`
   - Cochez **"Exécuter même si l'utilisateur n'est pas connecté"** (optionnel, nécessite de saisir votre mot de passe Windows)
   - Cochez **"Exécuter avec les autorisations les plus élevées"**

3. **Onglet Déclencheurs** — cliquez sur **"Nouveau..."** :
   - **Lancer la tâche** : `Selon une planification`
   - **Paramètres** : `Chaque jour`
   - **Démarrer** : choisissez l'heure, par ex. **02:00:00** (2h du matin)
   - Cochez **"Activé"**
   - Cliquez sur **OK**

4. **Onglet Actions** — cliquez sur **"Nouveau..."** :
   - **Action** : `Démarrer un programme`
   - **Programme/script** : `C:\Users\NicolasBERGER\MintEnergie\run_scraper.bat`
   - **Commencer dans** : `C:\Users\NicolasBERGER\MintEnergie`
   - Cliquez sur **OK**

5. **Onglet Conditions** :
   - Décochez **"Ne démarrer la tâche que si l'ordinateur est sur secteur"** (si vous avez un portable)
   - Cochez **"Réveiller l'ordinateur pour exécuter cette tâche"** (optionnel)

6. **Onglet Paramètres** :
   - Cochez **"Autoriser l'exécution de la tâche à la demande"** (pour pouvoir la lancer manuellement)
   - Cochez **"Si la tâche échoue, redémarrer toutes les"** : `1 heure`, **pendant** : `3 heures`
   - Cliquez sur **OK**

7. Si demandé, entrez votre **mot de passe Windows** et validez.

### Étape 4 : Tester la tâche

1. Dans le Planificateur, trouvez votre tâche dans la **Bibliothèque du Planificateur**
2. Clic droit → **"Exécuter"**
3. Vérifiez que les fichiers `data/conso_raw.json` et `data/conso_processed.json` sont créés/mis à jour
4. Consultez `data/scraper.log` pour les détails

---

## Visualiser le tableau de bord

### Méthode recommandée : serveur local Python

Le fichier `web/index.html` utilise `fetch()` pour charger les données JSON. Les navigateurs bloquent `fetch()` sur les fichiers locaux (`file://`) pour des raisons de sécurité. Il faut donc utiliser un mini-serveur local.

**Lancez cette commande depuis la racine du projet :**

```powershell
cd C:\Users\NicolasBERGER\MintEnergie
python -m http.server 8080
```

**Puis ouvrez votre navigateur à l'adresse :**

```
http://localhost:8080/web/index.html
```

> Laissez le terminal ouvert tant que vous voulez voir le tableau de bord. Fermez-le avec Ctrl+C.

### Astuce : raccourci sur le Bureau

Créez un fichier `dashboard.bat` à la racine du projet :

```bat
@echo off
cd /d C:\Users\NicolasBERGER\MintEnergie
start http://localhost:8080/web/index.html
python -m http.server 8080
```

Double-cliquez dessus pour lancer le serveur ET ouvrir le navigateur automatiquement.

---

## Logique des mois comptables (12→11)

Mint-Énergie facture du **12 du mois** au **11 du mois suivant**.

La règle appliquée dans `scripts/process_data.py` :

| Jour du mois | Mois comptable |
|---|---|
| **≥ 12** | Mois courant |
| **< 12** | Mois précédent |

**Exemples** :

| Date | Jour | Mois comptable |
|---|---|---|
| 2025-01-15 | 15 ≥ 12 | Janvier 2025 |
| 2025-02-05 | 5 < 12  | Janvier 2025 |
| 2025-02-20 | 20 ≥ 12 | Février 2025 |
| 2025-12-31 | 31 ≥ 12 | Décembre 2025 |
| 2026-01-08 | 8 < 12  | Décembre 2025 |

---

## Dépannage

### Le scraper ne trouve pas les champs de login

- Mettez `MINT_HEADLESS=false` dans `config/.env`
- Relancez le script et observez le navigateur
- Inspectez la page avec F12 et adaptez les sélecteurs dans `mint_scraper.py`
- Regardez les captures d'écran dans `data/debug_*.png`

### Aucune donnée récupérée

- Consultez le fichier `data/scraper.log`
- Lancez le script en mode non-headless
- Vérifiez l'onglet **Network** des DevTools pour identifier les requêtes XHR
- Adaptez les filtres/sélecteurs dans le script

### Le tableau de bord affiche une erreur

- Vérifiez que `data/conso_processed.json` existe et est valide (ouvrez-le dans un éditeur)
- Assurez-vous d'ouvrir le HTML via `http://localhost:8080` et non en double-cliquant le fichier
- Ouvrez la console du navigateur (F12 > Console) pour voir les erreurs JavaScript

### La tâche planifiée ne se lance pas

- Vérifiez que le chemin dans `run_scraper.bat` est correct
- Testez le `.bat` en double-cliquant dessus
- Dans le Planificateur, vérifiez l'historique de la tâche (clic droit > Propriétés > Historique)
- Assurez-vous que Python est dans le PATH ou utilisez le chemin complet vers `python.exe`

### Console qui se ferme immédiatement

Ajoutez `pause` à la fin de `run_scraper.bat` pour garder la fenêtre ouverte en cas d'erreur :

```bat
@echo off
cd /d C:\Users\NicolasBERGER\MintEnergie
call .venv\Scripts\activate.bat
python scripts\mint_scraper.py
pause
```

---

## Avertissement légal

**L'automatisation de la connexion à un site web peut être contraire à ses conditions d'utilisation.** Avant d'utiliser ce projet :

1. Consultez les CGU de Mint-Énergie
2. Ce script est fourni **à titre éducatif et pour un usage strictement personnel**
3. N'utilisez pas ce script de manière abusive (multiples connexions par jour, etc.)
4. Les données récupérées sont **vos propres données de consommation**
5. L'auteur de ce projet décline toute responsabilité en cas de violation des CGU
