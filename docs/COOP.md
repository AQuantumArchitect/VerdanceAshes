# Playing together (co-op)

One player per hero, one company. Everyone commands the whole company; each player is one of its heroes, and that hero is theirs (mission-critical, marked "You" on their sidebar). The campaign lives on the host's PC: the host picks the sorties, and the others join them.

## What each PC needs

- Beyond All Reason, started at least once, so its engine and game are installed and up to date. Both PCs need the same BAR version: let the BAR launcher update on both.
- Verdance's Ashes, with `SETUP.bat` run once.
- A way for the friend's PC to reach the host's: the same network, a VPN such as Tailscale, or the host's router forwarding port **8452** (UDP for the game, TCP for the sortie files). The first time the host plays co-op, Windows may ask whether to let Python and the game through its firewall: allow private networks.

## Host

1. `PLAY.bat` as usual. In **The company**, under **Players**, give a friend one of the company's heroes ("Add a player as"). Player 1 is always you.
2. The Players list shows this PC's addresses. Send one to your friend (the LAN one on the same network, the VPN one otherwise).
3. Pick the sortie. While it runs, the launcher hands the sortie out to joining players. The drop waits, paused, until everyone is in, and the sidebar says who it is waiting for. To start without someone, type `/luarules va_go` in the game's chat.

## Friend

1. `JOIN.bat`, then type the host's address (or `JOIN.bat 192.168.0.17`).
2. It waits for the host's sortie to load, downloads it, gets the map, and starts the game as the next free player. `JOIN.bat 192.168.0.17 --player 3` (or the hero's id) picks a seat.
3. Run it again for each sortie: every sortie is generated fresh on the host.

## How it works

- `verdance.company.players`: `company.players` gives each further player a hero; the mission carries `players` when there are several.
- The start script seats one engine player per hero on the company's team and listens on 8452 (`scripts/install_playable_slice.ps1`).
- `include/va_players.lua` matches engine players to heroes by name; `include/campaign/unsynced.lua` holds the start pause on the host while anyone is missing.
- `verdance_kernel.coop`: the host's read-only sortie server (`/coop/sortie.json`, `/coop/sortie.zip`, nothing else) and the join (wait for the host, fetch, install, map, connect, try again if it missed the host's game starting: Recoil gives a joining client 30 seconds to reach a server that is up).
- The trial rig plays it on one PC: `tools/autopilot_campaign_v1.py --players vane` joins a headless client per further player through the same join.
