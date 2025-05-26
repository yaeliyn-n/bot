# Standard library imports
import asyncio
import datetime # Zachowujemy ten import
import random
import re
import time
import typing
import json

# Third-party imports
import discord
from discord.ext import commands, tasks
from discord.ext.commands import Context, has_permissions
from discord import app_commands, Interaction, ButtonStyle
from discord.ui import Button, View, Select

# Local application/library specific imports
import config # Import konfiguracji

if typing.TYPE_CHECKING:
    from bot import BotDiscord # Zakładamy, że bot.py jest w głównym katalogu


class GiveawayJoinButton(Button['GiveawayView']):
    def __init__(self, giveaway_message_id: str, required_role_id: int | None, end_timestamp: int):
        super().__init__(style=ButtonStyle.green, label="Dołącz do Konkursu!", emoji="🎁", custom_id=f"giveaway_join_{giveaway_message_id}")
        self.giveaway_message_id = giveaway_message_id
        self.required_role_id = required_role_id
        self.end_timestamp = end_timestamp

    async def callback(self, interaction: Interaction):
        assert interaction.guild is not None
        assert isinstance(self.view, GiveawayView)

        cog: 'Giveaway' = self.view.cog
        bot: 'BotDiscord' = self.view.bot

        if bot.baza_danych is None:
            await interaction.response.send_message("Skarbiec Kronik (baza danych) jest chwilowo niedostępny.", ephemeral=True)
            return

        if int(time.time()) > self.end_timestamp:
            await interaction.response.send_message("Ten konkurs już się zakończył!", ephemeral=True)
            self.disabled = True
            if interaction.message:
                await interaction.message.edit(view=self.view)
            return

        if self.required_role_id:
            if isinstance(interaction.user, discord.Member):
                member_roles = [role.id for role in interaction.user.roles]
                if self.required_role_id not in member_roles:
                    required_role_obj = interaction.guild.get_role(self.required_role_id)
                    role_name = required_role_obj.name if required_role_obj else "wymaganej roli"
                    await interaction.response.send_message(f"Aby dołączyć do tego konkursu, musisz posiadać rolę **{role_name}**.", ephemeral=True)
                    return
            else:
                await interaction.response.send_message("Nie można zweryfikować Twoich ról.", ephemeral=True)
                return

        konkurs_info = await bot.baza_danych.pobierz_konkurs_po_wiadomosci_id(self.giveaway_message_id)
        if not konkurs_info or konkurs_info[10]: # czy_zakonczony jest na indeksie 10
            await interaction.response.send_message("Ten konkurs już się zakończył lub nie istnieje.", ephemeral=True)
            self.disabled = True
            if interaction.message:
                await interaction.message.edit(view=self.view)
            return

        dodano = await bot.baza_danych.dodaj_uczestnika_konkursu(self.giveaway_message_id, str(interaction.user.id))

        if dodano:
            await interaction.response.send_message("🎉 Pomyślnie dołączyłeś/aś do konkursu! Niech gwiazdy Ci sprzyjają!", ephemeral=True)
            if interaction.message:
                await cog.aktualizuj_embed_konkursu(interaction.message, self.giveaway_message_id)
        else:
            await interaction.response.send_message("Jesteś już zapisany/a do tego konkursu, Kronikarzu!", ephemeral=True)

class GiveawayView(View):
    message: discord.Message | None

    def __init__(self, cog: 'Giveaway', bot: 'BotDiscord', giveaway_message_id: str, required_role_id: int | None, end_timestamp: int, timeout: float | None = None):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.bot = bot
        self.message = None
        self.add_item(GiveawayJoinButton(giveaway_message_id, required_role_id, end_timestamp))

    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass
            except discord.HTTPException as e:
                self.cog.bot.logger.warning(f"Nie udało się edytować widoku konkursu po timeout: {e}")
        self.stop()


class Giveaway(commands.Cog, name="giveaway"):
    """🎁 Kapsuła do zarządzania konkursami (giveaways) w Kronikach Elary."""
    def __init__(self, bot: 'BotDiscord'):
        self.bot = bot
        self.active_giveaway_views: typing.Dict[int, GiveawayView] = {}

    @staticmethod
    def parse_duration(duration_str: str) -> int | None:
        regex = re.compile(r"(\d+)([smhdw])")
        parts = regex.findall(duration_str.lower())
        if not parts:
            return None

        total_seconds = 0
        time_multipliers = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800}
        for value, unit in parts:
            try:
                total_seconds += int(value) * time_multipliers[unit]
            except (KeyError, ValueError):
                return None
        return total_seconds if total_seconds > 0 else None

    async def cog_load(self):
        self.end_giveaways_task.start()
        self.bot.logger.info("Kapsuła Giveaway załadowana, zadanie end_giveaways_task uruchomione.")

    def cog_unload(self):
        self.end_giveaways_task.cancel()
        for view_id in list(self.active_giveaway_views.keys()):
            view = self.active_giveaway_views.pop(view_id, None)
            if view:
                view.stop()
        self.bot.logger.info("Kapsuła Giveaway rozładowana, zadanie end_giveaways_task zatrzymane.")

    async def _create_giveaway_embed(self, context: typing.Union[Context, Interaction, discord.TextChannel], title: str, description: str = "", color: discord.Color = config.GIVEAWAY_COLOR_DEFAULT) -> discord.Embed:
        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.datetime.now(datetime.timezone.utc))

        guild = None
        if isinstance(context, (Context, Interaction)):
            guild = context.guild
        elif isinstance(context, discord.TextChannel):
            guild = context.guild

        if guild and guild.icon:
            embed.set_footer(text=f"Konkursy | {guild.name}", icon_url=guild.icon.url)
        else:
            embed.set_footer(text="Konkursy | Kroniki Elary")

        if self.bot.user and self.bot.user.avatar:
            embed.set_author(name="Elara - Mistrzyni Konkursów", icon_url=self.bot.user.avatar.url)
        else:
            embed.set_author(name="Elara - Mistrzyni Konkursów")
        return embed

    async def aktualizuj_embed_konkursu(self, message: discord.Message, message_id_str: str, zakonczony: bool = False, zwyciezcy_ids: typing.Optional[list[str]] = None):
        if self.bot.baza_danych is None: return

        konkurs_info = await self.bot.baza_danych.pobierz_konkurs_po_wiadomosci_id(message_id_str)
        if not konkurs_info:
            self.bot.logger.warning(f"Nie znaleziono konkursu {message_id_str} do aktualizacji embedu.")
            return

        nagroda = konkurs_info[5]
        czas_zakonczenia_ts = konkurs_info[8]
        liczba_zwyciezcow_db = konkurs_info[6]
        wymagana_rola_id_str = konkurs_info[9]
        tworca_id_str = konkurs_info[4]

        uczestnicy_db_ids = await self.bot.baza_danych.pobierz_uczestnikow_konkursu(message_id_str)
        liczba_uczestnikow = len(uczestnicy_db_ids)

        tworca = None
        if tworca_id_str:
            try:
                tworca = self.bot.get_user(int(tworca_id_str)) or await self.bot.fetch_user(int(tworca_id_str))
            except (ValueError, discord.NotFound):
                self.bot.logger.warning(f"Nie można pobrać twórcy konkursu o ID: {tworca_id_str}")

        description = f"🎁 **Nagroda:** {nagroda}\n"
        if not zakonczony:
            description += f"⌛ **Zakończenie:** <t:{czas_zakonczenia_ts}:R> (<t:{czas_zakonczenia_ts}:F>)\n"
            description += f"🏆 **Liczba zwycięzców:** {liczba_zwyciezcow_db}\n"
            description += f"👥 **Liczba uczestników:** {liczba_uczestnikow}\n"
            if wymagana_rola_id_str and message.guild:
                try:
                    rola = message.guild.get_role(int(wymagana_rola_id_str))
                    if rola: description += f"🛡️ **Wymagana rola:** {rola.mention}\n"
                except ValueError: pass
            description += f"\n🎉 Kliknij przycisk poniżej, aby dołączyć do losowania!"
            embed_title = f"{config.GIVEAWAY_EMOJI_DEFAULT} Konkurs Aktywny! {config.GIVEAWAY_EMOJI_DEFAULT}"
            embed_color = config.GIVEAWAY_COLOR_DEFAULT
        else:
            description += f"Konkurs zakończył się <t:{int(time.time())}:R>.\n"
            description += f"👥 **Liczba uczestników (w momencie zakończenia):** {liczba_uczestnikow}\n"
            embed_title = f"{config.GIVEAWAY_EMOJI_DEFAULT} Konkurs Zakończony! {config.GIVEAWAY_EMOJI_DEFAULT}"
            embed_color = discord.Color.dark_grey()
            if zwyciezcy_ids:
                zwyciezcy_mentions = [f"<@{uid}>" for uid in zwyciezcy_ids]
                description += f"\n👑 **Zwycięzc{'a' if len(zwyciezcy_mentions) == 1 else 'y'} ({len(zwyciezcy_mentions)}):** {', '.join(zwyciezcy_mentions)}"
            else:
                description += "\n😢 **Brak zwycięzców** (nikt nie dołączył lub nie spełnił warunków)."

        embed = await self._create_giveaway_embed(
            typing.cast(discord.TextChannel, message.channel),
            title=embed_title,
            description=description,
            color=embed_color
        )
        if tworca:
            embed.set_author(name=f"Konkurs od {tworca.display_name}", icon_url=tworca.display_avatar.url if tworca.display_avatar else None)
        else:
            embed.set_author(name="Konkurs od Strażników Kronik", icon_url=(self.bot.user.avatar.url if self.bot.user and self.bot.user.avatar else None))

        try:
            view_to_set = None
            if not zakonczony and message.id in self.active_giveaway_views:
                 view_to_set = self.active_giveaway_views[message.id]
                 for item in view_to_set.children:
                     if isinstance(item, GiveawayJoinButton):
                         item.disabled = False

            if zakonczony:
                if message.id in self.active_giveaway_views:
                    active_view = self.active_giveaway_views.pop(message.id)
                    for item in active_view.children:
                        if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                            item.disabled = True
                    await message.edit(embed=embed, view=active_view)
                    active_view.stop()
                else:
                    await message.edit(embed=embed, view=None)
            else:
                await message.edit(embed=embed, view=view_to_set)

        except discord.HTTPException as e:
            self.bot.logger.error(f"Nie udało się zaktualizować embedu konkursu {message_id_str}: {e}")


    @tasks.loop(seconds=config.GIVEAWAY_CHECK_INTERVAL)
    async def end_giveaways_task(self):
        if self.bot.baza_danych is None:
            return

        try:
            konkursy_do_zakonczenia = await self.bot.baza_danych.pobierz_zakonczone_konkursy_do_ogloszenia()
            if not konkursy_do_zakonczenia:
                return

            for konkurs_tuple in konkursy_do_zakonczenia:
                (konkurs_db_id, server_id_str, kanal_id_str, msg_id_str,
                 tworca_id_str, nagroda, l_zwyc, czas_startu_ts, czas_konca_ts,
                 req_rola_id_str, czy_zakonczony_db, zwyciezcy_json_db) = konkurs_tuple

                self.bot.logger.info(f"Kończenie konkursu ID: {konkurs_db_id}, Wiadomość ID: {msg_id_str}, Nagroda: {nagroda}")

                guild = self.bot.get_guild(int(server_id_str))
                if not guild:
                    self.bot.logger.warning(f"Nie znaleziono serwera {server_id_str} dla konkursu {konkurs_db_id}. Oznaczam jako zakończony.")
                    await self.bot.baza_danych.zakoncz_konkurs(konkurs_db_id, [])
                    continue

                channel = guild.get_channel(int(kanal_id_str))
                if not channel or not isinstance(channel, discord.TextChannel):
                    self.bot.logger.warning(f"Nie znaleziono kanału tekstowego {kanal_id_str} dla konkursu {konkurs_db_id}. Oznaczam jako zakończony.")
                    await self.bot.baza_danych.zakoncz_konkurs(konkurs_db_id, [])
                    continue

                try:
                    giveaway_message = await channel.fetch_message(int(msg_id_str))
                except (discord.NotFound, discord.Forbidden):
                    self.bot.logger.warning(f"Nie można pobrać wiadomości {msg_id_str} dla konkursu {konkurs_db_id}. Oznaczam jako zakończony.")
                    await self.bot.baza_danych.zakoncz_konkurs(konkurs_db_id, [])
                    continue

                uczestnicy_db_ids = await self.bot.baza_danych.pobierz_uczestnikow_konkursu(msg_id_str)
                rzeczywisci_uczestnicy_ids = []

                if req_rola_id_str:
                    try:
                        required_role_id_int = int(req_rola_id_str)
                        required_role = guild.get_role(required_role_id_int)
                        if required_role:
                            for user_id_str_from_db in uczestnicy_db_ids:
                                member = guild.get_member(int(user_id_str_from_db))
                                if member and required_role in member.roles:
                                    rzeczywisci_uczestnicy_ids.append(user_id_str_from_db)
                        else:
                            rzeczywisci_uczestnicy_ids = []
                            self.bot.logger.warning(f"Wymagana rola ID {req_rola_id_str} nie istnieje na serwerze {guild.name} dla konkursu {konkurs_db_id}.")
                    except ValueError:
                        self.bot.logger.warning(f"Nieprawidłowe ID roli '{req_rola_id_str}' w konkursie {konkurs_db_id}. Traktuję jak brak wymaganej roli.")
                        rzeczywisci_uczestnicy_ids = uczestnicy_db_ids
                else:
                    rzeczywisci_uczestnicy_ids = uczestnicy_db_ids

                zwyciezcy_ids = []
                if rzeczywisci_uczestnicy_ids:
                    liczba_do_wylosowania = min(l_zwyc, len(rzeczywisci_uczestnicy_ids))
                    if liczba_do_wylosowania > 0:
                        zwyciezcy_ids = random.sample(rzeczywisci_uczestnicy_ids, k=liczba_do_wylosowania)

                await self.bot.baza_danych.zakoncz_konkurs(konkurs_db_id, zwyciezcy_ids)
                await self.aktualizuj_embed_konkursu(giveaway_message, msg_id_str, zakonczony=True, zwyciezcy_ids=zwyciezcy_ids)

                active_view = self.active_giveaway_views.pop(giveaway_message.id, None)
                if active_view:
                    active_view.stop()

                # Przyznawanie osiągnięć i misji za wygraną
                if zwyciezcy_ids and self.bot.baza_danych:
                    for zwyciezca_id_str in zwyciezcy_ids:
                        try:
                            zwyciezca_member = guild.get_member(int(zwyciezca_id_str))
                            if zwyciezca_member:
                                # Osiągnięcie
                                nowa_liczba_wygranych = await self.bot.baza_danych.inkrementuj_liczbe_wygranych_konkursow(zwyciezca_id_str, server_id_str)
                                await self.bot.sprawdz_i_przyznaj_osiagniecia(zwyciezca_member, guild, "liczba_wygranych_konkursow", nowa_liczba_wygranych)
                                # Misja
                                await self.bot.aktualizuj_i_sprawdz_misje_po_akcji(zwyciezca_member, guild, "wygraj_konkurs_od_resetu", 1)
                        except Exception as e_ach_miss:
                            self.bot.logger.error(f"Błąd podczas przyznawania osiągnięcia/misji za wygrany konkurs dla {zwyciezca_id_str}: {e_ach_miss}", exc_info=True)


                if zwyciezcy_ids:
                    zwyciezcy_mentions = [f"<@{uid}>" for uid in zwyciezcy_ids]
                    ogloszenie = f"🎉 Gratulacje {', '.join(zwyciezcy_mentions)}! Wygraliście **{nagroda}** w konkursie!"
                else:
                    ogloszenie = f"Niestety, konkurs na **{nagroda}** zakończył się bez zwycięzców (brak uprawnionych uczestników)."

                try:
                    await channel.send(ogloszenie, reference=giveaway_message, allowed_mentions=discord.AllowedMentions(users=True))
                except discord.HTTPException as e:
                    self.bot.logger.error(f"Nie udało się wysłać ogłoszenia o zwycięzcach dla konkursu {konkurs_db_id}: {e}")

        except Exception as e:
            self.bot.logger.error(f"Błąd w pętli end_giveaways_task: {e}", exc_info=True)


    @end_giveaways_task.before_loop
    async def before_end_giveaways_task(self):
        await self.bot.wait_until_ready()
        self.bot.logger.info("Pętla kończenia konkursów (end_giveaways_task) gotowa do startu.")

    @commands.hybrid_group(name="giveaway", aliases=["g", "konkurs"], description="Zarządzanie konkursami na serwerze.")
    @has_permissions(manage_guild=True)
    async def giveaway(self, context: Context):
        if context.invoked_subcommand is None:
            embed = await self._create_giveaway_embed(context,
                title=f"{config.GIVEAWAY_EMOJI_DEFAULT} System Konkursów Kronik Elary",
                description=f"Użyj podkomend, aby zarządzać konkursami. Np. `{context.prefix}giveaway start`.\n"
                            f"Dostępne podkomendy: `start`, `list`, `end`, `reroll`.",
                color=config.KOLOR_BOT_INFO
            )
            await context.send(embed=embed, ephemeral=True)


    @giveaway.command(name="start", description="Rozpoczyna nowy konkurs (giveaway).")
    @has_permissions(manage_guild=True)
    @app_commands.describe(
        czas_trwania="Czas trwania (np. 10m, 1h, 2d). Jednostki: s, m, h, d, w.",
        liczba_zwyciezcow="Ilu zwycięzców wylosować (domyślnie 1).",
        nagroda="Co jest do wygrania?",
        kanal="Kanał, na którym ogłosić konkurs (domyślnie bieżący).",
        wymagana_rola="Opcjonalna rola wymagana do udziału."
    )
    async def giveaway_start(self, context: Context, czas_trwania: str, nagroda: str, liczba_zwyciezcow: int = 1,
                             kanal: typing.Optional[discord.TextChannel] = None,
                             wymagana_rola: typing.Optional[discord.Role] = None):
        if not context.guild or self.bot.baza_danych is None:
            await context.send("Błąd systemowy. Spróbuj ponownie później.", ephemeral=True); return

        target_channel = kanal or typing.cast(discord.TextChannel, context.channel)
        if not isinstance(target_channel, discord.TextChannel):
            await context.send("Konkurs można ogłosić tylko na kanale tekstowym.", ephemeral=True); return

        sekundy_trwania = Giveaway.parse_duration(czas_trwania)
        if sekundy_trwania is None or sekundy_trwania <= 0:
            embed_error = await self._create_giveaway_embed(context, title="🚫 Błędny Czas Trwania", description="Podano nieprawidłowy format czasu trwania. Użyj np. `10m`, `2h30m`, `1d`. Dozwolone jednostki: s, m, h, d, w.", color=config.KOLOR_BOT_BLAD)
            await context.send(embed=embed_error, ephemeral=True); return

        if liczba_zwyciezcow <= 0:
            embed_error = await self._create_giveaway_embed(context, title="🚫 Błędna Liczba Zwycięzców", description="Liczba zwycięzców musi być większa od zera.", color=config.KOLOR_BOT_BLAD)
            await context.send(embed=embed_error, ephemeral=True); return

        czas_zakonczenia_ts = int(time.time()) + sekundy_trwania
        wymagana_rola_id_str = str(wymagana_rola.id) if wymagana_rola else None

        description = f"🎁 **Nagroda:** {nagroda}\n"
        description += f"⌛ **Zakończenie:** <t:{czas_zakonczenia_ts}:R> (<t:{czas_zakonczenia_ts}:F>)\n"
        description += f"🏆 **Liczba zwycięzców:** {liczba_zwyciezcow}\n"
        description += f"👥 **Liczba uczestników:** 0\n"
        if wymagana_rola:
            description += f"🛡️ **Wymagana rola:** {wymagana_rola.mention}\n"
        description += f"\n🎉 Kliknij przycisk poniżej, aby dołączyć do losowania!"

        embed = await self._create_giveaway_embed(
            context,
            title=f"{config.GIVEAWAY_EMOJI_DEFAULT} Nowy Konkurs Rozpoczęty! {config.GIVEAWAY_EMOJI_DEFAULT}",
            description=description
        )
        author_icon_url = None
        if context.author and hasattr(context.author, 'display_avatar') and context.author.display_avatar:
             author_icon_url = context.author.display_avatar.url
        embed.set_author(name=f"Konkurs od {context.author.display_name if context.author else 'Strażników Kronik'}", icon_url=author_icon_url)

        try:
            view_timeout = float(sekundy_trwania + 3600)

            giveaway_message = await target_channel.send(embed=embed)

            view = GiveawayView(self, self.bot, str(giveaway_message.id), wymagana_rola.id if wymagana_rola else None, czas_zakonczenia_ts, timeout=view_timeout)
            view.message = giveaway_message
            await giveaway_message.edit(view=view)

            self.active_giveaway_views[giveaway_message.id] = view

            await self.bot.baza_danych.stworz_konkurs(
                str(context.guild.id), str(target_channel.id), str(giveaway_message.id),
                str(context.author.id if context.author else self.bot.user.id if self.bot.user else "0"),
                nagroda, liczba_zwyciezcow,
                czas_zakonczenia_ts, wymagana_rola_id_str
            )

            confirm_msg = f"Konkurs na **{nagroda}** został pomyślnie rozpoczęty na kanale {target_channel.mention}!"
            if context.interaction:
                if not context.interaction.response.is_done():
                    await context.interaction.response.send_message(confirm_msg, ephemeral=True)
                else:
                    await context.interaction.followup.send(confirm_msg, ephemeral=True)
            else:
                await context.send(confirm_msg, ephemeral=True, delete_after=15)

        except discord.Forbidden:
            await context.send(f"Nie mam uprawnień do wysłania wiadomości na kanale {target_channel.mention}.", ephemeral=True)
        except Exception as e:
            self.bot.logger.error(f"Błąd podczas tworzenia konkursu: {e}", exc_info=True)
            await context.send(f"Wystąpił nieoczekiwany błąd podczas tworzenia konkursu: {e}", ephemeral=True)

    @giveaway.command(name="list", description="Wyświetla listę aktywnych konkursów.")
    @has_permissions(manage_guild=True)
    async def giveaway_list(self, context: Context):
        if not context.guild or self.bot.baza_danych is None:
            await context.send("Błąd systemowy lub komenda użyta poza serwerem.", ephemeral=True); return

        aktywne_konkursy_db = await self.bot.baza_danych.pobierz_aktywne_konkursy_serwera(str(context.guild.id))
        embed = await self._create_giveaway_embed(context, title=f"{config.GIVEAWAY_EMOJI_DEFAULT} Aktywne Konkursy w Kronikach", color=config.KOLOR_BOT_INFO)

        if not aktywne_konkursy_db:
            embed.description = "Obecnie nie ma żadnych aktywnych konkursów. Sprawdzaj regularnie!"
        else:
            embed.description = "Oto lista konkursów, w których możesz jeszcze wziąć udział:\n"
            for konkurs_tuple in aktywne_konkursy_db:
                (konkurs_db_id, server_id_str, kanal_id_str, msg_id_str,
                 tworca_id_str, nagroda, l_zwyc, czas_startu_ts, koniec_ts,
                 req_rola_id_str, czy_zakonczony_db, zwyciezcy_json_db) = konkurs_tuple

                link_do_wiadomosci = f"https://discord.com/channels/{context.guild.id}/{kanal_id_str}/{msg_id_str}"

                pole_value = (f"Kończy się: <t:{koniec_ts}:R> (<t:{koniec_ts}:f>)\n"
                              f"Liczba zwycięzców: {l_zwyc}\n"
                              f"[Przejdź do konkursu]({link_do_wiadomosci}) (ID: `{msg_id_str}`)")
                embed.add_field(name=f"🎁 **{nagroda}**", value=pole_value, inline=False)
        await context.send(embed=embed, ephemeral=True)


    @giveaway.command(name="end", description="Natychmiast kończy aktywny konkurs.")
    @has_permissions(manage_guild=True)
    @app_commands.describe(id_wiadomosci_konkursu="ID wiadomości konkursu, który chcesz zakończyć.")
    async def giveaway_end(self, context: Context, id_wiadomosci_konkursu: str):
        if not context.guild or self.bot.baza_danych is None:
            await context.send("Błąd systemowy.", ephemeral=True); return

        try:
            msg_id_int = int(id_wiadomosci_konkursu)
        except ValueError:
            await context.send(f"Nieprawidłowe ID wiadomości: `{id_wiadomosci_konkursu}`.", ephemeral=True); return

        konkurs_info = await self.bot.baza_danych.pobierz_konkurs_po_wiadomosci_id(str(msg_id_int))
        if not konkurs_info:
            await context.send(f"Nie znaleziono konkursu o ID wiadomości `{id_wiadomosci_konkursu}`.", ephemeral=True); return
        if konkurs_info[10]:
            await context.send(f"Ten konkurs (ID: `{id_wiadomosci_konkursu}`) już się zakończył.", ephemeral=True); return

        konkurs_db_id = konkurs_info[0]
        nagroda = konkurs_info[5]

        await self.bot.baza_danych.connection.execute(
            "UPDATE aktywne_konkursy SET czas_zakonczenia_ts = ? WHERE id_konkursu = ?",
            (int(time.time()) - 5, konkurs_db_id)
        )
        await self.bot.baza_danych.connection.commit()

        await context.send(f"Zlecono natychmiastowe zakończenie konkursu na **{nagroda}** (ID: {id_wiadomosci_konkursu}). Zwycięzcy zostaną wylosowani za chwilę przez automatyczny system.", ephemeral=True)


    @giveaway.command(name="reroll", description="Ponownie losuje zwycięzcę/zwycięzców dla zakończonego konkursu.")
    @has_permissions(manage_guild=True)
    @app_commands.describe(id_wiadomosci_konkursu="ID wiadomości zakończonego konkursu.")
    async def giveaway_reroll(self, context: Context, id_wiadomosci_konkursu: str):
        if not context.guild or self.bot.baza_danych is None:
            await context.send("Błąd systemowy.", ephemeral=True); return

        try:
            msg_id_int = int(id_wiadomosci_konkursu)
        except ValueError:
            await context.send(f"Nieprawidłowe ID wiadomości: `{id_wiadomosci_konkursu}`.", ephemeral=True); return

        konkurs_info = await self.bot.baza_danych.pobierz_konkurs_po_wiadomosci_id(str(msg_id_int))
        if not konkurs_info:
            await context.send(f"Nie znaleziono konkursu o ID wiadomości `{id_wiadomosci_konkursu}`.", ephemeral=True); return
        if not konkurs_info[10]:
            await context.send(f"Konkurs (ID: `{id_wiadomosci_konkursu}`) jeszcze się nie zakończył. Użyj `/giveaway end`, jeśli chcesz go zakończyć teraz.", ephemeral=True); return

        konkurs_db_id = konkurs_info[0]
        server_id_str = konkurs_info[1]
        nagroda = konkurs_info[5]
        liczba_zwyc = konkurs_info[6]
        req_rola_id_str = konkurs_info[9]
        kanal_id_str = konkurs_info[2]
        poprzedni_zwyciezcy_json = konkurs_info[11]

        guild = self.bot.get_guild(int(server_id_str))
        if not guild:
            await context.send("Nie można znaleźć serwera, na którym był konkurs.", ephemeral=True); return


        channel = guild.get_channel(int(kanal_id_str))
        if not channel or not isinstance(channel, discord.TextChannel):
            await context.send("Nie można znaleźć kanału, na którym był konkurs.", ephemeral=True); return

        try:
            giveaway_message = await channel.fetch_message(int(id_wiadomosci_konkursu))
        except (discord.NotFound, discord.Forbidden):
            await context.send("Nie można odnaleźć oryginalnej wiadomości konkursu.", ephemeral=True); return

        uczestnicy_db_ids = await self.bot.baza_danych.pobierz_uczestnikow_konkursu(str(msg_id_int))
        rzeczywisci_uczestnicy_ids = []
        if req_rola_id_str:
            try:
                required_role_id_int = int(req_rola_id_str)
                required_role = guild.get_role(required_role_id_int)
                if required_role:
                    for user_id_str_from_db in uczestnicy_db_ids:
                        member = guild.get_member(int(user_id_str_from_db))
                        if member and required_role in member.roles:
                            rzeczywisci_uczestnicy_ids.append(user_id_str_from_db)
            except ValueError:
                self.bot.logger.warning(f"Nieprawidłowe ID roli '{req_rola_id_str}' w konkursie {konkurs_db_id}")
                rzeczywisci_uczestnicy_ids = uczestnicy_db_ids
        else:
            rzeczywisci_uczestnicy_ids = uczestnicy_db_ids

        if not rzeczywisci_uczestnicy_ids:
            await context.send("Brak uprawnionych uczestników do ponownego losowania.", ephemeral=True); return

        poprzedni_zwyciezcy_ids_list = json.loads(poprzedni_zwyciezcy_json) if poprzedni_zwyciezcy_json else []

        kandydaci_do_reroll = [uid for uid in rzeczywisci_uczestnicy_ids if uid not in poprzedni_zwyciezcy_ids_list]

        if not kandydaci_do_reroll:
            if rzeczywisci_uczestnicy_ids and all(uid in poprzedni_zwyciezcy_ids_list for uid in rzeczywisci_uczestnicy_ids):
                 await context.send("Wszyscy uprawnieni uczestnicy już wygrali w poprzednich losowaniach tego konkursu. Brak nowych kandydatów do ponownego losowania.", ephemeral=True); return
            else:
                 await context.send("Brak dostępnych kandydatów do ponownego losowania (np. nikt nie spełnił warunków lub wszyscy już wygrali).", ephemeral=True); return

        nowi_zwyciezcy_ids = []
        liczba_do_wylosowania_reroll = min(liczba_zwyc, len(kandydaci_do_reroll))
        if liczba_do_wylosowania_reroll > 0:
            nowi_zwyciezcy_ids = random.sample(kandydaci_do_reroll, k=liczba_do_wylosowania_reroll)

        await self.bot.baza_danych.zakoncz_konkurs(konkurs_db_id, nowi_zwyciezcy_ids)

        # Przyznawanie osiągnięć i misji za wygraną w rerollu
        if nowi_zwyciezcy_ids and self.bot.baza_danych:
            for zwyciezca_id_str in nowi_zwyciezcy_ids:
                try:
                    zwyciezca_member = guild.get_member(int(zwyciezca_id_str))
                    if zwyciezca_member:
                        # Osiągnięcie
                        nowa_liczba_wygranych = await self.bot.baza_danych.inkrementuj_liczbe_wygranych_konkursow(zwyciezca_id_str, server_id_str)
                        await self.bot.sprawdz_i_przyznaj_osiagniecia(zwyciezca_member, guild, "liczba_wygranych_konkursow", nowa_liczba_wygranych)
                        # Misja
                        await self.bot.aktualizuj_i_sprawdz_misje_po_akcji(zwyciezca_member, guild, "wygraj_konkurs_od_resetu", 1)
                except Exception as e_ach_miss:
                    self.bot.logger.error(f"Błąd podczas przyznawania osiągnięcia/misji za wygrany konkurs (reroll) dla {zwyciezca_id_str}: {e_ach_miss}", exc_info=True)


        original_embed = giveaway_message.embeds[0] if giveaway_message.embeds else None
        if original_embed:
            embed = original_embed.copy()
            embed.title = f"{config.GIVEAWAY_EMOJI_DEFAULT} Ponowne Losowanie! {config.GIVEAWAY_EMOJI_DEFAULT}"
            embed.color = config.KOLOR_BOT_SUKCES
            new_description_parts = []
            if embed.description:
                for line in embed.description.split('\n'):
                    if "Nagroda:" in line or "Prize:" in line :
                        new_description_parts.append(line)
                        break
            if not new_description_parts: new_description_parts.append(f"**Nagroda:** {nagroda}")

            new_description_parts.append(f"Ponowne losowanie zakończyło się <t:{int(time.time())}:R>.")
            embed.description = "\n".join(new_description_parts)
            embed.clear_fields()
        else:
            embed = await self._create_giveaway_embed(
                typing.cast(discord.TextChannel, channel),
                title=f"{config.GIVEAWAY_EMOJI_DEFAULT} Ponowne Losowanie! {config.GIVEAWAY_EMOJI_DEFAULT}",
                description=f"**Nagroda:** {nagroda}\nPonowne losowanie zakończyło się <t:{int(time.time())}:R>.",
                color=config.KOLOR_BOT_SUKCES
            )

        nowi_zwyciezcy_mentions = [f"<@{uid}>" for uid in nowi_zwyciezcy_ids]

        if nowi_zwyciezcy_mentions:
            embed.add_field(name=f"👑 Now{'y' if len(nowi_zwyciezcy_mentions) == 1 else 'i'} Zwycięzc{'a' if len(nowi_zwyciezcy_mentions) == 1 else 'y'} ({len(nowi_zwyciezcy_mentions)}):", value=", ".join(nowi_zwyciezcy_mentions), inline=False)
            wiadomosc_ogloszenia_reroll = f"Nastąpiło ponowne losowanie! Gratulacje dla {', '.join(nowi_zwyciezcy_mentions)} za wygranie **{nagroda}**!"
        else:
            embed.add_field(name="😢 Brak Nowych Zwycięzców", value="Nie udało się wylosować nowych zwycięzców w ponownym losowaniu.", inline=False)
            wiadomosc_ogloszenia_reroll = f"Ponowne losowanie dla konkursu na **{nagroda}** nie wyłoniło nowych zwycięzców."

        try:
            await giveaway_message.edit(embed=embed, view=None)
            await channel.send(wiadomosc_ogloszenia_reroll, reference=giveaway_message, allowed_mentions=discord.AllowedMentions(users=True))
            await context.send(f"Pomyślnie przelosowano zwycięzców dla konkursu na **{nagroda}**.", ephemeral=True)
        except discord.HTTPException as e:
            self.bot.logger.error(f"Błąd podczas edycji wiadomości reroll konkursu {id_wiadomosci_konkursu}: {e}")
            await context.send("Wystąpił błąd podczas ogłaszania nowych zwycięzców.", ephemeral=True)

async def setup(bot: 'BotDiscord'):
    await bot.add_cog(Giveaway(bot))