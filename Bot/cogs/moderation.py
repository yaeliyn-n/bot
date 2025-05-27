import os
from datetime import datetime, timezone # Dodano timezone
import typing # Dodano import typing

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context

import config # Import konfiguracji

if typing.TYPE_CHECKING:
    from bot import BotDiscord # Zakładamy, że bot.py jest w głównym katalogu

class Moderacja(commands.Cog, name="moderacja"):
    """🛡️ Kapsuła z komendami moderacyjnymi dla strażników porządku w Kronikach Elary."""
    COG_EMOJI = "🛡️"

    def __init__(self, bot: 'BotDiscord') -> None:
        self.bot = bot

    async def _create_moderation_embed(self, context: Context, title: str, description: str = "", color: discord.Color = config.KOLOR_BOT_INFO) -> discord.Embed:
        """Pomocnicza funkcja do tworzenia embedów moderacyjnych dla tej kapsuły."""
        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.now(timezone.utc))
        if self.bot.user and self.bot.user.avatar:
             embed.set_author(name=f"{self.bot.user.display_name} - Moderacja", icon_url=self.bot.user.avatar.url)
        else:
            embed.set_author(name="Moderacja Kronik Elary")
        
        if context.guild and context.guild.icon:
            embed.set_footer(text=f"Serwer: {context.guild.name} | Kroniki Elary", icon_url=context.guild.icon.url)
        else:
            embed.set_footer(text="Kroniki Elary")
        return embed

    @commands.hybrid_command(
        name="wyrzuc",
        description="Wyrzuca użytkownika z serwera.",
    )
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    @app_commands.describe(
        user="Użytkownik, który powinien zostać wyrzucony.",
        reason="Powód, dla którego użytkownik powinien zostać wyrzucony.",
    )
    async def wyrzuc(
        self, context: Context, user: discord.User, *, reason: str = "Nie podano"
    ) -> None:
        if not context.guild:
            await context.send("Tej komendy można użyć tylko na serwerze.", ephemeral=True)
            return
        member = context.guild.get_member(user.id) or await context.guild.fetch_member(user.id)
        if member.guild_permissions.administrator:
            embed = await self._create_moderation_embed(context, "⛔ Błąd", "Użytkownik ma uprawnienia administratora.", config.KOLOR_BOT_BLAD)
            await context.send(embed=embed)
        else:
            try:
                dm_message = f"Zostałeś/aś wyrzucony/a przez **{context.author.display_name}** z serwera **{context.guild.name}**!\nPowód: {reason}"
                try:
                    await member.send(dm_message)
                except discord.Forbidden:
                    pass 

                await member.kick(reason=f"{reason} (Moderator: {context.author.name}#{context.author.discriminator})")
                
                embed = await self._create_moderation_embed(context, "👢 Użytkownik Wyrzucony", f"**{member.display_name}** ({member.id}) został/a wyrzucony/a przez **{context.author.mention}**!", config.KOLOR_BOT_OSTRZEZENIE)
                embed.add_field(name="Powód:", value=reason, inline=False)
                await context.send(embed=embed)

            except discord.Forbidden:
                embed = await self._create_moderation_embed(context, "⛔ Błąd Uprawnień", "Nie mam uprawnień, aby wyrzucić tego użytkownika. Upewnij się, że moja rola jest wyżej.", config.KOLOR_BOT_BLAD)
                await context.send(embed=embed)
            except Exception as e:
                self.bot.logger.error(f"Błąd podczas wyrzucania użytkownika {user.id}: {e}", exc_info=True)
                embed = await self._create_moderation_embed(context, "❌ Wystąpił Błąd", "Podczas próby wyrzucenia użytkownika wystąpił nieoczekiwany błąd.", config.KOLOR_BOT_BLAD_KRYTYCZNY)
                await context.send(embed=embed)

    @commands.hybrid_command(
        name="zmienpseudonim",
        description="Zmienia pseudonim użytkownika na serwerze.",
    )
    @commands.has_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    @app_commands.describe(
        user="Użytkownik, którego pseudonim ma zostać zmieniony.",
        nickname="Nowy pseudonim, który ma zostać ustawiony (pozostaw puste, aby usunąć).",
    )
    async def zmienpseudonim(
        self, context: Context, user: discord.Member, *, nickname: typing.Optional[str] = None
    ) -> None:
        if not context.guild:
            await context.send("Tej komendy można użyć tylko na serwerze.", ephemeral=True)
            return
        try:
            old_nickname = user.display_name
            await user.edit(nick=nickname)
            action_description = f"zmieniono na **{nickname}**" if nickname else "usunięto (przywrócono domyślny)"
            embed = await self._create_moderation_embed(context, "👤 Pseudonim Zmieniony", f"Pseudonim użytkownika **{old_nickname}** ({user.mention}) {action_description}!", config.KOLOR_BOT_SUKCES)
            await context.send(embed=embed)
        except discord.Forbidden:
            embed = await self._create_moderation_embed(context, "⛔ Błąd Uprawnień", "Nie mam uprawnień do zmiany pseudonimu tego użytkownika. Upewnij się, że moja rola jest wyżej.", config.KOLOR_BOT_BLAD)
            await context.send(embed=embed)
        except Exception as e:
            self.bot.logger.error(f"Błąd podczas zmiany pseudonimu użytkownika {user.id}: {e}", exc_info=True)
            embed = await self._create_moderation_embed(context, "❌ Wystąpił Błąd", "Podczas próby zmiany pseudonimu wystąpił nieoczekiwany błąd.", config.KOLOR_BOT_BLAD_KRYTYCZNY)
            await context.send(embed=embed)

    @commands.hybrid_command(
        name="zbanuj",
        description="Banuje użytkownika na serwerze.",
    )
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @app_commands.describe(
        user="Użytkownik, który powinien zostać zbanowany.",
        reason="Powód, dla którego użytkownik powinien zostać zbanowany.",
    )
    async def zbanuj(
        self, context: Context, user: discord.User, *, reason: str = "Nie podano"
    ) -> None:
        if not context.guild:
            await context.send("Tej komendy można użyć tylko na serwerze.", ephemeral=True)
            return
        member = context.guild.get_member(user.id) 
        if member and member.guild_permissions.administrator:
            embed = await self._create_moderation_embed(context, "⛔ Błąd", "Użytkownik ma uprawnienia administratora.", config.KOLOR_BOT_BLAD)
            await context.send(embed=embed)
            return
        
        try:
            dm_message = f"Zostałeś/aś zbanowany/a przez **{context.author.display_name}** na serwerze **{context.guild.name}**!\nPowód: {reason}"
            try:
                await user.send(dm_message) 
            except discord.Forbidden:
                pass

            await context.guild.ban(user, reason=f"{reason} (Moderator: {context.author.name}#{context.author.discriminator})")
            
            embed = await self._create_moderation_embed(context, "🔨 Użytkownik Zbanowany", f"**{user.name}#{user.discriminator}** ({user.id}) został/a zbanowany/a przez **{context.author.mention}**!", config.KOLOR_BOT_BLAD_KRYTYCZNY)
            embed.add_field(name="Powód:", value=reason, inline=False)
            await context.send(embed=embed)

        except discord.Forbidden:
            embed = await self._create_moderation_embed(context, "⛔ Błąd Uprawnień", "Nie mam uprawnień, aby zbanować tego użytkownika. Upewnij się, że moja rola jest wyżej.", config.KOLOR_BOT_BLAD)
            await context.send(embed=embed)
        except Exception as e:
            self.bot.logger.error(f"Błąd podczas banowania użytkownika {user.id}: {e}", exc_info=True)
            embed = await self._create_moderation_embed(context, "❌ Wystąpił Błąd", "Podczas próby zbanowania użytkownika wystąpił nieoczekiwany błąd.", config.KOLOR_BOT_BLAD_KRYTYCZNY)
            await context.send(embed=embed)

    @commands.hybrid_group(
        name="ostrzezenie",
        description="Zarządza ostrzeżeniami użytkownika na serwerze.",
    )
    @commands.has_permissions(manage_messages=True)
    async def ostrzezenie(self, context: Context) -> None:
        if not context.guild:
            await context.send("Tej komendy można użyć tylko na serwerze.", ephemeral=True)
            return
        if context.invoked_subcommand is None:
            embed = await self._create_moderation_embed(context, "📒 System Ostrzeżeń", "Proszę podać podkomendę.\n\n**Podkomendy:**\n`dodaj` - Dodaj ostrzeżenie użytkownikowi.\n`usun` - Usuń ostrzeżenie użytkownikowi.\n`lista` - Wyświetl wszystkie ostrzeżenia użytkownika.", config.KOLOR_BOT_OSTRZEZENIE)
            await context.send(embed=embed, ephemeral=True)

    @ostrzezenie.command(
        name="dodaj",
        description="Dodaje ostrzeżenie użytkownikowi na serwerze.",
    )
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(
        user="Użytkownik, który powinien zostać ostrzeżony.",
        reason="Powód, dla którego użytkownik powinien zostać ostrzeżony.",
    )
    async def ostrzezenie_dodaj(
        self, context: Context, user: discord.Member, *, reason: str = "Nie podano"
    ) -> None:
        if not context.guild:
            await context.send("Tej komendy można użyć tylko na serwerze.", ephemeral=True)
            return
        if self.bot.baza_danych is None:
            await context.send("Baza danych jest niedostępna.", ephemeral=True); return

        id_ostrzezenia = await self.bot.baza_danych.dodaj_ostrzezenie(
            user.id, context.guild.id, context.author.id, reason
        )
        dane_ostrzezen = await self.bot.baza_danych.pobierz_ostrzezenia(user.id, context.guild.id)
        liczba_ostrzezen = len(dane_ostrzezen)

        embed = await self._create_moderation_embed(context, "⚠️ Użytkownik Ostrzeżony", f"**{user.mention}** został/a ostrzeżony/a przez **{context.author.mention}**! (Ostrzeżenie #{id_ostrzezenia})\nŁączna liczba ostrzeżeń: **{liczba_ostrzezen}**", config.KOLOR_BOT_OSTRZEZENIE)
        embed.add_field(name="Powód:", value=reason, inline=False)
        await context.send(embed=embed)
        try:
            await user.send(f"Zostałeś/aś ostrzeżony/a przez **{context.author.display_name}** na serwerze **{context.guild.name}**!\nPowód: {reason}\nTo Twoje {liczba_ostrzezen}. ostrzeżenie.")
        except discord.Forbidden:
            await context.send(f"{user.mention}, zostałeś/aś ostrzeżony/a! (DM zablokowane)", ephemeral=True)


    @ostrzezenie.command(
        name="usun",
        description="Usuwa ostrzeżenie użytkownikowi na serwerze.",
    )
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(
        user="Użytkownik, któremu ma zostać usunięte ostrzeżenie.",
        warn_id="ID ostrzeżenia, które ma zostać usunięte.",
    )
    async def ostrzezenie_usun(
        self, context: Context, user: discord.Member, warn_id: int
    ) -> None:
        if not context.guild:
            await context.send("Tej komendy można użyć tylko na serwerze.", ephemeral=True)
            return
        if self.bot.baza_danych is None:
            await context.send("Baza danych jest niedostępna.", ephemeral=True); return
            
        liczba_pozostalych = await self.bot.baza_danych.usun_ostrzezenie(warn_id, user.id, context.guild.id)
        embed = await self._create_moderation_embed(context, "✅ Ostrzeżenie Usunięte", f"Usunąłem ostrzeżenie **#{warn_id}** od **{user.mention}**!\nPozostała liczba ostrzeżeń: **{liczba_pozostalych}**", config.KOLOR_BOT_SUKCES)
        await context.send(embed=embed)

    @ostrzezenie.command(
        name="lista",
        description="Pokazuje ostrzeżenia użytkownika na serwerze.",
    )
    @commands.has_guild_permissions(manage_messages=True)
    @app_commands.describe(user="Użytkownik, którego ostrzeżenia chcesz zobaczyć.")
    async def ostrzezenie_lista(self, context: Context, user: discord.Member) -> None:
        if not context.guild:
            await context.send("Tej komendy można użyć tylko na serwerze.", ephemeral=True)
            return
        if self.bot.baza_danych is None:
            await context.send("Baza danych jest niedostępna.", ephemeral=True); return

        lista_ostrzezen_db = await self.bot.baza_danych.pobierz_ostrzezenia(user.id, context.guild.id)
        embed = await self._create_moderation_embed(context, f"📒 Ostrzeżenia Użytkownika: {user.display_name}", color=config.KOLOR_BOT_INFO)
        if user.display_avatar:
            embed.set_thumbnail(url=user.display_avatar.url)

        if not lista_ostrzezen_db:
            embed.description = "Ten użytkownik nie ma żadnych ostrzeżeń."
        else:
            opis = []
            for ostrz in lista_ostrzezen_db:
                warn_actual_id = ostrz[0] 
                moderator_id_db = ostrz[3]
                reason_db = ostrz[4]
                created_at_val = ostrz[5] 
                
                timestamp_discord_str = ""
                # Sprawdzamy, czy created_at_val jest stringiem i próbujemy go sparsować
                # Zakładamy, że baza danych zwraca string w formacie '%Y-%m-%d %H:%M:%S' dla timestamp
                if isinstance(created_at_val, str):
                    try:
                        dt_obj = datetime.strptime(created_at_val, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                        timestamp_discord_str = f"<t:{int(dt_obj.timestamp())}:R>"
                    except ValueError:
                         # Jeśli parsowanie się nie uda, próbujemy jako timestamp (jeśli to int)
                        try:
                            timestamp_discord_str = f"<t:{int(created_at_val)}:R>"
                        except (ValueError, TypeError):
                            timestamp_discord_str = f"(Nieznana data: {created_at_val})"
                elif isinstance(created_at_val, (int, float)): # Jeśli już jest timestampem
                     timestamp_discord_str = f"<t:{int(created_at_val)}:R>"
                else: # Jeśli to obiekt datetime
                    try:
                        timestamp_discord_str = f"<t:{int(created_at_val.replace(tzinfo=timezone.utc).timestamp())}:R>"
                    except Exception:
                        timestamp_discord_str = "(Nieprawidłowa data)"


                moderator_mention = f"<@{moderator_id_db}>"
                opis.append(f"**ID: {warn_actual_id}** | Przez: {moderator_mention} | {timestamp_discord_str}\n*Powód:* {reason_db}")
            
            embed.description = "\n\n".join(opis) if opis else "Brak ostrzeżeń do wyświetlenia."
        await context.send(embed=embed)

    @commands.hybrid_command(
        name="czysc",
        description="Usuwa określoną liczbę wiadomości.",
    )
    @commands.has_guild_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @app_commands.describe(amount="Liczba wiadomości, które mają zostać usunięte (1-100).")
    async def czysc(self, context: Context, amount: commands.Range[int, 1, 100]) -> None:
        if not context.guild:
            await context.send("Tej komendy można użyć tylko na serwerze.", ephemeral=True)
            return
        if context.interaction: 
            await context.interaction.response.defer(ephemeral=True)
        
        # +1 aby usunąć również komendę wywołującą (jeśli to komenda tekstowa)
        # Dla slash command, defer() już obsłużył interakcję.
        limit_do_usuniecia = amount + 1 if not context.interaction else amount
        usuniete_wiadomosci = await context.channel.purge(limit=limit_do_usuniecia)
        
        # Odejmujemy 1 od usuniętych, jeśli komenda była tekstowa, bo sama komenda też została usunięta
        liczba_faktycznie_usunietych = len(usuniete_wiadomosci) - 1 if not context.interaction and len(usuniete_wiadomosci) > 0 else len(usuniete_wiadomosci)

        potwierdzenie_embed = await self._create_moderation_embed(context, "🧹 Wiadomości Usunięte", f"**{context.author.mention}** usunął/usunęła **{liczba_faktycznie_usunietych}** wiadomości!", config.KOLOR_BOT_SUKCES)
        
        if context.interaction:
            await context.interaction.followup.send(embed=potwierdzenie_embed, ephemeral=True)
        else: 
            await context.send(embed=potwierdzenie_embed, delete_after=10)


    @commands.hybrid_command(
        name="hackban",
        description="Banuje użytkownika, który nie musi być na serwerze (wg ID).",
    )
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @app_commands.describe(
        user_id="ID użytkownika, który powinien zostać zbanowany.",
        reason="Powód, dla którego użytkownik powinien zostać zbanowany.",
    )
    async def hackban(
        self, context: Context, user_id: str, *, reason: str = "Nie podano"
    ) -> None:
        if not context.guild:
            await context.send("Tej komendy można użyć tylko na serwerze.", ephemeral=True)
            return
        try:
            user_id_int = int(user_id)
            user_to_ban = discord.Object(id=user_id_int) 
        except ValueError:
            embed = await self._create_moderation_embed(context, "⛔ Błąd", "Podano nieprawidłowe ID użytkownika.", config.KOLOR_BOT_BLAD)
            await context.send(embed=embed); return

        try:
            await context.guild.ban(user_to_ban, reason=f"{reason} (Hackban przez: {context.author.name}#{context.author.discriminator})")
            
            try:
                banned_user_obj = await self.bot.fetch_user(user_id_int)
                user_display = f"{banned_user_obj.name}#{banned_user_obj.discriminator}"
            except discord.NotFound:
                user_display = f"Użytkownik o ID {user_id_int}"

            embed = await self._create_moderation_embed(context, "🔨 Użytkownik Zbanowany (Hackban)", f"**{user_display}** został/a zbanowany/a przez **{context.author.mention}**!", config.KOLOR_BOT_BLAD_KRYTYCZNY)
            embed.add_field(name="Powód:", value=reason, inline=False)
            await context.send(embed=embed)
        except discord.Forbidden:
            embed = await self._create_moderation_embed(context, "⛔ Błąd Uprawnień", "Nie mam uprawnień, aby zbanować tego użytkownika. Upewnij się, że moja rola jest wyżej.", config.KOLOR_BOT_BLAD)
            await context.send(embed=embed)
        except Exception as e:
            self.bot.logger.error(f"Błąd podczas hackbanowania użytkownika {user_id}: {e}", exc_info=True)
            embed = await self._create_moderation_embed(context, "❌ Wystąpił Błąd", "Podczas próby zbanowania użytkownika (hackban) wystąpił nieoczekiwany błąd.", config.KOLOR_BOT_BLAD_KRYTYCZNY)
            await context.send(embed=embed)


    @commands.hybrid_command(
        name="archiwizuj",
        description="Archiwizuje w pliku tekstowym ostatnie wiadomości z wybranym limitem.",
    )
    @commands.has_permissions(manage_messages=True)
    @app_commands.describe(
        limit="Limit wiadomości, które mają zostać zarchiwizowane (1-1000).",
    )
    async def archiwizuj(self, context: Context, limit: commands.Range[int, 1, 1000] = 10) -> None:
        if not context.guild:
            await context.send("Tej komendy można użyć tylko na serwerze.", ephemeral=True)
            return
        if not self.bot.intents.message_content: # Sprawdzenie intencji
            await context.send("Ta komenda wymaga intencji `MESSAGE_CONTENT` do poprawnego działania (aby odczytać treść wiadomości). Skontaktuj się z administratorem bota.", ephemeral=True)
            self.bot.logger.warning("Próba użycia komendy 'archiwizuj' bez intencji MESSAGE_CONTENT.")
            return

        if context.interaction:
            await context.interaction.response.defer(ephemeral=False) 

        plik_logu_nazwa = f"archiwum_{context.channel.id}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.txt"
        
        try:
            with open(plik_logu_nazwa, "w", encoding="UTF-8") as f:
                f.write(
                    f'Zarchiwizowane wiadomości z kanału: #{context.channel.name} ({context.channel.id})\n'
                    f'Serwer: "{context.guild.name}" ({context.guild.id})\n'
                    f'Data archiwizacji: {datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M:%S %Z")}\n'
                    f'Archiwizujący: {context.author.name}#{context.author.discriminator} ({context.author.id})\n'
                    f'Limit wiadomości: {limit}\n\n'
                    f'{"="*50}\n\n'
                )
                
                counter = 0
                # Iterujemy po historii, aby zachować kolejność chronologiczną w pliku (od najstarszych do najnowszych)
                messages_history = [message async for message in context.channel.history(limit=limit)]
                for message in reversed(messages_history): # Odwracamy listę
                    counter += 1
                    zalaczniki_str_list = [att.url for att in message.attachments]
                    tekst_zalacznikow = f"[Załączniki: {', '.join(zalaczniki_str_list)}]" if zalaczniki_str_list else ""
                    
                    f.write(
                        f"[{message.created_at.replace(tzinfo=timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')}] "
                        f"{message.author.name}#{message.author.discriminator} ({message.author.id}):\n"
                        f"{message.content}\n" 
                        f"{tekst_zalacznikow}\n"
                        f"---\n"
                    )
            
            plik_do_wyslania = discord.File(plik_logu_nazwa)
            
            if context.interaction:
                await context.interaction.followup.send(f"Archiwum {limit} wiadomości z kanału {context.channel.mention} zostało utworzone.", file=plik_do_wyslania)
            else:
                await context.send(f"Archiwum {limit} wiadomości z kanału {context.channel.mention} zostało utworzone.", file=plik_do_wyslania)

        except Exception as e:
            self.bot.logger.error(f"Błąd podczas archiwizacji kanału {context.channel.id}: {e}", exc_info=True)
            error_message = "Wystąpił błąd podczas tworzenia archiwum."
            if context.interaction and not context.interaction.response.is_done():
                await context.interaction.followup.send(error_message, ephemeral=True)
            elif not context.interaction :
                 await context.send(error_message, ephemeral=True)
            elif context.interaction and context.interaction.response.is_done(): # Fallback jeśli followup nie zadziała
                 await context.send(error_message, ephemeral=True)


        finally:
            if os.path.exists(plik_logu_nazwa):
                os.remove(plik_logu_nazwa)


async def setup(bot: 'BotDiscord') -> None:
    await bot.add_cog(Moderacja(bot))
