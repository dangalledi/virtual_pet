# Pingu: your desktop work assistant 🐧

![Penguin](/images/penguin_idle_01.png)

An animated penguin that lives on your screen (Python + PyQt5) and keeps an eye on your workday:
Woffu hours, meetings, Rocket.Chat messages, VPN and breaks. It talks to you with comic-style speech bubbles.

## In short

**What Pingu does**

- ⏱ **Woffu** — worked hours and estimated leave time, clock in/out from the menu, reminders if you forgot to clock in or out, 🎉 when you complete your hours, summer intensive schedule, who's absent today
- 📅 **Meetings** — bubble 10 min before each meeting in your SOGo calendar, and today's list in the menu
- 💬 **Rocket.Chat** — bubble with direct messages and mentions (click it to open the chat); optional automatic status (meeting → *No molestar*, away → *Ausente*)
- 🔌 **VPN** — warns you when the VPN drops and opens a terminal to reconnect it with one click
- ☀️ **Daily summary** — each workday morning: clock-in, leave time, meetings and absences
- 🧘 **Breaks** — reminds you to stand up after 90 min of continuous use
- 🔐 **2FA** — copies your TOTP code to the clipboard (like the `my2fa` alias)
- 🙈 **Hide** — double-click and it hides next to the clock for 30 min

**How to set it up**

1. Install: `./install.sh` (creates `.venv`, installs dependencies, asks for your Woffu details and offers autostart)
2. Edit `.env` (use `.env.example` as a template) and fill in only what you use — every block is optional:

   | To get… | Fill in |
   |---|---|
   | Woffu hours, clock in/out, reminders | `WOFFU_EMAIL`, `WOFFU_PASSWORD` |
   | Who's absent today | `WOFFU_ICAL_URL` |
   | Meeting reminders | `SOGO_USER`, `SOGO_PASSWORD`, `SOGO_CALENDAR_URL` |
   | Rocket.Chat messages and status | `ROCKET_CHAT_URL`, `ROCKET_CHAT_APP_ID`, `ROCKET_CHAT_APP_SECRET` |
   | "Connect VPN" button | `VPN_CONNECT_CMD` |
   | 2FA code | an `oathtool` secret file (default `~/.ssh/.2fa_secret`) |

3. Run: `./run.sh` — then **right-click the penguin** to see everything it can do. Options you turn on/off in the menu are remembered.

## Using the penguin

| Action | What happens |
|---|---|
| Drag | Move the penguin |
| Double-click | Hide it in the top bar for 30 min (click the bar icon to bring it back) |
| Triple-click | Tells a joke |
| Right-click | Menu with everything below |
| Click a bubble | Closes it (and opens the chat / connects the VPN / copies the code, if the bubble says so) |
| `←` `→` `↑` `↓` `A` | Walk, jump, slide, attack |

**Right-click menu**

- Woffu status line · 📋 Daily summary · ⏱ Hours today · 🕒 Clock in/out · ☀️ Intensive schedule today · 🏖️ Who's absent today
- 📅 Today's meetings · 🔔 Meeting reminders *(on/off)*
- 💬 Message and mention alerts *(on/off)* · 🤖 Automatic Rocket.Chat status *(on/off, off by default)* · 🟢 Change Rocket.Chat status
- 🔐 Copy 2FA code · 🧘 Break reminders *(on/off)* · 🔌 Connect VPN · 📶 Check VPN · 😂 Joke · 🙈 Hide · Close

The top-bar icon (when hidden) has *Come back now*, *Copy 2FA code* and *Close*.

## Features in detail

### Woffu
- Checks your clock-ins every minute; the menu shows hours worked, time left and estimated leave time
- 🎉 Jumps when you complete your hours (7h, or 6h 30min in the summer intensive schedule, 21-Jun → 15-Sep; outside those dates turn it on for today from the menu)
- ⏰ Reminders on weekdays if you haven't clocked in by 10:00, or you're still clocked in at 18:30
- 🚽 Warns you 10 min before lunch; after clocking out it offers a 30-min "you can come back" reminder
- Clocking in/out from the menu always asks for confirmation

### Meetings (SOGo calendar)
- Bubble 10 min before each meeting with the title, time and room (recurring meetings included)
- The calendar is only reachable through the VPN: without it, Pingu uses the last copy of today's calendar

### Rocket.Chat
- **Messages and mentions**: direct messages, and `@you` / `@all` / `@here` in channels. Several at once are grouped in one bubble. Nothing is marked as read
- **Automatic status** (off by default): in a meeting → 🔴 *No molestar*; penguin hidden or clocked out → 🟡 *Ausente*; otherwise 🟢 *Disponible*. If you set another status by hand (or you're invisible) it leaves it alone until you're *Disponible* again

### VPN
- Two checks: the tunnel interface (`ppp0`) is up, and internal machines answer over SSH (no login). It's only considered down when all of them fail
- When it drops, the red bubble says *click here to connect it*: it opens a terminal running `VPN_CONNECT_CMD`, where you type your passwords as usual. **Closing that terminal disconnects the VPN**

### Daily summary, breaks and alerts
- **Daily summary**: weekdays, the first time you're at the computer between 07:00 and 15:00 (once a day)
- **Breaks**: after 90 min using keyboard/mouse without a 5-min pause (uses GNOME's idle monitor). Not during meetings or after clocking out
- **Alert queue**: important alerts stay until you click them; if several arrive at once they wait in line
- **2FA**: if the code expires in less than 5 s it waits for the next one, and clears it from the clipboard when it expires

## Configuration

All settings live in `.env` (see `.env.example`). Besides the credentials above:

| Variable | Default | What it does |
|---|---|---|
| `WOFFU_HOURS` / `WOFFU_HOURS_INTENSIVA` | `7` / `6.5` | Daily hours, normal / intensive |
| `LUNCH_TIME`, `LUNCH_REMINDER_MINUTES` | `13:00`, `10` | Lunch time and how early to warn |
| `RECORDATORIO_ENTRADA`, `RECORDATORIO_SALIDA`, `RECORDATORIO_SALIDA_FIN` | `10:00`, `18:30`, `21:00` | Clock-in / clock-out reminder times |
| `REUNION_AVISO_MIN` | `10` | Minutes before a meeting to warn |
| `RESUMEN_DESDE`, `RESUMEN_HASTA` | `07:00`, `15:00` | Time window for the daily summary |
| `PAUSA_CADA_MIN`, `PAUSA_IDLE_MIN` | `90`, `5` | Break reminder interval / idle minutes that count as a break |
| `VPN_INTERFACE`, `VPN_CHECK_HOSTS` | `ppp0`, two BSC hosts | How the VPN is checked |
| `VPN_CONNECT_CMD` | *(empty)* | Command to connect the VPN (empty = no "Connect VPN") |
| `TOTP_SECRET_FILE` | `~/.ssh/.2fa_secret` | 2FA secret file |
| `PENGUIN_SIZE` | `100` | Penguin size in pixels |
| `HIDE_MINUTES` | `30` | Minutes it stays hidden after a double-click |

Menu on/off choices are saved in `settings.json`. `.env`, `settings.json` and logs are git-ignored.

## Autostart

`install.sh` offers it, or create `~/.config/autostart/virtual-pet.desktop` with
`Exec=/path/to/virtual_pet/run.sh --autostart`. When started that way, the log goes to `pingu.log`.
Only one penguin can run at a time: launching a second one just exits.

## Requirements

- Linux with GNOME (tested on Ubuntu 22.04). The top-bar icon needs the *AppIndicator* extension (enabled by default on Ubuntu)
- Python 3.8+ and the packages in `requirements.txt` (PyQt5, requests, python-dotenv, icalendar)
- Optional: `oathtool` (2FA), `openfortivpn` (VPN), `gnome-terminal`

Manual install instead of `install.sh`:
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # and fill it in
./run.sh
```

## Code layout

| File | What it does |
|------|--------------|
| `main.py` | Starts the app (one instance only) |
| `penguin.py` | The penguin: animations, mouse/keyboard, right-click menu, bubbles, alert queue, tray |
| `globo.py` | Comic-style speech bubble |
| `asistente.py` | Background thread, once a minute: VPN, meetings, Woffu, daily summary, breaks |
| `woffu.py` | Woffu client: login, clock-ins, hours, clock in/out |
| `calendario.py` | SOGo meetings (CalDAV) and team absences (Woffu iCal) |
| `rocketchat.py` | Rocket.Chat client and message/mention watcher |
| `estado_rc.py` | Automatic Rocket.Chat status rules |
| `vpn.py` | VPN check and "Connect VPN" terminal |
| `dosfa.py` | 2FA (TOTP) code with `oathtool` |
| `utils.py` | `.env`, logging, saved settings, idle time |

## License

This project is licensed under the [GPL-3.0](LICENSE) license.
