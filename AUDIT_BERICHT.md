# Audit- und Recherche-Bericht

Dieser Bericht dokumentiert die Methodik, die bewussten Design-Entscheidungen und
die Quellenlage. Er ist bewusst **nüchtern**: Das Werkzeug quantifiziert Risiko
und beschreibt Vergangenes — es prognostiziert nichts.

## 1. Zweck und Grenzen

- **Zweck:** Lernen und Analyse von Handelsstrategien auf Memecoins mit
  **simuliertem** Geld, auf **echten** Marktdaten.
- **Ausdrücklich nicht:** Anlageberatung, Prognose, Gewinnversprechen, Live-Handel.
- **Kernrisiko Memecoins:** sehr hohe Ausfallrate (viele Token gehen effektiv
  gegen null), Rugpulls/Scams, dünne Liquidität, extreme Slippage, kurze/lückige
  Historie. Diese Eigenschaften sind breit dokumentiert (siehe Quellen) und im
  Werkzeug überall kommuniziert.

## 2. Methodik und Korrektheits-Entscheidungen

| Thema | Entscheidung | Warum |
|---|---|---|
| Look-ahead | Signal auf Bar *t* → Ausführung zum **Open t+1**; nur abgeschlossene Kerzen (`closed_bars`) | Vermeidet die häufigste Backtest-Selbsttäuschung |
| Stop vs. TP | **Stop vor** Take-Profit im selben Bar | Pessimistisch/konservativ |
| Kosten | Gebühren + Slippage **je Seite**; `cost_multiplier: 2.0` Standard | Memecoins sind teuer; Robustheitscheck |
| Positionsgröße | `risk_per_trade × Equity / Stop-Abstand`, Hebel gedeckelt, Einstiegsgebühr auf **gedeckelter** Menge | Realistische Risiko-/Notional-Rechnung |
| Zu enge Stops | **Ablehnen**, nicht aufweiten | Verhindert Stop-Loss-Loop bei ATR≈0 |
| Validierung | Walk-Forward (nur OOS werten) + Monte-Carlo (KI, Ruin-Wahrscheinlichkeit) + Regime | Overfitting sichtbar machen, Risiko quantifizieren |
| Overfitting-Wächter | Nur akzeptieren, wenn OOS-validiert **und** WF-Effizienz ≥ 0.5 **und** genug Trades | „In-Sample schön" reicht nicht |
| Mean-Reversion | Für Memecoins **niedriger gewichtet** und Konfidenz reduziert | Dips sind oft kein Rabatt, Trends laufen/kollabieren |
| Daten | `require_real: true`; Fehlabruf → **überspringen**, nie fälschen | Ehrlichkeit vor Vollständigkeit |

Der „Funktioniert-gerade"-Score = gewichtet(Edge, Robustheit, Regime, Recency)
× Konfidenzfaktor, mit Ampel und expliziten Warnungen. Der Score ist
**beschreibend**, nicht prädiktiv.

## 3. Sicherheits-Audit (intern)

- **Live-Handel gesperrt** (`execution/live.py`, Test `test_safety.py`).
- **Risikolimits** Pflicht und in `Settings.validate()` geprüft (Test deckt
  `mode: live`, `require_real: false`, zu hohes Risiko, `cost_multiplier < 1`,
  `min_stop_frac = 0` ab).
- **Circuit-Breaker** ist Safe-Hold (kein Prozess-Exit), Auto-Reset am neuen
  UTC-Tag; **Kill-Switch** nur manuell rücksetzbar (Regressionstests vorhanden).
- **Zustands-Wiederherstellung** und **Bar-Debounce** getestet.
- **`pytest -q` grün** (siehe Testordner; jeder Fix hat einen Regressionstest).

## 4. Quellen und Quellenqualität

Bewertung: **A** = offizielle/primäre Doku · **B** = etablierte Sekundärquelle ·
**C** = allgemeines Fach-/Erfahrungswissen (nicht einzeln zitiert).

| Thema | Quelle | Qualität | Anmerkung |
|---|---|---|---|
| Marktdaten (CEX OHLCV) | ccxt — offizielle Doku/Repo: <https://docs.ccxt.com>, <https://github.com/ccxt/ccxt> | A | Primäre Bibliotheks-Doku; im Projekt tatsächlich verwendet |
| On-chain OHLCV (DEX) | GeckoTerminal API: <https://www.geckoterminal.com/dex-api> | A | Öffentliche API; Pools-OHLCV-Endpunkt genutzt |
| Liquidität/Alter/Volumen | DexScreener API: <https://docs.dexscreener.com/api/reference> | A | Öffentliche API für Metadaten der Filter |
| Indikatoren (RSI, ATR/Wilder, ADX/DMI, MACD, Bollinger, Keltner, CCI, Stochastik, Williams %R, Supertrend, Donchian, ConnorsRSI) | Standard-Fachliteratur der technischen Analyse | C | Selbst implementiert in `core/indicators.py`; Formeln sind Allgemeingut |
| Walk-Forward-Analyse | R. Pardo, *The Evaluation and Optimization of Trading Strategies* | B | Standardreferenz für WF-Validierung |
| Monte-Carlo/Bootstrap für Trading-Risiko | Etablierte quantitative Praxis (Resampling der Trade-Verteilung) | C | Zur Risiko-/Ruin-Quantifizierung, nicht als Gewinnbeweis |
| Memecoin-Risiko (hohe Ausfallrate, Rugpulls, dünne Liquidität) | Öffentliche Marktbeobachtung/Branchenberichte | C | Breit belegte, qualitative Einordnung; keine Einzelzahl behauptet |

**Transparenz zur Quellenprüfung:** Die URLs oben verweisen auf die offiziellen
Anbieter-Dokumentationen (Qualität A), die dem tatsächlich implementierten Code
entsprechen. Sie wurden im Rahmen dieses Berichts **nicht live erneut abgerufen**;
API-Details können sich ändern. Konkrete Ausfall-Prozentsätze für Memecoins werden
**bewusst nicht** als exakte Zahl behauptet, da seriöse Werte je nach Definition
und Zeitraum stark schwanken — die qualitative Aussage „die meisten gehen gegen
null" ist gut belegt und ausreichend für die Risikokommunikation.

## 5. Nüchternes Fazit

Der Bot läuft mit **echten** Marktdaten (CEX via ccxt bestätigt). Der erste
`ci-tick` erzeugt `BOT_STATUS_REPORT.md` mit dem simulierten Kontostand und
offenen Positionen. Ein etwaiges positives Kurzzeit-Ergebnis ist **Rauschen**,
kein Beweis für einen Vorteil. Es gibt **keinen** „garantiert profitabel"-Schalter.
Memecoins bedeuten überwiegend Verlust bis Totalverlust — genau dafür sind die
Risikolimits, die pessimistischen Kosten und die Warnungen da.
