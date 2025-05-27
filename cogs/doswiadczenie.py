import discord
from discord import app_commands, Interaction
from discord.ext import commands, tasks
from discord.ext.commands import Context, has_permissions
import time
from datetime import datetime, UTC, date as date_obj, timedelta

# Import konfiguracji
import config
import typing

if typing.TYPE_CHECKING:
    from bot import BotDiscord


class Doswiadczenie(commands.Cog, name="doświadczenie"):
    """📜 Kapsuła zarządzająca Mocą Opowieści (XP), poziomami, rankingami i bohaterskimi czynami (osiągnięciami) Kronikarzy."""
    COG_EMOJI = "📜"

    def __init__(self, bot: 'BotDiscord'):
        self.bot = bot

    async def _create_exp_embed(self, context: typing.Union[Context, Interaction], title: str, description: str = "", color: discord.Color = config.KOLOR_XP_PROFIL) -> discord.Embed:
        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.now(UTC))
        author_name = f"{self.bot.user.display_name} - System Doświadczenia" if self.bot.user else "System Doświadczenia Kronik Elary"
        author_icon_url = self.bot.user.avatar.url if self.bot.user and self.bot.user.avatar else None
        embed.set_author(name=author_name, icon_url=author_icon_url)

        guild_obj = None
        if isinstance(context, Context):
            guild_obj = context.guild
        elif isinstance(context, Interaction):
            guild_obj = context.guild

        if guild_obj and guild_obj.icon:
            embed.set_footer(text=f"Serwer: {guild_obj.name} | Kroniki Elary", icon_url=guild_obj.icon.url)
        else:
            embed.set_footer(text="Kroniki Elary")
        return embed

    @commands.hybrid_command(
        name="profil",
        description="Wyświetla Twój profil Kronikarza z poziomem, XP i Gwiezdnymi Dukatami."
    )
    @app_commands.describe(uzytkownik="Użytkownik, którego profil chcesz zobaczyć (opcjonalnie).")
    async def profil(self, context: Context, uzytkownik: typing.Optional[discord.Member] = None):
        target_user = uzytkownik if uzytkownik else context.author
        if not context.guild:
            await context.send("Tej komendy można używać tylko w granicach Kronik Elary (na serwerze).", ephemeral=True)
            return
        if self.bot.baza_danych is None:
            await context.send("Błąd: Archiwa Kronik są chwilowo niedostępne.", ephemeral=True)
            return
        if target_user.bot:
            await context.send("Elara szanuje prywatność innych botów - nie zagląda w ich mechanizmy.", ephemeral=True)
            return

        dane_xp_full = await self.bot.baza_danych.pobierz_lub_stworz_doswiadczenie(target_user.id, context.guild.id)
        xp_calkowite, poziom, czas_glosowy_sek = dane_xp_full[2], dane_xp_full[3], dane_xp_full[4]
        xp_zablokowane_indywidualnie, aktualny_streak, ostatni_dzien_streaka_iso = dane_xp_full[7], dane_xp_full[8], dane_xp_full[9]
        liczba_wiad, liczba_reak = dane_xp_full[10], dane_xp_full[11]

        dane_portfela = await self.bot.baza_danych.pobierz_lub_stworz_portfel(target_user.id, context.guild.id)
        dukaty, krysztaly = dane_portfela[2], dane_portfela[3]

        xp_do_nastepnego_poziomu_calkowite = self.bot.oblicz_xp_dla_poziomu(poziom)
        xp_bazowe_dla_obecnego_poziomu = self.bot.oblicz_xp_dla_poziomu(poziom - 1) if poziom > 0 else 0
        xp_na_obecnym_poziomie = max(0, xp_calkowite - xp_bazowe_dla_obecnego_poziomu)
        wymagane_xp_na_poziomie = max(1, xp_do_nastepnego_poziomu_calkowite - xp_bazowe_dla_obecnego_poziomu)

        procent_postepu = min(1.0, max(0.0, (xp_na_obecnym_poziomie / wymagane_xp_na_poziomie if wymagane_xp_na_poziomie > 0 else 0) ))
        pasek = "▓" * int(15 * procent_postepu) + "░" * (15 - int(15 * procent_postepu))

        embed_color = target_user.color if target_user.color != discord.Color.default() else config.KOLOR_XP_PROFIL
        embed = await self._create_exp_embed(context, title=f"📜 Karta Kronikarza: {target_user.display_name}", color=embed_color)
        if target_user.display_avatar: embed.set_thumbnail(url=target_user.display_avatar.url)

        embed.add_field(name="🌟 Poziom Opowieści", value=f"**{poziom}**", inline=True)
        embed.add_field(name="✨ Gwiezdne Dukaty", value=f"**{dukaty}**", inline=True)
        embed.add_field(name=f"{config.SYMBOL_WALUTY_PREMIUM} {config.NAZWA_WALUTY_PREMIUM}", value=f"**{krysztaly}**", inline=True)
        embed.add_field(name="🔮 Zdobywanie Mocy (XP)", value="Wyłączone" if xp_zablokowane_indywidualnie else "Włączone", inline=True)
        embed.add_field(name="💫 Całkowita Moc Opowieści (XP)", value=str(xp_calkowite), inline=False)
        embed.add_field(name="📊 Postęp do Następnego Poziomu", value=f"`{pasek}` ({procent_postepu*100:.1f}%)\n*{xp_na_obecnym_poziomie} / {wymagane_xp_na_poziomie} XP*", inline=False)
        embed.add_field(name="⏳ Czas na Głosowych Naradach", value=self.bot.formatuj_czas(czas_glosowy_sek), inline=True)

        ostatni_dzien_streaka_str = "Brak danych"
        if ostatni_dzien_streaka_iso:
            try: ostatni_dzien_streaka_str = date_obj.fromisoformat(ostatni_dzien_streaka_iso).strftime('%d.%m.%Y')
            except ValueError: ostatni_dzien_streaka_str = "Nieprawidłowa data"
        elif aktualny_streak == 0: ostatni_dzien_streaka_str = "Brak aktywnego streaka"
        embed.add_field(name="🔥 Płomień Aktywności (Streak)", value=f"{aktualny_streak} {'dzień' if aktualny_streak == 1 else 'dni'}\n(Ost. aktywność: {ostatni_dzien_streaka_str})", inline=True)
        embed.add_field(name="✒️ Zapiski Aktywności", value=f"Wysłane zwoje: {liczba_wiad}\nDodane pieczęcie: {liczba_reak}", inline=False)

        aktywne_bonusy_zakupione = await self.bot.baza_danych.pobierz_aktywne_zakupione_bonusy_xp_uzytkownika(str(target_user.id), str(context.guild.id))
        if aktywne_bonusy_zakupione:
            opis_bonusow = "".join([f"• **+{wartosc_b*100:.0f}%** XP (wygasa za: {self.bot.formatuj_czas(czas_wygasniecia_b - int(time.time()), precyzyjnie=True)})\n"
                                    for typ_b, wartosc_b, czas_wygasniecia_b in aktywne_bonusy_zakupione
                                    if typ_b == "xp_mnoznik" and czas_wygasniecia_b and (czas_wygasniecia_b - int(time.time())) > 0] +
                                   [f"• **+{wartosc_b*100:.0f}%** XP (Stały)\n"
                                    for typ_b, wartosc_b, _ in aktywne_bonusy_zakupione if typ_b == "xp_mnoznik" and _ is None])
            if opis_bonusow: embed.add_field(name="🌌 Aktywne Artefakty Wzmocnienia", value=opis_bonusow.strip(), inline=False)

        zdobyte_tiery_db = await self.bot.baza_danych.pobierz_zdobyte_osiagniecia_uzytkownika(str(target_user.id), str(context.guild.id))
        zdobyte_tiery_ids = {tier_id for tier_id, _ in zdobyte_tiery_db}
        odznaki_do_wyswietlenia = []
        for os_bazowe_dane in self.bot.DEFINICJE_OSIAGNIEC.values():
            for tier_dane in os_bazowe_dane.get("tiery", []):
                if tier_dane["id"] in zdobyte_tiery_ids and tier_dane.get("odznaka_emoji"):
                    odznaki_do_wyswietlenia.append(tier_dane["odznaka_emoji"])

        if odznaki_do_wyswietlenia:
            max_odznak_w_profilu = 5
            embed.add_field(name="🎖️ Zdobyte Odznaki", value=" ".join(odznaki_do_wyswietlenia[:max_odznak_w_profilu]) + (f" ... (i {len(odznaki_do_wyswietlenia) - max_odznak_w_profilu} więcej)" if len(odznaki_do_wyswietlenia) > max_odznak_w_profilu else ""), inline=False)


        embed.set_footer(text=f"ID Kronikarza: {target_user.id} | Kroniki Elary", icon_url=context.guild.icon.url if context.guild.icon else None)
        await context.send(embed=embed)

    @commands.hybrid_command(name="rankingxp", description="Wyświetla ranking Mocy Opowieści (XP) w Kronikach.")
    async def rankingxp(self, context: Context):
        if not context.guild or self.bot.baza_danych is None: await context.send("Błąd.", ephemeral=True); return
        ranking = await self.bot.baza_danych.pobierz_ranking_xp(context.guild.id, limit=10)
        embed = await self._create_exp_embed(context, title=f"🏆 Najpotężniejsi Kronikarze Serwera {context.guild.name}", color=config.KOLOR_XP_RANKING)
        if context.guild.icon: embed.set_thumbnail(url=context.guild.icon.url)
        if not ranking: embed.description = "Księga Mocy jest pusta."
        else:
            opis_list = []
            medale = ["🥇", "🥈", "🥉"]
            for i, (uid_str, xp, poz) in enumerate(ranking): # uid jest stringiem z bazy
                uid = int(uid_str)
                uzytkownik_obj = context.guild.get_member(uid)
                nazwa_uzytkownika = uzytkownik_obj.display_name if uzytkownik_obj else f"Nieznany ({uid})"
                medal_str = medale[i] if i < len(medale) else f"**{i+1}.**"
                opis_list.append(f"{medal_str} {nazwa_uzytkownika} - Poziom: **{poz}**, XP: **{xp}**")
            embed.description = "\n".join(opis_list)
        embed.set_footer(text="Niech Twoja legenda rośnie!", icon_url=context.guild.icon.url if context.guild.icon else None)
        await context.send(embed=embed)

    @commands.hybrid_command(name="rankingmiesiecznyxp", aliases=["miesiecznyrankingxp", "topxpsezon"], description="Wyświetla miesięczny ranking XP.")
    @app_commands.describe(
        rok="Rok, dla którego wyświetlić ranking (opcjonalnie, domyślnie bieżący/poprzedni).",
        miesiac="Miesiąc (1-12), dla którego wyświetlić ranking (opcjonalnie, domyślnie bieżący/poprzedni)."
    )
    async def rankingmiesiecznyxp(self, context: Context, rok: typing.Optional[int] = None, miesiac: typing.Optional[int] = None):
        if not context.guild or self.bot.baza_danych is None:
            await context.send("Ta komenda może być użyta tylko na serwerze, a baza danych musi być dostępna.", ephemeral=True)
            return

        teraz = datetime.now(UTC)
        
        if rok is None or miesiac is None:
            # Domyślnie pokaż ranking za bieżący miesiąc, jeśli nie jest zbyt wcześnie
            # lub za poprzedni, jeśli jest początek miesiąca
            if teraz.day < 3 and teraz.month == 1: # Jeśli jest 1 lub 2 stycznia, pokaż grudzień poprzedniego roku
                 docelowa_data_do_rankingu = datetime(teraz.year -1, 12, 1, tzinfo=UTC)
            elif teraz.day < 3 : # Jeśli jest 1 lub 2 dzień miesiąca (ale nie stycznia), pokaż poprzedni miesiąc
                 docelowa_data_do_rankingu = (teraz.replace(day=1) - timedelta(days=1)).replace(day=1)
            else: # W pozostałych przypadkach pokaż bieżący miesiąc
                 docelowa_data_do_rankingu = teraz.replace(day=1)
        else:
            if not (1 <= miesiac <= 12):
                await context.send("Nieprawidłowy numer miesiąca. Podaj liczbę od 1 do 12.", ephemeral=True)
                return
            try:
                docelowa_data_do_rankingu = datetime(rok, miesiac, 1, tzinfo=UTC)
            except ValueError:
                await context.send("Nieprawidłowa data. Sprawdź rok i miesiąc.", ephemeral=True)
                return
        
        rok_rankingu = docelowa_data_do_rankingu.year
        miesiac_rankingu = docelowa_data_do_rankingu.month
        
        nazwy_miesiecy = [
            "Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec",
            "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień"
        ]
        nazwa_miesiaca_pl = nazwy_miesiecy[miesiac_rankingu - 1]

        ranking_data = await self.bot.baza_danych.pobierz_ranking_miesiecznego_xp(str(context.guild.id), rok_rankingu, miesiac_rankingu, limit=10)

        embed = await self._create_exp_embed(
            context,
            title=f"🏆 Ranking Miesięczny XP - {nazwa_miesiaca_pl} {rok_rankingu}",
            color=config.KOLOR_RANKINGU_SEZONOWEGO
        )
        if context.guild.icon:
            embed.set_thumbnail(url=context.guild.icon.url)

        if not ranking_data:
            embed.description = f"Brak danych rankingowych dla {nazwa_miesiaca_pl} {rok_rankingu} na serwerze **{context.guild.name}**.\nMoże sezon się jeszcze nie rozpoczął lub nikt nie zdobył jeszcze XP w tym miesiącu?"
        else:
            opisy_rankingu = []
            medale = ["🥇", "🥈", "🥉"]
            for i, (user_id_db_str, xp_miesieczne) in enumerate(ranking_data):
                user_id_db = int(user_id_db_str)
                uzytkownik_obj = context.guild.get_member(user_id_db)
                nazwa_uzytkownika = uzytkownik_obj.display_name if uzytkownik_obj else f"Nieznany Kronikarz ({user_id_db})"
                medal_str = medale[i] if i < len(medale) else f"**{i+1}.**"
                opisy_rankingu.append(f"{medal_str} {nazwa_uzytkownika} - **{xp_miesieczne} XP**")
            embed.description = "\n".join(opisy_rankingu)
        
        embed.set_footer(text=f"Ranking dla {nazwa_miesiaca_pl} {rok_rankingu} | Kroniki Elary", icon_url=context.guild.icon.url if context.guild.icon else None)
        await context.send(embed=embed)

    @commands.hybrid_command(name="dodajrolenagrode", description="Dodaje rolę jako nagrodę za osiągnięcie poziomu.")
    @has_permissions(administrator=True)
    @app_commands.describe(poziom="Poziom, za który przyznawana jest rola.", rola="Rola-nagroda.")
    async def dodajrolenagrode(self, context: Context, poziom: int, rola: discord.Role):
        if not context.guild or self.bot.baza_danych is None or poziom <= 0: await context.send("Błąd.", ephemeral=True); return
        await self.bot.baza_danych.dodaj_nagrode_za_poziom(context.guild.id, poziom, rola.id)
        embed = await self._create_exp_embed(context, title="🛡️ Nagroda za Poziom Ustawiona", description=f"Rola {rola.mention} za Poziom **{poziom}**.", color=config.KOLOR_BOT_SUKCES)
        await context.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="usunrolenagrode", description="Usuwa nagrodę-rolę za dany poziom.")
    @has_permissions(administrator=True)
    @app_commands.describe(poziom="Poziom, dla którego usuwana jest nagroda.")
    async def usunrolenagrode(self, context: Context, poziom: int):
        if not context.guild or self.bot.baza_danych is None or poziom <= 0: await context.send("Błąd.", ephemeral=True); return
        if not await self.bot.baza_danych.pobierz_nagrode_za_poziom(context.guild.id, poziom):
            embed = await self._create_exp_embed(context, title="⚠️ Błąd", description=f"Brak nagrody dla Poziomu {poziom}.", color=config.KOLOR_BOT_BLAD)
            await context.send(embed=embed, ephemeral=True); return
        await self.bot.baza_danych.usun_nagrode_za_poziom(context.guild.id, poziom)
        embed = await self._create_exp_embed(context, title="🛡️ Nagroda Usunięta", description=f"Usunięto nagrodę za Poziom **{poziom}**.", color=config.KOLOR_BOT_SUKCES)
        await context.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="listujrolenagrody", description="Pokazuje listę nagród za poziomy.")
    @has_permissions(manage_guild=True)
    async def listujrolenagrody(self, context: Context):
        if not context.guild or self.bot.baza_danych is None: await context.send("Błąd.", ephemeral=True); return
        nagrody = await self.bot.baza_danych.pobierz_wszystkie_nagrody_za_poziom_serwera(context.guild.id)
        embed = await self._create_exp_embed(context, title=f"📜 Nagrody za Poziomy na {context.guild.name}", color=config.KOLOR_XP_ADMIN)
        if context.guild.icon: embed.set_thumbnail(url=context.guild.icon.url)
        if not nagrody: embed.description = "Brak skonfigurowanych nagród."
        else:
            opis_list = [f"**Poziom {p_val}:** {(context.guild.get_role(int(r_id)) or f'ID: {r_id} (Nieznana)').mention}" for p_val, r_id in nagrody]
            embed.description = "\n".join(opis_list)
        embed.set_footer(text="Niech ścieżka rozwoju będzie pełna chwały!", icon_url=context.guild.icon.url if context.guild.icon else None)
        await context.send(embed=embed, ephemeral=True)

    @commands.hybrid_group(name="xpadmin", description="Komendy administracyjne dla XP.")
    @has_permissions(manage_guild=True)
    async def xpadmin(self, context: Context):
        if not context.guild or context.invoked_subcommand is None:
            embed = await self._create_exp_embed(context, title="🛠️ Panel XP", description="Dostępne: `event`, `blokuj`, `odblokuj`, `liveranking`, `bonusroli`, `kanalyxp`, `resetujxp`, `blokujxpgracza`.", color=config.KOLOR_XP_ADMIN)
            await context.send(embed=embed, ephemeral=True)

    @xpadmin.command(name="event", description="Ustawia event XP (mnożnik).")
    @app_commands.describe(mnoznik="Mnożnik XP (np. 1.5, 1.0 aby wyłączyć).", nazwa_eventu="Nazwa eventu (opcjonalnie).")
    async def xpadmin_event(self, context: Context, mnoznik: float, nazwa_eventu: typing.Optional[str] = None):
        if not context.guild or mnoznik < 0.1: await context.send("Błąd.", ephemeral=True); return
        cfg = self.bot.pobierz_konfiguracje_xp_serwera(context.guild.id)
        cfg["mnoznik_xp"], cfg["nazwa_eventu"] = mnoznik, nazwa_eventu
        msg = f"🎉 Event **'{nazwa_eventu}'**! Mnożnik XP: **x{mnoznik}**." if nazwa_eventu and mnoznik != 1.0 else f"Mnożnik XP: **x{mnoznik}**." if mnoznik != 1.0 else "Mnożnik XP przywrócony (x1.0)."
        embed = await self._create_exp_embed(context, title="✨ Event XP Zaktualizowany", description=msg, color=config.KOLOR_BOT_SUKCES if mnoznik != 1.0 else config.KOLOR_BOT_INFO)
        await context.send(embed=embed)

    @xpadmin.command(name="blokuj", description="Blokuje zdobywanie XP na serwerze.")
    async def xpadmin_blokuj(self, context: Context):
        if not context.guild: await context.send("Błąd.", ephemeral=True); return
        self.bot.pobierz_konfiguracje_xp_serwera(context.guild.id)["xp_zablokowane"] = True
        embed = await self._create_exp_embed(context, title="🔒 Zdobywanie XP Zablokowane", description="Zdobywanie XP zostało globalnie **zablokowane**.", color=config.KOLOR_XP_ADMIN)
        await context.send(embed=embed)

    @xpadmin.command(name="odblokuj", description="Odblokowuje zdobywanie XP na serwerze.")
    async def xpadmin_odblokuj(self, context: Context):
        if not context.guild: await context.send("Błąd.", ephemeral=True); return
        self.bot.pobierz_konfiguracje_xp_serwera(context.guild.id)["xp_zablokowane"] = False
        embed = await self._create_exp_embed(context, title="🔓 Zdobywanie XP Odblokowane", description="Zdobywanie XP zostało globalnie **odblokowane**.", color=config.KOLOR_XP_ADMIN)
        await context.send(embed=embed)

    @xpadmin.command(name="liveranking", description="Ustawia kanał dla live rankingu XP.")
    @app_commands.describe(kanal="Kanał dla live rankingu (pozostaw puste, aby wyłączyć).")
    async def xpadmin_liveranking(self, context: Context, kanal: typing.Optional[discord.TextChannel] = None):
        if not context.guild: await context.send("Błąd.", ephemeral=True); return
        cfg = self.bot.pobierz_konfiguracje_xp_serwera(context.guild.id)
        if kanal is None:
            old_ch_id, old_msg_id = cfg.get("live_ranking_channel_id"), cfg.get("live_ranking_message_id")
            if old_ch_id and old_msg_id:
                try:
                    old_ch = await self.bot.fetch_channel(old_ch_id)
                    if isinstance(old_ch, discord.TextChannel):
                        old_msg = await old_ch.fetch_message(old_msg_id)
                        await old_msg.delete()
                except: pass
            cfg["live_ranking_channel_id"], cfg["live_ranking_message_id"] = None, None
            embed = await self._create_exp_embed(context, title="📊 Live Ranking Wyłączony", color=config.KOLOR_BOT_INFO)
            await context.send(embed=embed, ephemeral=True); return

        init_embed = await self._create_exp_embed(context, title="🏆 Live Ranking Kronik Elary 🏆", description="Inicjalizacja...", color=config.KOLOR_XP_RANKING)
        if context.guild.icon: init_embed.set_thumbnail(url=context.guild.icon.url)
        try:
            msg = await kanal.send(embed=init_embed)
            cfg["live_ranking_channel_id"], cfg["live_ranking_message_id"] = kanal.id, msg.id
            embed = await self._create_exp_embed(context, title="📊 Live Ranking Ustawiony", description=f"Ustawiono na {kanal.mention}.", color=config.KOLOR_BOT_SUKCES)
            await context.send(embed=embed, ephemeral=True)
            if self.bot.zadanie_live_ranking.is_running(): self.bot.zadanie_live_ranking.restart()
            else: self.bot.zadanie_live_ranking.start()
        except discord.Forbidden: await context.send(f"Brak uprawnień na {kanal.mention}.", ephemeral=True)
        except Exception as e: await context.send(f"Błąd: {e}", ephemeral=True)

    @xpadmin.group(name="bonusroli", description="Zarządza bonusami XP dla ról.")
    async def xpadmin_bonusroli(self, context: Context):
        if not context.guild or context.invoked_subcommand is None:
            embed = await self._create_exp_embed(context, title="🛠️ Bonusy XP dla Ról", description="Dostępne: `dodaj`, `usun`, `lista`.", color=config.KOLOR_XP_ADMIN)
            await context.send(embed=embed, ephemeral=True)

    @xpadmin_bonusroli.command(name="dodaj", description="Dodaje/aktualizuje bonus XP dla roli.")
    @app_commands.describe(rola="Rola.", mnoznik="Mnożnik XP (np. 1.2). 1.0 usuwa bonus.")
    async def xpadmin_bonusroli_dodaj(self, context: Context, rola: discord.Role, mnoznik: float):
        if not context.guild or self.bot.baza_danych is None or mnoznik < 0: await context.send("Błąd.", ephemeral=True); return
        await self.bot.baza_danych.ustaw_bonus_xp_roli(str(context.guild.id), str(rola.id), mnoznik)
        desc = f"Usunięto bonus dla {rola.mention}." if mnoznik == 1.0 else f"Ustawiono bonus **x{mnoznik}** dla {rola.mention}."
        color = config.KOLOR_BOT_INFO if mnoznik == 1.0 else config.KOLOR_BOT_SUKCES
        embed = await self._create_exp_embed(context, title="✨ Bonus XP Roli Zmieniony", description=desc, color=color)
        await context.send(embed=embed, ephemeral=True)

    @xpadmin_bonusroli.command(name="usun", description="Usuwa bonus XP dla roli.")
    @app_commands.describe(rola="Rola.")
    async def xpadmin_bonusroli_usun(self, context: Context, rola: discord.Role):
        if not context.guild or self.bot.baza_danych is None: await context.send("Błąd.", ephemeral=True); return
        await self.bot.baza_danych.ustaw_bonus_xp_roli(str(context.guild.id), str(rola.id), 1.0)
        embed = await self._create_exp_embed(context, title="✨ Bonus XP Roli Usunięty", description=f"Usunięto bonus dla {rola.mention}.", color=config.KOLOR_BOT_INFO)
        await context.send(embed=embed, ephemeral=True)

    @xpadmin_bonusroli.command(name="lista", description="Wyświetla role z bonusami XP.")
    async def xpadmin_bonusroli_lista(self, context: Context):
        if not context.guild or self.bot.baza_danych is None: await context.send("Błąd.", ephemeral=True); return
        bonusy = await self.bot.baza_danych.pobierz_bonusy_xp_rol_serwera(str(context.guild.id))
        embed = await self._create_exp_embed(context, title=f"✨ Bonusy XP dla Ról na {context.guild.name}", color=config.KOLOR_XP_ADMIN)
        if context.guild.icon: embed.set_thumbnail(url=context.guild.icon.url)
        if not bonusy: embed.description = "Brak ról z bonusami."
        else:
            opis_list = [f"{(context.guild.get_role(int(r_id)) or f'ID: {r_id}').mention}: Mnożnik **x{mn}**" for r_id, mn in bonusy if mn != 1.0]
            embed.description = "\n".join(opis_list) if opis_list else "Brak aktywnych bonusów (wszystkie x1.0)."
        await context.send(embed=embed, ephemeral=True)

    @xpadmin.group(name="kanalyxp", description="Zarządza ustawieniami XP dla kanałów.")
    async def xpadmin_kanalyxp(self, context: Context):
        if not context.guild or context.invoked_subcommand is None:
            embed = await self._create_exp_embed(context, title="🛠️ Ustawienia XP Kanałów", description="Dostępne: `ustaw`, `usun`, `lista`.", color=config.KOLOR_XP_ADMIN)
            await context.send(embed=embed, ephemeral=True)

    @xpadmin_kanalyxp.command(name="ustaw", description="Ustawia konfigurację XP dla kanału.")
    @app_commands.describe(kanal="Kanał.", blokuj_xp="Czy zablokować XP? (tak/nie)", mnoznik="Mnożnik XP (np. 0.5, 1.5). Domyślnie 1.0.")
    @app_commands.choices(blokuj_xp=[app_commands.Choice(name="Tak", value="tak"), app_commands.Choice(name="Nie", value="nie")])
    async def xpadmin_kanalyxp_ustaw(self, context: Context, kanal: typing.Union[discord.TextChannel, discord.VoiceChannel, discord.Thread], blokuj_xp: app_commands.Choice[str], mnoznik: float = 1.0):
        if not context.guild or self.bot.baza_danych is None or mnoznik < 0: await context.send("Błąd.", ephemeral=True); return
        czy_blokowac = blokuj_xp.value == "tak"
        await self.bot.baza_danych.ustaw_konfiguracje_xp_kanalu(str(context.guild.id), str(kanal.id), czy_blokowac, mnoznik)
        status_blokady = "zablokowane" if czy_blokowac else "odblokowane"
        embed = await self._create_exp_embed(context, title="⚙️ Konfiguracja Kanału Zmieniona", description=f"Kanał {kanal.mention}:\n- XP: **{status_blokady}**\n- Mnożnik: **x{mnoznik}**", color=config.KOLOR_BOT_SUKCES)
        await context.send(embed=embed, ephemeral=True)

    @xpadmin_kanalyxp.command(name="usun", description="Usuwa konfigurację XP dla kanału.")
    @app_commands.describe(kanal="Kanał.")
    async def xpadmin_kanalyxp_usun(self, context: Context, kanal: typing.Union[discord.TextChannel, discord.VoiceChannel, discord.Thread]):
        if not context.guild or self.bot.baza_danych is None: await context.send("Błąd.", ephemeral=True); return
        await self.bot.baza_danych.usun_konfiguracje_xp_kanalu(str(context.guild.id), str(kanal.id))
        embed = await self._create_exp_embed(context, title="⚙️ Konfiguracja Kanału Usunięta", description=f"Usunięto konfigurację dla {kanal.mention}.", color=config.KOLOR_BOT_INFO)
        await context.send(embed=embed, ephemeral=True)

    @xpadmin_kanalyxp.command(name="lista", description="Wyświetla kanały z niestandardową konfiguracją XP.")
    async def xpadmin_kanalyxp_lista(self, context: Context):
        if not context.guild or self.bot.baza_danych is None: await context.send("Błąd.", ephemeral=True); return
        konfiguracje = await self.bot.baza_danych.pobierz_wszystkie_konfiguracje_xp_kanalow_serwera(str(context.guild.id))
        embed = await self._create_exp_embed(context, title=f"⚙️ Konfiguracja XP Kanałów na {context.guild.name}", color=config.KOLOR_XP_ADMIN)
        if context.guild.icon: embed.set_thumbnail(url=context.guild.icon.url)
        if not konfiguracje: embed.description = "Brak kanałów z niestandardową konfiguracją."
        else:
            opis_list = [f"{(context.guild.get_channel(int(k_id)) or f'ID: {k_id}').mention}: {'**Zablokowane**' if zabl_int else 'Odblokowane'}, Mnożnik **x{mn}**" for k_id, zabl_int, mn in konfiguracje]
            embed.description = "\n".join(opis_list) if opis_list else "Brak kanałów z niestandardową konfiguracją."
        await context.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="xpustawienia", description="Zarządzaj swoimi ustawieniami zdobywania XP.")
    @app_commands.describe(status="Włącz lub wyłącz zdobywanie XP.")
    @app_commands.choices(status=[app_commands.Choice(name="Włącz", value="wlacz"), app_commands.Choice(name="Wyłącz", value="wylacz")])
    async def xpustawienia(self, context: Context, status: app_commands.Choice[str]):
        if not context.guild or self.bot.baza_danych is None: await context.send("Błąd.", ephemeral=True); return
        nowy_status_blokady = status.value == "wylacz"
        await self.bot.baza_danych.ustaw_indywidualna_blokade_xp(context.author.id, context.guild.id, nowy_status_blokady)
        msg = "Wyłączyłeś/aś zdobywanie XP." if nowy_status_blokady else "Włączyłeś/aś zdobywanie XP."
        title = "🚫 XP Wyłączone" if nowy_status_blokady else "✅ XP Włączone"
        color = config.KOLOR_BOT_INFO if nowy_status_blokady else config.KOLOR_BOT_SUKCES
        embed = await self._create_exp_embed(context, title=title, description=msg, color=color)
        await context.send(embed=embed, ephemeral=True)

    @commands.hybrid_group(name="osiagniecia", description="Wyświetla informacje o Twoich osiągnięciach.")
    async def osiagniecia(self, context: Context):
        if not context.guild: await context.send("Tylko w granicach Kronik.", ephemeral=True); return
        if context.invoked_subcommand is None:
            await self.wyswietl_osiagniecia_uzytkownika(context, context.author)

    @osiagniecia.command(name="pokaz", description="Pokazuje zdobyte osiągnięcia (Twoje lub innego Kronikarza).")
    @app_commands.describe(uzytkownik="Kronikarz, którego osiągnięcia chcesz zobaczyć (opcjonalnie).")
    async def osiagniecia_pokaz(self, context: Context, uzytkownik: typing.Optional[discord.Member] = None):
        if not context.guild: await context.send("Tylko w granicach Kronik.", ephemeral=True); return
        target_user = uzytkownik if uzytkownik else context.author
        await self.wyswietl_osiagniecia_uzytkownika(context, target_user)

    async def wyswietl_osiagniecia_uzytkownika(self, context: Context, target_user: discord.Member):
        if self.bot.baza_danych is None: await context.send("Błąd: Archiwa.", ephemeral=True); return

        zdobyte_tiery_db = await self.bot.baza_danych.pobierz_zdobyte_osiagniecia_uzytkownika(str(target_user.id), str(context.guild.id))
        zdobyte_tiery_ids = {tier_id for tier_id, _ in zdobyte_tiery_db}

        embed_color = target_user.color if target_user.color != discord.Color.default() else config.KOLOR_XP_OSIAGNIECIE
        embed = await self._create_exp_embed(context, title=f"🏆 Zapiski Bohaterskich Czynów: {target_user.display_name}", color=embed_color)
        if target_user.display_avatar: embed.set_thumbnail(url=target_user.display_avatar.url)

        opis_osiagniec_list = []
        liczba_zdobytych_tierow_jawnych = 0

        for os_bazowe_id, os_bazowe_dane in self.bot.DEFINICJE_OSIAGNIEC.items():
            czy_bazowe_ukryte = os_bazowe_dane.get("ukryte", False)
            zdobyte_tiery_tego_osiagniecia = []

            for tier_dane in os_bazowe_dane.get("tiery", []):
                if tier_dane["id"] in zdobyte_tiery_ids:
                    zdobyte_tiery_tego_osiagniecia.append(tier_dane)
                    if not czy_bazowe_ukryte:
                        liczba_zdobytych_tierow_jawnych +=1


            if zdobyte_tiery_tego_osiagniecia:
                najwyzszy_zdobyty_tier = max(zdobyte_tiery_tego_osiagniecia, key=lambda t: t["wartosc_warunku"])
                
                nazwa_wyswietlana = najwyzszy_zdobyty_tier.get("nazwa_tieru", os_bazowe_dane.get("nazwa_bazowa", "Nieznane Osiągnięcie"))
                opis_wyswietlany = najwyzszy_zdobyty_tier.get("opis_tieru", os_bazowe_dane.get("opis_bazowy", "Zdobyto!"))
                ikona_bazowa = os_bazowe_dane.get("ikona", "🏆")
                odznaka_tieru = najwyzszy_zdobyty_tier.get("odznaka_emoji", "")

                data_zdobycia_ts = next((ts for tid, ts in zdobyte_tiery_db if tid == najwyzszy_zdobyty_tier["id"]), None)
                data_str = f"<t:{data_zdobycia_ts}:D>" if data_zdobycia_ts else "Nieznana data"

                opis_osiagniec_list.append(f"{ikona_bazowa} {odznaka_tieru} **{nazwa_wyswietlana}**\n_{opis_wyswietlany}_\n*Zdobyto: {data_str}*")

        if not opis_osiagniec_list:
            embed.description = "Ten Kronikarz nie zapisał jeszcze żadnych bohaterskich czynów w Wielkiej Księdze."
        else:
            embed.description = "\n\n".join(opis_osiagniec_list)
        
        calkowita_liczba_jawnych_tierow = 0
        for os_id, os_dane in self.bot.DEFINICJE_OSIAGNIEC.items():
            if not os_dane.get("ukryte", False):
                calkowita_liczba_jawnych_tierow += len(os_dane.get("tiery", []))
        
        embed.set_footer(text=f"Zdobyto {liczba_zdobytych_tierow_jawnych} z {calkowita_liczba_jawnych_tierow} jawnych tierów osiągnięć.", icon_url=context.guild.icon.url if context.guild and context.guild.icon else None)
        await context.send(embed=embed, ephemeral=True if target_user != context.author else False)


    @osiagniecia.command(name="lista", description="Wyświetla listę wszystkich dostępnych bohaterskich czynów.")
    async def osiagniecia_lista(self, context: Context):
        if not context.guild: await context.send("Tylko w granicach Kronik.", ephemeral=True); return
        
        embed = await self._create_exp_embed(context, title="📜 Katalog Bohaterskich Czynów Kronik Elary", color=config.KOLOR_BOT_INFO)
        if context.guild and context.guild.icon: embed.set_thumbnail(url=context.guild.icon.url)

        if not self.bot.DEFINICJE_OSIAGNIEC:
            embed.description = "Wielka Księga Czynów jest obecnie pusta."
        else:
            lista_opisow_kategorie: typing.Dict[str, list[str]] = {}

            for os_bazowe_id, os_bazowe_dane in self.bot.DEFINICJE_OSIAGNIEC.items():
                if os_bazowe_dane.get("ukryte", False):
                    continue

                kategoria = os_bazowe_dane.get("kategoria_osiagniecia", "Inne")
                if kategoria not in lista_opisow_kategorie:
                    lista_opisow_kategorie[kategoria] = []

                ikona = os_bazowe_dane.get("ikona", "🏆")
                nazwa_bazowa = os_bazowe_dane.get("nazwa_bazowa", "Nieznane Osiągnięcie")
                opis_bazowy = os_bazowe_dane.get("opis_bazowy", "Brak opisu.")
                
                tiery_opis = []
                for tier_dane in os_bazowe_dane.get("tiery", []):
                    nazwa_tieru = tier_dane.get("nazwa_tieru", "Tier")
                    opis_tieru_tieru = tier_dane.get("opis_tieru", "Brak opisu tieru.")
                    wartosc_warunku = tier_dane.get("wartosc_warunku")
                    typ_warunku = os_bazowe_dane.get("typ_warunku_bazowy", "nieznany")
                    odznaka_tieru = tier_dane.get("odznaka_emoji", "")

                    nagrody_str_list = []
                    if tier_dane.get("nagroda_xp", 0) > 0: nagrody_str_list.append(f"{tier_dane['nagroda_xp']} XP")
                    if tier_dane.get("nagroda_dukaty", 0) > 0: nagrody_str_list.append(f"{tier_dane['nagroda_dukaty']} ✨")
                    if tier_dane.get("nagroda_krysztaly", 0) > 0: nagrody_str_list.append(f"{tier_dane['nagroda_krysztaly']} {config.SYMBOL_WALUTY_PREMIUM}")
                    if tier_dane.get("nagroda_rola_id") and context.guild:
                        try:
                            rola = context.guild.get_role(int(tier_dane["nagroda_rola_id"]))
                            if rola: nagrody_str_list.append(f"Rola: {rola.mention}")
                        except: pass
                    
                    nagrody_str = ", ".join(nagrody_str_list) if nagrody_str_list else "Chwała"
                    warunek_str = f"(Warunek: {typ_warunku.replace('_', ' ')} >= {wartosc_warunku})"
                    tiery_opis.append(f"  - {odznaka_tieru} **{nazwa_tieru}**: _{opis_tieru_tieru}_ {warunek_str}\n    *Nagroda: {nagrody_str}*")
                
                tiery_opis_str = "\n".join(tiery_opis) if tiery_opis else "  Brak zdefiniowanych tierów."
                lista_opisow_kategorie[kategoria].append(f"{ikona} **{nazwa_bazowa}**\n_{opis_bazowy}_\n{tiery_opis_str}")

            if not lista_opisow_kategorie:
                 embed.description = "W Kronikach nie ma obecnie jawnych bohaterskich czynów do odkrycia."
            else:
                final_description_parts = []
                for kategoria in sorted(lista_opisow_kategorie.keys()):
                    opisy_w_kategorii = lista_opisow_kategorie[kategoria]
                    final_description_parts.append(f"\n**✨ Kategoria: {kategoria}**\n" + "\n\n".join(opisy_w_kategorii))
                
                final_description = "\n".join(final_description_parts)
                if len(final_description) > 4000:
                    final_description = final_description[:3990] + "\n... (więcej osiągnięć dostępnych)"
                embed.description = final_description.strip()
        
        await context.send(embed=embed, ephemeral=True)

async def setup(bot: 'BotDiscord'):
    await bot.add_cog(Doswiadczenie(bot))