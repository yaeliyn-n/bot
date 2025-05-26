import discord
from discord import app_commands, Interaction
from discord.ext import commands
from discord.ext.commands import Context, has_permissions
import time
from datetime import datetime, UTC, timedelta
import typing

# Import konfiguracji globalnej
import config

if typing.TYPE_CHECKING:
    from bot import BotDiscord

class PurchaseConfirmationButton(discord.ui.Button['ShopPurchaseView']):
    def __init__(self, item_id: str, item_data: dict, currency_to_use: str, **kwargs):
        super().__init__(**kwargs)
        self.item_id = item_id
        self.item_data = item_data
        self.currency_to_use = currency_to_use

    async def callback(self, interaction: Interaction):
        assert self.view is not None
        view: ShopPurchaseView = self.view # type: ignore

        if interaction.user.id != view.original_author_id:
            await interaction.response.send_message("Tylko osoba, która zainicjowała zakup, może go potwierdzić!", ephemeral=True)
            return

        if view.bot.baza_danych is None:
            await interaction.response.edit_message(content="Skarbiec jest chwilowo niedostępny, spróbuj później.", embed=None, view=None)
            return

        user_id = interaction.user.id
        server_id = interaction.guild_id if interaction.guild else None
        if not server_id or not interaction.guild: # Dodatkowe sprawdzenie dla interaction.guild
             await interaction.response.edit_message(content="Ta akcja musi być wykonana na serwerze.", embed=None, view=None)
             return

        koszt_dukatow = self.item_data.get("koszt_dukatow")
        koszt_krysztalow = self.item_data.get("koszt_krysztalow")

        koszt = 0
        waluta_symbol = ""
        if self.currency_to_use == "dukaty" and koszt_dukatow is not None:
            koszt = koszt_dukatow
            waluta_symbol = "✨"
        elif self.currency_to_use == "krysztaly" and koszt_krysztalow is not None:
            koszt = koszt_krysztalow
            waluta_symbol = config.SYMBOL_WALUTY_PREMIUM
        else:
            await interaction.response.edit_message(content="Błąd: Nie można określić waluty lub kosztu przedmiotu.", embed=None, view=None)
            return

        portfel_dane = await view.bot.baza_danych.pobierz_lub_stworz_portfel(user_id, server_id)
        aktualne_dukaty = portfel_dane[2]
        aktualne_krysztaly = portfel_dane[3]

        posiadana_waluta = aktualne_dukaty if self.currency_to_use == "dukaty" else aktualne_krysztaly

        if posiadana_waluta < koszt:
            nazwa_waluty = "Gwiezdnych Dukatów" if self.currency_to_use == "dukaty" else config.NAZWA_WALUTY_PREMIUM
            embed_error = await view.cog._create_currency_embed(
                view.original_context,
                title=f"📉 Brak Wystarczających Środków ({nazwa_waluty})",
                description=f"Nie udało się zakupić **{self.item_data['nazwa']}**.\nPotrzebujesz: **{koszt}** {waluta_symbol}, posiadasz: **{posiadana_waluta}** {waluta_symbol}.",
                color=config.KOLOR_BOT_BLAD
            )
            await interaction.response.edit_message(embed=embed_error, view=None)
            return

        # Aktualizacja portfela
        if self.currency_to_use == "dukaty":
            await view.bot.baza_danych.aktualizuj_portfel(user_id, server_id, ilosc_dukatow_do_dodania=-koszt)
        else:
            await view.bot.baza_danych.aktualizuj_portfel(user_id, server_id, ilosc_krysztalow_do_dodania=-koszt)

        czas_zakupu_ts = int(time.time())
        czas_wygasniecia_ts = None
        if "czas_trwania_sekundy" in self.item_data and self.item_data["czas_trwania_sekundy"] is not None:
             czas_wygasniecia_ts = czas_zakupu_ts + self.item_data["czas_trwania_sekundy"]

        typ_bonusu_przedmiotu = self.item_data.get("typ_bonusu", "nieznany_typ_bonusu")
        wartosc_bonusu_przedmiotu = self.item_data.get("wartosc_bonusu", 0.0)

        # Logika specyficzna dla typu przedmiotu
        wiadomosc_sukcesu_dodatkowa = ""

        if typ_bonusu_przedmiotu == "timed_role":
            rola_id_str = self.item_data.get("id_roli_do_nadania")
            if not rola_id_str or not interaction.guild: # Sprawdzenie interaction.guild
                view.bot.logger.error(f"Brak id_roli_do_nadania lub guild w item_data dla timed_role: {self.item_id}")
                await interaction.response.edit_message(content="Błąd konfiguracji przedmiotu (brak ID roli). Skontaktuj się z administratorem.", embed=None, view=None)
                return
            try:
                rola_id_int = int(rola_id_str)
                rola_obj = interaction.guild.get_role(rola_id_int)
                if not rola_obj:
                    view.bot.logger.error(f"Nie znaleziono roli o ID {rola_id_int} na serwerze {interaction.guild.name} dla przedmiotu {self.item_id}.")
                    await interaction.response.edit_message(content="Błąd: Rola do nadania nie istnieje na tym serwerze. Skontaktuj się z administratorem.", embed=None, view=None)
                    return

                if not isinstance(interaction.user, discord.Member):
                    await interaction.response.edit_message(content="Błąd: Nie można nadać roli użytkownikowi (brak obiektu Member).", embed=None, view=None)
                    return

                await interaction.user.add_roles(rola_obj, reason=f"Zakup przedmiotu w sklepie: {self.item_data['nazwa']}")

                if czas_wygasniecia_ts: # Tylko jeśli jest czas wygaśnięcia, dodajemy do bazy ról czasowych
                    await view.bot.baza_danych.dodaj_aktywna_role_czasowa(
                        str(user_id), str(server_id), str(rola_id_int),
                        czas_zakupu_ts, czas_wygasniecia_ts, self.item_id
                    )
                    wiadomosc_sukcesu_dodatkowa = f"\n🛡️ Otrzymałeś/aś rolę **{rola_obj.name}**!"
                else: # Jeśli rola nie ma czasu wygaśnięcia (stała rola ze sklepu)
                    wiadomosc_sukcesu_dodatkowa = f"\n🛡️ Otrzymałeś/aś na stałe rolę **{rola_obj.name}**!"

                view.bot.logger.info(f"Przyznano rolę '{rola_obj.name}' użytkownikowi {interaction.user.display_name} po zakupie '{self.item_data['nazwa']}'.")

            except ValueError:
                view.bot.logger.error(f"Nieprawidłowe ID roli '{rola_id_str}' w konfiguracji przedmiotu {self.item_id}.")
                await interaction.response.edit_message(content="Błąd konfiguracji roli. Skontaktuj się z administratorem.", embed=None, view=None)
                return
            except discord.Forbidden:
                view.bot.logger.warning(f"Brak uprawnień do nadania roli '{rola_id_str}' użytkownikowi {interaction.user.display_name}.")
                await interaction.response.edit_message(content="Nie udało się nadać roli (brak uprawnień bota). Skontaktuj się z administratorem.", embed=None, view=None)
                return
            except Exception as e:
                view.bot.logger.error(f"Nieoczekiwany błąd podczas nadawania roli czasowej {self.item_id}: {e}", exc_info=True)
                await interaction.response.edit_message(content="Wystąpił nieoczekiwany błąd przy nadawaniu roli. Skontaktuj się z administratorem.", embed=None, view=None)
                return
        else:
            # Dla innych typów bonusów (np. xp_mnoznik) dodajemy do posiadane_przedmioty
            await view.bot.baza_danych.dodaj_przedmiot_uzytkownika(
                str(user_id), str(server_id), self.item_id,
                czas_zakupu_ts, czas_wygasniecia_ts,
                typ_bonusu_przedmiotu, wartosc_bonusu_przedmiotu
            )

        czas_trwania_str = view.cog.bot.formatuj_czas(self.item_data.get("czas_trwania_sekundy", 0), precyzyjnie=True) # Zmieniono na view.cog.bot.formatuj_czas
        emoji_przedmiotu = self.item_data.get("emoji", "🎉")
        nazwa_waluty_zakupu = "Gwiezdnych Dukatów" if self.currency_to_use == "dukaty" else config.NAZWA_WALUTY_PREMIUM

        opis_embed_sukces = (f"Pomyślnie zakupiłeś/aś **{self.item_data['nazwa']}** za {koszt} {waluta_symbol} {nazwa_waluty_zakupu}!"
                             f"{wiadomosc_sukcesu_dodatkowa}\n" +
                             (f"Artefakt będzie aktywny przez **{czas_trwania_str}**." if self.item_data.get("czas_trwania_sekundy") and typ_bonusu_przedmiotu != "timed_role" else
                              (f"Rola będzie aktywna przez **{czas_trwania_str}**." if typ_bonusu_przedmiotu == "timed_role" and czas_wygasniecia_ts else
                               ("Artefakt został dodany do Twojego ekwipunku." if typ_bonusu_przedmiotu != "timed_role" else ""))))


        embed_success = await view.cog._create_currency_embed(
            view.original_context,
            title=f"{emoji_przedmiotu} Artefakt Nabyty!",
            description=opis_embed_sukces.strip(),
            color=config.KOLOR_BOT_SUKCES
        )
        if interaction.user.display_avatar:
            embed_success.set_thumbnail(url=interaction.user.display_avatar.url)
        await interaction.response.edit_message(embed=embed_success, view=None)
        view.bot.logger.info(f"Użytkownik {interaction.user.display_name} zakupił '{self.item_data['nazwa']}' na serwerze {interaction.guild.name if interaction.guild else 'DM'} za {koszt} {waluta_symbol} ({self.currency_to_use}) poprzez menu.")


class CancelPurchaseButton(discord.ui.Button['ShopView']): # Zmieniono typ widoku na ShopView
    async def callback(self, interaction: Interaction):
        assert self.view is not None
        # Ten przycisk powinien być używany w kontekście widoku, który go dodał.
        # Zakładamy, że self.view to instancja ShopView lub widoku z przyciskami zakupu,
        # który przechowuje referencje do cog i original_context.

        view_parent: ShopView = self.view # type: ignore

        if interaction.user.id != view_parent.original_author_id:
            await interaction.response.send_message("Tylko osoba, która otworzyła sklep, może go anulować!", ephemeral=True)
            return

        shop_embed = await view_parent.cog._build_shop_embed(view_parent.original_context)
        # Tworzymy nowy ShopView, aby zresetować stan (np. wybór w select)
        new_shop_view = ShopView(view_parent.original_context, view_parent.bot, view_parent.cog)

        # Edytujemy wiadomość, aby wrócić do głównego widoku sklepu
        if interaction.message: # Upewniamy się, że wiadomość istnieje
            await interaction.message.edit(embed=shop_embed, view=new_shop_view)
            new_shop_view.message = interaction.message # Aktualizujemy referencję do wiadomości w nowym widoku
        else: # Jeśli nie ma wiadomości do edycji (np. interakcja była deferred i nie było followup)
            await interaction.response.send_message(embed=shop_embed, view=new_shop_view)
            # new_shop_view.message = await interaction.original_response() # Jeśli to była nowa odpowiedź


class ShopPurchaseView(discord.ui.View):
    message: typing.Optional[discord.Message]

    def __init__(self, context: Context, bot: 'BotDiscord', cog: 'Waluta', item_id: str, item_data: dict, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.original_context = context
        self.original_author_id = context.author.id
        self.bot = bot
        self.cog = cog
        self.item_id = item_id
        self.item_data = item_data
        self.message = None

        # Przyciski zakupu w zależności od dostępnych walut
        can_buy_with_dukaty = item_data.get("koszt_dukatow") is not None
        can_buy_with_krysztaly = item_data.get("koszt_krysztalow") is not None

        if can_buy_with_dukaty:
            self.add_item(PurchaseConfirmationButton(item_id, item_data, "dukaty", label=f"Kup za Dukaty ({item_data['koszt_dukatow']}✨)", style=discord.ButtonStyle.green, row=0))
        if can_buy_with_krysztaly:
            self.add_item(PurchaseConfirmationButton(item_id, item_data, "krysztaly", label=f"Kup za Kryształy ({item_data['koszt_krysztalow']}{config.SYMBOL_WALUTY_PREMIUM})", style=discord.ButtonStyle.blurple, row=0 if not can_buy_with_dukaty else 1 )) # Inny rząd jeśli oba są dostępne

        self.add_item(CancelPurchaseButton(label="❌ Anuluj", style=discord.ButtonStyle.red, row=2 if (can_buy_with_dukaty and can_buy_with_krysztaly) else (1 if (can_buy_with_dukaty or can_buy_with_krysztaly) else 0) ))


    async def on_timeout(self):
        if self.message:
            try:
                timeout_embed = await self.cog._create_currency_embed(
                    self.original_context,
                    title="⏳ Czas na Decyzję Minął",
                    description="Sesja zakupu wygasła. Jeśli chcesz coś kupić, użyj komendy `/sklep` ponownie.",
                    color=config.KOLOR_COOLDOWN_WALUTA
                )
                await self.message.edit(embed=timeout_embed, view=None)
            except discord.NotFound:
                pass
            except Exception as e:
                self.bot.logger.warning(f"Błąd podczas timeoutu ShopPurchaseView: {e}")
        self.stop()


class ShopItemSelect(discord.ui.Select['ShopView']):
    def __init__(self, context: Context, bot: 'BotDiscord', cog: 'Waluta'):
        self.original_context = context
        self.bot = bot
        self.cog = cog

        options = []
        if not config.PRZEDMIOTY_SKLEPU:
            options.append(discord.SelectOption(label="Skarbiec jest pusty!", value="_empty", emoji="💨"))
        else:
            for item_id, item_data in config.PRZEDMIOTY_SKLEPU.items():
                emoji = item_data.get("emoji", "🛍️")
                price_str_parts = []
                if item_data.get("koszt_dukatow") is not None:
                    price_str_parts.append(f"{item_data['koszt_dukatow']} ✨")
                if item_data.get("koszt_krysztalow") is not None:
                    price_str_parts.append(f"{item_data['koszt_krysztalow']} {config.SYMBOL_WALUTY_PREMIUM}")
                price_str = " lub ".join(price_str_parts) if price_str_parts else "Darmowy?"

                options.append(discord.SelectOption(
                    label=f"{item_data['nazwa']} ({price_str})",
                    value=item_id,
                    description=item_data['opis'][:100],
                    emoji=emoji
                ))

        super().__init__(
            placeholder="Wybierz artefakt do zbadania...",
            min_values=1,
            max_values=1,
            options=options,
            disabled=not config.PRZEDMIOTY_SKLEPU
        )

    async def callback(self, interaction: Interaction):
        assert self.view is not None
        view: ShopView = self.view # type: ignore

        if interaction.user.id != self.original_context.author.id:
            await interaction.response.send_message("Tylko osoba, która otworzyła sklep, może wybierać przedmioty!", ephemeral=True)
            return

        selected_item_id = self.values[0]
        if selected_item_id == "_empty":
            await interaction.response.defer()
            return

        item_data = config.PRZEDMIOTY_SKLEPU.get(selected_item_id)
        if not item_data:
            await interaction.response.edit_message(content="Wybrany artefakt zniknął z naszego skarbca!", embed=None, view=None)
            return

        emoji = item_data.get("emoji", "🛍️")

        koszt_dukaty_str = f"{item_data['koszt_dukatow']} ✨ Gwiezdnych Dukatów" if item_data.get("koszt_dukatow") is not None else ""
        koszt_krysztaly_str = f"{item_data['koszt_krysztalow']} {config.SYMBOL_WALUTY_PREMIUM} {config.NAZWA_WALUTY_PREMIUM}" if item_data.get("koszt_krysztalow") is not None else ""

        koszt_opis = ""
        if koszt_dukaty_str and koszt_krysztaly_str:
            koszt_opis = f"**Koszt:** {koszt_dukaty_str} LUB {koszt_krysztaly_str}"
        elif koszt_dukaty_str:
            koszt_opis = f"**Koszt:** {koszt_dukaty_str}"
        elif koszt_krysztaly_str:
            koszt_opis = f"**Koszt:** {koszt_krysztaly_str}"
        else:
            koszt_opis = "**Koszt:** Przedmiot darmowy lub nieustalony."

        opis_przedmiotu_embed = (f"{item_data['opis']}\n\n{koszt_opis}\n")
        if item_data.get("typ_bonusu") == "timed_role":
            opis_przedmiotu_embed += f"**Typ:** Rola Czasowa\n"
            if item_data.get("id_roli_do_nadania") and interaction.guild:
                try:
                    rola_obj = interaction.guild.get_role(int(item_data["id_roli_do_nadania"]))
                    if rola_obj:
                        opis_przedmiotu_embed += f"**Rola:** {rola_obj.mention}\n"
                except: pass # Ignorujemy błąd, jeśli rola nie istnieje

        # Zmieniono na self.cog.bot.formatuj_czas
        opis_przedmiotu_embed += (f"**Czas trwania:** {self.cog.bot.formatuj_czas(item_data['czas_trwania_sekundy'], precyzyjnie=True)}" if 'czas_trwania_sekundy' in item_data and item_data['czas_trwania_sekundy'] is not None else "**Efekt:** Natychmiastowy / Jednorazowy")


        embed = await self.cog._create_currency_embed(
            self.original_context,
            title=f"{emoji} {item_data['nazwa']}",
            description=opis_przedmiotu_embed,
            color=config.KOLOR_SKLEPU_PRZEDMIOT
        )
        if self.original_context.guild and self.original_context.guild.icon:
             embed.set_thumbnail(url=self.original_context.guild.icon.url)

        # Używamy ShopPurchaseView do potwierdzenia
        purchase_view = ShopPurchaseView(self.original_context, self.bot, self.cog, selected_item_id, item_data)

        await interaction.response.edit_message(embed=embed, view=purchase_view)
        if interaction.message: # Przekazujemy wiadomość do nowego widoku
            purchase_view.message = interaction.message


class ShopView(discord.ui.View):
    message: typing.Optional[discord.Message]

    def __init__(self, context: Context, bot: 'BotDiscord', cog: 'Waluta', timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.original_context = context
        self.original_author_id = context.author.id # Dodajemy ID autora
        self.bot = bot
        self.cog = cog
        self.message = None
        self.add_item(ShopItemSelect(context, bot, cog))

    async def on_timeout(self):
        if self.message:
            try:
                self.clear_items()
                timeout_embed = await self.cog._create_currency_embed(
                    self.original_context,
                    title="🚪 Skarbiec Zamknięty",
                    description="Sesja przeglądania skarbca wygasła. Użyj komendy `/sklep` ponownie, jeśli chcesz coś kupić.",
                    color=config.KOLOR_COOLDOWN_WALUTA
                )
                await self.message.edit(embed=timeout_embed, view=self)
            except discord.NotFound:
                pass
            except Exception as e:
                self.bot.logger.warning(f"Błąd podczas timeoutu ShopView: {e}")
        self.stop()


class Waluta(commands.Cog, name="waluta"):
    """💰 Kapsuła zarządzająca Gwiezdnymi Dukatami, Kryształami i Skarbcem Artefaktów w Kronikach Elary."""
    COG_EMOJI = "💰"

    def __init__(self, bot: 'BotDiscord'):
        self.bot = bot

    # Usunięto zduplikowaną metodę formatuj_czas

    async def _create_currency_embed(self, context: Context, title: str, description: str = "", color: discord.Color = config.KOLOR_WALUTY_GLOWNY) -> discord.Embed:
        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.now(UTC))
        if context.guild and context.guild.icon:
            embed.set_footer(text="System Waluty | Kroniki Elary", icon_url=context.guild.icon.url)
        else:
            embed.set_footer(text="System Waluty | Kroniki Elary")
        return embed

    async def _build_shop_embed(self, context: Context) -> discord.Embed:
        embed = await self._create_currency_embed(context, title="🏪 Skarbiec Artefaktów Mocy", description="Wybierz artefakt z menu poniżej, aby dowiedzieć się więcej lub dokonać zakupu.", color=config.KOLOR_SKLEPU_LISTA)
        if context.guild and context.guild.icon:
             embed.set_thumbnail(url=context.guild.icon.url)

        if not config.PRZEDMIOTY_SKLEPU:
            embed.description += "\n\nNiestety, skarbiec jest obecnie pusty. Runa pracuje nad nowymi magicznymi przedmiotami!"
        return embed

    @commands.hybrid_command(
        name="codzienna",
        aliases=["daily", "dziennanagroda"],
        description="Odbierz swoją codzienną porcję Gwiezdnych Dukatów!"
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def codzienna_nagroda(self, context: Context):
        if not context.guild:
            await context.send("Tej komendy można używać tylko w granicach Kronik Elary.", ephemeral=True)
            return
        if self.bot.baza_danych is None:
            await context.send("Skarbiec Kronik jest chwilowo niedostępny. Spróbuj ponownie później.", ephemeral=True)
            return

        user_id = context.author.id
        server_id = context.guild.id

        sukces, odpowiedz_lub_czas, nowe_saldo_dukatow = await self.bot.baza_danych.odbierz_codzienna_nagrode(
            user_id, server_id, config.ILOSC_DUKATOW_ZA_DAILY, config.COOLDOWN_DAILY_SEKUNDY
        )

        if sukces:
            embed = await self._create_currency_embed(
                context,
                title="🎉 Codzienna Nagroda Odebrana! 🎉",
                description=f"{context.author.mention}, {odpowiedz_lub_czas}\nTwoje aktualne saldo: **{nowe_saldo_dukatow}** ✨ Gwiezdnych Dukatów.",
                color=config.KOLOR_BOT_SUKCES
            )
            if context.author.display_avatar:
                embed.set_thumbnail(url=context.author.display_avatar.url)
        else:
            # Zmieniono na self.bot.formatuj_czas
            pozostaly_czas_str = self.bot.formatuj_czas(odpowiedz_lub_czas, precyzyjnie=True) # type: ignore
            embed = await self._create_currency_embed(
                context,
                title="⏳ Jeszcze Nie Teraz, Kronikarzu!",
                description=f"{context.author.mention}, możesz odebrać kolejną dzienną porcję Gwiezdnych Dukatów za: **{pozostaly_czas_str}**.",
                color=config.KOLOR_COOLDOWN_WALUTA
            )
        await context.send(embed=embed)


    @commands.hybrid_command(
        name="portfel",
        aliases=["balans", "saldo", "dukaty", "krysztaly"],
        description="Sprawdza Twoje aktualne saldo walut."
    )
    @app_commands.describe(uzytkownik="Użytkownik, którego portfel chcesz sprawdzić (opcjonalnie).")
    async def portfel(self, context: Context, uzytkownik: typing.Optional[discord.Member] = None):
        if not context.guild:
            await context.send("Tej komendy można używać tylko na serwerze.", ephemeral=True)
            return
        if self.bot.baza_danych is None:
            await context.send("Błąd: Skarbiec jest chwilowo niedostępny.", ephemeral=True)
            return

        target_user = uzytkownik or context.author

        portfel_dane = await self.bot.baza_danych.pobierz_lub_stworz_portfel(target_user.id, context.guild.id)
        dukaty = portfel_dane[2]
        krysztaly = portfel_dane[3]

        embed = await self._create_currency_embed(
            context,
            title=f"💰 Portfel Kronikarza: {target_user.display_name}",
            description=f"✨ Gwiezdne Dukaty: **{dukaty}**\n"
                        f"{config.SYMBOL_WALUTY_PREMIUM} {config.NAZWA_WALUTY_PREMIUM}: **{krysztaly}**",
            color=config.KOLOR_WALUTY_GLOWNY
        )
        if target_user.display_avatar:
            embed.set_thumbnail(url=target_user.display_avatar.url)

        await context.send(embed=embed)


    @commands.hybrid_command(
        name="rankingwaluty",
        aliases=["topbogaczy", "rankingdukatow", "rankingkrysztalow"],
        description="Wyświetla ranking walut w Kronikach."
    )
    @app_commands.describe(typ_waluty="Wybierz typ waluty do rankingu (dukaty lub krysztaly).")
    @app_commands.choices(typ_waluty=[
        app_commands.Choice(name="✨ Gwiezdne Dukaty", value="dukaty"),
        app_commands.Choice(name=f"{config.SYMBOL_WALUTY_PREMIUM} {config.NAZWA_WALUTY_PREMIUM}", value="krysztaly")
    ])
    async def rankingwaluty(self, context: Context, typ_waluty: app_commands.Choice[str]):
        if not context.guild: await context.send("Tylko w granicach Kronik.", ephemeral=True); return
        if self.bot.baza_danych is None: await context.send("Błąd: Skarbiec.", ephemeral=True); return

        waluta_value = typ_waluty.value
        ranking = await self.bot.baza_danych.pobierz_ranking_waluta(context.guild.id, limit=10, typ_waluty=waluta_value)

        nazwa_rankingu = "Gwiezdnych Dukatów" if waluta_value == "dukaty" else config.NAZWA_WALUTY_PREMIUM
        symbol_rankingu = "✨" if waluta_value == "dukaty" else config.SYMBOL_WALUTY_PREMIUM
        kolor_rankingu = config.KOLOR_WALUTY_GLOWNY if waluta_value == "dukaty" else config.KOLOR_WALUTY_PREMIUM

        embed = await self._create_currency_embed(context, title=f"{symbol_rankingu} Najbogatsi Kronikarze ({nazwa_rankingu})", color=kolor_rankingu)
        if context.guild.icon: embed.set_thumbnail(url=context.guild.icon.url)

        if not ranking:
            embed.description = f"Skarbiec {nazwa_rankingu} jest pusty. Czas wyruszyć na przygodę i zdobyć fortunę!"
        else:
            opis_list = []
            medale = ["🥇", "🥈", "🥉"]
            for i, (user_id_db, ilosc_waluty) in enumerate(ranking):
                uzytkownik_obj = context.guild.get_member(user_id_db)
                nazwa_uzytkownika = uzytkownik_obj.display_name if uzytkownik_obj else f"Nieznany Kronikarz ({user_id_db})"
                medal_str = medale[i] if i < len(medale) else f"**{i+1}.**"
                opis_list.append(f"{medal_str} {nazwa_uzytkownika} - **{ilosc_waluty}** {symbol_rankingu}")
            embed.description = "\n".join(opis_list)

        if context.guild.icon:
            embed.set_footer(text="Niech Twój skarbiec pęka w szwach!", icon_url=context.guild.icon.url)
        else:
            embed.set_footer(text="Niech Twój skarbiec pęka w szwach!")
        await context.send(embed=embed)

    @commands.hybrid_command(
        name="sklep",
        description="Otwiera interaktywny Skarbiec Artefaktów Mocy."
    )
    async def sklep_interactive(self, context: Context):
        if not context.guild: await context.send("Tylko w granicach Kronik.", ephemeral=True); return
        if self.bot.baza_danych is None: await context.send("Błąd: Skarbiec jest chwilowo niedostępny.", ephemeral=True); return

        embed = await self._build_shop_embed(context)
        view = ShopView(context, self.bot, self)

        sent_message = await context.send(embed=embed, view=view)
        view.message = sent_message


    @commands.hybrid_group(name="adminwaluta", description="Zarządzanie walutami użytkowników.")
    @has_permissions(manage_guild=True)
    async def adminwaluta(self, context: Context):
        if not context.guild:
            await context.send("Tej komendy można używać tylko w granicach Kronik Elary.", ephemeral=True)
            return
        if context.invoked_subcommand is None:
            embed = await self._create_currency_embed(context, title="🛠️ Panel Administracyjny Walut", description=f"Nie podano podkomendy. Dostępne: `daj`, `zabierz`, `ustaw`.\nUżyj opcji `typ_waluty`, aby wybrać między Dukatami a {config.NAZWA_WALUTY_PREMIUM}.", color=config.KOLOR_ADMIN_WALUTA)
            await context.send(embed=embed, ephemeral=True)

    @adminwaluta.command(name="daj", description="Dodaje walutę użytkownikowi.")
    @app_commands.describe(uzytkownik="Użytkownik.", ilosc="Ilość do dodania.", typ_waluty="Rodzaj waluty.", powod="Opcjonalny powód.")
    @app_commands.choices(typ_waluty=[
        app_commands.Choice(name="✨ Gwiezdne Dukaty", value="dukaty"),
        app_commands.Choice(name=f"{config.SYMBOL_WALUTY_PREMIUM} {config.NAZWA_WALUTY_PREMIUM}", value="krysztaly")
    ])
    async def adminwaluta_daj(self, context: Context, uzytkownik: discord.Member, ilosc: int, typ_waluty: app_commands.Choice[str], powod: typing.Optional[str] = None):
        if not context.guild or self.bot.baza_danych is None: await context.send("Błąd.", ephemeral=True); return
        if ilosc <= 0: await context.send("Ilość musi być dodatnia.", ephemeral=True); return

        waluta_code = typ_waluty.value
        nowe_dukaty, nowe_krysztaly = 0, 0

        if waluta_code == "dukaty":
            nowe_dukaty, nowe_krysztaly = await self.bot.baza_danych.aktualizuj_portfel(uzytkownik.id, context.guild.id, ilosc_dukatow_do_dodania=ilosc)
        else:
            nowe_dukaty, nowe_krysztaly = await self.bot.baza_danych.aktualizuj_portfel(uzytkownik.id, context.guild.id, ilosc_krysztalow_do_dodania=ilosc)

        nazwa_waluty_str = "Gwiezdnych Dukatów ✨" if waluta_code == "dukaty" else f"{config.NAZWA_WALUTY_PREMIUM} {config.SYMBOL_WALUTY_PREMIUM}"
        aktualne_saldo_str = f"{nowe_dukaty} ✨" if waluta_code == "dukaty" else f"{nowe_krysztaly} {config.SYMBOL_WALUTY_PREMIUM}"

        opis_embed = f"Przyznano **{ilosc}** {nazwa_waluty_str} użytkownikowi {uzytkownik.mention}.\nNowe saldo tej waluty: **{aktualne_saldo_str}**."
        if powod: opis_embed += f"\nPowód: *{powod}*"

        embed = await self._create_currency_embed(context, title=f"💸 {nazwa_waluty_str.split(' ')[-2]} Przyznane", description=opis_embed, color=config.KOLOR_BOT_SUKCES)
        await context.send(embed=embed)
        self.bot.logger.info(f"Admin {context.author.display_name} przyznał {ilosc} {waluta_code} użytkownikowi {uzytkownik.display_name}. Powód: {powod or 'Nie podano'}.")


    @adminwaluta.command(name="zabierz", description="Odbiera walutę użytkownikowi.")
    @app_commands.describe(uzytkownik="Użytkownik.", ilosc="Ilość do zabrania.", typ_waluty="Rodzaj waluty.", powod="Opcjonalny powód.")
    @app_commands.choices(typ_waluty=[
        app_commands.Choice(name="✨ Gwiezdne Dukaty", value="dukaty"),
        app_commands.Choice(name=f"{config.SYMBOL_WALUTY_PREMIUM} {config.NAZWA_WALUTY_PREMIUM}", value="krysztaly")
    ])
    async def adminwaluta_zabierz(self, context: Context, uzytkownik: discord.Member, ilosc: int, typ_waluty: app_commands.Choice[str], powod: typing.Optional[str] = None):
        if not context.guild or self.bot.baza_danych is None: await context.send("Błąd.", ephemeral=True); return
        if ilosc <= 0: await context.send("Ilość musi być dodatnia.", ephemeral=True); return

        waluta_code = typ_waluty.value
        nowe_dukaty, nowe_krysztaly = 0, 0

        if waluta_code == "dukaty":
            nowe_dukaty, nowe_krysztaly = await self.bot.baza_danych.aktualizuj_portfel(uzytkownik.id, context.guild.id, ilosc_dukatow_do_dodania=-ilosc)
        else:
            nowe_dukaty, nowe_krysztaly = await self.bot.baza_danych.aktualizuj_portfel(uzytkownik.id, context.guild.id, ilosc_krysztalow_do_dodania=-ilosc)

        nazwa_waluty_str = "Gwiezdnych Dukatów ✨" if waluta_code == "dukaty" else f"{config.NAZWA_WALUTY_PREMIUM} {config.SYMBOL_WALUTY_PREMIUM}"
        aktualne_saldo_str = f"{nowe_dukaty} ✨" if waluta_code == "dukaty" else f"{nowe_krysztaly} {config.SYMBOL_WALUTY_PREMIUM}"

        opis_embed = f"Zabrano **{ilosc}** {nazwa_waluty_str} użytkownikowi {uzytkownik.mention}.\nNowe saldo tej waluty: **{aktualne_saldo_str}**."
        if powod: opis_embed += f"\nPowód: *{powod}*"

        embed = await self._create_currency_embed(context, title=f"💸 {nazwa_waluty_str.split(' ')[-2]} Zabrane", description=opis_embed, color=config.KOLOR_BOT_BLAD)
        await context.send(embed=embed)
        self.bot.logger.info(f"Admin {context.author.display_name} zabrał {ilosc} {waluta_code} użytkownikowi {uzytkownik.display_name}. Powód: {powod or 'Nie podano'}.")


    @adminwaluta.command(name="ustaw", description="Ustawia saldo waluty użytkownika.")
    @app_commands.describe(uzytkownik="Użytkownik.", ilosc="Nowe saldo.", typ_waluty="Rodzaj waluty.", powod="Opcjonalny powód.")
    @app_commands.choices(typ_waluty=[
        app_commands.Choice(name="✨ Gwiezdne Dukaty", value="dukaty"),
        app_commands.Choice(name=f"{config.SYMBOL_WALUTY_PREMIUM} {config.NAZWA_WALUTY_PREMIUM}", value="krysztaly")
    ])
    async def adminwaluta_ustaw(self, context: Context, uzytkownik: discord.Member, ilosc: int, typ_waluty: app_commands.Choice[str], powod: typing.Optional[str] = None):
        if not context.guild or self.bot.baza_danych is None: await context.send("Błąd.", ephemeral=True); return
        if ilosc < 0: await context.send("Saldo nie może być ujemne.", ephemeral=True); return

        waluta_code = typ_waluty.value
        nowe_dukaty, nowe_krysztaly = 0, 0

        if waluta_code == "dukaty":
            nowe_dukaty, nowe_krysztaly = await self.bot.baza_danych.ustaw_saldo_portfela(uzytkownik.id, context.guild.id, nowe_saldo_dukatow=ilosc)
        else:
            nowe_dukaty, nowe_krysztaly = await self.bot.baza_danych.ustaw_saldo_portfela(uzytkownik.id, context.guild.id, nowe_saldo_krysztalow=ilosc)

        nazwa_waluty_str = "Gwiezdnych Dukatów ✨" if waluta_code == "dukaty" else f"{config.NAZWA_WALUTY_PREMIUM} {config.SYMBOL_WALUTY_PREMIUM}"
        aktualne_saldo_str = f"{nowe_dukaty} ✨" if waluta_code == "dukaty" else f"{nowe_krysztaly} {config.SYMBOL_WALUTY_PREMIUM}"

        opis_embed = f"Ustawiono saldo {nazwa_waluty_str} użytkownika {uzytkownik.mention} na **{aktualne_saldo_str}**."
        if powod: opis_embed += f"\nPowód: *{powod}*"

        embed = await self._create_currency_embed(context, title=f"💸 Saldo {nazwa_waluty_str.split(' ')[-2]} Zaktualizowane", description=opis_embed, color=config.KOLOR_ADMIN_WALUTA)
        await context.send(embed=embed)
        self.bot.logger.info(f"Admin {context.author.display_name} ustawił saldo {waluta_code} użytkownika {uzytkownik.display_name} na {ilosc}. Powód: {powod or 'Nie podano'}.")


async def setup(bot: 'BotDiscord'):
    await bot.add_cog(Waluta(bot))
