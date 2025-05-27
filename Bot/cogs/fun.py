import random
import aiohttp
import discord
from discord.ext import commands
from discord.ext.commands import Context
from discord import Interaction # Dodano import Interaction
import typing
from datetime import datetime, UTC # Dodano import UTC dla _create_fun_embed

# Import konfiguracji, jeśli potrzebne (np. dla kolorów embedów)
import config

if typing.TYPE_CHECKING:
    from bot import BotDiscord # Zakładamy, że bot.py jest w głównym katalogu


class WyborMonety(discord.ui.View):
    def __init__(self, original_author_id: int) -> None:
        super().__init__(timeout=60.0)
        self.value: typing.Optional[str] = None
        self.original_author_id = original_author_id
        self.message: typing.Optional[discord.Message] = None

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.original_author_id:
            await interaction.response.send_message("To nie Twój rzut monetą! Użyj własnej komendy.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Orzeł", style=discord.ButtonStyle.primary, emoji="🪙")
    async def orzel_button(self, interaction: Interaction, button: discord.ui.Button):
        self.value = "orzeł"
        self.stop()
        if self.message:
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
            await self.message.edit(view=self)


    @discord.ui.button(label="Reszka", style=discord.ButtonStyle.secondary, emoji="🪙")
    async def reszka_button(self, interaction: Interaction, button: discord.ui.Button):
        self.value = "reszka"
        self.stop()
        if self.message:
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
            await self.message.edit(view=self)

    async def on_timeout(self):
        if self.message:
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
            try:
                # Sprawdzamy czy interaction istnieje i czy odpowiedź nie została wysłana
                if self.message.interaction and not self.message.interaction.response.is_done():
                    await self.message.edit(content="Czas na wybór minął. Spróbuj ponownie!", view=self)
                elif not self.message.interaction: # Jeśli to zwykła wiadomość
                     await self.message.edit(content="Czas na wybór minął. Spróbuj ponownie!", view=self)

            except discord.NotFound:
                pass
            except AttributeError: # message.interaction może nie istnieć
                try:
                    await self.message.edit(content="Czas na wybór minął. Spróbuj ponownie!", view=self)
                except discord.NotFound:
                    pass
        self.stop()


class PapierKamienNozyceSelect(discord.ui.Select['PapierKamienNozyceView']):
    def __init__(self) -> None:
        opcje = [
            discord.SelectOption(label="Nożyce", description="Wybierasz nożyce.", emoji="✂️"),
            discord.SelectOption(label="Kamień", description="Wybierasz kamień.", emoji="🪨"),
            discord.SelectOption(label="Papier", description="Wybierasz papier.", emoji="🧻"),
        ]
        super().__init__(
            placeholder="Wybierz swój ruch...",
            min_values=1,
            max_values=1,
            options=opcje,
        )

    async def callback(self, interaction: Interaction) -> None:
        assert self.view is not None
        view: PapierKamienNozyceView = self.view # type: ignore

        if interaction.user.id != view.original_author_id:
            await interaction.response.send_message("To nie Twoja gra! Użyj własnej komendy.", ephemeral=True)
            return

        wybory_gracza = {"kamień": 0, "papier": 1, "nożyce": 2}
        wybor_uzytkownika = self.values[0].lower()
        indeks_wyboru_uzytkownika = wybory_gracza[wybor_uzytkownika]

        wybor_bota = random.choice(list(wybory_gracza.keys()))
        indeks_wyboru_bota = wybory_gracza[wybor_bota]

        embed_wyniku = await view.cog._create_fun_embed(
            interaction, # Przekazujemy interaction jako context
            title="⚔️ Pojedynek Papier-Kamień-Nożyce!"
        )
        embed_wyniku.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url if interaction.user.display_avatar else None)

        zwyciezca = (3 + indeks_wyboru_uzytkownika - indeks_wyboru_bota) % 3
        if zwyciezca == 0:
            embed_wyniku.description = f"**Remis!**\nTy wybrałeś/aś **{wybor_uzytkownika.capitalize()}**, a ja wybrałem/am **{wybor_bota.capitalize()}**."
            embed_wyniku.colour = config.KOLOR_BOT_OSTRZEZENIE
        elif zwyciezca == 1:
            embed_wyniku.description = f"**Wygrałeś/aś!** 🎉\nTy wybrałeś/aś **{wybor_uzytkownika.capitalize()}**, a ja wybrałem/am **{wybor_bota.capitalize()}**."
            embed_wyniku.colour = config.KOLOR_BOT_SUKCES
        else:
            embed_wyniku.description = f"**Przegrałeś/aś!** 😢\nTy wybrałeś/aś **{wybor_uzytkownika.capitalize()}**, a ja wybrałem/am **{wybor_bota.capitalize()}**."
            embed_wyniku.colour = config.KOLOR_BOT_BLAD

        self.disabled = True
        await interaction.response.edit_message(embed=embed_wyniku, view=view)
        view.stop()


class PapierKamienNozyceView(discord.ui.View):
    def __init__(self, cog: 'Rozrywka', original_author_id: int) -> None:
        super().__init__(timeout=60.0)
        self.cog = cog
        self.original_author_id = original_author_id
        self.message: typing.Optional[discord.Message] = None
        self.add_item(PapierKamienNozyceSelect())

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.original_author_id:
            await interaction.response.send_message("To nie Twoja gra! Użyj własnej komendy.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.message:
            for item in self.children:
                if isinstance(item, discord.ui.Select):
                    item.disabled = True
            try:
                if self.message.interaction and not self.message.interaction.response.is_done():
                     await self.message.edit(content="Czas na wybór w grze Papier-Kamień-Nożyce minął. Spróbuj ponownie!", view=self)
                elif not self.message.interaction:
                     await self.message.edit(content="Czas na wybór w grze Papier-Kamień-Nożyce minął. Spróbuj ponownie!", view=self)
            except discord.NotFound:
                pass
            except AttributeError:
                try:
                    await self.message.edit(content="Czas na wybór w grze Papier-Kamień-Nożyce minął. Spróbuj ponownie!", view=self)
                except discord.NotFound:
                    pass
        self.stop()


class Rozrywka(commands.Cog, name="rozrywka"):
    """🎮 Kapsuła z zabawnymi komendami dla odprężenia w Kronikach Elary."""
    COG_EMOJI = "🎮"

    def __init__(self, bot: 'BotDiscord') -> None:
        self.bot = bot

    async def _create_fun_embed(self, context: typing.Union[Context, Interaction], title: str, description: str = "", color: discord.Color = config.KOLOR_OGOLNY_DOMYSLNY) -> discord.Embed:
        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.now(UTC))
        if self.bot.user and self.bot.user.avatar:
             embed.set_author(name=f"{self.bot.user.display_name} - Rozrywka", icon_url=self.bot.user.avatar.url)
        else:
            embed.set_author(name="Rozrywka w Kronikach")

        # Poprawiona linia - context.guild jest dostępne dla obu typów
        guild = context.guild

        if guild and guild.icon:
            embed.set_footer(text=f"Serwer: {guild.name} | Kroniki Elary", icon_url=guild.icon.url)
        else:
            embed.set_footer(text="Kroniki Elary")
        return embed

    @commands.hybrid_command(name="losowyfakt", description="Uzyskaj losowy, ciekawy fakt.")
    async def losowyfakt(self, context: Context) -> None:
        """
        Elara podzieli się z Tobą losowym, często zaskakującym faktem ze świata!
        Idealne na chwilę przerwy i poszerzenie horyzontów.
        """
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get("https://uselessfacts.jsph.pl/random.json?language=en") as request:
                    if request.status == 200:
                        data = await request.json()
                        embed = await self._create_fun_embed(context, title="💡 Losowy Fakt!", description=data["text"], color=config.KOLOR_BOT_INFO)
                    else:
                        self.bot.logger.warning(f"Nie udało się pobrać losowego faktu, status API: {request.status}")
                        embed = await self._create_fun_embed(context, title="🤔 Coś Poszło Nie Tak...", description="Niestety, skarbnica faktów jest chwilowo zamknięta. Spróbuj później!", color=config.KOLOR_BOT_BLAD)
            except aiohttp.ClientError as e:
                self.bot.logger.error(f"Błąd połączenia z API losowych faktów: {e}")
                embed = await self._create_fun_embed(context, title="🕸️ Problem z Połączeniem", description="Nie udało mi się dotrzeć do skarbca faktów. Sprawdź swoje połączenie lub spróbuj później.", color=config.KOLOR_BOT_BLAD)
            await context.send(embed=embed)

    @commands.hybrid_command(name="rzutmoneta", description="Rzuć monetą - orzeł czy reszka?")
    async def rzutmoneta(self, context: Context) -> None:
        """
        Nie możesz się zdecydować? Pozwól losowi wybrać!
        Elara rzuci magiczną monetą. Najpierw obstaw, co wypadnie!
        """
        widok_wyboru = WyborMonety(context.author.id)
        embed_pytanie = await self._create_fun_embed(context, title="🪙 Rzut Monetą", description="Co obstawiasz, Kronikarzu? Orzeł czy reszka?", color=config.KOLOR_BOT_INFO)

        message_to_edit: typing.Optional[discord.Message] = None
        if context.interaction:
            await context.interaction.response.send_message(embed=embed_pytanie, view=widok_wyboru, ephemeral=False)
            message_to_edit = await context.interaction.original_response()
        else:
            message_to_edit = await context.send(embed=embed_pytanie, view=widok_wyboru)

        if message_to_edit:
            widok_wyboru.message = message_to_edit

        await widok_wyboru.wait()

        if widok_wyboru.value is None:
            return

        wynik_rzutu = random.choice(["orzeł", "reszka"])

        if widok_wyboru.value == wynik_rzutu:
            opis_wyniku = f"Brawo, {context.author.mention}! 🥳\nObstawiałeś/aś **{widok_wyboru.value.capitalize()}** i wypadł/a **{wynik_rzutu.capitalize()}**!"
            kolor_wyniku = config.KOLOR_BOT_SUKCES
        else:
            opis_wyniku = f"Niestety, {context.author.mention}... 😥\nObstawiałeś/aś **{widok_wyboru.value.capitalize()}**, a wypadł/a **{wynik_rzutu.capitalize()}**. Spróbuj szczęścia następnym razem!"
            kolor_wyniku = config.KOLOR_BOT_BLAD

        embed_wynik = await self._create_fun_embed(context, title=f"🪙 Wynik Rzutu: {wynik_rzutu.capitalize()}!", description=opis_wyniku, color=kolor_wyniku)

        if message_to_edit: # Upewniamy się, że wiadomość istnieje
            await message_to_edit.edit(embed=embed_wynik, view=None)


    @commands.hybrid_command(name="pkn", aliases=["kamienpapiernozyce", "rps"], description="Zagraj w Papier, Kamień, Nożyce z Elarą!")
    async def papier_kamien_nozyce(self, context: Context) -> None:
        """
        Zmierz się z Elarą w klasycznej grze Papier, Kamień, Nożyce!
        Wybierz swój ruch z menu poniżej.
        """
        widok_pkn = PapierKamienNozyceView(self, context.author.id)
        embed_start = await self._create_fun_embed(context, title="⚔️ Wyzwanie: Papier, Kamień, Nożyce!", description=f"{context.author.mention}, wybierz swój ruch z menu poniżej, aby zmierzyć się z Elarą!", color=config.KOLOR_BOT_INFO)

        message_to_edit: typing.Optional[discord.Message] = None
        if context.interaction:
            await context.interaction.response.send_message(embed=embed_start, view=widok_pkn)
            message_to_edit = await context.interaction.original_response()
        else:
            message_to_edit = await context.send(embed=embed_start, view=widok_pkn)

        if message_to_edit:
            widok_pkn.message = message_to_edit

async def setup(bot: 'BotDiscord') -> None:
    await bot.add_cog(Rozrywka(bot))
