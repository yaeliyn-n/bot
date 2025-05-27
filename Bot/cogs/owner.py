import discord
from discord.ext import commands
from discord.ext.commands import Context
import time
from datetime import datetime, UTC
import typing
import asyncio

import config # Import konfiguracji

if typing.TYPE_CHECKING:
    from bot import BotDiscord # Zakładamy, że bot.py jest w głównym katalogu


class Wlasciciel(commands.Cog, name="wlasciciel"):
    """👑 Kapsuła z komendami dostępnymi tylko dla Tkacza Przeznaczeń (Właściciela Bota)."""
    def __init__(self, bot: 'BotDiscord'):
        self.bot = bot

    async def _create_owner_embed(self, context: Context, title: str, description: str, color: discord.Color) -> discord.Embed:
        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.now(UTC))
        if self.bot.user and self.bot.user.avatar:
            embed.set_author(name=f"Panel Właściciela - {self.bot.user.display_name}", icon_url=self.bot.user.avatar.url)
        else:
            embed.set_author(name="Panel Właściciela")

        if context.guild and context.guild.icon:
            embed.set_footer(text=f"Serwer: {context.guild.name} | Kroniki Elary", icon_url=context.guild.icon.url)
        else:
            embed.set_footer(text="Kroniki Elary")
        return embed

    @commands.command(
        name="synchronizuj",
        description="Synchronizuje komendy slash z Discordem. Opcjonalnie czyści stare komendy.",
    )
    @commands.is_owner()
    async def synchronizuj(self, context: Context, scope: str = "global", action: str = "sync") -> None:
        """
        Standardowa synchronizacja komend slash.
        Zakres (scope): 'global' lub 'guild'. Domyślnie 'global'.
        Akcja (action): 'sync' lub 'clear'. Domyślnie 'sync'.
        """
        if scope.lower() not in ["global", "guild"]:
            embed = await self._create_owner_embed(context, "⚠️ Błędny Zakres Synchronizacji", "Możliwe wartości dla 'scope' to `global` lub `guild`.", config.KOLOR_ADMIN_BLAD_OWNER)
            await context.send(embed=embed, ephemeral=True); return

        if action.lower() not in ["sync", "clear"]:
            embed = await self._create_owner_embed(context, "⚠️ Błędna Akcja Synchronizacji", "Możliwe wartości dla 'action' to `sync` lub `clear`.", config.KOLOR_ADMIN_BLAD_OWNER)
            await context.send(embed=embed, ephemeral=True); return

        start_time = time.time()
        log_message_parts = []
        target_guild_obj = context.guild if scope.lower() == "guild" else None

        if action.lower() == "clear":
            self.bot.logger.info(f"Rozpoczynam czyszczenie komend dla zakresu: {scope} (serwer: {target_guild_obj.name if target_guild_obj else 'Globalnie'}).")
            try:
                if target_guild_obj:
                    self.bot.tree.clear_commands(guild=target_guild_obj)
                    await self.bot.tree.sync(guild=target_guild_obj)
                    log_message_parts.append(f"Wyczyszczono komendy aplikacji dla serwera **{target_guild_obj.name}**.")
                else:
                    self.bot.tree.clear_commands(guild=None)
                    await self.bot.tree.sync()
                    log_message_parts.append("Wyczyszczono **globalne** komendy aplikacji.")
                self.bot.logger.info(f"Zakończono czyszczenie komend dla zakresu: {scope}.")
            except Exception as e:
                self.bot.logger.error(f"Błąd podczas czyszczenia komend ({scope}): {e}", exc_info=True)
                log_message_parts.append(f"❌ Błąd podczas czyszczenia komend ({scope}): `{e}`")

        # Właściwa synchronizacja
        self.bot.logger.info(f"Rozpoczynam synchronizację komend dla zakresu: {scope} (serwer: {target_guild_obj.name if target_guild_obj else 'Globalnie'}).")
        try:
            synced_commands = []
            if target_guild_obj:
                # Jeśli chcemy tylko synchronizować dla danego serwera, bez kopiowania globalnych:
                # synced_commands = await self.bot.tree.sync(guild=target_guild_obj)
                # Jeśli chcemy skopiować globalne i zsynchronizować:
                self.bot.tree.copy_global_to(guild=target_guild_obj)
                synced_commands = await self.bot.tree.sync(guild=target_guild_obj)
            else:
                synced_commands = await self.bot.tree.sync()

            log_message_parts.append(f"Zsynchronizowano **{len(synced_commands)}** komend w zakresie **{scope}**.")
            self.bot.logger.info(f"Zakończono synchronizację {len(synced_commands)} komend dla zakresu: {scope}.")
        except Exception as e:
            self.bot.logger.error(f"Błąd podczas synchronizacji komend ({scope}): {e}", exc_info=True)
            log_message_parts.append(f"❌ Błąd podczas synchronizacji komend ({scope}): `{e}`")

        end_time = time.time()
        czas_wykonania = end_time - start_time

        final_log_message = "\n".join(log_message_parts)
        embed_color = config.KOLOR_ADMIN_SUKCES_OWNER if "❌" not in final_log_message else config.KOLOR_ADMIN_BLAD_OWNER
        embed = await self._create_owner_embed(context, "🔄 Status Synchronizacji", f"{final_log_message}\nCzas wykonania: `{czas_wykonania:.2f}s`.", embed_color)
        await context.send(embed=embed)

    @commands.command(
        name="forcesync",
        description="Agresywnie czyści i synchronizuje komendy slash dla serwera lub globalnie."
    )
    @commands.is_owner()
    async def forcesync(self, context: Context, scope: str = "guild"):
        """
        Agresywnie czyści (ustawia pustą listę) i synchronizuje komendy.
        Używaj ostrożnie, zwłaszcza z 'global'.
        Zakres (scope): 'guild' (dla bieżącego serwera) lub 'global'.
        """
        if scope.lower() not in ["guild", "global"]:
            embed = await self._create_owner_embed(context, "⚠️ Błędny Zakres", "Dozwolone zakresy: `guild` lub `global`.", config.KOLOR_ADMIN_BLAD_OWNER)
            await context.send(embed=embed); return

        target_guild_obj = context.guild if scope.lower() == "guild" else None
        if scope.lower() == "guild" and not target_guild_obj:
            embed = await self._create_owner_embed(context, "⚠️ Błąd", "Zakres 'guild' wymaga wykonania komendy na serwerze.", config.KOLOR_ADMIN_BLAD_OWNER)
            await context.send(embed=embed); return

        start_time = time.time()
        messages = []
        color = config.KOLOR_ADMIN_BLAD_OWNER # Domyślnie błąd

        try:
            self.bot.logger.info(f"[ForceSync] Czyszczenie komend dla zakresu '{scope}'...")
            if target_guild_obj:
                self.bot.tree.clear_commands(guild=target_guild_obj) 
                await self.bot.tree.sync(guild=target_guild_obj)     
                messages.append(f"Wyczyszczono komendy dla serwera **{target_guild_obj.name}**.")
                self.bot.logger.info(f"[ForceSync] Wysłano pustą listę komend dla serwera {target_guild_obj.name}.")
            else: # global
                self.bot.tree.clear_commands(guild=None) 
                await self.bot.tree.sync(guild=None)    
                messages.append("Wyczyszczono **globalne** komendy aplikacji.")
                self.bot.logger.info("[ForceSync] Wysłano pustą listę globalnych komend.")

            # Krótka pauza, aby Discord przetworzył czyszczenie
            await asyncio.sleep(5) 

            self.bot.logger.info(f"[ForceSync] Rejestrowanie aktualnych komend dla zakresu '{scope}'...")
            synced_commands_count = 0
            if target_guild_obj:
                self.bot.tree.copy_global_to(guild=target_guild_obj) # Kopiuje globalne komendy do tego serwera
                synced = await self.bot.tree.sync(guild=target_guild_obj) # Synchronizuje (w tym skopiowane globalne i specyficzne dla serwera)
                synced_commands_count = len(synced)
            else: # global
                synced = await self.bot.tree.sync() # Synchronizuje globalne komendy
                synced_commands_count = len(synced)

            messages.append(f"Zarejestrowano **{synced_commands_count}** komend w zakresie **{scope}**.")
            self.bot.logger.info(f"[ForceSync] Zakończono rejestrację {synced_commands_count} komend dla zakresu: {scope}.")
            color = config.KOLOR_ADMIN_SUKCES_OWNER # Sukces, jeśli doszło tutaj bez błędu

        except Exception as e:
            self.bot.logger.error(f"[ForceSync] Błąd podczas force sync ({scope}): {e}", exc_info=True)
            messages.append(f"❌ Błąd podczas force sync ({scope}): `{e}`")
            # Kolor pozostaje na błąd

        end_time = time.time()
        czas_wykonania = end_time - start_time
        final_message = "\n".join(messages)
        embed = await self._create_owner_embed(context, f"⚙️ Force Sync Status ({scope.capitalize()})", f"{final_message}\nCzas wykonania: `{czas_wykonania:.2f}s`.", color)
        await context.send(embed=embed)


    @commands.command(
        name="rozladuj",
        aliases=["unload"],
        description="Rozładowuje wybraną kapsułę (cog).",
    )
    @commands.is_owner()
    async def rozladuj(self, context: Context, cog_name: str) -> None:
        try:
            await self.bot.unload_extension(f"cogs.{cog_name}")
            self.bot.logger.info(f"Pomyślnie rozładowano kapsułę: {cog_name}")
            embed = await self._create_owner_embed(context, "🔧 Kapsuła Rozładowana", f"Kapsuła `{cog_name}` została pomyślnie rozładowana.", config.KOLOR_ADMIN_SUKCES_OWNER)
        except commands.ExtensionNotLoaded:
            self.bot.logger.warning(f"Próba rozładowania niezaładowanej kapsuły: {cog_name}")
            embed = await self._create_owner_embed(context, "⚠️ Błąd Rozładowania", f"Kapsuła `{cog_name}` nie była załadowana.", config.KOLOR_ADMIN_BLAD_OWNER)
        except Exception as e:
            self.bot.logger.error(f"Błąd podczas rozładowywania kapsuły {cog_name}: {e}", exc_info=True)
            embed = await self._create_owner_embed(context, "❌ Krytyczny Błąd Rozładowania", f"Wystąpił błąd podczas rozładowywania `{cog_name}`:\n```py\n{e}\n```", config.KOLOR_ADMIN_BLAD_OWNER)
        await context.send(embed=embed)

    @commands.command(
        name="zaladuj",
        aliases=["load"],
        description="Ładuje wybraną kapsułę (cog).",
    )
    @commands.is_owner()
    async def zaladuj(self, context: Context, cog_name: str) -> None:
        try:
            await self.bot.load_extension(f"cogs.{cog_name}")
            self.bot.logger.info(f"Pomyślnie załadowano kapsułę: {cog_name}")
            embed = await self._create_owner_embed(context, "🔧 Kapsuła Załadowana", f"Kapsuła `{cog_name}` została pomyślnie załadowana.", config.KOLOR_ADMIN_SUKCES_OWNER)
        except commands.ExtensionAlreadyLoaded:
            self.bot.logger.warning(f"Próba załadowania już załadowanej kapsuły: {cog_name}")
            embed = await self._create_owner_embed(context, "⚠️ Błąd Ładowania", f"Kapsuła `{cog_name}` jest już załadowana.", config.KOLOR_ADMIN_BLAD_OWNER)
        except commands.ExtensionNotFound:
            self.bot.logger.error(f"Nie znaleziono kapsuły do załadowania: {cog_name}")
            embed = await self._create_owner_embed(context, "⚠️ Błąd Ładowania", f"Nie znaleziono kapsuły o nazwie `{cog_name}`.", config.KOLOR_ADMIN_BLAD_OWNER)
        except Exception as e:
            self.bot.logger.error(f"Błąd podczas ładowania kapsuły {cog_name}: {e}", exc_info=True)
            embed = await self._create_owner_embed(context, "❌ Krytyczny Błąd Ładowania", f"Wystąpił błąd podczas ładowania `{cog_name}`:\n```py\n{e}\n```", config.KOLOR_ADMIN_BLAD_OWNER)
        await context.send(embed=embed)

    @commands.command(
        name="przeladuj",
        aliases=["reload"],
        description="Przeładowuje wybraną kapsułę (cog) lub wszystkie.",
    )
    @commands.is_owner()
    async def przeladuj(self, context: Context, cog_name: str) -> None:
        if cog_name.lower() in ["wszystkie", "all"]:
            reloaded_cogs = []
            errors = []
            for extension in list(self.bot.extensions.keys()): # list() aby uniknąć błędu zmiany rozmiaru podczas iteracji
                try:
                    await self.bot.reload_extension(extension)
                    reloaded_cogs.append(extension.split('.')[-1]) # Bierzemy tylko nazwę coga
                except Exception as e:
                    self.bot.logger.error(f"Błąd podczas przeładowywania kapsuły {extension}: {e}", exc_info=True)
                    errors.append(f"**{extension.split('.')[-1]}**: {e}")

            if not errors:
                embed = await self._create_owner_embed(context, "🔧 Wszystkie Kapsuły Przeładowane", f"Pomyślnie przeładowano kapsuły: `{'`, `'.join(reloaded_cogs)}`.", config.KOLOR_ADMIN_SUKCES_OWNER)
            else:
                error_msg = "\n".join(errors)
                success_msg = f"Pomyślnie przeładowano: `{'`, `'.join(reloaded_cogs)}`.\n\n" if reloaded_cogs else ""
                embed = await self._create_owner_embed(context, "⚠️ Błędy Podczas Przeładowywania", f"{success_msg}**Błędy:**\n{error_msg}", config.KOLOR_ADMIN_BLAD_OWNER)
            await context.send(embed=embed)
            return

        try:
            await self.bot.reload_extension(f"cogs.{cog_name}")
            self.bot.logger.info(f"Pomyślnie przeładowano kapsułę: {cog_name}")
            embed = await self._create_owner_embed(context, "🔧 Kapsuła Przeładowana", f"Kapsuła `{cog_name}` została pomyślnie przeładowana.", config.KOLOR_ADMIN_SUKCES_OWNER)
        except commands.ExtensionNotLoaded:
            self.bot.logger.warning(f"Próba przeładowania niezaładowanej kapsuły: {cog_name}. Ładowanie...")
            try:
                await self.bot.load_extension(f"cogs.{cog_name}")
                self.bot.logger.info(f"Pomyślnie załadowano kapsułę: {cog_name} (po próbie przeładowania).")
                embed = await self._create_owner_embed(context, "🔧 Kapsuła Załadowana", f"Kapsuła `{cog_name}` nie była załadowana, więc została załadowana.", config.KOLOR_ADMIN_SUKCES_OWNER)
            except Exception as e_load:
                self.bot.logger.error(f"Błąd podczas ładowania kapsuły {cog_name} (po próbie przeładowania): {e_load}", exc_info=True)
                embed = await self._create_owner_embed(context, "❌ Krytyczny Błąd", f"Kapsuła `{cog_name}` nie była załadowana. Próba załadowania również nie powiodła się:\n```py\n{e_load}\n```", config.KOLOR_ADMIN_BLAD_OWNER)
        except Exception as e:
            self.bot.logger.error(f"Błąd podczas przeładowywania kapsuły {cog_name}: {e}", exc_info=True)
            embed = await self._create_owner_embed(context, "❌ Krytyczny Błąd Przeładowania", f"Wystąpił błąd podczas przeładowywania `{cog_name}`:\n```py\n{e}\n```", config.KOLOR_ADMIN_BLAD_OWNER)
        await context.send(embed=embed)

    @commands.command(
        name="restart", description="Restartuje bota (jeśli skonfigurowano z procesem nadrzędnym)."
    )
    @commands.is_owner()
    async def restart(self, context: Context) -> None:
        embed = await self._create_owner_embed(context, "🔄 Restartowanie Kronik Elary...", "Otrzymano polecenie restartu. Za chwilę powinienem powrócić do życia.", config.KOLOR_ADMIN_SPECIAL_OWNER)
        await context.send(embed=embed)
        self.bot.logger.info("Otrzymano polecenie restartu. Próba zamknięcia połączenia...")
        # W praktyce, proces nadrzędny (np. systemd, skrypt shell) powinien monitorować bota i go zrestartować.
        # Samo bot.close() tylko zakończy działanie obecnej instancji.
        await self.bot.close() 

    @commands.command(
        name="wylacz",
        aliases=["shutdown"],
        description="Wyłącza bota.",
    )
    @commands.is_owner()
    async def wylacz(self, context: Context) -> None:
        embed = await self._create_owner_embed(context, "🔌 Wyłączanie Kronik Elary...", "Do zobaczenia wkrótce, Kronikarze! Zapisuję ostatnie zwoje...", config.KOLOR_ADMIN_SPECIAL_OWNER)
        await context.send(embed=embed)
        self.bot.logger.info("Otrzymano polecenie wyłączenia. Zamykanie...")
        await self.bot.close()

    @commands.command(
        name="prefix",
        description="Zmienia prefix bota (tylko dla komend tekstowych)."
    )
    @commands.is_owner()
    async def prefix(self, context: Context, nowy_prefix: str) -> None:
        if len(nowy_prefix) > 5:
            embed = await self._create_owner_embed(context, "⚠️ Błędny Prefix", "Prefix nie może być dłuższy niż 5 znaków.", config.KOLOR_ADMIN_BLAD_OWNER)
            await context.send(embed=embed); return

        # Zmiana prefixu w `commands.Bot` wymaga ponownego przypisania `command_prefix`
        # Jeśli `command_prefix` było funkcją (np. `commands.when_mentioned_or(...)`),
        # to trzeba by ją zrekonstruować. W tym przypadku zakładamy, że jest to prosty string
        # lub lista stringów.
        # Dla `commands.when_mentioned_or` można by przechowywać oryginalne prefixy i je modyfikować.
        # Tutaj upraszczamy, zakładając, że `self.bot.prefix_bota` jest głównym prefixem.
        
        self.bot.prefix_bota = nowy_prefix # Aktualizacja atrybutu w klasie bota
        self.bot.command_prefix = commands.when_mentioned_or(nowy_prefix) # Aktualizacja atrybutu w instancji bota

        self.bot.logger.info(f"Zmieniono prefix bota na: '{nowy_prefix}'")
        embed = await self._create_owner_embed(context, "⚙️ Prefix Zmieniony", f"Nowy prefix dla komend tekstowych to: `{nowy_prefix}`\nTeraz bot będzie reagował na `{nowy_prefix}nazwa_komendy` oraz na wzmiankę.", config.KOLOR_ADMIN_SUKCES_OWNER)
        await context.send(embed=embed)

    @commands.command(
        name="ustawstatus",
        description="Ustawia niestandardowy status bota."
    )
    @commands.is_owner()
    async def ustawstatus(self, context: Context, *, tekst_statusu: str):
        if len(tekst_statusu) > 128:
            embed = await self._create_owner_embed(context, "⚠️ Tekst Statusu Za Długi", "Status może mieć maksymalnie 128 znaków.", config.KOLOR_ADMIN_BLAD_OWNER)
            await context.send(embed=embed); return

        if hasattr(self.bot, 'zadanie_statusu') and self.bot.zadanie_statusu.is_running(): # type: ignore
            self.bot.zadanie_statusu.cancel() # type: ignore
            self.bot.logger.info("Zatrzymano automatyczną pętlę statusów, aby ustawić status niestandardowy.")

        try:
            await self.bot.change_presence(activity=discord.Game(name=tekst_statusu))
            self.bot.logger.info(f"Ustawiono niestandardowy status: '{tekst_statusu}'")
            embed = await self._create_owner_embed(context, "✨ Status Ustawiony", f"Nowy status bota to: **{tekst_statusu}**\n_Aby przywrócić losowe statusy, użyj komendy `przeladuj status` (jeśli taka istnieje) lub zrestartuj bota._", config.KOLOR_ADMIN_SUKCES_OWNER)
        except Exception as e:
            self.bot.logger.error(f"Błąd podczas ustawiania statusu: {e}", exc_info=True)
            embed = await self._create_owner_embed(context, "❌ Błąd Ustawiania Statusu", f"Nie udało się ustawić statusu:\n```py\n{e}\n```", config.KOLOR_ADMIN_BLAD_OWNER)
        await context.send(embed=embed)

async def setup(bot: 'BotDiscord'):
    await bot.add_cog(Wlasciciel(bot))
