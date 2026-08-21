# Anleitung (Deutsch)

Ein **Lern- und Analysewerkzeug** für Memecoin-Strategien mit **simuliertem
Geld**. Es handelt **nicht** mit echtem Geld.

> ⚠️ **Keine Anlageberatung. Keine Prognosen. Nur Papierhandel.**
> Live-Handel ist **gesperrt** (`execution/live.py` wirft `LiveTradingNotEnabled`).
> Memecoins sind **extrem riskant**: die meisten gehen gegen null, Rugpulls sind
> häufig, die Liquidität ist dünn und die Slippage hoch. Ein positives
> Kurzzeit-Ergebnis im Papierhandel ist fast immer **Rauschen**, kein Vorteil.

## 1. Installation

Python 3.10+ installieren. Dann im Ordner `memecoin-bot`:

```bash
pip install -r requirements.txt
```

Windows: einfach `START.bat` doppelklicken und Menüpunkt **[1]** wählen.

## 2. Selbsttest

```bash
python cli.py doctor
python cli.py doctor --data     # prüft zusätzlich einen echten Datenabruf
```

`doctor` prüft Abhängigkeiten, Konfiguration, Strategien, die Backtest-Engine und
dass der **Live-Handel gesperrt** ist.

## 3. Konfiguration

Alles steht in [`config/config.yaml`](config/config.yaml). Wichtig:

- `mode: paper` (bleibt paper — `live` wird abgelehnt).
- `data.require_real: true` (niemals falsche Daten).
- `data.universe`: die Memecoins, die deine Börse listet (z. B. `DOGE/USDT`).
- `engine.cost_multiplier: 2.0`: **pessimistischer** Standard (Gebühren+Slippage
  verdoppelt) als Robustheitscheck.
- `engine.min_stop_frac`: zu enge Stops werden **abgelehnt**, nicht aufgeweitet.
- Risiko: `risk_per_trade: 0.01`, Tagesverlust-Breaker `0.03`, Kill-Switch `0.25`.

Optional Auto-Discovery der Top-Memecoins: `data.auto_discovery.enabled: true`.

## 4. Analysieren

```bash
python cli.py backtest --strategy supertrend --symbol DOGE/USDT
python cli.py rank --db --limit 40            # bewertet & rankt auf echten Daten
python cli.py rank --all-strategies --db      # alle 15 Strategien
python cli.py export-active --min-score 55    # schreibt active_combos.yaml
```

Der Score ist eine **beschreibende** Kennzahl der Vergangenheit (Ampel + Warnungen),
**keine Prognose**.

## 5. Papierhandel (Dauerbetrieb)

```bash
python cli.py serve            # tickt fortlaufend, Ctrl-C zum Stoppen
python cli.py status           # Status/Equity/Positionen
python cli.py control --stop   # sicheres Anhalten über die control-Tabelle
python cli.py control --run
python cli.py control --reset-breaker   # Tages-Breaker manuell zurücksetzen
```

Bei Absturz/Neustart wird der Zustand (Kapital + Positionen) automatisch aus der
SQLite-DB wiederhergestellt. Ein ausgelöster Tagesverlust-Breaker **beendet den
Prozess nicht** (Safe-Hold: keine neuen Orders, tickt weiter, Auto-Reset am neuen
UTC-Tag).

## 6. Dashboard

```bash
streamlit run dashboard/app.py
```

Zeigt PAPER-Banner, Memecoin-Risiko-Banner, Kill-Switch, Kapitalkurve,
Kerzenchart mit Kauf/Verkauf-Markern, Ranking, Detail, Portfolio, Heatmap,
Audit-Log. Im Cloud-Nur-Lese-Modus (`CLOUD_READONLY=1`) sind Steuerknöpfe aus.

## 7. Tests

```bash
pytest -q
```

Jeder Bugfix hat einen Regressionstest. Am Ende ist `pytest -q` grün.

## 8. Gratis-Cloud

Siehe [`DEPLOY_GRATIS.md`](DEPLOY_GRATIS.md): GitHub Actions (Cron) hält den
Papierstand aktuell; Streamlit Community Cloud zeigt einen öffentlichen
Nur-Lese-Blick.

## Ehrliche Einordnung

Dieses Werkzeug **quantifiziert Risiko** und **beschreibt vergangenes simuliertes
Verhalten**. Es gibt **keinen „garantiert profitabel"-Schalter** — den gibt es
nicht. Die meisten Memecoins gehen gegen null.
