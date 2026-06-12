ctabot simulator — Windows quick start
======================================

WHAT THIS IS
  A paper-trading simulator for a systematic futures strategy
  (trend-following across stock indices, bonds, metals, energy, ags).
  It trades PAPER MONEY only. No real orders are sent anywhere, ever.

RUN IT
  1) Double-click ctabot-simulator.exe
  2) A console window opens and fetches ~3 years of market data from
     Yahoo Finance (needs internet, first load takes ~30-60 seconds)
  3) Your browser opens the dashboard at http://127.0.0.1:8765
  4) It immediately invests the $10,000,000 paper account according to
     the strategy's current signals and tracks profit/loss from that
     moment on, marking prices about once a minute.

  Leave it running (or close and reopen later: the account is saved in
  ctabot_sim_state.json next to the exe and resumes where it left off).

OTHER MODES
  ctabot-simulator.exe live 50000000     larger paper account ($50M)
  ctabot-simulator.exe replay            replay 1982-2024 history
                                         (copy the repo's data folder
                                         next to the exe first)

GOOD TO KNOW
  - Quotes are delayed ~10-20 minutes (Yahoo). Futures trade almost
    24h on weekdays; nothing moves on weekends.
  - Live mode runs the trend sleeve only (no futures-curve data on
    Yahoo, so the carry signal is off), and continuous quotes jump a
    few times a year when contracts roll - small noise in live marks.
  - Windows SmartScreen may warn about an unsigned exe: that is
    expected for a freshly built PyInstaller binary. "More info" ->
    "Run anyway", or build it yourself from source with build_exe.bat.
  - This is research software, not investment advice.
