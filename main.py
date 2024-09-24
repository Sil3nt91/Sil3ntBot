import os
import discord
from discord.ext import commands
import yt_dlp as youtube_dl
from googleapiclient.discovery import build
import json
import asyncio
from functools import partial
from types import SimpleNamespace

# Verifica che Opus sia caricato correttamente
if not discord.opus.is_loaded():
    discord.opus.load_opus('libopus.so')

# Crea l'istanza del bot con gli intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True
bot = commands.Bot(command_prefix="!", intents=intents)

# File per salvare le playlist
PLAYLISTS_FILE = 'playlists.json'

# Funzioni per caricare e salvare le playlist
def load_playlists():
    if os.path.exists(PLAYLISTS_FILE):
        with open(PLAYLISTS_FILE, 'r') as f:
            return json.load(f)
    else:
        return {
            'playlist1': {'songs': [], 'name': 'Playlist 1'},
            'playlist2': {'songs': [], 'name': 'Playlist 2'},
            'playlist3': {'songs': [], 'name': 'Playlist 3'},
        }

def save_playlists():
    with open(PLAYLISTS_FILE, 'w') as f:
        json.dump(playlists, f, indent=4)

# Inizializza le playlist
playlists = load_playlists()
max_songs_per_playlist = 10

# Dizionario per memorizzare il volume per ogni guild
volumes = {}  # e.g., {guild_id: 0.5}

# Dizionario per memorizzare le code delle canzoni per ogni guild
song_queues = {}  # e.g., {guild_id: [song1, song2, ...]}

# YouTube API setup
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

# Funzione per cercare su YouTube tramite API
async def search_youtube(query: str):
    try:
        search_response = youtube.search().list(
            q=query,
            part='id,snippet',
            maxResults=1,
            type='video'
        ).execute()

        if 'items' in search_response and len(search_response['items']) > 0:
            video = search_response['items'][0]
            video_title = video['snippet']['title']
            video_id = video['id']['videoId']
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            print(f"Trovato: {video_title} - {video_url}")
            return {'title': video_title, 'url': video_url}
        else:
            print("Nessun risultato trovato.")
            return None
    except Exception as e:
        print(f"Errore durante la ricerca su YouTube: {e}")
        return None

# Funzione per creare automaticamente il canale testuale "Sil3ntBot"
async def create_text_channel_if_not_exists(guild):
    existing_channel = discord.utils.get(guild.text_channels, name="sil3ntbot")
    if not existing_channel:
        return await guild.create_text_channel('sil3ntbot')
    return existing_channel

# Evento che si attiva quando un utente si unisce a un canale vocale
@bot.event
async def on_voice_state_update(member, before, after):
    if after.channel is not None and before.channel != after.channel:
        guild = member.guild
        text_channel = await create_text_channel_if_not_exists(guild)
        await text_channel.send(f"{member.display_name} è entrato nel canale vocale {after.channel.name}.", view=MainCommandsView())

# Classe per la vista dei comandi principali
class MainCommandsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        # Bottone per cercare canzoni
        search_button = discord.ui.Button(label="🔍 Cerca Canzone", style=discord.ButtonStyle.primary)
        search_button.callback = self.search_song
        self.add_item(search_button)

        # Pulsanti di controllo della riproduzione
        playback_buttons = [
            ("⏸️ Pausa", discord.ButtonStyle.primary, self.pause),
            ("▶️ Riprendi", discord.ButtonStyle.success, self.resume),
            ("⏹️ Stop", discord.ButtonStyle.danger, self.stop),
            ("⏭️ Skip", discord.ButtonStyle.secondary, self.skip)
        ]

        for label, style, callback in playback_buttons:
            button = discord.ui.Button(label=label, style=style)
            button.callback = callback
            self.add_item(button)

        # Aggiungiamo i bottoni delle playlist
        for i in range(1, 4):
            playlist_key = f'playlist{i}'
            playlist_name = playlists[playlist_key]['name']
            button = discord.ui.Button(label=f"🎵 {playlist_name}", style=discord.ButtonStyle.primary)
            button.callback = partial(self.playlist_callback, playlist_key=playlist_key)
            self.add_item(button)

    async def search_song(self, interaction: discord.Interaction):
        await interaction.response.send_modal(SearchModal())

    async def pause(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            await interaction.response.send_message("Musica in pausa.", ephemeral=True)
        else:
            await interaction.response.send_message("Nessuna canzone in riproduzione.", ephemeral=True)

    async def resume(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            await interaction.response.send_message("Riproduzione ripresa.", ephemeral=True)
        else:
            await interaction.response.send_message("Nessuna canzone in pausa.", ephemeral=True)

    async def stop(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if voice_client:
            song_queues[interaction.guild.id] = []  # Svuota la coda
            voice_client.stop()
            await interaction.response.send_message("Riproduzione fermata.", ephemeral=True)
        else:
            await interaction.response.send_message("Nessuna canzone in riproduzione.", ephemeral=True)

    async def skip(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.stop()
            await interaction.response.send_message("Canzone saltata.", ephemeral=True)
        else:
            await interaction.response.send_message("Nessuna canzone in riproduzione.", ephemeral=True)

    async def playlist_callback(self, interaction: discord.Interaction, playlist_key):
        playlist = playlists.get(playlist_key)
        if playlist and playlist['songs']:
            await interaction.response.send_message(
                f"Ecco le canzoni nella playlist **{playlist['name']}**:",
                view=PlaylistSongsView(playlist_key),
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"La playlist **{playlist['name']}** è vuota.",
                ephemeral=True
            )

# Classe per mostrare le canzoni di una playlist
class PlaylistSongsView(discord.ui.View):
    def __init__(self, playlist_key):
        super().__init__(timeout=None)
        self.playlist_key = playlist_key
        self.playlist = playlists[playlist_key]

        # Aggiungiamo un bottone per ogni canzone nella playlist
        for song in self.playlist['songs']:
            button = discord.ui.Button(label=song['title'], style=discord.ButtonStyle.secondary)
            button.callback = partial(self.play_song_from_playlist, song=song)
            self.add_item(button)

    async def play_song_from_playlist(self, interaction: discord.Interaction, song):
        await interaction.response.defer()
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            # Chiedi se riprodurre subito o aggiungere alla coda
            await interaction.followup.send(
                f"Una canzone è in riproduzione. Vuoi riprodurre subito **{song['title']}** o aggiungerla alla coda?",
                view=PlayNowOrQueueView(song),
                ephemeral=True
            )
        else:
            # Riproduci la canzone selezionata
            success = await play_song(interaction, song)
            if not success:
                await interaction.followup.send("Errore durante la riproduzione della canzone.", ephemeral=True)

# Classe per la modale di ricerca canzone
class SearchModal(discord.ui.Modal, title="Cerca Canzone"):
    query = discord.ui.TextInput(label="Inserisci il titolo della canzone")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        video = await search_youtube(self.query.value)
        if not video:
            await interaction.followup.send("Nessun risultato trovato.", ephemeral=True)
            return

        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            # Se una canzone è in riproduzione, chiedi all'utente cosa fare
            await interaction.followup.send(
                f"Una canzone è in riproduzione. Vuoi riprodurre subito **{video['title']}** o aggiungerla alla coda?",
                view=PlayNowOrQueueView(video),
                ephemeral=True
            )
        else:
            # Nessuna canzone in riproduzione, riproduci subito
            success = await play_song(interaction, video)
            if not success:
                return

# Classe per chiedere se riprodurre subito o aggiungere alla coda
class PlayNowOrQueueView(discord.ui.View):
    def __init__(self, video):
        super().__init__(timeout=30)
        self.video = video

    @discord.ui.button(label="Riproduci Subito", style=discord.ButtonStyle.primary)
    async def play_now(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        success = await play_song(interaction, self.video, play_now=True)
        if not success:
            await interaction.followup.send("Errore durante la riproduzione.", ephemeral=True)

    @discord.ui.button(label="Aggiungi alla Coda", style=discord.ButtonStyle.secondary)
    async def add_to_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = interaction.guild.id
        # Inizializza la coda se non esiste
        if guild_id not in song_queues:
            song_queues[guild_id] = []
        song_queues[guild_id].append(self.video)
        await interaction.response.send_message(f"Canzone **{self.video['title']}** aggiunta alla coda.", ephemeral=True)

# Funzione per riprodurre la canzone
async def play_song(interaction, video, play_now=False):
    guild_id = interaction.guild.id
    voice_client = interaction.guild.voice_client

    # Inizializza la coda per la guild se non esiste
    if guild_id not in song_queues:
        song_queues[guild_id] = []

    # Se non siamo connessi al canale vocale, connettiti
    if not voice_client:
        if interaction.user.voice:
            try:
                voice_client = await interaction.user.voice.channel.connect()
            except Exception as e:
                await interaction.followup.send(f"Errore durante la connessione al canale vocale: {e}", ephemeral=True)
                return False
        else:
            await interaction.followup.send("Devi essere in un canale vocale per riprodurre musica!", ephemeral=True)
            return False

    # Ferma la canzone corrente se necessario
    if play_now and (voice_client.is_playing() or voice_client.is_paused()):
        voice_client.stop()

    # Se una canzone è in riproduzione e non vogliamo riprodurre subito, aggiungila alla coda
    if voice_client.is_playing() and not play_now:
        song_queues[guild_id].append(video)
        await interaction.followup.send(f"Canzone **{video['title']}** aggiunta alla coda.", ephemeral=True)
        return True

    # Altrimenti, riproduci la canzone immediatamente
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'noplaylist': True,
            'cookiefile': 'cookies.txt'  # Assicurati che questo file esista se lo usi
        }

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video['url'], download=False)
            audio_url = info['url']
            audio_source = discord.FFmpegPCMAudio(audio_url)
            volume = volumes.get(guild_id, 0.5)
            pcm_volume = discord.PCMVolumeTransformer(audio_source, volume=volume)

            # Definisci una funzione di callback per quando la canzone finisce
            def after_playing(error):
                if error:
                    print(f"Errore durante la riproduzione: {error}")
                # Riproduci la prossima canzone in coda, se presente
                asyncio.run_coroutine_threadsafe(play_next_song(interaction.guild), bot.loop)

            voice_client.play(pcm_volume, after=after_playing)

            # Invia il messaggio con i controlli
            view = CombinedView(guild_id, video)
            message = await interaction.followup.send(
                content=f"Riproducendo: **{video['title']}**",
                view=view
            )
            view.message = message
            view.channel = message.channel
            return True
    except Exception as e:
        await interaction.followup.send(f"Errore durante la riproduzione: {e}", ephemeral=True)
        return False

# Funzione per riprodurre la prossima canzone in coda
async def play_next_song(guild):
    guild_id = guild.id
    voice_client = guild.voice_client

    if guild_id in song_queues and song_queues[guild_id]:
        # Prendi la prossima canzone dalla coda
        next_song = song_queues[guild_id].pop(0)
        # Crea un oggetto fittizio per l'interazione
        # Trova un canale testuale per inviare i messaggi
        text_channel = await create_text_channel_if_not_exists(guild)
        fake_interaction = SimpleNamespace(
            guild=guild,
            user=guild.me,
            followup=text_channel
        )
        # Riproduci la prossima canzone
        await play_song(fake_interaction, next_song, play_now=True)
    else:
        # Se la coda è vuota, disconnettiti
        if voice_client:
            await voice_client.disconnect()

# Classe che combina i controlli di riproduzione e l'aggiunta alla playlist
class CombinedView(discord.ui.View):
    def __init__(self, guild_id, video):
        super().__init__(timeout=20)
        self.guild_id = guild_id
        self.video = video
        self.message = None
        self.channel = None

        # Pulsanti di controllo della riproduzione
        playback_buttons = [
            ("⏸️ Pausa", discord.ButtonStyle.primary, self.pause),
            ("▶️ Riprendi", discord.ButtonStyle.success, self.resume),
            ("⏹️ Stop", discord.ButtonStyle.danger, self.stop),
            ("⏭️ Skip", discord.ButtonStyle.secondary, self.skip),
            ("🔊 Volume +", discord.ButtonStyle.secondary, self.volume_up),
            ("🔉 Volume -", discord.ButtonStyle.secondary, self.volume_down),
        ]

        for label, style, callback in playback_buttons:
            button = discord.ui.Button(label=label, style=style)
            button.callback = callback
            self.add_item(button)

        # Pulsante per aggiungere alla playlist
        add_button = discord.ui.Button(label="➕ Aggiungi alla Playlist", style=discord.ButtonStyle.success)
        add_button.callback = self.add_to_playlist
        self.add_item(add_button)

    async def on_timeout(self):
        if self.channel:
            await self.channel.send("Ecco i comandi principali:", view=MainCommandsView())

    async def add_to_playlist(self, interaction: discord.Interaction):
        await interaction.response.send_message("In quale playlist vuoi aggiungere la canzone?", view=SelectPlaylistView(self.video), ephemeral=True)

    # Callback per i controlli di riproduzione
    async def pause(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            await interaction.response.send_message("Musica in pausa.", ephemeral=True)
        else:
            await interaction.response.send_message("Nessuna canzone in riproduzione.", ephemeral=True)

    async def resume(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            await interaction.response.send_message("Riproduzione ripresa.", ephemeral=True)
        else:
            await interaction.response.send_message("Nessuna canzone in pausa.", ephemeral=True)

    async def stop(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if voice_client:
            song_queues[interaction.guild.id] = []  # Svuota la coda
            voice_client.stop()
            await interaction.response.send_message("Riproduzione fermata.", ephemeral=True)
        else:
            await interaction.response.send_message("Nessuna canzone in riproduzione.", ephemeral=True)

    async def skip(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.stop()
            await interaction.response.send_message("Canzone saltata.", ephemeral=True)
        else:
            await interaction.response.send_message("Nessuna canzone in riproduzione.", ephemeral=True)

    async def volume_up(self, interaction: discord.Interaction):
        guild_id = self.guild_id
        volumes[guild_id] = min(1.0, volumes.get(guild_id, 0.5) + 0.1)
        if interaction.guild.voice_client and interaction.guild.voice_client.source:
            interaction.guild.voice_client.source.volume = volumes[guild_id]
        await interaction.response.send_message(f"Volume aumentato a {int(volumes[guild_id] * 100)}%.", ephemeral=True)

    async def volume_down(self, interaction: discord.Interaction):
        guild_id = self.guild_id
        volumes[guild_id] = max(0.0, volumes.get(guild_id, 0.5) - 0.1)
        if interaction.guild.voice_client and interaction.guild.voice_client.source:
            interaction.guild.voice_client.source.volume = volumes[guild_id]
        await interaction.response.send_message(f"Volume ridotto a {int(volumes[guild_id] * 100)}%.", ephemeral=True)

# Classe per selezionare la playlist
class SelectPlaylistView(discord.ui.View):
    def __init__(self, video):
        super().__init__()
        self.video = video

        for i in range(1, 4):
            playlist_key = f'playlist{i}'
            playlist_name = playlists[playlist_key]['name']
            button = discord.ui.Button(label=f"🎵 {playlist_name}", style=discord.ButtonStyle.primary)
            button.callback = partial(self.add_to_playlist, playlist_key=playlist_key)
            self.add_item(button)

    async def add_to_playlist(self, interaction, playlist_key):
        playlist = playlists.get(playlist_key)
        if playlist and len(playlist['songs']) < max_songs_per_playlist:
            playlist['songs'].append(self.video)
            save_playlists()
            await interaction.response.send_message(f"Canzone aggiunta a {playlist['name']}. Vuoi cambiare il nome della playlist?", view=ChangePlaylistNameView(playlist_key))
        else:
            await interaction.response.send_message(f"La playlist {playlist['name']} è piena.", ephemeral=True)

# Classe per la modale di cambio nome playlist
class ChangePlaylistNameModal(discord.ui.Modal, title="Cambia Nome Playlist"):
    new_name = discord.ui.TextInput(label="Nuovo Nome della Playlist", max_length=50)

    def __init__(self, playlist_key):
        super().__init__()
        self.playlist_key = playlist_key

    async def on_submit(self, interaction: discord.Interaction):
        new_name = self.new_name.value.strip()
        if new_name:
            old_name = playlists[self.playlist_key]['name']
            playlists[self.playlist_key]['name'] = new_name
            save_playlists()
            await interaction.response.send_message(f"Nome della playlist cambiato da **{old_name}** a **{new_name}**.")
            await interaction.followup.send("Ecco i comandi disponibili:", view=MainCommandsView())
        else:
            await interaction.response.send_message("Il nome non può essere vuoto.", ephemeral=True)

# Classe per visualizzare la richiesta di cambio nome playlist
class ChangePlaylistNameView(discord.ui.View):
    def __init__(self, playlist_key):
        super().__init__()
        self.playlist_key = playlist_key

        yes_button = discord.ui.Button(label="Sì", style=discord.ButtonStyle.success)
        yes_button.callback = self.change_yes
        self.add_item(yes_button)

        no_button = discord.ui.Button(label="No", style=discord.ButtonStyle.danger)
        no_button.callback = self.change_no
        self.add_item(no_button)

    async def change_yes(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ChangePlaylistNameModal(self.playlist_key))

    async def change_no(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"Nome della playlist **{playlists[self.playlist_key]['name']}** mantenuto.")
        await interaction.followup.send("Ecco i comandi disponibili:", view=MainCommandsView())

# Avvia il bot con il token preso dalle variabili di ambiente
bot.run(os.getenv('DISCORD_BOT_TOKEN'))
