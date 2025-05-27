import discord
from discord.ext import commands
from discord.ext.commands import Context
from datetime import datetime, UTC
import typing
from discord import app_commands, Interaction # Dodano Interaction

# Import konfiguracji
import config

if typing.TYPE_CHECKING:
    from bot import BotDiscord # Zakładamy, że bot.py jest w głównym katalogu

class HelpSelect(discord.ui.Select):
    def __init__(self, help_command: 'CustomHelpCommand', filtered_cog_mapping: dict):
        self.help_command = help_command
        self.cog_mapping = filtered_cog_mapping

        options = [
            discord.SelectOption(label="Strona Główna Pomocy", emoji="🏠", value="_main", description="Wróć do listy kategorii")
        ]
        for cog, _ in filtered_cog_mapping.items():
            if cog is None:
                continue

            cog_name = cog.qualified_name.capitalize()
            emoji = getattr(cog, "COG_EMOJI", "✨")

            options.append(discord.SelectOption(
                label=cog_name,
                emoji=emoji,
                value=cog.qualified_name,
                description=cog.description[:100] if cog.description else "Wybierz, aby zobaczyć komendy."
            ))

        super().__init__(
            placeholder="Wybierz kategorię zwojów...",
            min_values=1,
            max_values=1,
            options=options if len(options) > 1 else [options[0]], # Zapewnienie, że opcje nie są puste
            row=0
        )
        if len(options) <=1 :
            self.disabled = True


    async def callback(self, interaction: Interaction):
        selected_value = self.values[0]
        if not self.help_command.context or not self.help_command.context.bot:
            await interaction.response.send_message("Wystąpił błąd z kontekstem pomocy.", ephemeral=True)
            return

        bot_mapping = self.help_command.get_bot_mapping()
        filtered_mapping_for_view = await self.help_command._filter_mapping(bot_mapping, self.help_command.context)


        if selected_value == "_main":
            embed = await self.help_command._build_bot_help_embed(filtered_mapping_for_view)
            view = HelpView(self.help_command, filtered_mapping_for_view)
            await interaction.response.edit_message(embed=embed, view=view)
            return

        selected_cog = self.help_command.context.bot.get_cog(selected_value)

        if selected_cog:
            embed = await self.help_command._build_cog_help_embed(selected_cog)
            view = HelpView(self.help_command, filtered_mapping_for_view)
            for item in list(view.children): # Tworzymy kopię listy, aby móc modyfikować oryginał
                if isinstance(item, HelpSelect):
                    view.remove_item(item)
            view.add_item(HelpSelect(self.help_command, filtered_mapping_for_view))
            view.add_item(HelpGoBackButton(self.help_command, filtered_mapping_for_view))
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            await interaction.response.send_message(f"Nie znaleziono kategorii: {selected_value}", ephemeral=True)

class HelpGoBackButton(discord.ui.Button):
    def __init__(self, help_command: 'CustomHelpCommand', filtered_cog_mapping: dict):
        super().__init__(label="Powrót do Kategorii", emoji="↩️", style=discord.ButtonStyle.grey, row=1) # Poprawione emoji
        self.help_command = help_command
        self.filtered_cog_mapping = filtered_cog_mapping

    async def callback(self, interaction: Interaction):
        embed = await self.help_command._build_bot_help_embed(self.filtered_cog_mapping)
        view = HelpView(self.help_command, self.filtered_cog_mapping)
        await interaction.response.edit_message(embed=embed, view=view)


class HelpView(discord.ui.View):
    message: typing.Optional[discord.Message]

    def __init__(self, help_command: 'CustomHelpCommand', filtered_cog_mapping: dict, timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.help_command = help_command
        self.filtered_cog_mapping = filtered_cog_mapping
        self.message = None
        if filtered_cog_mapping: # Dodajemy select tylko jeśli są kategorie
            self.add_item(HelpSelect(help_command, filtered_cog_mapping))


    async def on_timeout(self):
        if self.message:
            try:
                self.clear_items()
                if self.message.embeds:
                    original_embed = self.message.embeds[0]
                    original_embed.set_footer(text=f"{original_embed.footer.text if original_embed.footer and original_embed.footer.text else 'Kroniki Elary'} (Menu pomocy wygasło)")
                    await self.message.edit(embed=original_embed, view=self)
                else:
                    await self.message.edit(content="Menu pomocy wygasło.", view=self)
            except discord.NotFound:
                pass
            except Exception as e:
                if self.help_command.context and self.help_command.context.bot and hasattr(self.help_command.context.bot, 'logger'):
                    self.help_command.context.bot.logger.warning(f"Błąd podczas timeoutu HelpView: {e}")
        self.stop()


class CustomHelpCommand(commands.HelpCommand):
    def __init__(self):
        super().__init__(command_attrs={
            'hidden': True,
            'help': 'Wewnętrzny mechanizm formatowania pomocy dla Kronik Elary.'
        })

    async def _create_help_embed(self, title: str, description: str = "", color: discord.Color = config.KOLOR_POMOCY_GLOWNY) -> discord.Embed:
        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.now(UTC))
        bot_user = self.context.bot.user
        author_name = "📜 Zwoje Wiedzy Kronik Elary"
        author_icon_url = bot_user.avatar.url if bot_user and bot_user.avatar else None
        embed.set_author(name=author_name, icon_url=author_icon_url)

        guild_icon_url = self.context.guild.icon.url if self.context.guild and self.context.guild.icon else None
        embed.set_footer(text="Kroniki Elary", icon_url=guild_icon_url)
        return embed

    async def _filter_mapping(self, mapping: dict, ctx: Context) -> dict:
        filtered_mapping = {}
        for cog, commands_list in mapping.items():
            if cog is None: # Pomijamy komendy bez kategorii (np. wbudowana komenda help)
                continue
            visible_commands = await self.filter_commands(commands_list, sort=True)
            if visible_commands:
                filtered_mapping[cog] = visible_commands
        return filtered_mapping

    async def _build_bot_help_embed(self, filtered_mapping: dict) -> discord.Embed:
        invoked_command_name = self.context.invoked_with or (self.context.command.name if self.context.command else "pomoc")
        prefix = self.context.prefix

        embed = await self._create_help_embed(
            title="📜 Zwoje Wiedzy Kronik Elary - Główne Archiwum",
            description=(
                f"Witaj, Kronikarzu! Wybierz zwój (kategorię) z poniższego menu, aby odkryć jego zaklęcia (komendy).\n"
                f"Możesz również użyć `{prefix}{invoked_command_name} [nazwa_zaklęcia]` dla szczegółów o konkretnym zaklęciu."
            )
        )

        if not filtered_mapping:
             embed.add_field(
                name="Brak Dostępnych Kategorii",
                value="Wygląda na to, że nie ma żadnych kategorii komend, do których masz obecnie dostęp lub które są skonfigurowane.",
                inline=False
            )
        else:
            embed.add_field(
                name="Jak korzystać z Archiwum?",
                value="Użyj rozwijanego menu poniżej, aby nawigować po kategoriach zaklęć. "
                      "Każda kategoria to zbiór powiązanych ze sobą mocy, które możesz przywołać.",
                inline=False
            )
        return embed

    async def _build_cog_help_embed(self, cog: commands.Cog) -> discord.Embed:
        emoji = getattr(cog, "COG_EMOJI", "✨")
        cog_name_cap = cog.qualified_name.capitalize()

        embed = await self._create_help_embed(
            title=f"{emoji} Zwój Wiedzy: {cog_name_cap}",
            description=cog.description or "Oto lista zaklęć (komend) dostępnych w tym zwoju:",
            color=config.KOLOR_POMOCY_KATEGORIA
        )

        filtered_commands = await self.filter_commands(cog.get_commands(), sort=True)
        if not filtered_commands:
            embed.description = "Ten zwój jest pusty lub nie masz dostępu do żadnych zaklęć w nim zawartych."
        else:
            for command in filtered_commands:
                embed.add_field(
                    name=f"`{self.get_command_signature(command)}`",
                    value=command.short_doc or "Brak krótkiego opisu tego zaklęcia.",
                    inline=False
                )
        return embed

    async def send_bot_help(self, mapping):
        self.context = self.context or await self.context.bot.get_context(self.message) if hasattr(self, 'message') and self.message else self.context # type: ignore
        if not self.context: return

        filtered_mapping = await self._filter_mapping(mapping, self.context)
        embed = await self._build_bot_help_embed(filtered_mapping)
        view = HelpView(self, filtered_mapping)
        sent_message = await self.get_destination().send(embed=embed, view=view)
        if isinstance(view, HelpView): # Dodatkowe sprawdzenie dla pewności
            view.message = sent_message

    async def send_cog_help(self, cog: commands.Cog):
        self.context = self.context or await self.context.bot.get_context(self.message) if hasattr(self, 'message') and self.message else self.context # type: ignore
        if not self.context: return

        embed = await self._build_cog_help_embed(cog)
        bot_mapping = self.get_bot_mapping()
        filtered_mapping = await self._filter_mapping(bot_mapping, self.context)

        view = HelpView(self, filtered_mapping)
        for item in list(view.children): # Tworzymy kopię listy
            if isinstance(item, HelpSelect):
                view.remove_item(item)
        view.add_item(HelpSelect(self, filtered_mapping))
        view.add_item(HelpGoBackButton(self, filtered_mapping))

        sent_message = await self.get_destination().send(embed=embed, view=view)
        if isinstance(view, HelpView):
            view.message = sent_message

    async def send_group_help(self, group: commands.Group):
        self.context = self.context or await self.context.bot.get_context(self.message) if hasattr(self, 'message') and self.message else self.context # type: ignore
        if not self.context: return

        embed = await self._create_help_embed(
            title=f"📜 Zwój Grupy Zaklęć: `{self.get_command_signature(group)}`",
            description=group.help or "Oto lista pod-zaklęć (subkomend) w tej grupie:",
            color=config.KOLOR_POMOCY_KOMENDA
        )
        filtered_commands = await self.filter_commands(group.commands, sort=True)
        if not filtered_commands:
             embed.description = "Ta grupa zaklęć nie zawiera dostępnych pod-zaklęć lub nie masz do nich dostępu."
        else:
            for command in filtered_commands:
                embed.add_field(name=f"`{self.get_command_signature(command)}`", value=command.short_doc or "Brak krótkiego opisu.", inline=False)

        bot_mapping = self.get_bot_mapping()
        filtered_mapping = await self._filter_mapping(bot_mapping, self.context)
        view = HelpView(self, filtered_mapping)
        for item in list(view.children): # Tworzymy kopię listy
            if isinstance(item, HelpSelect):
                view.remove_item(item)
        view.add_item(HelpSelect(self, filtered_mapping))
        view.add_item(HelpGoBackButton(self, filtered_mapping))

        sent_message = await self.get_destination().send(embed=embed, view=view)
        if isinstance(view, HelpView):
            view.message = sent_message

    async def send_command_help(self, command: commands.Command):
        self.context = self.context or await self.context.bot.get_context(self.message) if hasattr(self, 'message') and self.message else self.context # type: ignore
        if not self.context: return

        can_run = True # Zakładamy, że można uruchomić, jeśli nie ma kontekstu do sprawdzenia
        if self.context:
            try:
                can_run = await command.can_run(self.context)
            except commands.CommandError: # np. MissingPermissions
                can_run = False
            except Exception as e:
                self.context.bot.logger.warning(f"Nieoczekiwany błąd podczas sprawdzania command.can_run dla '{command.qualified_name}': {e}")
                can_run = False # Bezpieczniej założyć, że nie można

        if not can_run:
            embed = await self._create_help_embed(
                title="⛔ Brak Dostępu do Zaklęcia",
                description=f"Nie posiadasz odpowiednich magicznych pieczęci, aby poznać szczegóły tego zaklęcia (`{command.qualified_name}`).",
                color=config.KOLOR_BOT_BLAD
            )
            await self.get_destination().send(embed=embed)
            return

        embed = await self._create_help_embed(
            title=f"📖 Szczegóły Zaklęcia: `{self.get_command_signature(command)}`",
            description=command.help or "Brak szczegółowego opisu dla tego zaklęcia.",
            color=config.KOLOR_POMOCY_KOMENDA
        )
        if command.aliases:
            embed.add_field(name="Alternatywne Inwokacje (Aliasy)", value=f"`{', '.join(command.aliases)}`", inline=False)

        bot_mapping = self.get_bot_mapping()
        filtered_mapping = await self._filter_mapping(bot_mapping, self.context)
        view = HelpView(self, filtered_mapping)
        for item in list(view.children): # Tworzymy kopię listy
            if isinstance(item, HelpSelect):
                view.remove_item(item)
        view.add_item(HelpSelect(self, filtered_mapping))
        if command.cog: # Dodajemy przycisk powrotu tylko jeśli komenda należy do jakiejś kategorii
            view.add_item(HelpGoBackButton(self, filtered_mapping))

        sent_message = await self.get_destination().send(embed=embed, view=view)
        if isinstance(view, HelpView):
            view.message = sent_message

    async def on_help_command_error(self, ctx: Context, error: commands.CommandError):
        current_context = ctx or self.context or (await self.context.bot.get_context(self.message) if hasattr(self, 'message') and self.message else None) # type: ignore
        if not current_context:
            if hasattr(self.bot, 'logger'): # Sprawdzenie czy bot ma logger
                self.bot.logger.error(f"Błąd w komendzie pomocy (brak kontekstu): {error}", exc_info=True)
            return

        if isinstance(error, commands.CommandInvokeError) and isinstance(error.original, discord.Forbidden):
            if hasattr(current_context.bot, 'logger'):
                 current_context.bot.logger.warning(f"Brak uprawnień do wysłania wiadomości pomocy na kanale {current_context.channel}.")
            try:
                await current_context.author.send("Nie mam uprawnień, aby wysłać wiadomość pomocy na tym kanale. Spróbuj w wiadomości prywatnej lub na innym kanale.")
            except discord.Forbidden:
                pass
        else:
            embed = await self._create_help_embed(
                title="🌪️ Coś Poszło Nie Tak z Archiwami Pomocy",
                description=f"Przepraszam, ale napotkałam problem podczas próby wyświetlenia zwojów wiedzy.\n`{str(error)}`",
                color=config.KOLOR_BOT_BLAD
            )
            await current_context.send(embed=embed, ephemeral=True)
            if hasattr(current_context.bot, 'logger'):
                current_context.bot.logger.error(f"Błąd w komendzie pomocy: {error}", exc_info=True)


class Pomoc(commands.Cog, name="pomoc"):
    """❓ Kapsuła zawierająca niestandardową, interaktywną komendę pomocy dla Kronik Elary."""
    COG_EMOJI = "❓"

    def __init__(self, bot: 'BotDiscord'):
        self.bot = bot
        self._original_help_command = bot.help_command
        new_help_command = CustomHelpCommand()
        new_help_command.cog = self
        bot.help_command = new_help_command


    @commands.hybrid_command(
        name="pomoc",
        aliases=['khelp', 'zwoje', 'manualkronik', 'h'],
        description="Wyświetla Zwoje Wiedzy Kronik Elary - interaktywną pomoc."
    )
    @app_commands.describe(komenda_lub_kategoria="Nazwa komendy lub kategorii, dla której chcesz zobaczyć pomoc.")
    async def glowna_komenda_pomocy_slash(self, context: Context, *, komenda_lub_kategoria: typing.Optional[str] = None):
        """
        Wyświetla interaktywną pomoc dotyczącą komend bota.
        Możesz podać nazwę komendy lub kategorii, aby uzyskać szczegółowe informacje.
        Jeśli nic nie podasz, wyświetli główną stronę pomocy z listą kategorii.
        """
        if self.bot.help_command:
            self.bot.help_command.context = context # Ustawienie kontekstu dla CustomHelpCommand

            target_command_or_cog_name = komenda_lub_kategoria

            if target_command_or_cog_name:
                target_obj_command = self.bot.get_command(target_command_or_cog_name)
                # Sprawdzamy zarówno z dużej jak i małej litery dla nazw cogów
                target_obj_cog = self.bot.get_cog(target_command_or_cog_name.capitalize()) or self.bot.get_cog(target_command_or_cog_name.lower())


                if target_obj_command:
                    await self.bot.help_command.send_command_help(target_obj_command)
                elif target_obj_cog:
                    await self.bot.help_command.send_cog_help(target_obj_cog)
                else:
                    await self.bot.help_command.on_help_command_error(context, commands.CommandNotFound(f"Nie znaleziono komendy ani kategorii: `{target_command_or_cog_name}`"))
            else:
                await self.bot.help_command.send_bot_help(self.bot.help_command.get_bot_mapping())
        else:
            await context.send("Mechanizm pomocy jest obecnie niedostępny.", ephemeral=True)


    async def cog_unload(self):
        self.bot.help_command = self._original_help_command

async def setup(bot: 'BotDiscord'):
    await bot.add_cog(Pomoc(bot))
