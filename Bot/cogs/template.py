from discord.ext import commands
from discord.ext.commands import Context
import typing

if typing.TYPE_CHECKING:
    from bot import BotDiscord # Zakładamy, że bot.py jest w głównym katalogu

# Tutaj nazywamy kapsułę i tworzymy nową klasę dla niej.
class Szablon(commands.Cog, name="szablon"):
    """📝 Szablonowa kapsuła dla nowych funkcjonalności Kronik Elary."""
    COG_EMOJI = "📝" # Dodajemy emoji dla tego coga

    def __init__(self, bot: 'BotDiscord') -> None:
        self.bot = bot

    # Tutaj możesz po prostu dodać własne komendy, zawsze musisz podać "self" jako pierwszy parametr.

    @commands.hybrid_command(
        name="testowakomenda", 
        description="To jest testowa komenda, która nic nie robi.", 
    )
    async def testowakomenda(self, context: Context) -> None:
        """
        To jest testowa komenda, która nic nie robi.
        Służy jako przykład i punkt wyjścia do tworzenia nowych komend.

        :param context: Kontekst komendy hybrydowej.
        """
        # Tutaj wykonaj swoje działania
        await context.send(f"Witaj, {context.author.mention}! To jest testowa komenda z kapsuły '{self.qualified_name}'.", ephemeral=True)
        # Nie zapomnij usunąć "pass", jeśli dodajesz logikę.
        # pass


# A następnie ostatecznie dodajemy kapsułę do bota, aby mógł ją załadować, odładować, przeładować i używać jej zawartości.
async def setup(bot: 'BotDiscord') -> None:
    await bot.add_cog(Szablon(bot))
