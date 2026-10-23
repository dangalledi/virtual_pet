# Virtual Pet: Animated Penguin 🐧

![Penguin](/images/penguin_idle_01.png)

A **virtual desktop pet** built with Python and PyQt5. An animated penguin lives on your screen, reacts to your workday, and integrates with **Woffu** to track your hours.

## Features

- **Sprite Animation** — smooth animations with multiple frames: idle, walk, jump, attack, slide
- **Mouse Drag** — drag the penguin anywhere on the screen
- **Hide** — double-click the penguin to hide it in the top bar (next to the clock) for 30 min (`HIDE_MINUTES`). Click the tray icon to bring it back; any alert brings it back too
- **Jokes** — triple-click or right-click → "Cuéntame un chiste"
- **Context Menu** — right-click to see current Woffu hours status
- **Auto-move** — the penguin moves on its own every minute
- **Woffu Integration**
  - Monitors worked hours in the background
  - 🎉 Celebrates with a jump + bubble when you complete your daily hours
  - 🚽 Alerts you N minutes before lunch so you have time to go to the bathroom first
  - 🕒 Clock in/out from the right-click menu (asks for confirmation)
  - ⏰ Reminders if you haven't clocked in by 10:00 or are still clocked in at 18:30
  - ☀️ Summer intensive schedule (6h 30min, 21-Jun → 15-Sep), or turn it on for today from the menu
  - 🏖️ Who from the team is absent today (Woffu iCal)
- **Meeting reminders (SOGo calendar)**
  - 📅 See today's meetings from the menu
  - 🔔 Get a bubble N minutes before each meeting — turn it on/off from the menu (remembered in `settings.json`)
  - Without VPN it uses the last copy of today's calendar
- **Rocket.Chat direct messages and mentions** — a blue speech bubble with who wrote and what (DMs, and `@you` / `@all` / `@here` in channels); click it to open the chat. Turn on/off from the menu
- **Automatic Rocket.Chat status** — in a meeting → *No molestar*; penguin hidden or clocked out → *Ausente*; otherwise *Disponible*. If you set another status by hand (or you're invisible/offline) it leaves it alone. Change it by hand from the menu too
- **Daily summary** — on weekdays, the first time you're at the computer: clock-in time, estimated leave time, today's meetings and who's absent. Also in the menu
- **Break reminders** — after 90 min of continuous use (keyboard/mouse, via GNOME's idle monitor) it reminds you to take a break. Not during meetings; 5 min idle counts as a break
- **2FA code** — right-click → "Copiar código 2FA" (also in the tray icon menu) copies the TOTP code to the clipboard, like the `my2fa` alias. If it expires in < 5 s it waits for the next one; when it expires it is cleared from the clipboard
- **Alert queue** — if several alerts arrive at once they wait in line: close one (click it) and the next appears
- **Speech bubbles** — comic-style bubble with a tail pointing at the penguin; click a bubble to close it
- **VPN check** — checks the `ppp0` interface and that internal machines answer over SSH
- **Keyboard Controls**

| Key | Action |
|-----|--------|
| `→` | Walk right |
| `←` | Walk left |
| `↑` | Jump |
| `↓` | Slide (bounces around the screen) |
| `A` | Attack |

## Code layout

| File | What it does |
|------|--------------|
| `main.py` | Starts the app |
| `penguin.py` | The penguin: animations, mouse/keyboard, right-click menu, bubbles, tray |
| `globo.py` | Comic-style speech bubble |
| `asistente.py` | Background thread, once a minute: VPN, meetings, Woffu, daily summary, breaks |
| `woffu.py` | Woffu client: login, clock-ins, hours, clock in/out |
| `calendario.py` | SOGo meetings (CalDAV) and team absences (Woffu iCal) |
| `rocketchat.py` | Rocket.Chat client and DM/mention watcher |
| `estado_rc.py` | Automatic Rocket.Chat status rules |
| `vpn.py` | VPN check (interface + internal hosts over SSH) |
| `dosfa.py` | 2FA (TOTP) code with `oathtool` |
| `utils.py` | `.env`, logging, saved settings, idle time |

## Requirements

- Python 3.6+
- PyQt5 >= 5.15.0
- requests >= 2.28.0
- python-dotenv >= 1.0.0
- icalendar >= 5.0

## Installation

1. **Clone the repository**

2. **Create and activate a virtual environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure your environment** — create a `.env` file in the project root:
   ```env
   # Woffu
   WOFFU_URL=https://bsc.woffu.com
   WOFFU_EMAIL=your_email@company.com
   WOFFU_PASSWORD=your_password
   WOFFU_HOURS=7

   # Lunch reminder
   LUNCH_TIME=13:00
   LUNCH_REMINDER_MINUTES=10
   ```

5. **Run**
   ```bash
   python3 main.py
   ```

## Woffu Integration

The penguin polls Woffu every minute in a background thread:

- **Daily hours completed** → penguin jumps and shows a bubble: `🎉 ¡7h completadas!`
- **Lunch reminder** → penguin attacks and shows a bubble: `🚽 En 10 min son las 13:00 — ¡ve al baño!`
- **Current status** → right-click the penguin to see live hours (and estimated leave time) in the context menu
- **Clock-in reminders** → `⏰ Son las 10:00 y no has fichado la entrada.`

Both the lunch time and reminder offset are configurable via `.env`. See `.env.example` for all options
(intensive schedule, reminder times, absences iCal, SOGo calendar).

## License

This project is licensed under the [GPL-3.0](LICENSE) license.
