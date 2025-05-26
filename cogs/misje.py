import discord
from discord import app_commands, Interaction
from discord.ext import commands
from discord.ext.commands import Context
import time
from datetime import datetime, UTC, date as date_obj, timedelta, time as time_obj
import typing

# Import konfiguracji
import config

if typing.TYPE_CHECKING:
    from bot import BotDiscord 

class MisjeCog(commands.Cog, name="misje"):
    """🎯 Kapsuła zarządzająca Zleceniami i Misjami dla Kronikarzy."""
    COG_EMOJI = "🎯"

    def __init__(self, bot: 'BotDiscord'):
        self.bot = bot

    async def _create_missions_embed(self, context: typing.Union[Context, Interaction], title: str, description: str = "", color: discord.Color = config.KOLOR_BOT_INFO) -> discord.Embed:
        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.now(UTC))
        if self.bot.user and self.bot.user.avatar:
            embed.set_author(name=f"{self.bot.user.display_name} - Zlecenia Kronik", icon_url=self.bot.user.avatar.url)
        else:
            embed.set_author(name="Zlecenia Kronik Elary")
        
        guild = context.guild if isinstance(context, Context) else (context.guild if isinstance(context, Interaction) else None)
        
        if guild and guild.icon:
            embed.set_footer(text=f"Serwer: {guild.name} | Kroniki Elary", icon_url=guild.icon.url)
        else:
            embed.set_footer(text="Kroniki Elary")
        return embed

    def _get_current_cycle_start_ts(self, mission_type: str) -> int:
        now_utc = datetime.now(UTC)
        if mission_type == "dzienna":
            reset_time_today = datetime.combine(now_utc.date(), time_obj(hour=config.RESET_MISJI_DZIENNYCH_GODZINA_UTC, tzinfo=UTC))
            if now_utc >= reset_time_today:
                return int(reset_time_today.timestamp())
            else:
                return int((reset_time_today - timedelta(days=1)).timestamp())
        elif mission_type == "tygodniowa":
            today_weekday = now_utc.weekday() 
            reset_weekday = config.RESET_MISJI_TYGODNIOWYCH_DZIEN_TYGODNIA
            days_since_last_reset = (today_weekday - reset_weekday + 7) % 7
            last_reset_date = now_utc.date() - timedelta(days=days_since_last_reset)
            reset_datetime_this_week = datetime.combine(last_reset_date, time_obj(hour=config.RESET_MISJI_TYGODNIOWYCH_GODZINA_UTC, tzinfo=UTC))
            if now_utc < reset_datetime_this_week : 
                return int((reset_datetime_this_week - timedelta(weeks=1)).timestamp())
            return int(reset_datetime_this_week.timestamp())
        return 0 

    @commands.hybrid_command(name="misje", aliases=["zlecenia", "zadania"], description="Wyświetla dostępne misje i Twój postęp.")
    async def wyswietl_misje(self, context: Context):
        if not context.guild or self.bot.baza_danych is None:
            await context.send("Ta komenda jest dostępna tylko na serwerze, a Skarbiec Kronik musi być otwarty.", ephemeral=True)
            return

        user_id_str = str(context.author.id)
        server_id_str = str(context.guild.id)

        embed = await self._create_missions_embed(context, title=f"{self.COG_EMOJI} Tablica Zleceń Kronikarza: {context.author.display_name}")
        if context.author.display_avatar:
            embed.set_thumbnail(url=context.author.display_avatar.url)

        sekcje_misji = {"dzienna": [], "tygodniowa": [], "jednorazowa": [], "ukonczone_cykliczne": []}
        wszystkie_misje_def = self.bot.DEFINICJE_MISJI

        for misja_id, misja_def in wszystkie_misje_def.items():
            typ_misji = misja_def["typ_misji"]
            nazwa_misji = misja_def["nazwa"]
            opis_misji = misja_def["opis"]
            ikona_misji = misja_def.get("ikona", "🎯")
            
            ukonczona_w_tym_cyklu = False
            if typ_misji == "jednorazowa":
                if await self.bot.baza_danych.czy_misja_jednorazowa_ukonczona(user_id_str, server_id_str, misja_id):
                    ukonczona_w_tym_cyklu = True 
            elif typ_misji in ["dzienna", "tygodniowa"]:
                poczatek_cyklu_ts = self._get_current_cycle_start_ts(typ_misji)
                if await self.bot.baza_danych.czy_misja_ukonczona_w_cyklu(user_id_str, server_id_str, misja_id, poczatek_cyklu_ts):
                    ukonczona_w_tym_cyklu = True
            
            if ukonczona_w_tym_cyklu and typ_misji != "jednorazowa":
                 sekcje_misji["ukonczone_cykliczne"].append(f"{ikona_misji} ~~**{nazwa_misji}**~~ (Ukończono w tym cyklu)")
                 continue 
            elif ukonczona_w_tym_cyklu and typ_misji == "jednorazowa":
                 continue

            postep_opis_czesci = []
            wszystkie_warunki_dla_embed_spelnione = True

            for warunek_def in misja_def["warunki"]:
                typ_warunku_misji = warunek_def["typ_warunku"]
                wymagana_wartosc = warunek_def["wartosc"]
                
                ostatni_reset_ts = self._get_current_cycle_start_ts(typ_misji)
                
                _, _, _, _, _, aktualny_postep, _ = await self.bot.baza_danych.pobierz_lub_stworz_postep_misji(
                    user_id_str, server_id_str, misja_id, typ_warunku_misji, ostatni_reset_ts
                )

                procent_postepu_warunku = min(100, (aktualny_postep / wymagana_wartosc) * 100) if wymagana_wartosc > 0 else 100
                
                opis_warunku_dla_embed = f"  - {typ_warunku_misji.replace('_', ' ').capitalize()}: {aktualny_postep}/{wymagana_wartosc} ({procent_postepu_warunku:.0f}%)"
                if typ_warunku_misji == "czas_na_glosowym_od_resetu_sekundy":
                    # Używamy self.bot.formatuj_czas zamiast self.formatuj_czas
                    aktual_str = self.bot.formatuj_czas(aktualny_postep)
                    wym_str = self.bot.formatuj_czas(wymagana_wartosc)
                    opis_warunku_dla_embed = f"  - Czas na głosowym: {aktual_str}/{wym_str} ({procent_postepu_warunku:.0f}%)"
                
                postep_opis_czesci.append(opis_warunku_dla_embed)
                
                if aktualny_postep < wymagana_wartosc:
                    wszystkie_warunki_dla_embed_spelnione = False
            
            status_emoji = "✅" if wszystkie_warunki_dla_embed_spelnione else "⏳"
            postep_str = "\n".join(postep_opis_czesci)
            
            tekst_misji = f"{ikona_misji} **{nazwa_misji}** {status_emoji}\n_{opis_misji}_\n{postep_str}"
            
            if typ_misji == "dzienna":
                sekcje_misji["dzienna"].append(tekst_misji)
            elif typ_misji == "tygodniowa":
                sekcje_misji["tygodniowa"].append(tekst_misji)
            elif typ_misji == "jednorazowa": 
                sekcje_misji["jednorazowa"].append(tekst_misji)

        if sekcje_misji["dzienna"]:
            embed.add_field(name="☀️ Misje Dzienne", value="\n\n".join(sekcje_misji["dzienna"]) + "\n────────────────────", inline=False)
        else:
            embed.add_field(name="☀️ Misje Dzienne", value="Brak aktywnych misji dziennych lub wszystkie ukończone!", inline=False)

        if sekcje_misji["tygodniowa"]:
            embed.add_field(name="📅 Misje Tygodniowe", value="\n\n".join(sekcje_misji["tygodniowa"]) + "\n────────────────────", inline=False)
        else:
            embed.add_field(name="📅 Misje Tygodniowe", value="Brak aktywnych misji tygodniowych lub wszystkie ukończone!", inline=False)
            
        if sekcje_misji["jednorazowa"]:
            embed.add_field(name="✨ Misje Jednorazowe", value="\n\n".join(sekcje_misji["jednorazowa"]) + "\n────────────────────", inline=False)
        
        if sekcje_misji["ukonczone_cykliczne"]:
             embed.add_field(name="🎉 Ukończone w Tym Cyklu", value="\n".join(sekcje_misji["ukonczone_cykliczne"]), inline=False)


        if not sekcje_misji["dzienna"] and not sekcje_misji["tygodniowa"] and not sekcje_misji["jednorazowa"] and not sekcje_misji["ukonczone_cykliczne"]:
             embed.description = "Wygląda na to, że nie ma dla Ciebie żadnych aktywnych zleceń, Kronikarzu. Być może wszystkie już wykonałeś/aś? Sprawdź ponownie później!"
        
        await context.send(embed=embed)


async def setup(bot: 'BotDiscord'):
    await bot.add_cog(MisjeCog(bot))

