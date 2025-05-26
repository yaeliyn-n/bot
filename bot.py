# WERSJA KODU: BOT_PY_VERY_FINAL_CHECK_27_05_A
"""
Copyright © Krypton 2019-Present - https://github.com/kkrypt0nn (https://krypton.ninja)
Opis:
🐍 Prosty szablon do rozpoczęcia kodowania własnego i spersonalizowanego bota Discord w Pythonie

Wersja: 6.3.0
"""

import json
import logging
import os
import platform
import random
import sys
import time
import asyncio
from datetime import datetime, UTC, date as date_obj, timedelta, timezone, time as time_obj
import typing

import aiosqlite
import discord
from discord.ext import commands, tasks
from discord.ext.commands import Context
from dotenv import load_dotenv

from database import ZarzadcaBazyDanych
import config

load_dotenv()

# --- Konfiguracja Zmiennych Środowiskowych ---
PREFIX_ENV = os.getenv("PREFIX", "!")
TOKEN_ENV = os.getenv("TOKEN")
INVITE_LINK_ENV = os.getenv("INVITE_LINK")
WELCOME_CHANNEL_ID_ENV = os.getenv("WELCOME_CHANNEL_ID")
DEFAULT_ROLE_ID_ENV = os.getenv("DEFAULT_ROLE_ID")
API_PORT_ENV = os.getenv("API_PORT")
API_KEY_ENV = os.getenv("API_KEY")
MAIN_SERVER_ID_ENV = os.getenv("MAIN_SERVER_ID")
# --- Koniec Konfiguracji Zmiennych ---


intencje = discord.Intents.default()
intencje.members = True
intencje.voice_states = True
intencje.reactions = True
intencje.message_content = True

class FormatterLogowania(logging.Formatter):
    czarny = "\x1b[30m"; czerwony = "\x1b[31m"; zielony = "\x1b[32m"; zolty = "\x1b[33m"
    niebieski = "\x1b[34m"; szary = "\x1b[38m"; reset = "\x1b[0m"; pogrubienie = "\x1b[1m"
    KOLORY = {
        logging.DEBUG: szary + pogrubienie, logging.INFO: niebieski + pogrubienie,
        logging.WARNING: zolty + pogrubienie, logging.ERROR: czerwony,
        logging.CRITICAL: czerwony + pogrubienie,
    }
    def format(self, record):
        kolor_logu = self.KOLORY.get(record.levelno, self.szary + self.pogrubienie)
        format_str = "(czarny){asctime}(reset) (kolor_poziomu){levelname:<8}(reset) (zielony){name}(reset) {message}"
        format_str = format_str.replace("(czarny)", self.czarny + self.pogrubienie).replace("(reset)", self.reset)
        format_str = format_str.replace("(kolor_poziomu)", kolor_logu).replace("(zielony)", self.zielony + self.pogrubienie)
        formatter = logging.Formatter(format_str, "%Y-%m-%d %H:%M:%S", style="{")
        return formatter.format(record)

logger = logging.getLogger("discord_bot")
logger.setLevel(logging.INFO)
handler_konsoli = logging.StreamHandler()
handler_konsoli.setFormatter(FormatterLogowania())
handler_pliku = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w")
formatter_handler_pliku = logging.Formatter(
    "[{asctime}] [{levelname:<8}] {name}: {message}", "%Y-%m-%d %H:%M:%S", style="{"
)
handler_pliku.setFormatter(formatter_handler_pliku)
logger.addHandler(handler_konsoli)
logger.addHandler(handler_pliku)

class BotDiscord(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned_or(PREFIX_ENV),
            intents=intencje,
            help_command=None
        )
        self.logger = logger
        self.baza_danych: typing.Optional[ZarzadcaBazyDanych] = None
        self.prefix_bota = PREFIX_ENV
        self.link_zaproszenia = INVITE_LINK_ENV
        self.welcome_channel_id = int(WELCOME_CHANNEL_ID_ENV) if WELCOME_CHANNEL_ID_ENV and WELCOME_CHANNEL_ID_ENV.isdigit() else None
        self.default_role_id = int(DEFAULT_ROLE_ID_ENV) if DEFAULT_ROLE_ID_ENV and DEFAULT_ROLE_ID_ENV.isdigit() else None
        self.api_port = int(API_PORT_ENV) if API_PORT_ENV and API_PORT_ENV.isdigit() else 8080
        self.api_key = API_KEY_ENV
        self.main_server_id = int(MAIN_SERVER_ID_ENV) if MAIN_SERVER_ID_ENV and MAIN_SERVER_ID_ENV.isdigit() else None

        self.aktywni_na_glosowym_start_time: dict[int, dict[int, float]] = {}
        self.konfiguracja_xp_serwera: dict[int, dict] = {}
        self.DEFINICJE_OSIAGNIEC = config.DEFINICJE_OSIAGNIEC
        self.DEFINICJE_MISJI = config.DEFINICJE_MISJI

        self.ostatni_reset_misji_dziennych_ts: int = 0
        self.ostatni_reset_misji_tygodniowych_ts: int = 0

    def formatuj_czas(self, sekundy: int, precyzyjnie: bool = False) -> str:
        if sekundy < 0: sekundy = 0
        dni, pozostale_sekundy = divmod(sekundy, 86400)
        godziny, pozostale_sekundy = divmod(pozostale_sekundy, 3600)
        minuty, sekundy_finalne = divmod(pozostale_sekundy, 60)
        czesci = []
        if dni > 0: czesci.append(f"{int(dni)} {'dzień' if dni == 1 else ('dni' if 1 < dni < 5 else 'dni')}")
        if godziny > 0: czesci.append(f"{int(godziny)} {'godz.' if precyzyjnie else 'g'}")
        if minuty > 0: czesci.append(f"{int(minuty)} {'min.' if precyzyjnie else 'm'}")
        if sekundy_finalne > 0 or (not czesci and precyzyjnie) or (not czesci and not precyzyjnie):
            czesci.append(f"{int(sekundy_finalne)} {'sek.' if precyzyjnie else 's'}")
        return " ".join(czesci) if czesci else ("0 sek." if precyzyjnie else "0s")

    def pobierz_konfiguracje_xp_serwera(self, server_id: int) -> dict:
        if server_id not in self.konfiguracja_xp_serwera:
            self.konfiguracja_xp_serwera[server_id] = {
                "xp_zablokowane": False,
                "mnoznik_xp": 1.0,
                "nazwa_eventu": None,
                "live_ranking_message_id": None,
                "live_ranking_channel_id": None,
            }
        return self.konfiguracja_xp_serwera[server_id]

    async def inicjalizuj_bd(self) -> None:
        db_path = f"{os.path.realpath(os.path.dirname(__file__))}/database/database.db"
        schema_path = f"{os.path.realpath(os.path.dirname(__file__))}/database/schema.sql"

        self.logger.info(f"Ścieżka do bazy danych: {db_path}")
        self.logger.info(f"Ścieżka do pliku schematu: {schema_path}")

        if not os.path.exists(schema_path):
            self.logger.critical(f"KRYTYCZNY BŁĄD: Nie znaleziono pliku schematu bazy danych w: {schema_path}")
            self.logger.critical("Bot nie może kontynuować bez schematu bazy danych. Zamykanie...")
            await self.close()
            sys.exit("Brak pliku schema.sql")
            return

        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        self.logger.info("Próba połączenia z bazą danych i wykonania skryptu schematu...")
        async with aiosqlite.connect(db_path) as db:
            try:
                with open(schema_path, "r", encoding="utf-8") as plik_schematu:
                    schema_content = plik_schematu.read()
                    self.logger.debug(f"Zawartość pliku schematu (pierwsze 500 znaków):\n{schema_content[:500]}")
                    self.logger.info("Rozpoczynam wykonywanie skryptu schematu...")
                    await db.executescript(schema_content)
                    self.logger.info("Pomyślnie ZAKOŃCZONO wykonywanie skryptu schematu bazy danych dla Kronik Elary.")
            except FileNotFoundError:
                self.logger.error(f"Nie znaleziono pliku schematu: {schema_path}")
            except aiosqlite.Error as e_sqlite:
                self.logger.error(f"Błąd SQLite podczas wykonywania skryptu schematu bazy danych: {e_sqlite}", exc_info=True)
                self.logger.critical("Bot nie może kontynuować z powodu błędu bazy danych. Sprawdź plik schema.sql. Zamykanie...")
                await self.close()
                sys.exit(f"Błąd SQLite w schema.sql: {e_sqlite}")
                return
            except Exception as e:
                self.logger.error(f"Ogólny błąd podczas wykonywania skryptu schematu bazy danych: {e}", exc_info=True)
                self.logger.critical("Bot nie może kontynuować z powodu błędu bazy danych. Zamykanie...")
                await self.close()
                sys.exit(f"Ogólny błąd w schema.sql: {e}")
                return

            self.logger.info("Próba wykonania db.commit()...")
            await db.commit()
            self.logger.info("db.commit() wykonany pomyślnie.")

    async def zaladuj_kapsuly(self) -> None:
        cogs_dir = f"{os.path.realpath(os.path.dirname(__file__))}/cogs"
        if not os.path.exists(cogs_dir):
            os.makedirs(cogs_dir)
            self.logger.info(f"Utworzono katalog cogs: {cogs_dir}")

        for plik in os.listdir(cogs_dir):
            if plik.endswith(".py"):
                rozszerzenie = plik[:-3]
                try:
                    await self.load_extension(f"cogs.{rozszerzenie}")
                    self.logger.info(f"Załadowano kapsułę '{rozszerzenie}' dla Kronik Elary.")
                except commands.ExtensionAlreadyLoaded:
                    self.logger.info(f"Kapsuła '{rozszerzenie}' była już załadowana.")
                except commands.ExtensionNotFound:
                    self.logger.error(f"Nie znaleziono kapsuły '{rozszerzenie}'.")
                except commands.NoEntryPointError:
                    self.logger.error(f"Kapsuła '{rozszerzenie}' nie posiada funkcji `setup`.")
                except Exception as e:
                    self.logger.error(f"Błąd ładowania kapsuły {rozszerzenie}: {type(e).__name__}: {e}", exc_info=True)

    @tasks.loop(minutes=1.0)
    async def zadanie_statusu(self) -> None:
        statusy = [
            "słucha szeptów Aethelgardu...", f"pomaga Elarze katalogować anime!",
            "liczy Gwiezdne Dukaty w skarbcu.", "odwiedza Wielką Bibliotekę Opowieści.",
            "poleruje Edykty Królestwa z Kaelenem.", "planuje festiwal z Lyrą!",
            "ulepsza techno-magię z Runą.", f"pilnuje prefixu: {self.prefix_bota or '!'}",
            "czeka na Twoją opowieść...", "w Kronikach Elary!"
        ]
        await self.change_presence(activity=discord.Game(random.choice(statusy)))

    @zadanie_statusu.before_loop
    async def przed_zadaniem_statusu(self) -> None:
        await self.wait_until_ready()

    async def setup_hook(self) -> None:
        self.logger.info(f"Zalogowano jako {self.user.name} (ID: {self.user.id}) - Witaj w Kronikach Elary!") # type: ignore
        self.logger.info(f"discord.py API: {discord.__version__}, Python: {platform.python_version()}")
        self.logger.info(f"Działam na: {platform.system()} {platform.release()} ({os.name})")
        self.logger.info(f"Prefix bota: {self.prefix_bota}")
        if self.welcome_channel_id: self.logger.info(f"Kanał powitalny: {self.welcome_channel_id}")
        if self.default_role_id: self.logger.info(f"Domyślna rola: {self.default_role_id}")
        if self.main_server_id: self.logger.info(f"Główny ID serwera API: {self.main_server_id}")
        else: self.logger.warning("MAIN_SERVER_ID nie ustawiony! API może nie działać.")
        if self.api_key: self.logger.info("Klucz API załadowany.")
        else: self.logger.warning("API_KEY nie ustawiony. Dostęp otwarty (DEV).")
        self.logger.info(f"API serwer na porcie: {self.api_port}")
        self.logger.info("-------------------")

        await self.inicjalizuj_bd()

        db_connection_path = f"{os.path.realpath(os.path.dirname(__file__))}/database/database.db"
        try:
            db_connection = await aiosqlite.connect(db_connection_path)
            self.baza_danych = ZarzadcaBazyDanych(connection=db_connection)
            self.logger.info("Połączono z bazą danych i zainicjowano Zarządcę.")
        except aiosqlite.Error as e:
            self.logger.critical(f"Nie udało się połączyć z bazą danych {db_connection_path} dla Zarządcy: {e}", exc_info=True)
            self.logger.critical("Bot nie może kontynuować bez połączenia z bazą danych. Zamykanie...")
            await self.close()
            sys.exit(f"Błąd połączenia z bazą danych: {e}")
            return

        now_utc = datetime.now(UTC)
        reset_time_daily_utc = time_obj(hour=config.RESET_MISJI_DZIENNYCH_GODZINA_UTC, tzinfo=UTC)
        current_date_utc = now_utc.date()
        last_possible_reset_dt_daily = datetime.combine(current_date_utc, reset_time_daily_utc)
        if now_utc < last_possible_reset_dt_daily:
            last_possible_reset_dt_daily -= timedelta(days=1)
        self.ostatni_reset_misji_dziennych_ts = int(last_possible_reset_dt_daily.timestamp())

        reset_weekday_utc = config.RESET_MISJI_TYGODNIOWYCH_DZIEN_TYGODNIA
        reset_time_weekly_utc = time_obj(hour=config.RESET_MISJI_TYGODNIOWYCH_GODZINA_UTC, tzinfo=UTC)
        days_since_last_reset_day = (now_utc.weekday() - reset_weekday_utc + 7) % 7
        last_reset_date_weekly = now_utc.date() - timedelta(days=days_since_last_reset_day)
        last_possible_reset_dt_weekly = datetime.combine(last_reset_date_weekly, reset_time_weekly_utc)
        if now_utc < last_possible_reset_dt_weekly:
            last_possible_reset_dt_weekly -= timedelta(weeks=1)
        self.ostatni_reset_misji_tygodniowych_ts = int(last_possible_reset_dt_weekly.timestamp())

        self.logger.info(f"Inicjalizacja timestampów resetu misji: Dzienny: {datetime.fromtimestamp(self.ostatni_reset_misji_dziennych_ts, UTC)}, Tygodniowy: {datetime.fromtimestamp(self.ostatni_reset_misji_tygodniowych_ts, UTC)}")

        await self.zaladuj_kapsuly()
        self.zadanie_statusu.start()
        self.zadanie_xp_za_glos.start()
        self.zadanie_live_ranking.start()
        self.zadanie_czyszczenia_bonusow.start()
        self.zadanie_sprawdzania_rol_czasowych.start()
        self.zadanie_resetowania_misji.start()
        self.zadanie_konca_sezonu_miesiecznego.start()

    async def _create_bot_embed(self, context: typing.Optional[Context], title: str, description: str = "", color: discord.Color = config.KOLOR_BOT_GLOWNY) -> discord.Embed:
        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.now(UTC))
        if self.user and self.user.avatar: # type: ignore
            embed.set_author(name=self.user.display_name, icon_url=self.user.avatar.url) # type: ignore
        guild_icon_url = None
        if context and context.guild and context.guild.icon: guild_icon_url = context.guild.icon.url
        elif self.guilds and self.guilds[0].icon: guild_icon_url = self.guilds[0].icon.url
        embed.set_footer(text="Kroniki Elary", icon_url=guild_icon_url)
        return embed

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not self.welcome_channel_id: return
        guild = member.guild
        welcome_channel = guild.get_channel(self.welcome_channel_id)
        if not welcome_channel or not isinstance(welcome_channel, discord.TextChannel): return

        self.logger.info(f"Nowy Kronikarz: {member.display_name} ({member.id}) na {guild.name}.")
        embed = discord.Embed(
            title="🌌 Nowy Kronikarz Przekroczył Bramę!",
            description=f"Witaj w **Kronikach Elary**, {member.mention}!\n\n"
                        "Jesteśmy społecznością miłośników anime, mangi i kultury japońskiej.",
            color=config.KOLOR_POWITALNY, timestamp=datetime.now(UTC)
        )
        if member.display_avatar: embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="📜 Pierwsze Kroki:", value="- Zapoznaj się z regulaminem.\n- Odkryj mapę serwera.\n- Przedstaw się!", inline=False)
        embed.add_field(name="✨ Co Możesz Robić?", value="Dyskutować, dzielić się twórczością, brać udział w eventach, zdobywać XP i Dukaty!", inline=False)
        if guild.icon: embed.set_footer(text=f"Witamy w {guild.name}!", icon_url=guild.icon.url)
        else: embed.set_footer(text=f"Witamy w {guild.name}!")
        try: await welcome_channel.send(embed=embed)
        except discord.Forbidden: self.logger.warning(f"Brak uprawnień do wysłania powitania na {welcome_channel.name}.")
        if self.default_role_id:
            role = guild.get_role(self.default_role_id)
            if role:
                try: await member.add_roles(role, reason="Automatyczne nadanie roli.")
                except discord.Forbidden: self.logger.warning(f"Brak uprawnień do nadania roli '{role.name}'.")
            else: self.logger.warning(f"Nie znaleziono roli o ID {self.default_role_id}.")

    def oblicz_xp_dla_poziomu(self, poziom: int) -> int:
        if poziom < 0: return float('inf')
        if poziom == 0: return 100
        return 5 * (poziom ** 2) + (50 * poziom) + 100

    async def wyslij_wiadomosc_o_awansie(self, member: discord.Member, guild: discord.Guild, nowy_poziom: int, dukaty_za_poziom: int, nowe_saldo_dukatow: int):
        kanal_do_wyslania = guild.system_channel or (guild.text_channels[0] if guild.text_channels else None)
        if kanal_do_wyslania:
            try:
                embed = await self._create_bot_embed(
                    None, title="✨ Awans w Kronikach! ✨",
                    description=f"Gratulacje, {member.mention}! Twoja legenda rośnie w siłę!",
                    color=config.KOLOR_BOT_SUKCES
                )
                if member.display_avatar: embed.set_thumbnail(url=member.display_avatar.url)
                embed.add_field(name="🌟 Nowy Poziom Opowieści", value=f"**{nowy_poziom}**", inline=True)
                embed.add_field(name="💰 Nagroda", value=f"Otrzymujesz **{dukaty_za_poziom}** ✨ Gwiezdnych Dukatów!", inline=True)
                embed.add_field(name="🪙 Twoje Saldo", value=f"**{nowe_saldo_dukatow}** ✨ Gwiezdnych Dukatów", inline=False)
                if guild.icon: embed.set_footer(text="Niech Twoje opowieści będą wieczne!", icon_url=guild.icon.url)
                else: embed.set_footer(text="Niech Twoje opowieści będą wieczne!")
                await kanal_do_wyslania.send(embed=embed)
            except discord.Forbidden: self.logger.warning(f"Brak uprawnień do wysłania wiad. o awansie na {kanal_do_wyslania.name}.")

    async def sprawdz_i_awansuj(self, member: discord.Member, guild: discord.Guild, _processed_level_missions: typing.Optional[set[int]] = None):
        if _processed_level_missions is None:
            _processed_level_missions = set()

        if self.baza_danych is None: return
        user_id, server_id = member.id, guild.id
        dane_uzytkownika_pelne = await self.baza_danych.pobierz_lub_stworz_doswiadczenie(user_id, server_id)
        aktualne_xp, aktualny_poziom = dane_uzytkownika_pelne[2], dane_uzytkownika_pelne[3]
        xp_do_nastepnego_poziomu = self.oblicz_xp_dla_poziomu(aktualny_poziom)

        if aktualne_xp >= xp_do_nastepnego_poziomu:
            nowy_poziom_po_awansie = aktualny_poziom + 1
            await self.baza_danych.aktualizuj_doswiadczenie(user_id, server_id, nowy_poziom=nowy_poziom_po_awansie)
            dukaty_za_poziom = config.DUKATY_ZA_POZIOM

            _, nowe_saldo_dukatow_val = await self.baza_danych.aktualizuj_portfel(user_id, server_id, ilosc_dukatow_do_dodania=dukaty_za_poziom)

            await self.wyslij_wiadomosc_o_awansie(member, guild, nowy_poziom_po_awansie, dukaty_za_poziom, nowe_saldo_dukatow_val)
            await self.sprawdz_i_przyznaj_osiagniecia(member, guild, "poziom_xp", nowy_poziom_po_awansie)
            
            if nowy_poziom_po_awansie not in _processed_level_missions:
                await self.aktualizuj_i_sprawdz_misje_po_akcji(member, guild, "osiagniecie_poziomu_xp", nowy_poziom_po_awansie)
                _processed_level_missions.add(nowy_poziom_po_awansie)


            nagroda_rola_dane = await self.baza_danych.pobierz_nagrode_za_poziom(server_id, nowy_poziom_po_awansie)
            if nagroda_rola_dane:
                rola_id_int = int(nagroda_rola_dane[0])
                rola = guild.get_role(rola_id_int)
                if rola:
                    try:
                        await member.add_roles(rola, reason=f"Nagroda za Poziom {nowy_poziom_po_awansie}")
                        kanal_do_wyslania_rola = guild.system_channel or (guild.text_channels[0] if guild.text_channels else None)
                        if kanal_do_wyslania_rola:
                            embed_rola = await self._create_bot_embed(None, title="🎖️ Nowa Godność!", description=f"{member.mention}, za Poziom {nowy_poziom_po_awansie} otrzymałeś/aś **{rola.name}**!", color=config.KOLOR_BOT_SUKCES)
                            await kanal_do_wyslania_rola.send(embed=embed_rola)
                    except discord.Forbidden: self.logger.warning(f"Brak uprawnień do nadania roli '{rola.name}'.")
                else: self.logger.warning(f"Nie znaleziono roli o ID {rola_id_int} (nagroda za poziom).")
            await self.sprawdz_i_awansuj(member, guild, _processed_level_missions) # Przekazanie zbioru dalej

    async def sprawdz_i_przyznaj_osiagniecia(self, member: discord.Member, guild: discord.Guild, typ_sprawdzanego_warunku: typing.Optional[str] = None, aktualna_wartosc_warunku: typing.Optional[typing.Any] = None, dodatkowe_dane: typing.Optional[dict] = None):
        if self.baza_danych is None: return

        user_id_str, server_id_str = str(member.id), str(guild.id)
        dane_xp_krotka = await self.baza_danych.pobierz_lub_stworz_doswiadczenie(member.id, guild.id)

        poziom_uzytkownika = dane_xp_krotka[3]
        liczba_wiadomosci_uzytkownika = dane_xp_krotka[10]
        liczba_reakcji_uzytkownika = dane_xp_krotka[11]
        streak_uzytkownika = dane_xp_krotka[8]

        ilosc_dukatow_uzytkownika = 0
        dane_portfela = await self.baza_danych.pobierz_portfel(member.id, guild.id)
        if dane_portfela: ilosc_dukatow_uzytkownika = dane_portfela[2]

        liczba_wygranych_konkursow_val = await self.baza_danych.pobierz_liczbe_wygranych_konkursow(user_id_str, server_id_str)

        for os_bazowe_id, os_bazowe_dane in self.DEFINICJE_OSIAGNIEC.items():
            typ_warunku_dla_bazowego = os_bazowe_dane.get("typ_warunku_bazowy")

            for tier_dane in os_bazowe_dane.get("tiery", []):
                tier_id = tier_dane["id"]

                if await self.baza_danych.czy_uzytkownik_zdobyl_osiagniecie(user_id_str, server_id_str, tier_id):
                    continue

                warunek_spelniony = False
                wartosc_warunku_tieru = tier_dane["wartosc_warunku"]

                if typ_warunku_dla_bazowego == "liczba_wiadomosci" and (typ_sprawdzanego_warunku == "liczba_wiadomosci" or typ_sprawdzanego_warunku is None):
                    if liczba_wiadomosci_uzytkownika >= wartosc_warunku_tieru: warunek_spelniony = True
                elif typ_warunku_dla_bazowego == "liczba_reakcji" and (typ_sprawdzanego_warunku == "liczba_reakcji" or typ_sprawdzanego_warunku is None):
                    if liczba_reakcji_uzytkownika >= wartosc_warunku_tieru: warunek_spelniony = True
                elif typ_warunku_dla_bazowego == "poziom_xp" and (typ_sprawdzanego_warunku == "poziom_xp" or typ_sprawdzanego_warunku is None):
                    sprawdzany_poziom = int(aktualna_wartosc_warunku) if typ_sprawdzanego_warunku == "poziom_xp" and aktualna_wartosc_warunku is not None else poziom_uzytkownika
                    if sprawdzany_poziom >= wartosc_warunku_tieru: warunek_spelniony = True
                elif typ_warunku_dla_bazowego == "dlugosc_streaka" and (typ_sprawdzanego_warunku == "dlugosc_streaka" or typ_sprawdzanego_warunku is None):
                    sprawdzany_streak = int(aktualna_wartosc_warunku) if typ_sprawdzanego_warunku == "dlugosc_streaka" and aktualna_wartosc_warunku is not None else streak_uzytkownika
                    if sprawdzany_streak >= wartosc_warunku_tieru: warunek_spelniony = True
                elif typ_warunku_dla_bazowego == "ilosc_dukatow" and (typ_sprawdzanego_warunku == "ilosc_dukatow" or typ_sprawdzanego_warunku is None):
                    sprawdzane_dukaty = int(aktualna_wartosc_warunku) if typ_sprawdzanego_warunku == "ilosc_dukatow" and aktualna_wartosc_warunku is not None else ilosc_dukatow_uzytkownika
                    if sprawdzane_dukaty is not None and sprawdzane_dukaty >= wartosc_warunku_tieru: warunek_spelniony = True
                elif typ_warunku_dla_bazowego == "zakup_krysztalow" and (typ_sprawdzanego_warunku == "zakup_krysztalow" or typ_sprawdzanego_warunku is None):
                    if aktualna_wartosc_warunku is not None and int(aktualna_wartosc_warunku) >= wartosc_warunku_tieru:
                        warunek_spelniony = True
                elif typ_warunku_dla_bazowego == "odkrycie_sekretu_biblioteki" and (typ_sprawdzanego_warunku == "odkrycie_sekretu_biblioteki" or typ_sprawdzanego_warunku is None):
                    if aktualna_wartosc_warunku is not None and int(aktualna_wartosc_warunku) >= wartosc_warunku_tieru:
                        warunek_spelniony = True
                elif typ_warunku_dla_bazowego == "uzycie_specjalnej_komendy" and (typ_sprawdzanego_warunku == "uzycie_specjalnej_komendy" or typ_sprawdzanego_warunku is None):
                    if aktualna_wartosc_warunku is not None and int(aktualna_wartosc_warunku) >= wartosc_warunku_tieru:
                        warunek_spelniony = True
                elif typ_warunku_dla_bazowego == "liczba_wiadomosci_na_kanale" and (typ_sprawdzanego_warunku == "liczba_wiadomosci_na_kanale" or typ_sprawdzanego_warunku is None):
                    id_kanalu_warunku_osiagniecia = os_bazowe_dane.get("id_kanalu_warunku")
                    if id_kanalu_warunku_osiagniecia and dodatkowe_dane and str(dodatkowe_dane.get("kanal_id")) == str(id_kanalu_warunku_osiagniecia):
                        if aktualna_wartosc_warunku is not None and int(aktualna_wartosc_warunku) >= wartosc_warunku_tieru:
                            warunek_spelniony = True
                elif typ_warunku_dla_bazowego == "liczba_wygranych_konkursow" and (typ_sprawdzanego_warunku == "liczba_wygranych_konkursow" or typ_sprawdzanego_warunku is None):
                    sprawdzana_liczba_wygranych = int(aktualna_wartosc_warunku) if typ_sprawdzanego_warunku == "liczba_wygranych_konkursow" and aktualna_wartosc_warunku is not None else liczba_wygranych_konkursow_val
                    if sprawdzana_liczba_wygranych >= wartosc_warunku_tieru:
                        warunek_spelniony = True
                elif typ_warunku_dla_bazowego == "liczba_uzyc_komend_kategorii" and (typ_sprawdzanego_warunku == "liczba_uzyc_komend_kategorii" or typ_sprawdzanego_warunku is None):
                    kategoria_komendy_warunku_osiagniecia = os_bazowe_dane.get("kategoria_komendy_warunku")
                    if kategoria_komendy_warunku_osiagniecia and dodatkowe_dane and dodatkowe_dane.get("kategoria_komendy") == kategoria_komendy_warunku_osiagniecia:
                        if aktualna_wartosc_warunku is not None and int(aktualna_wartosc_warunku) >= wartosc_warunku_tieru:
                            warunek_spelniony = True

                if warunek_spelniony:
                    czy_nowo_zdobyte = await self.baza_danych.oznacz_osiagniecie_jako_zdobyte(user_id_str, server_id_str, tier_id)
                    if czy_nowo_zdobyte:
                        nazwa_wyswietlana_osiagniecia = tier_dane.get("nazwa_tieru", os_bazowe_dane.get("nazwa_bazowa", "Nieznane Osiągnięcie"))
                        opis_wyswietlany_osiagniecia = tier_dane.get("opis_tieru", os_bazowe_dane.get("opis_bazowy", "Zdobyłeś/aś osiągnięcie!"))
                        ikona_osiagniecia = os_bazowe_dane.get("ikona", "🏆")

                        self.logger.info(f"Użytkownik {member.display_name} ({member.id}) zdobył osiągnięcie '{nazwa_wyswietlana_osiagniecia}' (ID tieru: {tier_id}) na serwerze {guild.name}.")

                        nagroda_xp = tier_dane.get("nagroda_xp", 0)
                        nagroda_dukaty_val = tier_dane.get("nagroda_dukaty", 0)
                        nagroda_krysztaly_val = tier_dane.get("nagroda_krysztaly", 0)
                        nagroda_rola_id_str = tier_dane.get("nagroda_rola_id")

                        embed_title = f"{ikona_osiagniecia} Nowe Osiągnięcie!"
                        embed_description = f"Gratulacje {member.mention}! **{nazwa_wyswietlana_osiagniecia}**!\n\n_{opis_wyswietlany_osiagniecia}_"

                        if nagroda_xp > 0: embed_description += f"\n\n🎁 +**{nagroda_xp}** XP!"
                        if nagroda_dukaty_val > 0: embed_description += f"\n💰 +**{nagroda_dukaty_val}** ✨ Dukatów!"
                        if nagroda_krysztaly_val > 0: embed_description += f"\n💠 +**{nagroda_krysztaly_val}** {config.SYMBOL_WALUTY_PREMIUM} {config.NAZWA_WALUTY_PREMIUM}!"


                        if nagroda_rola_id_str:
                            try:
                                rola_id_int = int(nagroda_rola_id_str)
                                rola_do_nadania = guild.get_role(rola_id_int)
                                if rola_do_nadania and rola_do_nadania not in member.roles:
                                    await member.add_roles(rola_do_nadania, reason=f"Osiągnięcie: {nazwa_wyswietlana_osiagniecia}")
                                    embed_description += f"\n🛡️ Godność: **{rola_do_nadania.name}**!"
                            except Exception as e_role: self.logger.error(f"Błąd przyznawania roli za osiągnięcie {tier_id}: {e_role}", exc_info=True)

                        embed_osiagniecie = await self._create_bot_embed(None, title=embed_title, description=embed_description, color=config.KOLOR_XP_OSIAGNIECIE)
                        if member.display_avatar: embed_osiagniecie.set_thumbnail(url=member.display_avatar.url)

                        if nagroda_xp > 0:
                            await self.baza_danych.aktualizuj_doswiadczenie(member.id, guild.id, xp_dodane=nagroda_xp)
                            await self.sprawdz_i_awansuj(member, guild)
                        if nagroda_dukaty_val > 0 or nagroda_krysztaly_val > 0:
                            await self.baza_danych.aktualizuj_portfel(member.id, guild.id, ilosc_dukatow_do_dodania=nagroda_dukaty_val, ilosc_krysztalow_do_dodania=nagroda_krysztaly_val)
                            dane_portfela_po_nagrodzie = await self.baza_danych.pobierz_portfel(member.id, guild.id)
                            if dane_portfela_po_nagrodzie:
                                await self.sprawdz_i_przyznaj_osiagniecia(member, guild, "ilosc_dukatow", dane_portfela_po_nagrodzie[2])

                        kanal_do_powiadomien = guild.system_channel or (guild.text_channels[0] if guild.text_channels else None)
                        if kanal_do_powiadomien:
                            try: await kanal_do_powiadomien.send(embed=embed_osiagniecie)
                            except discord.Forbidden: self.logger.warning(f"Brak uprawnień do wysłania wiadomości o osiągnięciu na kanale {kanal_do_powiadomien.name}.")
                            except Exception as e_send: self.logger.error(f"Nieoczekiwany błąd podczas wysyłania wiadomości o osiągnięciu: {e_send}", exc_info=True)
                        else:
                            try: await member.send(embed=embed_osiagniecie)
                            except discord.Forbidden: self.logger.warning(f"Nie można wysłać DM o osiągnięciu do {member.display_name} (DM zablokowane lub brak uprawnień).")
                            except Exception as e_dm: self.logger.error(f"Nieoczekiwany błąd podczas wysyłania DM o osiągnięciu: {e_dm}", exc_info=True)
                        break


    async def przyznaj_xp(self, member: discord.Member, guild: discord.Guild, kanal: typing.Optional[discord.abc.GuildChannel | discord.Thread], bazowe_xp_min: int, bazowe_xp_max: int, cooldown_ts_field: typing.Optional[str], cooldown_value: int, event_type: str, inkrementuj_licznik_typ: typing.Optional[str] = None, dodatkowe_dane_dla_osiagniec: typing.Optional[dict] = None):
        if self.baza_danych is None or member.bot or not guild: return

        konfiguracja_serwera = self.pobierz_konfiguracje_xp_serwera(guild.id)
        if konfiguracja_serwera["xp_zablokowane"]: return

        user_id, server_id = member.id, guild.id
        aktualny_czas_ts = int(time.time())
        dzisiaj_utc = datetime.now(UTC).date()

        dane_uzytkownika_pelne = await self.baza_danych.pobierz_lub_stworz_doswiadczenie(user_id, server_id)
        if dane_uzytkownika_pelne[7]: return

        mnoznik_bonus_kanalu = 0.0
        if kanal:
            konfiguracja_kanalu = await self.baza_danych.pobierz_konfiguracje_xp_kanalu(str(server_id), str(kanal.id))
            if konfiguracja_kanalu:
                if konfiguracja_kanalu[0]: return
                mnoznik_bonus_kanalu = konfiguracja_kanalu[1] - 1.0

        if cooldown_ts_field:
            ostatni_event_ts_index = -1
            if cooldown_ts_field == "ostatnia_wiadomosc_timestamp": ostatni_event_ts_index = 5
            elif cooldown_ts_field == "ostatnia_reakcja_timestamp": ostatni_event_ts_index = 6
            if ostatni_event_ts_index != -1 and aktualny_czas_ts - dane_uzytkownika_pelne[ostatni_event_ts_index] < cooldown_value:
                return

        xp_bazowe = random.randint(bazowe_xp_min, bazowe_xp_max)
        mnoznik_bonus_eventu = konfiguracja_serwera["mnoznik_xp"] - 1.0
        mnoznik_bonus_rol = 0.0
        bonusy_rol_serwera = await self.baza_danych.pobierz_bonusy_xp_rol_serwera(str(server_id))
        for rola_id_str, mnoznik_roli_db in bonusy_rol_serwera:
            if any(r.id == int(rola_id_str) for r in member.roles):
                mnoznik_bonus_rol += (mnoznik_roli_db - 1.0)

        mnoznik_bonus_zakupiony = 0.0
        aktywne_zakupione_bonusy = await self.baza_danych.pobierz_aktywne_zakupione_bonusy_xp_uzytkownika(str(user_id), str(server_id))
        for typ_b, wartosc_b, _ in aktywne_zakupione_bonusy:
            if typ_b == "xp_mnoznik": mnoznik_bonus_zakupiony += wartosc_b

        finalny_mnoznik = 1.0 + mnoznik_bonus_eventu + mnoznik_bonus_rol + mnoznik_bonus_kanalu + mnoznik_bonus_zakupiony
        if finalny_mnoznik < 0: finalny_mnoznik = 0
        xp_po_mnoznikach = int(xp_bazowe * finalny_mnoznik)

        obecny_streak_dni_db = dane_uzytkownika_pelne[8]
        ostatni_dzien_aktywnosci_streak_db_str = dane_uzytkownika_pelne[9]
        ostatni_dzien_aktywnosci_streak_db = date_obj.fromisoformat(ostatni_dzien_aktywnosci_streak_db_str) if ostatni_dzien_aktywnosci_streak_db_str else None

        nowy_streak_dni_do_zapisu = obecny_streak_dni_db
        nowy_ostatni_dzien_streaka_do_zapisu_obj = ostatni_dzien_aktywnosci_streak_db
        xp_bonus_streaka = 0
        czy_aktualizowac_streak_w_bazie = False

        if ostatni_dzien_aktywnosci_streak_db is None or ostatni_dzien_aktywnosci_streak_db < dzisiaj_utc:
            if ostatni_dzien_aktywnosci_streak_db is None or ostatni_dzien_aktywnosci_streak_db < (dzisiaj_utc - timedelta(days=1)):
                nowy_streak_dni_do_zapisu = 1
            elif ostatni_dzien_aktywnosci_streak_db == (dzisiaj_utc - timedelta(days=1)):
                nowy_streak_dni_do_zapisu = obecny_streak_dni_db + 1
            nowy_ostatni_dzien_streaka_do_zapisu_obj = dzisiaj_utc
            czy_aktualizowac_streak_w_bazie = True
            bonus_za_dzien_streaka = min(nowy_streak_dni_do_zapisu, config.MAX_DNI_STREAKA_DLA_BONUSU) * config.XP_BONUS_ZA_DZIEN_STREAKA
            xp_bonus_streaka = bonus_za_dzien_streaka

        xp_finalne_do_dodania = xp_po_mnoznikach + xp_bonus_streaka
        kwargs_aktualizacji: dict[str, typing.Any] = {}
        if xp_finalne_do_dodania > 0: kwargs_aktualizacji["xp_dodane"] = xp_finalne_do_dodania
        if czy_aktualizowac_streak_w_bazie:
            kwargs_aktualizacji["nowy_streak_dni"] = nowy_streak_dni_do_zapisu
            kwargs_aktualizacji["nowy_ostatni_dzien_streaka_iso"] = nowy_ostatni_dzien_streaka_do_zapisu_obj.isoformat() if nowy_ostatni_dzien_streaka_do_zapisu_obj else None
        if cooldown_ts_field == "ostatnia_wiadomosc_timestamp": kwargs_aktualizacji["nowy_timestamp_wiadomosci"] = aktualny_czas_ts
        elif cooldown_ts_field == "ostatnia_reakcja_timestamp": kwargs_aktualizacji["nowy_timestamp_reakcji"] = aktualny_czas_ts
        if inkrementuj_licznik_typ == "wiadomosc": kwargs_aktualizacji["inkrementuj_wiadomosci"] = 1
        elif inkrementuj_licznik_typ == "reakcja": kwargs_aktualizacji["inkrementuj_reakcje"] = 1

        if kwargs_aktualizacji:
            await self.baza_danych.aktualizuj_doswiadczenie(user_id, server_id, **kwargs_aktualizacji)


        if xp_finalne_do_dodania > 0:
            self.logger.info(f"Przyznano {xp_finalne_do_dodania} XP dla {member.display_name} za {event_type}.")
            await self.sprawdz_i_awansuj(member, guild)
            if czy_aktualizowac_streak_w_bazie:
                await self.sprawdz_i_przyznaj_osiagniecia(member, guild, "dlugosc_streaka", nowy_streak_dni_do_zapisu)
                await self.aktualizuj_i_sprawdz_misje_po_akcji(member, guild, "osiagnij_x_streaka", nowy_streak_dni_do_zapisu)
        elif czy_aktualizowac_streak_w_bazie:
            await self.sprawdz_i_przyznaj_osiagniecia(member, guild, "dlugosc_streaka", nowy_streak_dni_do_zapisu)
            await self.aktualizuj_i_sprawdz_misje_po_akcji(member, guild, "osiagnij_x_streaka", nowy_streak_dni_do_zapisu)

        if inkrementuj_licznik_typ:
            dane_po_inkrementacji_full = await self.baza_danych.pobierz_lub_stworz_doswiadczenie(user_id, server_id)
            if inkrementuj_licznik_typ == "wiadomosc":
                await self.sprawdz_i_przyznaj_osiagniecia(member, guild, "liczba_wiadomosci", dane_po_inkrementacji_full[10])
                await self.aktualizuj_i_sprawdz_misje_po_akcji(member, guild, "liczba_wiadomosci_od_resetu", 1)
                if kanal and dodatkowe_dane_dla_osiagniec and "kanal_id" in dodatkowe_dane_dla_osiagniec:
                    nowa_liczba_na_kanale = await self.baza_danych.inkrementuj_liczbe_wiadomosci_na_kanale(str(user_id), str(server_id), str(kanal.id))
                    await self.sprawdz_i_przyznaj_osiagniecia(member, guild, "liczba_wiadomosci_na_kanale", nowa_liczba_na_kanale, dodatkowe_dane={"kanal_id": kanal.id})
            elif inkrementuj_licznik_typ == "reakcja":
                await self.sprawdz_i_przyznaj_osiagniecia(member, guild, "liczba_reakcji", dane_po_inkrementacji_full[11])
                await self.aktualizuj_i_sprawdz_misje_po_akcji(member, guild, "liczba_reakcji_od_resetu", 1)

        dane_portfela_po_zmianie = await self.baza_danych.pobierz_portfel(user_id, server_id)
        if dane_portfela_po_zmianie:
            await self.sprawdz_i_przyznaj_osiagniecia(member, guild, "ilosc_dukatow", dane_portfela_po_zmianie[2])

    def _get_mission_reset_timestamp(self, mission_type: str) -> int:
        if mission_type == "dzienna":
            return self.ostatni_reset_misji_dziennych_ts
        elif mission_type == "tygodniowa":
            return self.ostatni_reset_misji_tygodniowych_ts
        return 0

    async def aktualizuj_i_sprawdz_misje_po_akcji(self, member: discord.Member, guild: discord.Guild, typ_akcji: str, wartosc_akcji: int = 1, dodatkowe_dane: typing.Optional[dict] = None):
        if self.baza_danych is None or member.bot: return

        user_id_str, server_id_str = str(member.id), str(guild.id)
        teraz_ts = int(time.time())

        for misja_id, misja_def in self.DEFINICJE_MISJI.items():
            typ_misji = misja_def["typ_misji"]
            ostatni_reset_dla_tej_misji_ts = self._get_mission_reset_timestamp(typ_misji)

            if typ_misji == "jednorazowa" and await self.baza_danych.czy_misja_jednorazowa_ukonczona(user_id_str, server_id_str, misja_id):
                continue
            if typ_misji in ["dzienna", "tygodniowa"] and await self.baza_danych.czy_misja_ukonczona_w_cyklu(user_id_str, server_id_str, misja_id, ostatni_reset_dla_tej_misji_ts):
                continue

            wszystkie_warunki_spelnione = True
            for warunek_def in misja_def["warunki"]:
                typ_warunku_misji = warunek_def["typ_warunku"]
                wymagana_wartosc_warunku = warunek_def["wartosc"]

                _, _, _, _, _, aktualny_postep_warunku, _ = await self.baza_danych.pobierz_lub_stworz_postep_misji(
                    user_id_str, server_id_str, misja_id, typ_warunku_misji, ostatni_reset_dla_tej_misji_ts
                )
                nowy_postep_warunku = aktualny_postep_warunku

                if typ_warunku_misji == typ_akcji:
                    if typ_akcji == "uzycie_komendy_kategorii_od_resetu":
                        if dodatkowe_dane and dodatkowe_dane.get("kategoria_komendy") == warunek_def.get("kategoria_komendy"):
                            nowy_postep_warunku = await self.baza_danych.aktualizuj_postep_misji(user_id_str, server_id_str, misja_id, typ_warunku_misji, wartosc_do_dodania=wartosc_akcji)
                    elif typ_akcji == "uzycie_komendy":
                        if dodatkowe_dane and dodatkowe_dane.get("nazwa_komendy") == warunek_def.get("nazwa_komendy"):
                            nowy_postep_warunku = await self.baza_danych.aktualizuj_postep_misji(user_id_str, server_id_str, misja_id, typ_warunku_misji, wartosc_do_dodania=wartosc_akcji)
                    elif typ_akcji == "osiagniecie_poziomu_xp":
                        nowy_postep_warunku = wartosc_akcji
                    elif typ_akcji == "wygraj_konkurs_od_resetu":
                        nowy_postep_warunku = await self.baza_danych.aktualizuj_postep_misji(user_id_str, server_id_str, misja_id, typ_warunku_misji, wartosc_do_dodania=wartosc_akcji)
                    elif typ_akcji == "uzyj_przedmiotu_ze_sklepu_od_resetu":
                        if dodatkowe_dane and dodatkowe_dane.get("id_przedmiotu") == warunek_def.get("id_przedmiotu"):
                            nowy_postep_warunku = await self.baza_danych.aktualizuj_postep_misji(user_id_str, server_id_str, misja_id, typ_warunku_misji, wartosc_do_dodania=wartosc_akcji)
                    elif typ_akcji == "osiagnij_x_streaka":
                        if wartosc_akcji > aktualny_postep_warunku:
                             nowy_postep_warunku = await self.baza_danych.aktualizuj_postep_misji(user_id_str, server_id_str, misja_id, typ_warunku_misji, ustaw_wartosc=wartosc_akcji)
                        else:
                            nowy_postep_warunku = aktualny_postep_warunku
                    else:
                        nowy_postep_warunku = await self.baza_danych.aktualizuj_postep_misji(user_id_str, server_id_str, misja_id, typ_warunku_misji, wartosc_do_dodania=wartosc_akcji)

                if nowy_postep_warunku < wymagana_wartosc_warunku:
                    wszystkie_warunki_spelnione = False; break

            if wszystkie_warunki_spelnione:
                nagrody = misja_def.get("nagrody", {})
                if nagrody.get("xp", 0) > 0:
                    await self.baza_danych.aktualizuj_doswiadczenie(member.id, guild.id, xp_dodane=nagrody["xp"])
                    await self.sprawdz_i_awansuj(member, guild)

                dukaty_do_dodania = nagrody.get("gwiezdne_dukaty", 0)
                krysztaly_do_dodania = nagrody.get("gwiezdne_krysztaly", 0)
                if dukaty_do_dodania > 0 or krysztaly_do_dodania > 0:
                    await self.baza_danych.aktualizuj_portfel(member.id, guild.id, ilosc_dukatow_do_dodania=dukaty_do_dodania, ilosc_krysztalow_do_dodania=krysztaly_do_dodania)

                await self.baza_danych.oznacz_misje_jako_ukonczona(user_id_str, server_id_str, misja_id, teraz_ts)
                self.logger.info(f"Użytkownik {member.display_name} ukończył misję '{misja_def['nazwa']}'.")

                embed_misja = await self._create_bot_embed(None, title=f"{misja_def.get('ikona', '🎯')} Misja Ukończona!",
                    description=f"Gratulacje {member.mention}! Ukończyłeś/aś: **{misja_def['nazwa']}**!\n\n_{misja_def['opis']}_",
                    color=config.KOLOR_BOT_SUKCES)
                nagrody_opis = [f"**{v}** {k.replace('_', ' ').capitalize()}" for k, v in nagrody.items() if v > 0]
                if nagrody_opis: embed_misja.add_field(name="Nagrody:", value="\n".join(nagrody_opis), inline=False)
                try:
                    await member.send(embed=embed_misja)
                    self.logger.info(f"Wysłano powiadomienie o ukończeniu misji '{misja_def['nazwa']}' do {member.display_name}.")
                except discord.Forbidden:
                    self.logger.warning(f"Nie można wysłać DM o ukończeniu misji do {member.display_name} (DM zablokowane).")
                    kanal_systemowy = guild.system_channel
                    if kanal_systemowy and kanal_systemowy.permissions_for(guild.me).send_messages:
                        try:
                            await kanal_systemowy.send(content=f"{member.mention}", embed=embed_misja)
                            self.logger.info(f"Wysłano powiadomienie o ukończeniu misji '{misja_def['nazwa']}' na kanał systemowy dla {member.display_name}.")
                        except Exception as e_sys_chan:
                             self.logger.error(f"Błąd wysyłania powiadomienia o misji na kanał systemowy: {e_sys_chan}")
                except Exception as e_dm:
                    self.logger.error(f"Błąd wysyłania DM o ukończeniu misji do {member.display_name}: {e_dm}")


    @tasks.loop(minutes=30)
    async def zadanie_resetowania_misji(self):
        if self.baza_danych is None: return

        teraz_utc = datetime.now(UTC)

        godzina_resetu_dziennego_utc = time_obj(hour=config.RESET_MISJI_DZIENNYCH_GODZINA_UTC, tzinfo=UTC)
        data_ostatniego_resetu_dziennego = teraz_utc.date()
        dt_ostatniego_mozliwego_resetu_dziennego = datetime.combine(data_ostatniego_resetu_dziennego, godzina_resetu_dziennego_utc)

        if teraz_utc < dt_ostatniego_mozliwego_resetu_dziennego:
            dt_ostatniego_mozliwego_resetu_dziennego -= timedelta(days=1)

        timestamp_ostatniego_mozliwego_resetu_dziennego = int(dt_ostatniego_mozliwego_resetu_dziennego.timestamp())

        if self.ostatni_reset_misji_dziennych_ts < timestamp_ostatniego_mozliwego_resetu_dziennego:
            self.logger.info(f"Resetowanie misji dziennych. Poprzedni reset: {datetime.fromtimestamp(self.ostatni_reset_misji_dziennych_ts, UTC)}, Nowy reset: {datetime.fromtimestamp(timestamp_ostatniego_mozliwego_resetu_dziennego, UTC)}")
            self.ostatni_reset_misji_dziennych_ts = timestamp_ostatniego_mozliwego_resetu_dziennego

        dzien_resetu_tygodniowego_config = config.RESET_MISJI_TYGODNIOWYCH_DZIEN_TYGODNIA
        godzina_resetu_tygodniowego_utc = time_obj(hour=config.RESET_MISJI_TYGODNIOWYCH_GODZINA_UTC, tzinfo=UTC)

        dni_do_poprzedniego_dnia_resetu = (teraz_utc.weekday() - dzien_resetu_tygodniowego_config + 7) % 7
        data_ostatniego_dnia_resetu_tyg = teraz_utc.date() - timedelta(days=dni_do_poprzedniego_dnia_resetu)
        dt_ostatniego_mozliwego_resetu_tygodniowego = datetime.combine(data_ostatniego_dnia_resetu_tyg, godzina_resetu_tygodniowego_utc)

        if teraz_utc < dt_ostatniego_mozliwego_resetu_tygodniowego:
            dt_ostatniego_mozliwego_resetu_tygodniowego -= timedelta(weeks=1)

        timestamp_ostatniego_mozliwego_resetu_tygodniowego = int(dt_ostatniego_mozliwego_resetu_tygodniowego.timestamp())

        if self.ostatni_reset_misji_tygodniowych_ts < timestamp_ostatniego_mozliwego_resetu_tygodniowego:
            self.logger.info(f"Resetowanie misji tygodniowych. Poprzedni reset: {datetime.fromtimestamp(self.ostatni_reset_misji_tygodniowych_ts, UTC)}, Nowy reset: {datetime.fromtimestamp(timestamp_ostatniego_mozliwego_resetu_tygodniowego, UTC)}")
            self.ostatni_reset_misji_tygodniowych_ts = timestamp_ostatniego_mozliwego_resetu_tygodniowego


    @zadanie_resetowania_misji.before_loop
    async def przed_zadaniem_resetowania_misji(self):
        await self.wait_until_ready()
        self.logger.info("Pętla resetowania misji gotowa do startu.")

    @tasks.loop(minutes=config.SPRAWDZANIE_ROL_CZASOWYCH_CO_ILE_MINUT)
    async def zadanie_sprawdzania_rol_czasowych(self):
        if self.baza_danych is None: return
        try:
            wygasle_role_db = await self.baza_danych.pobierz_wygasle_role_czasowe()
            if not wygasle_role_db: return

            for wpis_id, user_id_str, server_id_str, rola_id_str, _ in wygasle_role_db:
                try:
                    guild = self.get_guild(int(server_id_str))
                    if not guild: await self.baza_danych.usun_aktywna_role_czasowa_po_id_wpisu(wpis_id); continue
                    member = guild.get_member(int(user_id_str))
                    rola_obj = guild.get_role(int(rola_id_str))
                    if not member or not rola_obj: await self.baza_danych.usun_aktywna_role_czasowa_po_id_wpisu(wpis_id); continue
                    if rola_obj in member.roles:
                        try: await member.remove_roles(rola_obj, reason="Rola czasowa wygasła.")
                        except: self.logger.error(f"Błąd usuwania roli {rola_obj.name} od {member.display_name}.")
                    await self.baza_danych.usun_aktywna_role_czasowa_po_id_wpisu(wpis_id)
                except Exception as e_inner: self.logger.error(f"Błąd przetwarzania wygasłej roli (wpis {wpis_id}): {e_inner}", exc_info=True); await self.baza_danych.usun_aktywna_role_czasowa_po_id_wpisu(wpis_id)
        except Exception as e: self.logger.error(f"Błąd w pętli ról czasowych: {e}", exc_info=True)

    @zadanie_sprawdzania_rol_czasowych.before_loop
    async def przed_zadaniem_sprawdzania_rol_czasowych(self): await self.wait_until_ready()

    @tasks.loop(hours=1)
    async def zadanie_konca_sezonu_miesiecznego(self):
        if self.baza_danych is None:
            self.logger.warning("Baza danych niedostępna, pomijam zadanie końca sezonu.")
            return

        teraz = datetime.now(UTC)
        if teraz.day == 1 and teraz.hour == 0 and teraz.minute < 5: 
            self.logger.info(f"Rozpoczynam zadanie końca sezonu miesięcznego dla {teraz.year}-{teraz.month-1 if teraz.month > 1 else 12}.")

            poprzedni_miesiac_dt = teraz - timedelta(days=1)
            rok_sezonu = poprzedni_miesiac_dt.year
            miesiac_sezonu = poprzedni_miesiac_dt.month

            self.logger.info(f"Przetwarzanie rankingu miesięcznego XP za {rok_sezonu}-{miesiac_sezonu}.")

            for guild in self.guilds:
                try:
                    ranking_miesieczny = await self.baza_danych.pobierz_ranking_miesiecznego_xp(str(guild.id), rok_sezonu, miesiac_sezonu, limit=5)
                    if not ranking_miesieczny:
                        self.logger.info(f"Brak danych rankingowych dla serwera {guild.name} ({guild.id}) za {rok_sezonu}-{miesiac_sezonu}.")
                        continue

                    self.logger.info(f"Ranking miesięczny XP dla {guild.name} ({rok_sezonu}-{miesiac_sezonu}): {ranking_miesieczny}")

                    embed_wyniki = discord.Embed(
                        title=f"🏆 Zakończenie Sezonu Rankingu XP - {miesiac_sezonu}/{rok_sezonu} 🏆",
                        description=f"Oto najlepsi Kronikarze serwera **{guild.name}** w minionym miesiącu!",
                        color=config.KOLOR_RANKINGU_SEZONOWEGO,
                        timestamp=teraz
                    )
                    if guild.icon:
                        embed_wyniki.set_thumbnail(url=guild.icon.url)

                    medale = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
                    opisy_zwyciezcow = []

                    for i, (user_id_str, xp_miesieczne_val) in enumerate(ranking_miesieczny):
                        miejsce = i + 1
                        member = guild.get_member(int(user_id_str))
                        nazwa_uzytkownika = ""
                        if not member:
                            try:
                                user_obj = await self.fetch_user(int(user_id_str))
                                nazwa_uzytkownika = user_obj.display_name if user_obj else f"Nieznany ({user_id_str})"
                            except discord.NotFound:
                                nazwa_uzytkownika = f"Nieznany ({user_id_str})"
                        else:
                            nazwa_uzytkownika = member.display_name

                        opisy_zwyciezcow.append(f"{medale[i] if i < len(medale) else f'**{miejsce}.**'} {nazwa_uzytkownika} - **{xp_miesieczne_val} XP**")

                        if miejsce in config.NAGRODY_RANKINGU_XP_MIESIECZNEGO:
                            nagroda_def = config.NAGRODY_RANKINGU_XP_MIESIECZNEGO[miejsce]
                            opis_nagrody_czesci = []

                            if nagroda_def.get("dukaty", 0) > 0 and self.baza_danych:
                                await self.baza_danych.aktualizuj_portfel(int(user_id_str), guild.id, ilosc_dukatow_do_dodania=nagroda_def["dukaty"])
                                opis_nagrody_czesci.append(f"{nagroda_def['dukaty']} ✨")
                            if nagroda_def.get("krysztaly", 0) > 0 and self.baza_danych:
                                await self.baza_danych.aktualizuj_portfel(int(user_id_str), guild.id, ilosc_krysztalow_do_dodania=nagroda_def["krysztaly"])
                                opis_nagrody_czesci.append(f"{nagroda_def['krysztaly']} {config.SYMBOL_WALUTY_PREMIUM}")

                            rola_id_nagrody = nagroda_def.get("rola_id")
                            if rola_id_nagrody and member and isinstance(member, discord.Member):
                                rola_do_nadania = guild.get_role(rola_id_nagrody)
                                if rola_do_nadania:
                                    try:
                                        await member.add_roles(rola_do_nadania, reason=f"Nagroda za Top {miejsce} w rankingu miesięcznym XP ({miesiac_sezonu}/{rok_sezonu})")
                                        opis_nagrody_czesci.append(f"Rola: {rola_do_nadania.mention}")
                                    except discord.Forbidden:
                                        self.logger.warning(f"Brak uprawnień do nadania roli nagrody {rola_do_nadania.name} użytkownikowi {member.display_name} na serwerze {guild.name}.")
                                    except Exception as e_role:
                                        self.logger.error(f"Błąd nadawania roli nagrody: {e_role}", exc_info=True)
                                else:
                                    self.logger.warning(f"Nie znaleziono roli nagrody o ID {rola_id_nagrody} na serwerze {guild.name}.")
                            
                            if nagroda_def.get("opis_dodatkowy"):
                                opis_nagrody_czesci.append(nagroda_def["opis_dodatkowy"])

                            if opis_nagrody_czesci:
                                opisy_zwyciezcow[-1] += f" (Nagroda: {', '.join(opis_nagrody_czesci)})"

                    embed_wyniki.add_field(name="🏆 Najlepsi Kronikarze Miesiąca:", value="\n".join(opisy_zwyciezcow), inline=False)
                    embed_wyniki.set_footer(text=f"Gratulacje! Nowy sezon rankingowy właśnie się rozpoczął! | Kroniki Elary")

                    kanal_ogloszen_id = config.ID_KANALU_OGLOSZEN_RANKINGU_MIESIECZNEGO
                    if kanal_ogloszen_id:
                        kanal_ogloszen = guild.get_channel(kanal_ogloszen_id)
                        if kanal_ogloszen and isinstance(kanal_ogloszen, discord.TextChannel):
                            try:
                                await kanal_ogloszen.send(embed=embed_wyniki)
                                self.logger.info(f"Ogłoszono wyniki rankingu miesięcznego XP dla {guild.name} na kanale {kanal_ogloszen.name}.")
                            except discord.Forbidden:
                                self.logger.warning(f"Brak uprawnień do wysłania ogłoszenia rankingu na kanale {kanal_ogloszen.name} ({guild.name}).")
                            except Exception as e_send:
                                self.logger.error(f"Błąd wysyłania ogłoszenia rankingu: {e_send}", exc_info=True)
                        else:
                            self.logger.warning(f"Nie znaleziono kanału ogłoszeń rankingu ({kanal_ogloszen_id}) na serwerze {guild.name} lub nie jest to kanał tekstowy.")
                    else:
                        self.logger.warning(f"ID_KANALU_OGLOSZEN_RANKINGU_MIESIECZNEGO nie jest skonfigurowane.")

                except Exception as e:
                    self.logger.error(f"Błąd podczas przetwarzania końca sezonu dla serwera {guild.name} ({guild.id}): {e}", exc_info=True)
            self.logger.info("Zakończono zadanie końca sezonu miesięcznego.")

    @zadanie_konca_sezonu_miesiecznego.before_loop
    async def przed_zadaniem_konca_sezonu_miesiecznego(self):
        await self.wait_until_ready()
        self.logger.info("Pętla końca sezonu miesięcznego gotowa do startu.")


    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot or not isinstance(message.channel, (discord.TextChannel, discord.Thread)):
            return
        if not isinstance(message.author, discord.Member):
             return

        await self.przyznaj_xp(
            message.author, message.guild, message.channel,
            config.XP_ZA_WIADOMOSC_MIN, config.XP_ZA_WIADOMOSC_MAX,
            "ostatnia_wiadomosc_timestamp", config.COOLDOWN_XP_WIADOMOSC_SEKUNDY,
            "napisanie wiadomości", inkrementuj_licznik_typ="wiadomosc",
            dodatkowe_dane_dla_osiagniec={"kanal_id": message.channel.id}
        )
        if self.intents.message_content: await self.process_commands(message)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id or (self.user and payload.user_id == self.user.id) or not payload.member: return # type: ignore
        guild = self.get_guild(payload.guild_id)
        if not guild: return
        member = payload.member
        if member.bot: return
        channel = guild.get_channel(payload.channel_id)
        if not channel or not isinstance(channel, (discord.TextChannel, discord.Thread)): return
        await self.przyznaj_xp(
            member, guild, channel,
            config.XP_ZA_REAKCJE_MIN, config.XP_ZA_REAKCJE_MAX,
            "ostatnia_reakcja_timestamp", config.COOLDOWN_XP_REAKCJE_SEKUNDY,
            "dodanie reakcji", inkrementuj_licznik_typ="reakcja"
        )

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot or self.baza_danych is None or not member.guild: return
        server_id, user_id = member.guild.id, member.id
        if server_id not in self.aktywni_na_glosowym_start_time:
            self.aktywni_na_glosowym_start_time[server_id] = {}

        def jest_aktywny(state: discord.VoiceState) -> bool:
            return (state.channel is not None and
                    (state.channel.guild.afk_channel is None or state.channel.guild.afk_channel.id != state.channel.id) and
                    not state.self_deaf and not state.self_mute)

        teraz_aktywny, byl_aktywny = jest_aktywny(after), jest_aktywny(before)

        if teraz_aktywny and not byl_aktywny:
            self.aktywni_na_glosowym_start_time[server_id][user_id] = time.time()
        elif not teraz_aktywny and byl_aktywny and user_id in self.aktywni_na_glosowym_start_time.get(server_id, {}):
            czas_startu = self.aktywni_na_glosowym_start_time[server_id].pop(user_id)
            czas_spedzony_sek = int(time.time() - czas_startu)
            if czas_spedzony_sek > 0:
                konfiguracja_serwera = self.pobierz_konfiguracje_xp_serwera(server_id)
                dane_xp_pelne = await self.baza_danych.pobierz_lub_stworz_doswiadczenie(user_id, server_id)
                indywidualnie_zablokowane = dane_xp_pelne[7]
                kanal_zablokowany_xp = False
                if before.channel:
                    konfig_kanalu = await self.baza_danych.pobierz_konfiguracje_xp_kanalu(str(server_id), str(before.channel.id))
                    if konfig_kanalu and konfig_kanalu[0]: kanal_zablokowany_xp = True
                if not konfiguracja_serwera["xp_zablokowane"] and not indywidualnie_zablokowane and not kanal_zablokowany_xp:
                    await self.baza_danych.aktualizuj_doswiadczenie(user_id, server_id, czas_dodany_glosowy=czas_spedzony_sek)
                    await self.aktualizuj_i_sprawdz_misje_po_akcji(member, member.guild, "czas_na_glosowym_od_resetu_sekundy", czas_spedzony_sek)

            if not self.aktywni_na_glosowym_start_time[server_id]: del self.aktywni_na_glosowym_start_time[server_id]

    @tasks.loop(minutes=config.XP_ZA_GLOS_CO_ILE_MINUT)
    async def zadanie_xp_za_glos(self):
        if self.baza_danych is None: return
        for guild_obj in self.guilds:
            if guild_obj.id in self.aktywni_na_glosowym_start_time:
                for user_id in list(self.aktywni_na_glosowym_start_time[guild_obj.id].keys()):
                    member = guild_obj.get_member(user_id)
                    if not member or member.bot:
                        if user_id in self.aktywni_na_glosowym_start_time[guild_obj.id]:
                            del self.aktywni_na_glosowym_start_time[guild_obj.id][user_id]
                        continue
                    if member.voice and member.voice.channel and \
                       (member.voice.channel.guild.afk_channel is None or member.voice.channel.guild.afk_channel.id != member.voice.channel.id) and \
                       not member.voice.self_deaf and not member.voice.self_mute and \
                       not member.voice.deaf and not member.voice.mute:
                        await self.przyznaj_xp(
                            member, guild_obj, member.voice.channel,
                            config.XP_ZA_GLOS_ILOSC_MIN, config.XP_ZA_GLOS_ILOSC_MAX,
                            None, 0, "aktywność na kanale głosowym"
                        )
                    else:
                        if user_id in self.aktywni_na_glosowym_start_time[guild_obj.id]:
                            del self.aktywni_na_glosowym_start_time[guild_obj.id][user_id]
            if guild_obj.id in self.aktywni_na_glosowym_start_time and not self.aktywni_na_glosowym_start_time[guild_obj.id]:
                del self.aktywni_na_glosowym_start_time[guild_obj.id]

    @zadanie_xp_za_glos.before_loop
    async def przed_zadaniem_xp_za_glos(self): await self.wait_until_ready()

    @tasks.loop(minutes=5)
    async def zadanie_live_ranking(self):
        if self.baza_danych is None: return
        teraz = datetime.now(UTC)
        medale = ["🥇", "🥈", "🥉"]
        for guild_id, config_data in list(self.konfiguracja_xp_serwera.items()):
            if config_data.get("live_ranking_message_id") and config_data.get("live_ranking_channel_id"):
                guild_obj = self.get_guild(guild_id)
                if not guild_obj: continue
                channel = guild_obj.get_channel(config_data["live_ranking_channel_id"])
                if not channel or not isinstance(channel, discord.TextChannel):
                    config_data["live_ranking_message_id"] = None; config_data["live_ranking_channel_id"] = None; continue
                try: message = await channel.fetch_message(config_data["live_ranking_message_id"])
                except (discord.NotFound, discord.Forbidden):
                    config_data["live_ranking_message_id"] = None; config_data["live_ranking_channel_id"] = None; continue

                ranking_all_time = await self.baza_danych.pobierz_ranking_xp(guild_id, limit=10)
                embed = await self._create_bot_embed(None, title="🏆 Wielka Tablica Kronikarzy 🏆", color=config.KOLOR_RANKINGU)
                embed.description = "Oto najdzielniejsi i najaktywniejsi Kronikarze!"
                embed.timestamp = teraz
                if guild_obj.icon: embed.set_thumbnail(url=guild_obj.icon.url)
                async def pobierz_nazwe_uzytkownika(uid: int) -> str:
                    member_obj = guild_obj.get_member(uid)
                    if member_obj: return member_obj.display_name
                    try:
                        user_obj = await self.fetch_user(uid)
                        return user_obj.display_name
                    except: return f"Tajemniczy Kronikarz ({uid})"
                if not ranking_all_time:
                    embed.add_field(name="📜 Puste Zwoje...", value="Księgi są puste. Czas pisać legendę!", inline=False)
                else:
                    opis_all_time_lines = [f"{medale[i] if i < 3 else f'**{i+1}.**'} {await pobierz_nazwe_uzytkownika(uid)} - Poziom: **{poz}** (XP: *{xp}*)" for i, (uid, xp, poz) in enumerate(ranking_all_time)]
                    embed.add_field(name="🌟 Najwięksi Bohaterowie (Ogólny Top 10)", value="\n".join(opis_all_time_lines), inline=False)
                if self.user and self.user.avatar: embed.set_footer(text=f"Aktualizacja co 5 min | Ostatnia: {teraz.strftime('%H:%M:%S UTC')}", icon_url=self.user.avatar.url) # type: ignore
                else: embed.set_footer(text=f"Aktualizacja co 5 min | Ostatnia: {teraz.strftime('%H:%M:%S UTC')}")
                try: await message.edit(embed=embed)
                except discord.HTTPException: pass

    @zadanie_live_ranking.before_loop
    async def przed_zadaniem_live_ranking(self): await self.wait_until_ready()

    @tasks.loop(hours=config.CZYSZCZENIE_BONUSOW_CO_ILE_GODZIN)
    async def zadanie_czyszczenia_bonusow(self):
        if self.baza_danych is None: return
        try:
            liczba_usunietych = await self.baza_danych.usun_wygasle_posiadane_przedmioty()
            if liczba_usunietych > 0: self.logger.info(f"Usunięto {liczba_usunietych} wygasłych przedmiotów/bonusów.")
        except Exception as e: self.logger.error(f"Błąd czyszczenia bonusów: {e}", exc_info=True)

    @zadanie_czyszczenia_bonusow.before_loop
    async def przed_zadaniem_czyszczenia_bonusow(self): await self.wait_until_ready()

    @tasks.loop(hours=1)
    async def zadanie_konca_sezonu_miesiecznego(self):
        if self.baza_danych is None:
            self.logger.warning("Baza danych niedostępna, pomijam zadanie końca sezonu.")
            return

        teraz = datetime.now(UTC)
        if teraz.day == 1 and teraz.hour == 0 and teraz.minute < 5: 
            self.logger.info(f"Rozpoczynam zadanie końca sezonu miesięcznego dla {teraz.year}-{teraz.month-1 if teraz.month > 1 else 12}.")

            poprzedni_miesiac_dt = teraz - timedelta(days=1)
            rok_sezonu = poprzedni_miesiac_dt.year
            miesiac_sezonu = poprzedni_miesiac_dt.month

            self.logger.info(f"Przetwarzanie rankingu miesięcznego XP za {rok_sezonu}-{miesiac_sezonu}.")

            for guild in self.guilds:
                try:
                    ranking_miesieczny = await self.baza_danych.pobierz_ranking_miesiecznego_xp(str(guild.id), rok_sezonu, miesiac_sezonu, limit=5)
                    if not ranking_miesieczny:
                        self.logger.info(f"Brak danych rankingowych dla serwera {guild.name} ({guild.id}) za {rok_sezonu}-{miesiac_sezonu}.")
                        continue

                    self.logger.info(f"Ranking miesięczny XP dla {guild.name} ({rok_sezonu}-{miesiac_sezonu}): {ranking_miesieczny}")

                    embed_wyniki = discord.Embed(
                        title=f"🏆 Zakończenie Sezonu Rankingu XP - {miesiac_sezonu}/{rok_sezonu} 🏆",
                        description=f"Oto najlepsi Kronikarze serwera **{guild.name}** w minionym miesiącu!",
                        color=config.KOLOR_RANKINGU_SEZONOWEGO,
                        timestamp=teraz
                    )
                    if guild.icon:
                        embed_wyniki.set_thumbnail(url=guild.icon.url)

                    medale = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
                    opisy_zwyciezcow = []

                    for i, (user_id_str, xp_miesieczne_val) in enumerate(ranking_miesieczny):
                        miejsce = i + 1
                        member = guild.get_member(int(user_id_str))
                        nazwa_uzytkownika = ""
                        if not member:
                            try:
                                user_obj = await self.fetch_user(int(user_id_str))
                                nazwa_uzytkownika = user_obj.display_name if user_obj else f"Nieznany ({user_id_str})"
                            except discord.NotFound:
                                nazwa_uzytkownika = f"Nieznany ({user_id_str})"
                        else:
                            nazwa_uzytkownika = member.display_name

                        opisy_zwyciezcow.append(f"{medale[i] if i < len(medale) else f'**{miejsce}.**'} {nazwa_uzytkownika} - **{xp_miesieczne_val} XP**")

                        if miejsce in config.NAGRODY_RANKINGU_XP_MIESIECZNEGO:
                            nagroda_def = config.NAGRODY_RANKINGU_XP_MIESIECZNEGO[miejsce]
                            opis_nagrody_czesci = []

                            if nagroda_def.get("dukaty", 0) > 0 and self.baza_danych:
                                await self.baza_danych.aktualizuj_portfel(int(user_id_str), guild.id, ilosc_dukatow_do_dodania=nagroda_def["dukaty"])
                                opis_nagrody_czesci.append(f"{nagroda_def['dukaty']} ✨")
                            if nagroda_def.get("krysztaly", 0) > 0 and self.baza_danych:
                                await self.baza_danych.aktualizuj_portfel(int(user_id_str), guild.id, ilosc_krysztalow_do_dodania=nagroda_def["krysztaly"])
                                opis_nagrody_czesci.append(f"{nagroda_def['krysztaly']} {config.SYMBOL_WALUTY_PREMIUM}")

                            rola_id_nagrody = nagroda_def.get("rola_id")
                            if rola_id_nagrody and member and isinstance(member, discord.Member):
                                rola_do_nadania = guild.get_role(rola_id_nagrody)
                                if rola_do_nadania:
                                    try:
                                        await member.add_roles(rola_do_nadania, reason=f"Nagroda za Top {miejsce} w rankingu miesięcznym XP ({miesiac_sezonu}/{rok_sezonu})")
                                        opis_nagrody_czesci.append(f"Rola: {rola_do_nadania.mention}")
                                    except discord.Forbidden:
                                        self.logger.warning(f"Brak uprawnień do nadania roli nagrody {rola_do_nadania.name} użytkownikowi {member.display_name} na serwerze {guild.name}.")
                                    except Exception as e_role:
                                        self.logger.error(f"Błąd nadawania roli nagrody: {e_role}", exc_info=True)
                                else:
                                    self.logger.warning(f"Nie znaleziono roli nagrody o ID {rola_id_nagrody} na serwerze {guild.name}.")
                            
                            if nagroda_def.get("opis_dodatkowy"):
                                opis_nagrody_czesci.append(nagroda_def["opis_dodatkowy"])

                            if opis_nagrody_czesci:
                                opisy_zwyciezcow[-1] += f" (Nagroda: {', '.join(opis_nagrody_czesci)})"

                    embed_wyniki.add_field(name="🏆 Najlepsi Kronikarze Miesiąca:", value="\n".join(opisy_zwyciezcow), inline=False)
                    embed_wyniki.set_footer(text=f"Gratulacje! Nowy sezon rankingowy właśnie się rozpoczął! | Kroniki Elary")

                    kanal_ogloszen_id = config.ID_KANALU_OGLOSZEN_RANKINGU_MIESIECZNEGO
                    if kanal_ogloszen_id:
                        kanal_ogloszen = guild.get_channel(kanal_ogloszen_id)
                        if kanal_ogloszen and isinstance(kanal_ogloszen, discord.TextChannel):
                            try:
                                await kanal_ogloszen.send(embed=embed_wyniki)
                                self.logger.info(f"Ogłoszono wyniki rankingu miesięcznego XP dla {guild.name} na kanale {kanal_ogloszen.name}.")
                            except discord.Forbidden:
                                self.logger.warning(f"Brak uprawnień do wysłania ogłoszenia rankingu na kanale {kanal_ogloszen.name} ({guild.name}).")
                            except Exception as e_send:
                                self.logger.error(f"Błąd wysyłania ogłoszenia rankingu: {e_send}", exc_info=True)
                        else:
                            self.logger.warning(f"Nie znaleziono kanału ogłoszeń rankingu ({kanal_ogloszen_id}) na serwerze {guild.name} lub nie jest to kanał tekstowy.")
                    else:
                        self.logger.warning(f"ID_KANALU_OGLOSZEN_RANKINGU_MIESIECZNEGO nie jest skonfigurowane.")

                except Exception as e:
                    self.logger.error(f"Błąd podczas przetwarzania końca sezonu dla serwera {guild.name} ({guild.id}): {e}", exc_info=True)
            self.logger.info("Zakończono zadanie końca sezonu miesięcznego.")

    @zadanie_konca_sezonu_miesiecznego.before_loop
    async def przed_zadaniem_konca_sezonu_miesiecznego(self):
        await self.wait_until_ready()
        self.logger.info("Pętla końca sezonu miesięcznego gotowa do startu.")


    @commands.Cog.listener()
    async def on_command_completion(self, context: Context) -> None:
        if not context.command or not context.guild or not isinstance(context.author, discord.Member): return
        self.logger.info(f"Wykonano '{context.command.qualified_name}' przez {context.author} na {context.guild.name if context.guild else 'DM'}.")

        await self.aktualizuj_i_sprawdz_misje_po_akcji(context.author, context.guild, "uzycie_komendy", 1, dodatkowe_dane={"nazwa_komendy": context.command.qualified_name})
        await self.sprawdz_i_przyznaj_osiagniecia(context.author, context.guild, "uzycie_specjalnej_komendy", 1, dodatkowe_dane={"nazwa_komendy": context.command.qualified_name})
        if context.command.cog_name:
            kategoria_komendy_lower = context.command.cog_name.lower()
            await self.aktualizuj_i_sprawdz_misje_po_akcji(context.author, context.guild, "uzycie_komendy_kategorii_od_resetu", 1, dodatkowe_dane={"kategoria_komendy": kategoria_komendy_lower})
            if self.baza_danych:
                nowa_liczba_uzyc_kategorii = await self.baza_danych.inkrementuj_uzycia_komend_kategorii(str(context.author.id), str(context.guild.id), kategoria_komendy_lower)
                await self.sprawdz_i_przyznaj_osiagniecia(context.author, context.guild, "liczba_uzyc_komend_kategorii", nowa_liczba_uzyc_kategorii, dodatkowe_dane={"kategoria_komendy": kategoria_komendy_lower})


    @commands.Cog.listener()
    async def on_command_error(self, context: Context, error) -> None:
        if isinstance(error, commands.CommandNotFound): return
        tytul_bledu, opis_bledu, kolor_bledu_embed, ephemeral_msg = "🔮 Coś Zakłóciło Magiczne Sploty...", "", config.KOLOR_BOT_BLAD, True
        if isinstance(error, commands.CommandOnCooldown):
            minuty, sekundy = divmod(error.retry_after, 60); godziny, minuty_reszta = divmod(minuty, 60); godziny %= 24
            czas_pozostaly_list = [f"{round(g)}g" for g in [godziny] if round(g) > 0] + [f"{round(m)}m" for m in [minuty_reszta] if round(m) > 0] + [f"{round(s)}s" for s in [sekundy] if round(s) > 0 or not czas_pozostaly_list]
            czas_pozostaly = " ".join(czas_pozostaly_list) if czas_pozostaly_list else "chwilę"
            tytul_bledu, opis_bledu, kolor_bledu_embed = "⏳ Chwila Oddechu!", f"Spróbuj ponownie za **{czas_pozostaly}**.", config.KOLOR_BOT_OSTRZEZENIE
        elif isinstance(error, commands.NotOwner): tytul_bledu, opis_bledu, kolor_bledu_embed = "⛔ Strefa Tkacza!", "Tylko Arcadius włada tą komendą.", config.KOLOR_BOT_BLAD_KRYTYCZNY
        elif isinstance(error, commands.MissingPermissions): tytul_bledu, opis_bledu = "🛡️ Brak Pieczęci!", f"Brakuje Ci pieczęci: {', '.join([f'`{p.replace('_', ' ').capitalize()}`' for p in error.missing_permissions])}."
        elif isinstance(error, commands.BotMissingPermissions): tytul_bledu, opis_bledu, ephemeral_msg = "⚠️ Osłabiona Magia!", f"Brakuje mi mocy: {', '.join([f'`{p.replace('_', ' ').capitalize()}`' for p in error.missing_permissions])}.", False
        elif isinstance(error, commands.MissingRequiredArgument): tytul_bledu, opis_bledu = "🤔 Zapomniany Składnik?", f"Potrzebny argument: `{error.param.name}`. Sprawdź `{self.prefix_bota}pomoc {context.command.qualified_name if context.command else ''}`."
        elif isinstance(error, commands.UserInputError): tytul_bledu, opis_bledu = "⚠️ Błędne Składniki", f"Nieprawidłowe argumenty. Szczegóły: {str(error)}"
        else: self.logger.error(f"Nieobsłużony błąd dla '{context.command.qualified_name if context.command else 'Nieznana'}': {error}", exc_info=True); tytul_bledu, opis_bledu, kolor_bledu_embed = "❗ Niespodziewane Zakłócenie", "Coś zakłóciło magię! Runa bada sprawę.", config.KOLOR_BOT_BLAD_KRYTYCZNY

        already_responded = False
        if context.interaction:
            try: already_responded = context.interaction.response.is_done()
            except Exception: pass
        if opis_bledu and not already_responded:
            embed = await self._create_bot_embed(context, title=tytul_bledu, description=opis_bledu, color=kolor_bledu_embed)
            try:
                if context.interaction:
                    if not context.interaction.response.is_done(): await context.interaction.response.send_message(embed=embed, ephemeral=ephemeral_msg)
                    else: await context.interaction.followup.send(embed=embed, ephemeral=ephemeral_msg)
                else: await context.send(embed=embed)
            except discord.HTTPException:
                try:
                    fallback_msg = f"**{tytul_bledu}**\n{opis_bledu}"
                    if context.interaction:
                        if not context.interaction.response.is_done(): await context.interaction.response.send_message(fallback_msg, ephemeral=ephemeral_msg)
                        else: await context.interaction.followup.send(fallback_msg, ephemeral=ephemeral_msg)
                    else: await context.send(fallback_msg)
                except Exception: pass

bot = BotDiscord()

if __name__ == "__main__":
    if TOKEN_ENV is None:
        bot.logger.critical("Nie znaleziono TOKENU bota! Zamykanie Kronik...")
        sys.exit("Brak tokenu bota.")
    try:
        bot.run(TOKEN_ENV)
    except discord.LoginFailure:
        bot.logger.critical("Nieprawidłowy token bota. Zamykanie Kronik...")
        sys.exit("Nieprawidłowy token bota.")
    except Exception as e:
        bot.logger.critical(f"Krytyczny błąd podczas uruchamiania Kronik Elary: {e}", exc_info=True)
        sys.exit(f"Krytyczny błąd: {e}")

