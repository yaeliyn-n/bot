import discord
from discord.ext import commands, tasks
from discord import app_commands, Interaction, ButtonStyle
from discord.ext.commands import Context
import asyncio
import typing
import yt_dlp
import re
from datetime import datetime, UTC

import config

if typing.TYPE_CHECKING:
    from bot import BotDiscord

YTDL_FORMAT_OPTIONS = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

class Song:
    def __init__(self, source_url: str, title: str, webpage_url: str, duration: int, requested_by: discord.Member):
        self.source_url = source_url
        self.title = title
        self.webpage_url = webpage_url
        self.duration = duration
        self.requested_by = requested_by

    def __str__(self):
        return f"**[{self.title}]({self.webpage_url})** (Poprosił/a: {self.requested_by.mention})"
    
    def to_embed_field(self, bot: 'BotDiscord') -> tuple[str, str]:
        duration_str = bot.formatuj_czas(self.duration, precyzyjnie=True)
        return (f"{self.title}", f"Czas: `{duration_str}` | Poprosił/a: {self.requested_by.mention}\n[Link]({self.webpage_url})")


class MusicControlView(discord.ui.View):
    def __init__(self, music_cog: 'Muzyka', guild_state: 'GuildMusicState', timeout: float = 3600.0):
        super().__init__(timeout=timeout)
        self.music_cog = music_cog
        self.guild_state = guild_state
        self.update_buttons() 

    async def interaction_check(self, interaction: Interaction) -> bool:
        if not interaction.guild or not self.guild_state.voice_client or not self.guild_state.voice_client.is_connected():
            if not interaction.response.is_done():
                await interaction.response.send_message("Bot nie jest połączony z kanałem głosowym.", ephemeral=True)
            return False
        if not isinstance(interaction.user, discord.Member) or interaction.user not in self.guild_state.voice_client.channel.members:
            if not interaction.response.is_done():
                await interaction.response.send_message("Musisz być na tym samym kanale głosowym co Elara, aby sterować muzyką.", ephemeral=True)
            return False
        return True

    def update_buttons(self):
        self.music_cog.bot.logger.info(f"[Guild {self.guild_state.guild_id}] MusicControlView.update_buttons: Rozpoczęto aktualizację przycisków.")
        for item in self.children[:]:
            if isinstance(item, discord.ui.Button):
                self.remove_item(item)

        if self.guild_state.voice_client and self.guild_state.voice_client.is_paused():
            pause_resume_label = "Wznów ▶️"
            pause_resume_style = ButtonStyle.green
        else:
            pause_resume_label = "Pauza ⏸️"
            pause_resume_style = ButtonStyle.secondary
        
        self.add_item(discord.ui.Button(label=pause_resume_label, style=pause_resume_style, custom_id="music_pause_resume", row=0))
        self.add_item(discord.ui.Button(label="Pomiń ⏭️", style=ButtonStyle.blurple, custom_id="music_skip", row=0, disabled=not self.guild_state.current_song))
        self.add_item(discord.ui.Button(label="Stop ⏹️", style=ButtonStyle.red, custom_id="music_stop", row=0, disabled=not self.guild_state.is_playing and not (self.guild_state.voice_client and self.guild_state.voice_client.is_paused())))

        loop_song_label = "Pętla Utworu 🔂"
        loop_song_style = ButtonStyle.success if self.guild_state.loop_current_song else ButtonStyle.grey
        self.add_item(discord.ui.Button(label=loop_song_label, style=loop_song_style, custom_id="music_loop_song", row=1))

        loop_queue_label = "Pętla Kolejki 🔁"
        loop_queue_style = ButtonStyle.success if self.guild_state.loop_queue else ButtonStyle.grey
        self.add_item(discord.ui.Button(label=loop_queue_label, style=loop_queue_style, custom_id="music_loop_queue", row=1))
        
        self.add_item(discord.ui.Button(label="Opuść Kanał 👋", style=ButtonStyle.danger, custom_id="music_leave", row=1))
        self.music_cog.bot.logger.info(f"[Guild {self.guild_state.guild_id}] MusicControlView.update_buttons: Zakończono. Liczba dzieci widoku: {len(self.children)}")


    async def on_timeout(self):
        self.guild_state.now_playing_message_view = None
        if self.guild_state.now_playing_message:
            try:
                await self.guild_state.now_playing_message.edit(view=None)
            except discord.HTTPException:
                pass
        self.stop()

    async def handle_button_press(self, interaction: Interaction, button_custom_id: str):
        if button_custom_id == "music_pause_resume":
            if self.guild_state.voice_client and self.guild_state.voice_client.is_playing():
                await self.music_cog._pause_command_logic(interaction, send_feedback=False)
            elif self.guild_state.voice_client and self.guild_state.voice_client.is_paused():
                await self.music_cog._resume_command_logic(interaction, send_feedback=False)
        elif button_custom_id == "music_skip":
            await self.music_cog._skip_command_logic(interaction, send_feedback=False)
        elif button_custom_id == "music_stop":
            await self.music_cog._stop_command_logic(interaction, send_feedback=False)
        elif button_custom_id == "music_loop_song":
            await self.music_cog._loop_command_logic(interaction, "song", send_feedback=False)
        elif button_custom_id == "music_loop_queue":
            await self.music_cog._loop_command_logic(interaction, "queue", send_feedback=False)
        elif button_custom_id == "music_leave":
            await self.music_cog._leave_command_logic(interaction, send_feedback=False)

        self.update_buttons()
        if self.guild_state.now_playing_message:
            embed_np = await self.music_cog._build_now_playing_embed(self.guild_state)
            try:
                await self.guild_state.now_playing_message.edit(embed=embed_np, view=self)
            except discord.HTTPException:
                pass
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except discord.NotFound:
            pass


class GuildMusicState:
    def __init__(self, bot_instance: 'BotDiscord', guild_id: int):
        self.bot = bot_instance
        self.guild_id = guild_id
        self.voice_client: typing.Optional[discord.VoiceClient] = None
        self.song_queue: asyncio.Queue[Song] = asyncio.Queue()
        self.current_song: typing.Optional[Song] = None
        self.is_playing: bool = False
        self.loop_current_song: bool = False
        self.loop_queue: bool = False
        self.volume: float = 0.5
        self.last_interaction_channel: typing.Optional[discord.TextChannel] = None
        self.now_playing_message: typing.Optional[discord.Message] = None
        self.now_playing_message_view: typing.Optional[MusicControlView] = None
        self.playback_task: typing.Optional[asyncio.Task] = None

    async def _cleanup_playback(self, from_leave: bool = False):
        self.is_playing = False
        
        if self.now_playing_message_view:
            self.now_playing_message_view.stop()
            if self.now_playing_message and not from_leave:
                try:
                    await self.now_playing_message.edit(view=None)
                except discord.HTTPException: pass
            self.now_playing_message_view = None
        
        if self.now_playing_message and from_leave:
             try:
                await self.now_playing_message.delete()
             except discord.HTTPException: pass
             self.now_playing_message = None

        if self.playback_task and not self.playback_task.done():
            self.playback_task.cancel()
        self.playback_task = None

    async def _play_next_song(self, error: typing.Optional[Exception] = None):
        self.bot.logger.info(f"[Guild {self.guild_id}] _play_next_song: Rozpoczęto przetwarzanie następnego utworu.")
        original_current_song_for_loop = self.current_song

        if error:
            self.bot.logger.error(f"Błąd podczas odtwarzania na serwerze {self.guild_id}: {error}", exc_info=error)
            if self.last_interaction_channel:
                await self.last_interaction_channel.send(f"Wystąpił błąd podczas odtwarzania: `{error}`")
        
        self.is_playing = False 
        next_song_to_play: typing.Optional[Song] = None

        if self.loop_current_song and original_current_song_for_loop:
            next_song_to_play = original_current_song_for_loop
        elif not self.song_queue.empty():
            next_song_to_play = self.song_queue.get_nowait()
            if self.loop_queue and original_current_song_for_loop:
                await self.song_queue.put(original_current_song_for_loop)
        elif self.loop_queue and original_current_song_for_loop:
            next_song_to_play = original_current_song_for_loop
        
        self.current_song = next_song_to_play

        if not self.current_song:
            self.bot.logger.info(f"[Guild {self.guild_id}] _play_next_song: Brak bieżącego utworu, kolejka pusta.")
            if self.last_interaction_channel:
                music_cog = self.bot.get_cog("muzyka")
                if music_cog:
                    temp_ctx_or_channel: typing.Union[Context, Interaction, discord.TextChannel] = self.last_interaction_channel
                    final_embed = await music_cog._create_music_embed(temp_ctx_or_channel, title="📜 Kolejka Zakończona", description="Kolejka jest pusta. Elara kończy sesję muzyczną. 🎶")
                    if self.now_playing_message:
                        try: await self.now_playing_message.edit(embed=final_embed, view=None)
                        except: pass
                        self.now_playing_message = None
                    else:
                        await self.last_interaction_channel.send(embed=final_embed)
            await self._cleanup_playback()
            return

        if not self.voice_client or not self.voice_client.is_connected():
            self.bot.logger.warning(f"[Guild {self.guild_id}] _play_next_song: Voice client nie połączony.")
            await self._cleanup_playback()
            return

        try:
            audio_source = discord.FFmpegPCMAudio(self.current_song.source_url, **FFMPEG_OPTIONS)
            transformed_source = discord.PCMVolumeTransformer(audio_source, volume=self.volume)
            
            def after_playing(error_after):
                if error_after:
                    self.bot.logger.error(f"Błąd w 'after' callback dla serwera {self.guild_id}: {error_after}", exc_info=error_after)
                self.is_playing = False 

            self.voice_client.play(transformed_source, after=after_playing)
            self.is_playing = True
            self.bot.logger.info(f"[Guild {self.guild_id}] _play_next_song: Rozpoczęto odtwarzanie: {self.current_song.title}")

            music_cog_ref: typing.Optional['Muzyka'] = self.bot.get_cog("muzyka")
            if self.last_interaction_channel and music_cog_ref:
                self.bot.logger.info(f"[Guild {self.guild_id}] _play_next_song: Tworzenie embedu NP i widoku kontrolek.")
                embed_np = await music_cog_ref._build_now_playing_embed(self)

                if self.now_playing_message_view:
                    self.bot.logger.info(f"[Guild {self.guild_id}] _play_next_song: Zatrzymywanie starego widoku kontrolek.")
                    self.now_playing_message_view.stop()
                
                control_view = MusicControlView(music_cog_ref, self)
                self.now_playing_message_view = control_view
                self.bot.logger.info(f"[Guild {self.guild_id}] _play_next_song: Utworzono nowy widok kontrolek. Liczba przycisków: {len(control_view.children)}")

                if self.now_playing_message:
                    self.bot.logger.info(f"[Guild {self.guild_id}] _play_next_song: Edytowanie istniejącej wiadomości NP z widokiem.")
                    try: 
                        await self.now_playing_message.edit(embed=embed_np, view=control_view)
                        self.bot.logger.info(f"[Guild {self.guild_id}] _play_next_song: Edytowano wiadomość NP z widokiem.")
                    except discord.HTTPException as e_edit: 
                        self.bot.logger.warning(f"[Guild {self.guild_id}] _play_next_song: Błąd edycji wiadomości NP ({e_edit}), wysyłanie nowej.")
                        self.now_playing_message = await self.last_interaction_channel.send(embed=embed_np, view=control_view)
                        self.bot.logger.info(f"[Guild {self.guild_id}] _play_next_song: Wysłano nową wiadomość NP z widokiem.")
                else:
                    self.bot.logger.info(f"[Guild {self.guild_id}] _play_next_song: Wysyłanie nowej wiadomości NP z widokiem.")
                    self.now_playing_message = await self.last_interaction_channel.send(embed=embed_np, view=control_view)
                    self.bot.logger.info(f"[Guild {self.guild_id}] _play_next_song: Wysłano nową wiadomość NP z widokiem.")
            else:
                if not self.last_interaction_channel:
                    self.bot.logger.warning(f"[Guild {self.guild_id}] _play_next_song: Brak last_interaction_channel.")
                if not music_cog_ref:
                    self.bot.logger.warning(f"[Guild {self.guild_id}] _play_next_song: Nie udało się pobrać music_cog_ref (nazwa koga: 'muzyka').")
        except Exception as e:
            self.bot.logger.error(f"[Guild {self.guild_id}] _play_next_song: Ogólny błąd w try: {e}", exc_info=True)
            self.is_playing = False


    def start_playback_loop(self):
        if self.playback_task and not self.playback_task.done():
             return
        self.bot.logger.debug(f"Starting playback task for guild {self.guild_id}.")
        self.playback_task = self.bot.loop.create_task(self._playback_loop_internal())

    async def _playback_loop_internal(self):
        try:
            while True:
                if self.voice_client and self.voice_client.is_connected():
                    if not self.is_playing and (not self.song_queue.empty() or (self.loop_current_song and self.current_song) or (self.loop_queue and self.current_song)):
                        await self._play_next_song()
                    elif not self.is_playing and self.song_queue.empty() and not self.current_song and not self.loop_current_song and not self.loop_queue:
                        pass 
                else: 
                    self.bot.logger.debug(f"Playback loop for guild {self.guild_id}: Voice client not connected. Cleaning up.")
                    await self._cleanup_playback(from_leave=True)
                    return 

                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            self.bot.logger.info(f"Pętla odtwarzania dla serwera {self.guild_id} została świadomie anulowana.")
        except Exception as e:
            self.bot.logger.error(f"Nieoczekiwany błąd w pętli odtwarzania dla serwera {self.guild_id}: {e}", exc_info=True)
        finally:
            self.bot.logger.debug(f"Playback loop for guild {self.guild_id} ended. Cleaning up.")
            await self._cleanup_playback(from_leave=True)


class Muzyka(commands.Cog, name="muzyka"):
    COG_EMOJI = "🎵"

    def __init__(self, bot: 'BotDiscord'):
        self.bot = bot
        self.guild_states: typing.Dict[int, GuildMusicState] = {}
        self.yt_dlp = yt_dlp.YoutubeDL(YTDL_FORMAT_OPTIONS)

    # --- DODANE METODY POMOCNICZE ---
    async def _get_guild_from_context_or_interaction(self, ctx_or_int: typing.Union[Context, Interaction]) -> typing.Optional[discord.Guild]:
        """Pomocnicza metoda do pobierania obiektu guild."""
        if isinstance(ctx_or_int, Interaction):
            return ctx_or_int.guild
        return ctx_or_int.guild

    async def _get_user_from_context_or_interaction(self, ctx_or_int: typing.Union[Context, Interaction]) -> typing.Union[discord.User, discord.Member, None]:
        """Pomocnicza metoda do pobierania obiektu user/author."""
        if isinstance(ctx_or_int, Interaction):
            return ctx_or_int.user
        return ctx_or_int.author
    # --- KONIEC DODANYCH METOD POMOCNICZYCH ---

    def _get_guild_state(self, guild_id: int) -> GuildMusicState:
        if guild_id not in self.guild_states:
            self.guild_states[guild_id] = GuildMusicState(self.bot, guild_id)
        return self.guild_states[guild_id]

    async def _create_music_embed(self, ctx_or_channel: typing.Union[Context, Interaction, discord.TextChannel], title: str, description: str = "", color: discord.Color = config.KOLOR_BOT_INFO) -> discord.Embed:
        guild = None
        if isinstance(ctx_or_channel, (Context, Interaction)):
            guild = ctx_or_channel.guild
        elif isinstance(ctx_or_channel, discord.TextChannel):
            guild = ctx_or_channel.guild

        embed = discord.Embed(title=f"{self.COG_EMOJI} {title}", description=description, color=color, timestamp=datetime.now(UTC))
        if self.bot.user and self.bot.user.avatar:
             embed.set_author(name=f"{self.bot.user.display_name} - Muzyka", icon_url=self.bot.user.avatar.url)
        else:
            embed.set_author(name="Muzyka w Kronikach")

        if guild and guild.icon:
            embed.set_footer(text=f"Serwer: {guild.name} | Kroniki Elary", icon_url=guild.icon.url)
        else:
            embed.set_footer(text="Kroniki Elary")
        return embed

    async def _build_now_playing_embed(self, state: GuildMusicState) -> discord.Embed:
        ctx_or_channel_for_embed: typing.Union[Context, Interaction, discord.TextChannel, None] = state.last_interaction_channel
        
        if not ctx_or_channel_for_embed:
            if state.voice_client and state.voice_client.channel:
                 guild = self.bot.get_guild(state.guild_id)
                 if guild and guild.text_channels:
                     ctx_or_channel_for_embed = guild.text_channels[0]
                 else:
                     return discord.Embed(title=f"{self.COG_EMOJI} Informacja Muzyczna", description="Stan odtwarzacza.", color=config.KOLOR_BOT_INFO)
            else:
                 return discord.Embed(title=f"{self.COG_EMOJI} Informacja Muzyczna", description="Stan odtwarzacza.", color=config.KOLOR_BOT_INFO)


        if not state.current_song:
            return await self._create_music_embed(ctx_or_channel_for_embed, "Nic nie jest odtwarzane", "Kolejka jest pusta.")

        desc = f"{str(state.current_song)}\n"
        desc += f"Głośność: `{int(state.volume * 100)}%`"
        if state.loop_current_song: desc += " | Pętla utworu: 🔂"
        if state.loop_queue: desc += " | Pętla kolejki: 🔁"
        
        embed = await self._create_music_embed(
            ctx_or_channel_for_embed,
            title="🎶 Teraz Odtwarzane",
            description=desc.strip(),
            color=config.KOLOR_BOT_INFO
        )
        return embed


    @commands.Cog.listener()
    async def on_interaction(self, interaction: Interaction):
        if interaction.type != discord.InteractionType.component or not interaction.data:
            return
        
        custom_id = interaction.data.get("custom_id")
        if not custom_id or not custom_id.startswith("music_"):
            return

        if not interaction.guild_id:
            if not interaction.response.is_done():
                await interaction.response.send_message("Ta interakcja wymaga kontekstu serwera.", ephemeral=True)
            return
            
        state = self._get_guild_state(interaction.guild_id)
        if state.now_playing_message_view and isinstance(state.now_playing_message_view, MusicControlView):
            await state.now_playing_message_view.handle_button_press(interaction, custom_id)
        else:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("Panel kontrolny muzyki jest nieaktywny lub wystąpił błąd.", ephemeral=True)
            except discord.NotFound:
                 pass


    async def _ensure_voice_channel(self, ctx_or_int: typing.Union[Context, Interaction]) -> typing.Optional[discord.VoiceClient]:
        guild = await self._get_guild_from_context_or_interaction(ctx_or_int) # Użycie nowej metody
        author = await self._get_user_from_context_or_interaction(ctx_or_int) # Użycie nowej metody
        
        # Pobieranie kanału w zależności od typu ctx_or_int
        if isinstance(ctx_or_int, Interaction):
            channel = ctx_or_int.channel # Dla Interaction, channel jest atrybutem
        else: # Context
            channel = ctx_or_int.channel

        if not guild:
            await self._send_response(ctx_or_int, content="Ta komenda może być używana tylko na serwerze.", ephemeral=True)
            return None
        if not isinstance(author, discord.Member) or not author.voice or not author.voice.channel:
            await self._send_response(ctx_or_int, content="Musisz być na kanale głosowym, aby użyć tej komendy!", ephemeral=True)
            return None

        state = self._get_guild_state(guild.id)
        target_channel = author.voice.channel
        
        if isinstance(channel, discord.TextChannel):
            state.last_interaction_channel = channel
        elif isinstance(ctx_or_int, Interaction) and ctx_or_int.channel and isinstance(ctx_or_int.channel, discord.TextChannel):
             state.last_interaction_channel = ctx_or_int.channel

        if state.voice_client is None or not state.voice_client.is_connected():
            try:
                state.voice_client = await target_channel.connect()
                self.bot.logger.info(f"Połączono z kanałem głosowym: {target_channel.name} na serwerze {guild.name}")
            except asyncio.TimeoutError:
                await self._send_response(ctx_or_int, content="Nie udało się połączyć z kanałem głosowym (timeout). Spróbuj ponownie.", ephemeral=True)
                return None
            except discord.ClientException as e:
                await self._send_response(ctx_or_int, content=f"Problem z połączeniem: {e}", ephemeral=True)
                return None
        elif state.voice_client.channel != target_channel:
            try:
                await state.voice_client.move_to(target_channel)
                self.bot.logger.info(f"Przeniesiono na kanał głosowy: {target_channel.name} na serwerze {guild.name}")
            except asyncio.TimeoutError:
                await self._send_response(ctx_or_int, content="Nie udało się przenieść na Twój kanał głosowy (timeout). Spróbuj ponownie.", ephemeral=True)
                return None
            except discord.ClientException as e:
                await self._send_response(ctx_or_int, content=f"Problem z przeniesieniem: {e}", ephemeral=True)
                return None
        return state.voice_client

    async def _send_response(self, ctx_or_int: typing.Union[Context, Interaction], **kwargs):
        if isinstance(ctx_or_int, Interaction):
            if not ctx_or_int.response.is_done():
                await ctx_or_int.response.send_message(**kwargs)
            else:
                await ctx_or_int.followup.send(**kwargs)
        else: 
            await ctx_or_int.send(**kwargs)


    @app_commands.command(name="play", description="Odtwarza utwór z YouTube (URL lub wyszukiwanie) lub dodaje do kolejki.")
    @app_commands.describe(zapytanie="Link do utworu YouTube lub fraza do wyszukania.")
    async def play_slash(self, interaction: Interaction, zapytanie: str):
        await interaction.response.defer(ephemeral=False, thinking=True)
        await self._play_command_logic(interaction, zapytanie)

    @commands.command(name="play", aliases=['p', 'graj'], help="Odtwarza utwór z YouTube (URL lub wyszukiwanie) lub dodaje do kolejki.\nPrzykład: `!play Never Gonna Give You Up` lub `!play <URL_YOUTUBE>`")
    async def play_prefix(self, context: Context, *, zapytanie: str):
        processing_msg = await context.send(f"🔍 Przetwarzam Twoje zapytanie o `{zapytanie[:50]}{'...' if len(zapytanie) > 50 else ''}`...")
        await self._play_command_logic(context, zapytanie, processing_msg)


    async def _play_command_logic(self, ctx_or_int: typing.Union[Context, Interaction], zapytanie: str, processing_msg: typing.Optional[discord.Message] = None):
        guild = await self._get_guild_from_context_or_interaction(ctx_or_int)
        author = await self._get_user_from_context_or_interaction(ctx_or_int)

        if not guild or not author :
            if processing_msg: 
                try: await processing_msg.delete()
                except: pass
            await self._send_response(ctx_or_int, content="Ta komenda wymaga kontekstu serwera i użytkownika.", ephemeral=True)
            return

        voice_client = await self._ensure_voice_channel(ctx_or_int)
        if not voice_client:
            if processing_msg: 
                try: await processing_msg.delete()
                except: pass
            return

        state = self._get_guild_state(guild.id)

        loop = self.bot.loop or asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(None, lambda: self.yt_dlp.extract_info(zapytanie, download=False))
        except yt_dlp.utils.DownloadError as e:
            self.bot.logger.warning(f"yt_dlp DownloadError dla zapytania '{zapytanie}': {e}")
            if processing_msg: 
                try: await processing_msg.delete()
                except: pass
            msg_content = f"Nie udało się znaleźć lub przetworzyć utworu: `{str(e).split(': ERROR: ')[-1]}`"
            await self._send_response(ctx_or_int, content=msg_content, ephemeral=True)
            return
        except Exception as e:
            self.bot.logger.error(f"Nieoczekiwany błąd yt_dlp dla zapytania '{zapytanie}': {e}", exc_info=True)
            if processing_msg: 
                try: await processing_msg.delete()
                except: pass
            msg_content = f"Wystąpił nieoczekiwany błąd podczas wyszukiwania utworu: `{e}`"
            await self._send_response(ctx_or_int, content=msg_content, ephemeral=True)
            return

        if processing_msg:
            try: await processing_msg.delete()
            except: pass


        if 'entries' in data:
            song_data = data['entries'][0]
        else:
            song_data = data

        if not song_data.get('url'):
            msg_content = "Nie udało się uzyskać bezpośredniego linku do audio dla tego utworu."
            await self._send_response(ctx_or_int, content=msg_content, ephemeral=True)
            return

        song = Song(
            source_url=song_data['url'],
            title=song_data.get('title', 'Nieznany utwór'),
            webpage_url=song_data.get('webpage_url', zapytanie),
            duration=int(song_data.get('duration', 0)),
            requested_by=typing.cast(discord.Member, author)
        )

        await state.song_queue.put(song)
        embed = await self._create_music_embed(ctx_or_int, title="➕ Dodano do Kolejki", description=str(song))
        
        await self._send_response(ctx_or_int, embed=embed)


        if not state.is_playing and not (state.voice_client and state.voice_client.is_playing()):
            state.start_playback_loop()


    async def _stop_command_logic(self, ctx_or_int: typing.Union[Context, Interaction], send_feedback: bool = True):
        guild = await self._get_guild_from_context_or_interaction(ctx_or_int)
        if not guild:
            if send_feedback: await self._send_response(ctx_or_int, content="Ta komenda działa tylko na serwerze.", ephemeral=True)
            return
        state = self._get_guild_state(guild.id)
        if not state.voice_client or not state.voice_client.is_connected():
            if send_feedback: await self._send_response(ctx_or_int, content="Elara nie jest aktualnie na żadnym kanale głosowym.", ephemeral=True)
            return

        state.song_queue = asyncio.Queue()
        state.loop_current_song = False
        state.loop_queue = False
        
        await state._cleanup_playback() 
        if state.voice_client and state.voice_client.is_playing():
             state.voice_client.stop()

        if send_feedback:
            embed = await self._create_music_embed(ctx_or_int, title="⏹️ Odtwarzanie Zatrzymane", description="Kolejka została wyczyszczona.")
            await self._send_response(ctx_or_int, embed=embed)

    async def _skip_command_logic(self, ctx_or_int: typing.Union[Context, Interaction], send_feedback: bool = True):
        guild = await self._get_guild_from_context_or_interaction(ctx_or_int)
        if not guild:
            if send_feedback: await self._send_response(ctx_or_int, content="Ta komenda działa tylko na serwerze.", ephemeral=True)
            return
        state = self._get_guild_state(guild.id)
        if not state.voice_client or not (state.voice_client.is_playing() or state.voice_client.is_paused()):
            if send_feedback: await self._send_response(ctx_or_int, content="Elara niczego aktualnie nie odtwarza.", ephemeral=True)
            return
        if not state.current_song:
             if send_feedback: await self._send_response(ctx_or_int, content="Nie ma czego pomijać.", ephemeral=True)
             return

        skipped_song_title = state.current_song.title
        state.loop_current_song = False
        if state.voice_client: state.voice_client.stop()

        if send_feedback:
            embed = await self._create_music_embed(ctx_or_int, title="⏭️ Pominięto Utwór", description=f"Pominięto: **{skipped_song_title}**")
            await self._send_response(ctx_or_int, embed=embed)

    async def _queue_command_logic(self, ctx_or_int: typing.Union[Context, Interaction]):
        guild = await self._get_guild_from_context_or_interaction(ctx_or_int)
        if not guild:
            await self._send_response(ctx_or_int, content="Ta komenda działa tylko na serwerze.", ephemeral=True)
            return
        state = self._get_guild_state(guild.id)

        embed = await self._create_music_embed(ctx_or_int, title="📜 Kolejka Odtwarzania")
        desc_parts = []

        if state.current_song:
            title, field_value = state.current_song.to_embed_field(self.bot)
            desc_parts.append(f"**Teraz odtwarzane:**\n🎶 {field_value}\n")
            if state.loop_current_song: desc_parts[-1] += "🔂 *Ten utwór jest zapętlony.*\n"


        if not state.song_queue.empty():
            desc_parts.append("**Następne w kolejce:**")
            temp_queue_list = list(state.song_queue._queue) # type: ignore
            for i, song in enumerate(temp_queue_list[:10]):
                _, field_value = song.to_embed_field(self.bot)
                desc_parts.append(f"{i+1}. {field_value}")
            if len(temp_queue_list) > 10:
                desc_parts.append(f"...i {len(temp_queue_list) - 10} więcej.")
            if state.loop_queue: desc_parts.append("\n🔁 *Kolejka jest zapętlona.*")
        elif not state.current_song : 
             desc_parts.append("Kolejka jest pusta.")


        if not desc_parts: 
             embed.description = "Kolejka jest pusta, a Elara niczego nie odtwarza."
        else:
            embed.description = "\n".join(desc_parts).strip()
            
        await self._send_response(ctx_or_int, embed=embed)

    async def _pause_command_logic(self, ctx_or_int: typing.Union[Context, Interaction], send_feedback: bool = True):
        guild = await self._get_guild_from_context_or_interaction(ctx_or_int)
        if not guild:
            if send_feedback: await self._send_response(ctx_or_int, content="Ta komenda działa tylko na serwerze.", ephemeral=True)
            return
        state = self._get_guild_state(guild.id)
        if state.voice_client and state.voice_client.is_playing():
            state.voice_client.pause()
            state.is_playing = False
            if send_feedback:
                embed = await self._create_music_embed(ctx_or_int, title="⏸️ Odtwarzanie Spauzowane")
                await self._send_response(ctx_or_int, embed=embed)
        elif send_feedback:
            await self._send_response(ctx_or_int, content="Nic nie jest aktualnie odtwarzane lub już jest spauzowane.", ephemeral=True)

    async def _resume_command_logic(self, ctx_or_int: typing.Union[Context, Interaction], send_feedback: bool = True):
        guild = await self._get_guild_from_context_or_interaction(ctx_or_int)
        if not guild:
            if send_feedback: await self._send_response(ctx_or_int, content="Ta komenda działa tylko na serwerze.", ephemeral=True)
            return
        state = self._get_guild_state(guild.id)
        if state.voice_client and state.voice_client.is_paused():
            state.voice_client.resume()
            state.is_playing = True
            if send_feedback:
                embed = await self._create_music_embed(ctx_or_int, title="▶️ Odtwarzanie Wznowione")
                await self._send_response(ctx_or_int, embed=embed)
        elif send_feedback:
            await self._send_response(ctx_or_int, content="Odtwarzanie nie jest spauzowane.", ephemeral=True)

    async def _leave_command_logic(self, ctx_or_int: typing.Union[Context, Interaction], send_feedback: bool = True):
        guild = await self._get_guild_from_context_or_interaction(ctx_or_int)
        if not guild:
            if send_feedback: await self._send_response(ctx_or_int, content="Ta komenda działa tylko na serwerze.", ephemeral=True)
            return
        state = self._get_guild_state(guild.id)
        if state.voice_client and state.voice_client.is_connected():
            await state._cleanup_playback(from_leave=True)
            await state.voice_client.disconnect()
            state.voice_client = None
            if send_feedback:
                embed = await self._create_music_embed(ctx_or_int, title="👋 Elara Opuszcza Kanał", description="Do usłyszenia następnym razem!")
                await self._send_response(ctx_or_int, embed=embed)

        elif send_feedback:
            await self._send_response(ctx_or_int, content="Elara nie jest na żadnym kanale głosowym.", ephemeral=True)

    async def _volume_command_logic(self, ctx_or_int: typing.Union[Context, Interaction], poziom: int, send_feedback: bool = True):
        guild = await self._get_guild_from_context_or_interaction(ctx_or_int)
        if not guild:
            if send_feedback: await self._send_response(ctx_or_int, content="Ta komenda działa tylko na serwerze.", ephemeral=True)
            return
        state = self._get_guild_state(guild.id)
        if not state.voice_client or not state.voice_client.is_connected():
            if send_feedback: await self._send_response(ctx_or_int, content="Elara nie jest na kanale głosowym.", ephemeral=True)
            return

        state.volume = poziom / 100.0
        if state.voice_client.source and isinstance(state.voice_client.source, discord.PCMVolumeTransformer):
            state.voice_client.source.volume = state.volume
        
        if send_feedback:
            emoji_glosnosci = "🔊" if poziom > 50 else "🔉" if poziom > 0 else "🔇"
            embed = await self._create_music_embed(ctx_or_int, title=f"{emoji_glosnosci} Głośność Ustawiona", description=f"Głośność ustawiona na **{poziom}%**.")
            await self._send_response(ctx_or_int, embed=embed)

    async def _loop_command_logic(self, ctx_or_int: typing.Union[Context, Interaction], tryb: str, send_feedback: bool = True):
        guild = await self._get_guild_from_context_or_interaction(ctx_or_int)
        if not guild:
            if send_feedback: await self._send_response(ctx_or_int, content="Ta komenda działa tylko na serwerze.", ephemeral=True)
            return
        state = self._get_guild_state(guild.id)

        if tryb == "song":
            state.loop_current_song = not state.loop_current_song
            state.loop_queue = False 
            status_str = "Włączono" if state.loop_current_song else "Wyłączono"
            embed = await self._create_music_embed(ctx_or_int, title=f"🔂 Zapętlanie Utworu {status_str}")
        elif tryb == "queue":
            state.loop_queue = not state.loop_queue
            state.loop_current_song = False
            status_str = "Włączono" if state.loop_queue else "Wyłączono"
            embed = await self._create_music_embed(ctx_or_int, title=f"🔁 Zapętlanie Kolejki {status_str}")
        elif tryb == "off":
            state.loop_current_song = False
            state.loop_queue = False
            embed = await self._create_music_embed(ctx_or_int, title="❌ Zapętlanie Wyłączone")
        else:
            if send_feedback: await self._send_response(ctx_or_int, content="Nieznany tryb zapętlania.", ephemeral=True)
            return
        
        if send_feedback:
            await self._send_response(ctx_or_int, embed=embed)


    # Komendy (pozostają bez zmian, teraz wołają _command_logic)
    @app_commands.command(name="stop", description="Zatrzymuje odtwarzanie i czyści kolejkę.")
    async def stop_slash(self, interaction: Interaction):
        await self._stop_command_logic(interaction)

    @commands.command(name="stop", aliases=['zatrzymaj', 's'], help="Zatrzymuje odtwarzanie muzyki i czyści kolejkę.")
    async def stop_prefix(self, context: Context):
        await self._stop_command_logic(context)

    @app_commands.command(name="skip", description="Pomija aktualnie odtwarzany utwór.")
    async def skip_slash(self, interaction: Interaction):
        await self._skip_command_logic(interaction)

    @commands.command(name="skip", aliases=['pomin', 'następny', 'n'], help="Pomija aktualnie odtwarzany utwór.")
    async def skip_prefix(self, context: Context):
        await self._skip_command_logic(context)

    @app_commands.command(name="queue", description="Wyświetla aktualną kolejkę utworów.")
    async def queue_slash(self, interaction: Interaction):
        await self._queue_command_logic(interaction)

    @commands.command(name="queue", aliases=['kolejka', 'q', 'lista'], help="Wyświetla aktualną kolejkę utworów.")
    async def queue_prefix(self, context: Context):
        await self._queue_command_logic(context)

    @app_commands.command(name="pause", description="Pauzuje odtwarzanie muzyki.")
    async def pause_slash(self, interaction: Interaction):
        await self._pause_command_logic(interaction)

    @commands.command(name="pause", aliases=['pauza'], help="Pauzuje odtwarzanie muzyki.")
    async def pause_prefix(self, context: Context):
        await self._pause_command_logic(context)

    @app_commands.command(name="resume", description="Wznawia odtwarzanie muzyki.")
    async def resume_slash(self, interaction: Interaction):
        await self._resume_command_logic(interaction)

    @commands.command(name="resume", aliases=['wznow', 'kontynuuj'], help="Wznawia odtwarzanie muzyki.")
    async def resume_prefix(self, context: Context):
        await self._resume_command_logic(context)

    @app_commands.command(name="leave", description="Elara opuszcza kanał głosowy.")
    async def leave_slash(self, interaction: Interaction):
        await self._leave_command_logic(interaction)

    @commands.command(name="leave", aliases=['opusc', 'disconnect', 'dc'], help="Elara opuszcza kanał głosowy.")
    async def leave_prefix(self, context: Context):
        await self._leave_command_logic(context)

    @app_commands.command(name="volume", description="Ustawia głośność odtwarzania (0-100%).")
    @app_commands.describe(poziom="Poziom głośności (liczba od 0 do 100).")
    async def volume_slash(self, interaction: Interaction, poziom: app_commands.Range[int, 0, 100]):
        await self._volume_command_logic(interaction, poziom)

    @commands.command(name="volume", aliases=['vol', 'glosnosc'], help="Ustawia głośność odtwarzania (0-100%).")
    async def volume_prefix(self, context: Context, poziom: int):
        if not (0 <= poziom <= 100):
            await context.send("Poziom głośności musi być liczbą od 0 do 100.", ephemeral=True)
            return
        await self._volume_command_logic(context, poziom)

    @app_commands.command(name="loop", description="Zapętla obecny utwór lub całą kolejkę.")
    @app_commands.describe(tryb="Tryb zapętlania: 'song' (utwór), 'queue' (kolejka), 'off' (wyłącz).")
    @app_commands.choices(tryb=[
        app_commands.Choice(name="🔂 Utwór (Song)", value="song"),
        app_commands.Choice(name="🔁 Kolejka (Queue)", value="queue"),
        app_commands.Choice(name="❌ Wyłącz (Off)", value="off"),
    ])
    async def loop_slash(self, interaction: Interaction, tryb: app_commands.Choice[str]):
        await self._loop_command_logic(interaction, tryb.value)

    @commands.command(name="loop", aliases=['zapętl', 'powtarzaj'], help="Zapętla obecny utwór ('song'), całą kolejkę ('queue') lub wyłącza zapętlanie ('off').")
    async def loop_prefix(self, context: Context, tryb: str):
        tryb_lower = tryb.lower()
        valid_modes = {"song", "queue", "off", "utwor", "utwór", "kolejka", "wyłącz", "wylacz"}
        if tryb_lower not in valid_modes:
            await context.send("Nieprawidłowy tryb zapętlania. Dostępne: `song`, `queue`, `off`.", ephemeral=True)
            return
        
        if tryb_lower in ["utwor", "utwór"]: tryb_mapped = "song"
        elif tryb_lower in ["wyłącz", "wylacz"]: tryb_mapped = "off"
        elif tryb_lower == "kolejka": tryb_mapped = "queue"
        else: tryb_mapped = tryb_lower 

        await self._loop_command_logic(context, tryb_mapped)


    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if not self.bot.user or member.id == self.bot.user.id: # type: ignore
            return

        if before.channel and before.channel.guild:
            state = self._get_guild_state(before.channel.guild.id)
            if state.voice_client and state.voice_client.channel == before.channel:
                if after.channel != before.channel and member.id == self.bot.user.id: 
                    if after.channel is None: 
                         self.bot.logger.info(f"Bot został rozłączony z kanału głosowego {before.channel.name} na serwerze {before.channel.guild.name}.")
                         await state._cleanup_playback(from_leave=True)
                         state.voice_client = None 
                    else: 
                         self.bot.logger.info(f"Bot został przeniesiony z {before.channel.name} do {after.channel.name} na serwerze {before.channel.guild.name}.")
                         for vc in self.bot.voice_clients:
                             if vc.guild.id == before.channel.guild.id:
                                 state.voice_client = vc
                                 break
                    return

                human_members = [m for m in before.channel.members if not m.bot]
                if not human_members: 
                    self.bot.logger.info(f"Bot jest sam na kanale {before.channel.name} ({before.channel.guild.name}). Rozpoczynam odliczanie do opuszczenia.")
                    await asyncio.sleep(60)
                    if state.voice_client and state.voice_client.channel == before.channel:
                        current_human_members = [m for m in before.channel.members if not m.bot]
                        if not current_human_members:
                            self.bot.logger.info(f"Bot nadal sam. Opuszczam kanał {before.channel.name}.")
                            await state._cleanup_playback(from_leave=True)
                            await state.voice_client.disconnect()
                            state.voice_client = None
                            if state.last_interaction_channel:
                                try:
                                    await state.last_interaction_channel.send("Elara opuściła kanał głosowy z powodu braku słuchaczy.")
                                except discord.HTTPException: pass


async def setup(bot: 'BotDiscord') -> None:
    try:
        process = await asyncio.create_subprocess_shell(
            "ffmpeg -version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            bot.logger.info("FFmpeg znaleziony. Kapsuła muzyczna może działać poprawnie.")
        else:
            bot.logger.warning("FFmpeg nie został znaleziony lub wystąpił błąd podczas sprawdzania wersji. Kapsuła muzyczna może nie działać poprawnie.")
            bot.logger.warning(f"FFmpeg stderr: {stderr.decode(errors='ignore').strip()}")
    except FileNotFoundError:
        bot.logger.error("KRYTYCZNY BŁĄD: FFmpeg nie został znaleziony w ścieżce systemowej. Kapsuła muzyczna NIE BĘDZIE DZIAŁAĆ.")
        bot.logger.error("Upewnij się, że FFmpeg jest zainstalowany i dodany do zmiennych środowiskowych PATH.")
    except Exception as e:
        bot.logger.error(f"Nieoczekiwany błąd podczas sprawdzania FFmpeg: {e}", exc_info=True)

    await bot.add_cog(Muzyka(bot))
