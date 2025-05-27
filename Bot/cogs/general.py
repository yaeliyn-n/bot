import discord
from discord.ext import commands
from discord.ext.commands import Context
from datetime import datetime, UTC
import typing
import os

# Import konfiguracji
import config

if typing.TYPE_CHECKING:
    from bot import BotDiscord  # Zakładamy, że bot.py jest w głównym katalogu

class General(commands.Cog, name="general"):
    """⚙️ Ogólne komendy użytkowe dla Kronik Elary, pomocne w codziennym odkrywaniu serwera."""
    def __init__(self, bot: 'BotDiscord'):
        self.bot = bot

    async def _create_general_embed(self, context: Context, title: str, description: str = "", color: discord.Color = config.KOLOR_OGOLNY_DOMYSLNY) -> discord.Embed:
        """Pomocnicza funkcja do tworzenia embedów ogólnych dla tej kapsuły."""
        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.now(UTC))
        if self.bot.user and self.bot.user.avatar:
             embed.set_author(name=f"{self.bot.user.display_name} - Ogólne", icon_url=self.bot.user.avatar.url)
        else:
            embed.set_author(name="Ogólne Komendy Kronik")
        
        if context.guild and context.guild.icon:
            embed.set_footer(text=f"Serwer: {context.guild.name} | Kroniki Elary", icon_url=context.guild.icon.url)
        else:
            embed.set_footer(text="Kroniki Elary")
        return embed

    @commands.hybrid_command(
        name="ping",
        description="Sprawdza opóźnienie bota i jego gotowość do tkania opowieści.",
    )
    async def ping(self, context: Context) -> None:
        """
        Wysyła magiczne echo do serwerów Discord, aby sprawdzić, jak szybko odpowiadam.
        Pokazuje aktualne opóźnienie (latency) bota w milisekundach.
        Im niższa wartość, tym szybciej mogę reagować na Twoje zaklęcia (komendy)!
        """
        opoznienie_ms = round(self.bot.latency * 1000)
        
        kolor_ping = config.KOLOR_OGOLNY_SUKCES_NISKI_PING
        if opoznienie_ms > 500:
            kolor_ping = config.KOLOR_OGOLNY_BLAD_WYSOKI_PING
        elif opoznienie_ms > 200:
            kolor_ping = config.KOLOR_OGOLNY_OSTRZEZENIE_SREDNI_PING

        embed = await self._create_general_embed(
            context,
            title="🏓 Magiczne Echo Powraca!",
            description=f"Moje połączenie z Krainą Discorda jest stabilne!\n"
                        f"Czas odpowiedzi echa: **{opoznienie_ms}ms**.\n\n"
                        f"Jestem gotów tkać kolejne opowieści w Kronikach Elary!",
            color=kolor_ping
        )
        if self.bot.user and self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            
        await context.send(embed=embed)

    @commands.hybrid_command(
        name="zapros",
        aliases=["invite", "dodajbota", "dodajelarę"],
        description="Wyświetla magiczny portal (link) do zaproszenia Elary na Twój serwer.",
    )
    async def zapros(self, context: Context) -> None:
        """
        Chcesz, aby Elara i jej Kroniki zagościły również w Twoich stronach?
        Ta komenda wyświetli Ci magiczny zwój z portalem (linkiem zaproszeniowym),
        który pozwoli Ci zaprosić mnie na Twój własny serwer Discord!
        """
        invite_link = getattr(self.bot, 'link_zaproszenia', None) or os.getenv("INVITE_LINK")

        if not invite_link:
            opis = ("Niestety, Tkacz Przeznaczeń nie udostępnił mi jeszcze magicznego portalu "
                    "(linku zaproszeniowego), bym mogła odwiedzić inne krainy. "
                    "Skontaktuj się z nim, aby to naprawić!")
            kolor = config.KOLOR_BOT_BLAD 
            view = None
        else:
            opis = (f"Pragniesz, abym i ja, Elara, zagościła w Twoich opowieściach i wniosła magię Kronik do Twojej społeczności?\n\n"
                    f"Oto zwój z zaklęciem przywołania (linkiem zaproszeniowym):\n"
                    f"✨ [**Otwórz Portal do Kronik Elary na Swoim Serwerze!**]({invite_link}) ✨\n\n"
                    f"Pamiętaj, że aby w pełni dzielić się magią, będę potrzebowała odpowiednich pozwoleń (uprawnień) w Twojej krainie (serwerze).")
            kolor = config.KOLOR_OGOLNY_INFO_GENERAL
            view = discord.ui.View()
            view.add_item(discord.ui.Button(label="Zaproś Elarę do Swoich Kronik!", url=invite_link, emoji="🔗", style=discord.ButtonStyle.link))
        
        embed = await self._create_general_embed(context, title="🌌 Rozszerz Kroniki Elary o Nowe Światy!", description=opis, color=kolor)
        if self.bot.user and self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        
        await context.send(embed=embed, view=view)


async def setup(bot: 'BotDiscord'):
    await bot.add_cog(General(bot))
