import asyncio
import re
import discord
from discord.ext import commands
import yt_dlp
from config import FFMPEG_OPTIONS, YDL_OPTIONS, YDL_PLAYLIST_OPTIONS

YOUTUBE_PLAYLIST_RE = re.compile(
    r"(https?://)?(www\.)?(youtube\.com/playlist\?|youtube\.com/watch\?.*[&?]list=|youtu\.be/.*[?&]list=)"
)


def is_playlist_url(query: str) -> bool:
    return bool(YOUTUBE_PLAYLIST_RE.match(query))


class Song:
    def __init__(self, source_url: str, title: str, webpage_url: str, duration: int, requester: discord.Member):
        self.source_url = source_url
        self.title = title
        self.webpage_url = webpage_url
        self.duration = duration
        self.requester = requester

    @classmethod
    async def from_query(cls, query: str, requester: discord.Member) -> "Song":
        loop = asyncio.get_event_loop()

        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            data = await loop.run_in_executor(
                None, lambda: ydl.extract_info(query, download=False)
            )

        if "entries" in data:
            data = data["entries"][0]

        return cls(
            source_url=data["url"],
            title=data.get("title", "Unbekannt"),
            webpage_url=data.get("webpage_url", data.get("url", "")),
            duration=data.get("duration", 0),
            requester=requester,
        )

    @classmethod
    async def from_entry(cls, entry: dict, requester: discord.Member) -> "Song":
        """Löst einen flachen Playlist-Eintrag zu einem vollständigen Song auf."""
        loop = asyncio.get_event_loop()

        url = entry.get("url") or entry.get("webpage_url") or entry.get("id")
        if not url:
            raise ValueError("Kein URL im Playlist-Eintrag gefunden")

        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            data = await loop.run_in_executor(
                None, lambda: ydl.extract_info(url, download=False)
            )

        if "entries" in data:
            data = data["entries"][0]

        return cls(
            source_url=data["url"],
            title=data.get("title", entry.get("title", "Unbekannt")),
            webpage_url=data.get("webpage_url", url),
            duration=data.get("duration", entry.get("duration", 0)),
            requester=requester,
        )

    def format_duration(self) -> str:
        if not self.duration:
            return "?"
        minutes, seconds = divmod(self.duration, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"


class GuildMusicState:
    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue()
        self.current: Song | None = None
        self.voice_client: discord.VoiceClient | None = None
        self.volume: float = 0.5

    def is_playing(self) -> bool:
        return self.voice_client is not None and self.voice_client.is_playing()

    def skip(self):
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()

    async def cleanup(self):
        self.queue = asyncio.Queue()
        if self.voice_client:
            await self.voice_client.disconnect()
            self.voice_client = None


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.states: dict[int, GuildMusicState] = {}

    def get_state(self, guild_id: int) -> GuildMusicState:
        if guild_id not in self.states:
            self.states[guild_id] = GuildMusicState()
        return self.states[guild_id]

    async def ensure_voice(self, ctx: commands.Context) -> bool:
        if not ctx.author.voice:
            await ctx.send("Du musst in einem Sprachkanal sein!")
            return False
        return True

    async def connect_if_needed(self, ctx: commands.Context) -> bool:
        state = self.get_state(ctx.guild.id)
        if not state.voice_client or not state.voice_client.is_connected():
            state.voice_client = await ctx.author.voice.channel.connect()
            self.bot.loop.create_task(self.player_loop(ctx))
        return True

    async def player_loop(self, ctx: commands.Context):
        state = self.get_state(ctx.guild.id)

        while True:
            try:
                song = await asyncio.wait_for(state.queue.get(), timeout=300)
            except asyncio.TimeoutError:
                await ctx.send("Keine weiteren Songs in der Warteschlange. Trenne Verbindung.")
                await state.cleanup()
                return

            state.current = song
            print(f"[DEBUG] Song geladen: {song.title}")
            print(f"[DEBUG] Source URL: {song.source_url[:80]}...")

            if not state.voice_client:
                await ctx.send("Fehler: Keine Verbindung zum Sprachkanal.")
                state.current = None
                continue

            # Warten bis Voice-Verbindung wirklich bereit ist
            for _ in range(20):
                if state.voice_client.is_connected():
                    break
                await asyncio.sleep(0.5)
            else:
                await ctx.send("Timeout: Voice-Verbindung nicht bereit.")
                state.current = None
                continue

            print(f"[DEBUG] Voice bereit: {state.voice_client.is_connected()}, starte FFmpeg...")

            try:
                source = discord.PCMVolumeTransformer(
                    discord.FFmpegPCMAudio(song.source_url, **FFMPEG_OPTIONS),
                    volume=state.volume,
                )
            except Exception as e:
                print(f"[DEBUG] FFmpeg Fehler: {e}")
                await ctx.send(f"FFmpeg Fehler: {e}")
                state.current = None
                continue

            finished = asyncio.Event()

            def after_play(error):
                if error:
                    print(f"[DEBUG] Player-Fehler: {error}")
                    self.bot.loop.create_task(ctx.send(f"Fehler bei der Wiedergabe: {error}"))
                else:
                    print("[DEBUG] Song fertig gespielt.")
                finished.set()

            state.voice_client.play(source, after=after_play)
            print("[DEBUG] voice_client.play() aufgerufen")

            embed = discord.Embed(
                title="Spielt jetzt",
                description=f"[{song.title}]({song.webpage_url})",
                color=discord.Color.green(),
            )
            embed.add_field(name="Dauer", value=song.format_duration())
            embed.add_field(name="Angefragt von", value=song.requester.mention)
            await ctx.send(embed=embed)

            await finished.wait()
            state.current = None

    @commands.command(name="play", aliases=["p"], help="Spielt einen Song, YouTube-URL oder sucht auf YouTube")
    async def play(self, ctx: commands.Context, *, query: str):
        if not await self.ensure_voice(ctx):
            return

        if is_playlist_url(query):
            await self._load_playlist(ctx, query)
            return

        await self.connect_if_needed(ctx)
        state = self.get_state(ctx.guild.id)

        async with ctx.typing():
            try:
                song = await Song.from_query(query, ctx.author)
            except Exception as e:
                await ctx.send(f"Fehler beim Laden des Songs: {e}")
                return

        await state.queue.put(song)
        if state.is_playing() or state.current:
            embed = discord.Embed(
                title="Zur Warteschlange hinzugefügt",
                description=f"[{song.title}]({song.webpage_url})",
                color=discord.Color.blue(),
            )
            embed.add_field(name="Position", value=state.queue.qsize())
            await ctx.send(embed=embed)

    @commands.command(name="playlist", aliases=["pl"], help="Lädt eine YouTube-Playlist in die Warteschlange")
    async def playlist_cmd(self, ctx: commands.Context, *, url: str):
        if not await self.ensure_voice(ctx):
            return
        await self._load_playlist(ctx, url)

    async def _load_playlist(self, ctx: commands.Context, url: str):
        await self.connect_if_needed(ctx)
        state = self.get_state(ctx.guild.id)

        async with ctx.typing():
            loop = asyncio.get_event_loop()
            try:
                with yt_dlp.YoutubeDL(YDL_PLAYLIST_OPTIONS) as ydl:
                    data = await loop.run_in_executor(
                        None, lambda: ydl.extract_info(url, download=False)
                    )
            except Exception as e:
                await ctx.send(f"Fehler beim Laden der Playlist: {e}")
                return

        entries = data.get("entries", [])
        if not entries:
            await ctx.send("Keine Songs in der Playlist gefunden.")
            return

        playlist_title = data.get("title", "Unbekannte Playlist")
        playlist_url = data.get("webpage_url", url)

        embed = discord.Embed(
            title="Playlist wird geladen",
            description=f"[{playlist_title}]({playlist_url})",
            color=discord.Color.orange(),
        )
        embed.add_field(name="Songs", value=str(len(entries)))
        embed.set_footer(text="Songs werden nach und nach zur Warteschlange hinzugefügt...")
        await ctx.send(embed=embed)

        # Songs werden im Hintergrund aufgelöst und zur Queue hinzugefügt
        self.bot.loop.create_task(
            self._enqueue_playlist_entries(ctx, state, entries, playlist_title)
        )

    async def _enqueue_playlist_entries(
        self,
        ctx: commands.Context,
        state: GuildMusicState,
        entries: list,
        playlist_title: str,
    ):
        added = 0
        failed = 0
        for entry in entries:
            try:
                song = await Song.from_entry(entry, ctx.author)
                await state.queue.put(song)
                added += 1
            except Exception as e:
                print(f"Playlist-Eintrag übersprungen ({entry.get('title', '?')}): {e}")
                failed += 1

        msg = f"**{playlist_title}**: {added} Songs zur Warteschlange hinzugefügt."
        if failed:
            msg += f" ({failed} konnten nicht geladen werden)"
        await ctx.send(msg)

    @commands.command(name="skip", aliases=["s"], help="Überspringt den aktuellen Song")
    async def skip(self, ctx: commands.Context):
        state = self.get_state(ctx.guild.id)
        if not state.is_playing():
            await ctx.send("Es wird gerade nichts gespielt.")
            return
        state.skip()
        await ctx.message.add_reaction("⏭️")

    @commands.command(name="pause", help="Pausiert die Wiedergabe")
    async def pause(self, ctx: commands.Context):
        state = self.get_state(ctx.guild.id)
        if state.voice_client and state.voice_client.is_playing():
            state.voice_client.pause()
            await ctx.message.add_reaction("⏸️")
        else:
            await ctx.send("Es wird gerade nichts gespielt.")

    @commands.command(name="resume", aliases=["r"], help="Setzt die Wiedergabe fort")
    async def resume(self, ctx: commands.Context):
        state = self.get_state(ctx.guild.id)
        if state.voice_client and state.voice_client.is_paused():
            state.voice_client.resume()
            await ctx.message.add_reaction("▶️")
        else:
            await ctx.send("Die Wiedergabe ist nicht pausiert.")

    @commands.command(name="stop", help="Stoppt die Wiedergabe und leert die Warteschlange")
    async def stop(self, ctx: commands.Context):
        state = self.get_state(ctx.guild.id)
        await state.cleanup()
        del self.states[ctx.guild.id]
        await ctx.message.add_reaction("⏹️")

    @commands.command(name="queue", aliases=["q"], help="Zeigt die Warteschlange")
    async def queue(self, ctx: commands.Context):
        state = self.get_state(ctx.guild.id)

        if not state.current and state.queue.empty():
            await ctx.send("Die Warteschlange ist leer.")
            return

        embed = discord.Embed(title="Warteschlange", color=discord.Color.purple())

        if state.current:
            embed.add_field(
                name="Spielt jetzt",
                value=f"[{state.current.title}]({state.current.webpage_url}) `{state.current.format_duration()}` — {state.current.requester.mention}",
                inline=False,
            )

        upcoming = list(state.queue._queue)
        if upcoming:
            lines = []
            for i, song in enumerate(upcoming[:10], 1):
                lines.append(f"`{i}.` [{song.title}]({song.webpage_url}) `{song.format_duration()}`")
            if len(upcoming) > 10:
                lines.append(f"... und {len(upcoming) - 10} weitere Songs")
            embed.add_field(name="Als nächstes", value="\n".join(lines), inline=False)

        await ctx.send(embed=embed)

    @commands.command(name="nowplaying", aliases=["np"], help="Zeigt den aktuellen Song")
    async def nowplaying(self, ctx: commands.Context):
        state = self.get_state(ctx.guild.id)
        if not state.current:
            await ctx.send("Es wird gerade nichts gespielt.")
            return

        song = state.current
        embed = discord.Embed(
            title="Spielt jetzt",
            description=f"[{song.title}]({song.webpage_url})",
            color=discord.Color.green(),
        )
        embed.add_field(name="Dauer", value=song.format_duration())
        embed.add_field(name="Angefragt von", value=song.requester.mention)
        await ctx.send(embed=embed)

    @commands.command(name="volume", aliases=["vol"], help="Lautstärke einstellen (0-100)")
    async def volume(self, ctx: commands.Context, vol: int):
        state = self.get_state(ctx.guild.id)
        if not 0 <= vol <= 100:
            await ctx.send("Lautstärke muss zwischen 0 und 100 liegen.")
            return
        state.volume = vol / 100
        if state.voice_client and state.voice_client.source:
            state.voice_client.source.volume = state.volume
        await ctx.send(f"Lautstärke auf **{vol}%** gesetzt.")

    @commands.command(name="leave", aliases=["dc", "disconnect"], help="Bot vom Sprachkanal trennen")
    async def leave(self, ctx: commands.Context):
        state = self.get_state(ctx.guild.id)
        await state.cleanup()
        if ctx.guild.id in self.states:
            del self.states[ctx.guild.id]
        await ctx.message.add_reaction("👋")

    @commands.command(name="remove", help="Song aus der Warteschlange entfernen (Position angeben)")
    async def remove(self, ctx: commands.Context, index: int):
        state = self.get_state(ctx.guild.id)
        items = list(state.queue._queue)
        if not 1 <= index <= len(items):
            await ctx.send(f"Ungültige Position. Warteschlange hat {len(items)} Songs.")
            return
        removed = items.pop(index - 1)
        state.queue = asyncio.Queue()
        for item in items:
            await state.queue.put(item)
        await ctx.send(f"**{removed.title}** aus der Warteschlange entfernt.")

    @commands.command(name="clear", help="Warteschlange leeren")
    async def clear(self, ctx: commands.Context):
        state = self.get_state(ctx.guild.id)
        state.queue = asyncio.Queue()
        await ctx.send("Warteschlange geleert.")
        await ctx.message.add_reaction("🗑️")


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
