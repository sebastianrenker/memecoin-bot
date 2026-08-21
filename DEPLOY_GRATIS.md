# Gratis-Cloud-Deploy (kostenlos, öffentlich, nur-lesend)

Ziel: Der Papier-Bot tickt regelmäßig in der Cloud (kostenlos) und ist als
**öffentlicher, nur-lesender** Blick sichtbar. Alles bleibt **simuliert**.

Zwei kostenlose Bausteine:

1. **GitHub Actions** (Cron) führt alle ~30 Minuten `python cli.py ci-tick` aus
   und committet den Zustand (`cloud/paper.db`, `BOT_STATUS_REPORT.md`) zurück.
2. **Streamlit Community Cloud** hostet `dashboard/app.py` als öffentliche
   Nur-Lese-Ansicht (`CLOUD_READONLY=1`, `TRADING_DB=cloud/paper.db`).

## Schritt 1 — Öffentliches Repo

```bash
git init
git add .
git commit -m "memecoin paper bot"
# neues, ÖFFENTLICHES GitHub-Repo anlegen und pushen:
git remote add origin https://github.com/<user>/<repo>.git
git branch -M main
git push -u origin main
```

Optional vorab aktive Kombinationen festlegen:

```bash
python cli.py export-active --min-score 55   # erzeugt active_combos.yaml
git add active_combos.yaml && git commit -m "active combos" && git push
```

## Schritt 2 — GitHub Actions

Die Workflow-Datei liegt bereits unter
[`.github/workflows/paper-tick.yml`](.github/workflows/paper-tick.yml):

- Cron `*/30 * * * *` (GitHub kann unter Last verzögern).
- Installiert die **schlanke** `requirements-ci.txt` (kein Streamlit).
- Setzt `TRADING_DB=cloud/paper.db`, führt `ci-tick` aus, committet den Zustand.
- Braucht `permissions: contents: write` (ist gesetzt).

Aktivieren: Im Repo unter **Actions** den Workflow erlauben. Manuell testen über
**Run workflow** (workflow_dispatch). Nach dem ersten Lauf existiert
`cloud/paper.db`.

> Hinweis: Der Bot committet zurück ins Repo. Das ist für ein privates Lernprojekt
> in Ordnung. Wenn dich die vielen Commits stören, nutze einen eigenen Branch
> oder ein separates State-Repo.

## Schritt 3 — Streamlit Community Cloud

1. Auf <https://share.streamlit.io> mit GitHub anmelden.
2. Neues App-Deployment: Repo wählen, Datei `dashboard/app.py`.
3. Unter **Advanced settings → Environment variables** setzen:
   - `CLOUD_READONLY = 1`
   - `TRADING_DB = cloud/paper.db`
4. Deploy. Die App zeigt den zuletzt committeten Papierstand (nur lesend, ohne
   Steuerknöpfe).

Die Streamlit-App liest dieselbe `cloud/paper.db`, die GitHub Actions aktualisiert.
Da Community Cloud den Repo-Stand zieht, aktualisiert sich die Ansicht mit jedem
neuen Commit des Workflows (ggf. App neu laden).

## Grenzen (ehrlich)

- GitHub-Cron ist **nicht** sekundengenau; Ticks kommen „ungefähr" alle 30 Min.
- Kostenlose Ressourcen sind begrenzt; das ist ein Lern-Setup, kein HFT.
- Es bleibt **simuliert**. Kein echter Handel, keine Prognose, keine Beratung.
