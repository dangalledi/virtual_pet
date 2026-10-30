# Pingu: your desktop work assistant 🐧

![Penguin](/images/penguin_idle_01.png)

An animated penguin that lives on your screen (Python + PyQt5) and keeps an eye on your workday:
Woffu hours, meetings, Rocket.Chat messages, VPN and breaks. It talks to you with comic-style speech bubbles.

## In short

**What Pingu does**

- ⏱ **Woffu** — worked hours and estimated leave time, clock in/out from the menu, reminders if you forgot to clock in or out, 🎉 when you complete your hours, summer intensive schedule, who's absent today / this week / next week
- 📅 **Meetings** — bubble 10 min before each meeting in your SOGo calendar, and today's list in the menu
- 💬 **Rocket.Chat** — bubble with direct messages and mentions (click it to bring your browser to the front — no new tabs); optional automatic status (meeting → *No molestar*, away → *Ausente*)
- 🔌 **VPN** — warns you when the VPN drops and opens a terminal to reconnect it with one click
- ☀️ **Daily summary** — each workday morning: clock-in, leave time, meetings and absences (the whole week on Mondays, next week on Fridays)
- 🧘 **Breaks** — reminds you to stand up after 45 min of continuous use
- 📝 **Notes and reminders** — "remind me in 15 min to…" and sticky notes, shown on screen as post-its
- 🔐 **2FA** — copies your TOTP code to the clipboard (like the `my2fa` alias)
- 🙈 **Hide** — double-click and it hides next to the clock for 30 min

**How to set it up**

1. Install: `./install.sh` (creates `.venv`, installs dependencies, asks for your Woffu details and offers autostart)
2. Edit `.env` (use `.env.example` as a template) and fill in only what you use — every block is optional:

   | To get… | Fill in |
   |---|---|
   | Your company (LDAP) username | `LDAP_USER` — wherever `{usuario}` appears (calendar URL, VPN command) it is replaced by this. Empty = your Linux username |
   | Woffu hours, clock in/out, reminders | `WOFFU_EMAIL`, `WOFFU_PASSWORD` (in double quotes if it has symbols like `#`, `$` or spaces) |
   | Team absences (today, this week, next week) | `WOFFU_ICAL_URL` |
   | Meeting reminders | `SOGO_PASSWORD`, `SOGO_CALENDAR_URL` (one or more calendars, comma-separated; yours is `https://calendar.empresa.com/SOGo/dav/{usuario}/Calendar/personal/`). The user is `LDAP_USER` (`SOGO_USER` only if it is different) |
   | Rocket.Chat messages and status | `ROCKET_CHAT_URL`, `ROCKET_CHAT_APP_ID`, `ROCKET_CHAT_APP_SECRET` |
   | "Connect VPN" button | `VPN_CONNECT_CMD` (e.g. `sudo openfortivpn gw.empresa.com:443 -u {usuario}`) |
   | 2FA code | `TOTP_SECRET_FILE` (a file with your base32 TOTP secret) + `oathtool` |

3. Run: `./run.sh` — then **right-click the penguin** to see everything it can do. Options you turn on/off in the menu are remembered.

## Using the penguin

| Action | What happens |
|---|---|
| Drag | Move the penguin |
| Double-click | Hide it in the top bar for 30 min (click the bar icon to bring it back) |
| Triple-click | Tells a joke (from its own collection, no repeats until it has told them all) |
| Right-click | Menu with everything below |
| Click a bubble | Closes it (and brings the browser to the front / connects the VPN / copies the code, if the bubble says so) |
| `←` `→` `↑` `↓` `A` | Walk, jump, slide, attack |

**Right-click menu**

- Woffu status line · 📋 Daily summary · ⏱ Hours today · 🕒 Clock in/out · ☀️ Intensive schedule today · 🏖️ Team absences ▸ today / this week / next week
- 📅 Today's meetings · 🔔 Meeting reminders *(on/off)*
- 💬 Message and mention alerts *(on/off)* · 🤖 Automatic Rocket.Chat status *(on/off, off by default)* · 🟢 Change Rocket.Chat status
- 🐾 Pet ▸ penguin / cat / chicken / duck
- 🔍 Size ▸ 100 % … 250 %
- 📝 Notes and reminders ▸ remind me… / new note… / your notes (view, remind me in…, done)
- 🔐 Copy 2FA code · 🧘 Break reminders *(on/off)* · 🔌 Connect VPN · 📶 Check VPN · 😂 Joke · 🙈 Hide · Close

When the penguin is hidden, the top-bar icon has the same menu (plus *Come back now*). Answers to menu options then appear as GNOME notifications and the penguin stays hidden; important alerts (meetings, messages, VPN…) still bring it back.

## Features in detail

### Woffu
- Checks your clock-ins every minute; the menu shows hours worked, time left and estimated leave time
- 🎉 Jumps when you complete your hours (7h, or 6h 30min in the summer intensive schedule, 21-Jun → 15-Sep; outside those dates turn it on for today from the menu)
- ⏰ Reminders on weekdays if you haven't clocked in by 10:00, or you're still clocked in at 18:30
- 🚽 Warns you 10 min before lunch; after clocking out it offers a 30-min "you can come back" reminder
- Clocking in/out from the menu always asks for confirmation
- 🏖️ Team absences for today, this week or next week, with the days each person is off (requests not yet approved are marked with `*`). On weekends, "this week" means the one starting on Monday

### Meetings (SOGo calendar)
- Bubble 10 min before each meeting with the title, time and room (recurring meetings included)
- **Several calendars**: put several URLs in `SOGO_CALENDAR_URL`, comma-separated (yours, your team's, shared ones…). Their meetings are merged (a meeting in two calendars shows once) and each one says which calendar it comes from
- The calendar is only reachable through the VPN: without it, Pingu uses the last copy of today's calendar

### Rocket.Chat
- **Messages and mentions**: direct messages, and `@you` / `@all` / `@here` in channels. Several at once are grouped in one bubble. Nothing is marked as read. Clicking the bubble brings to the front the browser window showing Rocket.Chat (or just the browser, if Rocket.Chat isn't the visible tab); it never opens a new tab. It recognises the Rocket.Chat tab because its title ends with the server's domain (e.g. `- chat.example.com`); if yours doesn't, set `ROCKET_CHAT_WINDOW_TITLE`
- **Automatic status** (off by default): in a meeting → 🔴 *No molestar*; penguin hidden or clocked out → 🟡 *Ausente*; otherwise 🟢 *Disponible*. If you set another status by hand (or you're invisible) it leaves it alone until you're *Disponible* again

### VPN
- It checks whether internal machines answer over SSH (no login); it's only considered down when all of them fail. The tunnel interface (`ppp0`) just tells *how* you're connected: without it but with the machines answering, you're on the office network and the VPN isn't needed (🏢 bubble instead of 🔴)
- When it drops, the red bubble says *click here to connect it*: it opens a terminal running `VPN_CONNECT_CMD`, where you type your passwords as usual. **Closing that terminal disconnects the VPN**

### Notes and reminders
- **⏰ Remind me…**: type what (e.g. *call Marta*) and when: in 5/15/30 min, 1/2 hours, or at a given time (if that time has passed, tomorrow). When it goes off it disappears
- **📝 New note…**: a sticky note that stays in the list until you mark it **✅ Done**. It can have a reminder too; after it goes off, the note stays
- Each note in the menu has its own submenu: view it, remind me in 15/30/60 min, remove the reminder, done
- **Post-its on screen**: every note shows as a little yellow window (orange if it has a reminder, with its time). They only show while Pingu has the focus (click the penguin to see them; click another window and they hide). Drag them anywhere and resize them from the bottom-right corner — they remember where and how big you left them. **Double-click** to edit, **right-click** to change the color, copy the text, set a reminder or reset the size. **📋** = copy the text, **✓** = done. When writing a note, Enter adds a new line and Ctrl+Enter saves. *Post-its always visible* in the submenu keeps them on screen all the time
- Saved in `notas.json`, so they survive restarts; reminders missed while Pingu was closed show up when it starts

### Pets
- **🐾 Pet** in the menu swaps the penguin for a **cat** (6 colours), a **chicken** (3 colours) or a **rubber duck**, from [vscode-pets](https://github.com/tonybaloney/vscode-pets). It changes on the spot and is remembered
- **🔍 Size** in the menu zooms everything at once (pet, bubbles, menus, post-its, dialogs) from 100 % to 250 % — handy on 2K/4K screens. Pingu restarts itself to apply it, and it is remembered (`zoom` in `settings.json`)
- The animations are read from the vscode-pets extension if you have it installed in VS Code. Without it, the chicken and duck are downloaded from the repo into `mascotas_cache/`; the cat needs the extension (the repo keeps its artwork encrypted because of its licence). `VSCODE_PETS_MEDIA` points to another `media/` folder
- Their drawings are not copied into this repo. Credits: cat by [seethingswarm](https://seethingswarm.itch.io/catset), rubber duck by [Marc Duiker](https://twitter.com/marcduiker), chicken from the [vscode-pets](https://github.com/tonybaloney/vscode-pets) project

### Daily summary, breaks and alerts
- **Daily summary**: weekdays, the first time you're at the computer between 07:00 and 15:00 (once a day). On Mondays it adds the week's absences, on Fridays next week's
- **Breaks**: after 45 min using keyboard/mouse without a 5-min pause (uses GNOME's idle monitor). Not during meetings or after clocking out
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
| `PAUSA_CADA_MIN`, `PAUSA_IDLE_MIN` | `45`, `5` | Break reminder interval / idle minutes that count as a break |
| `VPN_INTERFACE`, `VPN_CHECK_HOSTS` | `ppp0`, *(empty)* | How the VPN is checked: tunnel interface, and internal `host:port` machines answering SSH (empty = interface only, so Pingu can't tell you're at the office) |
| `VPN_CONNECT_CMD` | *(empty)* | Command to connect the VPN (empty = no "Connect VPN") |
| `TOTP_SECRET_FILE` | *(empty)* | 2FA secret file (empty = no 2FA option; it also hides if the file has no valid base32 secret or `oathtool` is missing — the reason goes to `pingu.log`) |
| `PENGUIN_SIZE` | `100` | Penguin size in pixels |
| `MASCOTA_SIZE` | 60 % of `PENGUIN_SIZE` | Height of the other pets (cat, chicken, duck) |
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
| `notas.py` | Notes and reminders: storage and the "new note" dialog |
| `mascotas.py` | Other pets (vscode-pets animations) |
| `postits.py` | On-screen post-its for the notes |
| `chistes.py` | The penguin's joke collection (no repeats until it has told them all) |
| `dosfa.py` | 2FA (TOTP) code with `oathtool` |
| `utils.py` | `.env`, logging, saved settings, idle time |

## License

This project is licensed under the [GPL-3.0](LICENSE) license.
