import asyncio
import discord
from discord.ext import commands
from config import TOKEN, PREFIX

# Opus manuell laden (nötig auf macOS)
if not discord.opus.is_loaded():
    try:
        discord.opus.load_opus("/opt/homebrew/lib/libopus.dylib")
        print("Opus geladen.")
    except Exception as e:
        print(f"Opus konnte nicht geladen werden: {e}")

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
