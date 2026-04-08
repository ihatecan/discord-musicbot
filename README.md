# Discord Musikbot

Ein Discord-Bot der Musik von YouTube abspielt.

## Features

- YouTube-Songs per Name oder URL abspielen
- YouTube-Playlists laden
- Warteschlange mit mehreren Songs
- Pause, Skip, Lautstärke und mehr

## Voraussetzungen

- **Windows:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) installieren (inkl. WSL2-Backend — Docker Desktop fragt beim ersten Start automatisch danach)
- **Mac/Linux:** [Docker](https://www.docker.com/get-started) installieren
- Ein Discord Bot Token ([Anleitung](#bot-token-erstellen))

## Installation

```bash
git clone https://github.com/ihatecan/discord-musicbot.git
cd DEIN_REPO
cp .env.example .env
```

Dann `.env` öffnen und den Token eintragen:

```
DISCORD_TOKEN=dein_token_hier
```

Bot starten:

```bash
docker compose up -d
```

Logs anzeigen:

```bash
docker compose logs -f
```

Bot stoppen:

```bash
docker compose down
```

## Bot Token erstellen

1. Geh zu [discord.com/developers/applications](https://discord.com/developers/applications)
2. **New Application** → Name eingeben → Create
3. Links auf **Bot** → **Reset Token** → Token kopieren
4. Runterscrollen → **Message Content Intent** aktivieren → Save

**Bot einladen:**
1. Links auf **OAuth2** → **URL Generator**
2. Scopes: `bot` ankreuzen
3. Permissions: `Connect`, `Speak`, `Send Messages`, `Read Message History`, `View Channels`
4. Generierte URL im Browser öffnen → Server auswählen → Autorisieren

## Befehle

| Befehl | Alias | Beschreibung |
|--------|-------|--------------|
| `!play <name/URL>` | `!p` | Song abspielen oder auf YouTube suchen |
| `!playlist <URL>` | `!pl` | YouTube-Playlist in die Warteschlange laden |
| `!skip` | `!s` | Aktuellen Song überspringen |
| `!pause` | — | Wiedergabe pausieren |
| `!resume` | `!r` | Wiedergabe fortsetzen |
| `!stop` | — | Stoppen und Warteschlange leeren |
| `!queue` | `!q` | Warteschlange anzeigen |
| `!nowplaying` | `!np` | Aktuellen Song anzeigen |
| `!volume <0-100>` | `!vol` | Lautstärke einstellen |
| `!remove <nr>` | — | Song aus der Warteschlange entfernen |
| `!clear` | — | Warteschlange leeren |
| `!leave` | `!dc` | Bot vom Sprachkanal trennen |
