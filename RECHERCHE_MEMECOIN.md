# Recherche: profitable Trader, Rug-Filter, Wallet-Tracking, Axiom/MockApe

Zusammenfassung meiner Web-Recherche (Stand August 2026), mit Quellen und einer
**ehrlichen** Einordnung. Diese Recherche steuert die Rug-Filter (`data/memecoin_filters.py`)
und das neutrale Signal-Modul (`data/signals.py`). Quellenqualität: **A** = offizielle
Doku/API · **B** = etablierte Sekundärquelle/Branche · **C** = Erfahrungs-/Community-Wissen.

## 1. Die harte Realität (zuerst, weil am wichtigsten)

- Die **meisten** Memecoin-Trader verlieren Geld — nicht weil der Markt „unmöglich" ist,
  sondern weil dieselben Fehler wiederholt werden, bis das Konto leer ist.
- Auf Solana zeigten **bis zu ~98 %** neuer Token Warnzeichen für Pump-and-Dump oder Rug;
  2025 gingen branchenweit über **2,8 Mrd. USD** durch Rugs verloren.
- „Bis ein Coin auf Twitter/X trendet, bist du meist **zu spät**." Deshalb ist der
  „welcher Coin explodiert"-Wunsch keine seriös lösbare Prognose — nur **Aufmerksamkeit**
  lässt sich messen, kein zukünftiger Kurs.
- Wer profitabel wird, ist nicht „schlauer", sondern **systematischer**: jeden Fehler
  loggen, wöchentlich auswerten, feste Regeln bauen. Genannt werden strikte Stops
  (z. B. „raus bei −50 %, keine Ausnahme"), Timing (früh vor dem Hype), und Kapital
  (unter ~1 000 USD ist es sehr schwer). Quelle C — survivorship-biased, mit Vorsicht.

> Konsequenz im Tool: keine Prognosen. „Attention" ist ausdrücklich **kein** Kursversprechen.
> Die Rug-Filter sind ein **Risiko**-Filter, keine Gewinn-Garantie.

## 2. Rug-/Scam-Erkennung — die Filter, die ich eingebaut habe

On-chain-Red-Flags (in `apply_filters` umgesetzt, sofern die Daten vorliegen):

- **Mint-Authority noch aktiv** → Besitzer kann beliebig nachdrucken und dumpen.
- **Freeze-Authority aktiv** → Besitzer kann deine Wallet einfrieren (nicht verkaufbar).
- **LP nicht gelockt/verbrannt** → Entwickler kann Liquidität abziehen (klassischer Rug).
- **Honeypot** (nicht verkaufbar) → fatal, harter Ausschluss.
- **Holder-Konzentration**: größter Holder / Top-10 / Insider-Bündel zu hoch.
- **Dünne Liquidität / totes Volumen / wenige eindeutige Käufer** → Wash-Trading-Verdacht.
- **Sehr frische Domain/Launch** (Tage) → hohes Rug-Risiko.
- **Aggregierter RugCheck-Risk-Score** über Schwelle.

Datenquellen (best-effort, graceful degradation):

- **RugCheck** — Solanas führender Token-Risiko-Scanner, öffentliche REST-API
  (`api.rugcheck.xyz`, Swagger; Endpunkte u. a. `/v1/tokens/{mint}/report`,
  `/wallet/{address}/risk`). Qualität **A**.
- **GoPlus Security** — Token-Security-API (Solana), ergänzt Autoritäten/Honeypot. **A**.
- **DexScreener** — öffentliche API (kein Key) für Liquidität, Volumen, Txns, Social-Links,
  Boosts, `token-boosts/latest`. Qualität **A**.
- Community-Checklisten (mint/pause/blacklist-Funktionen, Dev-Verkäufe, Buy/Sell-Ratio,
  kopierte Whitepaper, Bubblemaps/Solscan-Prüfung). Qualität **B/C**.

## 3. Wallet-Tracking (profitable Trader „verfolgen")

- **GMGN** — bester **kostenloser** Einstieg: Live-Leaderboards („Rank"), „Radar" zeigt
  früheste/größte/profitabelste Käufer eines Tokens; Telegram-Alerts, Copy-Trading. **B**.
- **Cielo** — gute „Monitoring-Schicht" für eigene Wallet-Listen, Multi-Chain-Alerts (~59 $/M). **B**.
- **Nansen** — umfassendste, gelabelte Smart-Money-Daten, aber teuer (150 $+/M). **B**.
- **Axiom** — YC-gestützter Solana-Terminal: vereint Token-Discovery, Ausführung,
  **Wallet-Tracking und X/Twitter-Sentiment** in einem Dashboard. **A/B**.

> Wie „profitable Trader gestartet sind" ist überwiegend **survivorship bias**: sichtbar
> sind fast nur Gewinner; frühe Käufer sind oft Insider/Snipers. Nachbauen ist nicht
> zuverlässig reproduzierbar. Das Tool verlinkt diese Dienste zur **eigenen Prüfung**,
> statt „Gewinner-Rezepte" zu versprechen.

## 4. Axiom & MockApe — was ehrlich geht

- **Axiom** ist ein **echter Live-Handels**-Terminal (nicht-kustodiale Wallets via Turnkey,
  Hyperliquid-Perps). Es gibt inoffizielle SDKs (Python `AxiomTradeAPI-py`, Rust
  `axiomtrade-rs`) für **echte** Orders. Dieser Bot handelt **nicht** live (gesperrt), also
  wird nichts zu Axiom geroutet. Was geht: **denselben Token auf Axiom beobachten**
  (Link `axiom.trade/t/<mint>`) — Kurs, Wallet-Aktivität, X-Sentiment.
- **MockApe** ist selbst ein **Paper-Trading**-Tool (Browser-Extension), das sich direkt in
  **Axiom, Padre und GMGN** einklinkt und dort mit virtuellem Geld auf Echtzeitdaten üben
  lässt. Das ist der **realitätsnächste** Weg zum Üben ohne echtes Risiko — und passt exakt
  zur Paper-only-Philosophie dieses Bots. Empfehlung: MockApe auf Axiom nutzen, um die
  Paper-Entscheidungen des Bots manuell nachzuvollziehen.

## 5. Quellenliste

- Rug-Erkennung: DEXTools „How to Spot a Rug Pull (2026)"; AMBCrypto „5 on-chain signs";
  Elliptic „automatically detects rug pulls"; ScamWatch „Rug Pull Anatomy 2025";
  Dipprofit „Honeypot scam guide". (B)
- RugCheck-API: `api.rugcheck.xyz/swagger`; Qodex „Rugcheck API Guide"; Solana Compass. (A/B)
- GoPlus: `api.gopluslabs.io` Solana token_security. (A)
- DexScreener-API: offizielle öffentliche Endpunkte; uwuu.ai „Endpoints & Limits (2026)". (A/B)
- Wallet-Tracking: GMGN-Blog „Track/Copy Solana Smart Money"; Nansen „track Solana wallets";
  Madeonsol „Nansen vs GMGN vs Cielo". (B)
- Axiom: QuickNode Builders-Guide; `AxiomTradeAPI-py` (chipadevteam); `axiomtrade-rs`
  (GitHub vibheksoni); axiompro.app Wallet-Tracking. (A/B)
- MockApe: mockape.com / Chrome Web Store „Paper Trade SOL & BNB Meme Coins". (A)
- Trader-Realität: Solana-Trading.com „Become a Better Memecoin Trader"; Coinmonks/Medium
  „Reality of Trading Memecoin 2025"; diverse YouTube-Titel („Why 90% lose", „Realistic
  Results with $200"). (C — mit Vorsicht, survivorship bias)

**Transparenz:** Diese Quellen wurden im August 2026 gesichtet; APIs/Feldnamen können sich
ändern (die Fetcher parsen defensiv und liefern bei Fehlern `None`, ohne zu erfinden).
Konkrete Erfolgsquoten von Tradern werden **nicht** als exakte Zahl behauptet — sie sind
nicht seriös belegbar. Die belastbare Aussage bleibt: **die große Mehrheit verliert, die
meisten Token gehen gegen null.**
