import asyncio
import discord
from discord.ext import commands
from config import TOKEN, PREFIX

# Opus laden - macOS (Homebrew) braucht manuellen Pfad, Linux findet es automatisch
if not discord.opus.is_loaded():
    opus_paths = [
        "/opt/homebrew/lib/libopus.dylib",  # macOS ARM (Apple Silicon)
        "/usr/local/lib/libopus.dylib",     # macOS Intel
        "libopus.so.0",                     # Linux (Docker)
    ]
    for path in opus_paths:
        try:
            discord.opus.load_opus(path)
            print(f"Opus geladen: {path}")
            break
        except Exception:
            continue
    else:
        print("Opus nicht manuell geladen (wird evtl. automatisch gefunden)")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=commands.DefaultHelpCommand())


@bot.event
async def on_ready():
    print(f"Bot eingeloggt als {bot.user} ({bot.user.id})")
    print(f"Präfix: {PREFIX}")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening,
        name=f"{PREFIX}play",
    ))


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Fehlende Angabe: `{error.param.name}`. Nutze `{PREFIX}help {ctx.command}` für Hilfe.")
    elif isinstance(error, commands.CommandNotFound):
        pass
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"Ungültiges Argument. Nutze `{PREFIX}help {ctx.command}` für Hilfe.")
    else:
        print(f"Unbehandelter Fehler: {error}")
        raise error


async def main():
    async with bot:
        await bot.load_extension("cogs.music")
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
