import discord
from discord.ext import commands
from discord import app_commands
from yt_dlp import YoutubeDL
import os
import asyncio
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# Charger les variables d'environnement
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

# Configuration Spotify API
sp = spotipy.Spotify(
    auth_manager=SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET))

# Configuration du bot
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# File d'attente des musiques
queues = {}


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Bot connecté en tant que {bot.user} et commandes synchronisées.")


def get_song_url(url):
    """ Récupère l'URL audio d'une musique depuis Spotify, YouTube ou Deezer."""
    if "spotify.com" in url:
        track_info = sp.track(url)
        track_name = track_info['name']
        artist_name = track_info['artists'][0]['name']
        query = f"{track_name} {artist_name}"
    else:
        query = url  # Direct URL YouTube ou Deezer

    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'default_search': 'ytsearch' if "spotify.com" in url else None,
        'noplaylist': True
    }

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=False)
        if 'entries' in info:
            return info['entries'][0]['url'], info['entries'][0]['title'], info['entries'][0]['uploader']
        elif 'url' in info:
            return info['url'], info.get('title', 'Titre inconnu'), info.get('uploader', 'Artiste inconnu')
        return None, None, None


def check_queue(guild):
    if guild.id in queues and queues[guild.id]:
        next_song = queues[guild.id].pop(0)
        guild.voice_client.play(discord.FFmpegPCMAudio(next_song['url'], executable="ffmpeg"),
                                after=lambda e: check_queue(guild))


@bot.tree.command(name="play", description="Joue une musique à partir d’un lien Spotify, YouTube ou Deezer")
async def play(interaction: discord.Interaction, url: str):
    await interaction.response.defer()

    voice_channel = interaction.user.voice.channel if interaction.user.voice else None
    if not voice_channel:
        await interaction.followup.send("❌ Vous devez être dans un canal vocal !")
        return

    if not interaction.guild.voice_client:
        await voice_channel.connect()

    song_url, track_name, artist_name = get_song_url(url)
    if not song_url:
        await interaction.followup.send("❌ Impossible de récupérer la musique.")
        return

    ffmpeg_options = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn -loglevel quiet'
    }

    guild_id = interaction.guild.id
    song_data = {"url": song_url, "title": track_name, "artist": artist_name}

    if guild_id not in queues:
        queues[guild_id] = {"now_playing": None, "queue": []}

    if interaction.guild.voice_client.is_playing():
        queues[guild_id]["queue"].append(song_data)
        await interaction.followup.send(f"🎵 **{track_name}** de **{artist_name}** ajouté à la file d'attente !")
    else:
        queues[guild_id]["now_playing"] = song_data
        interaction.guild.voice_client.play(
            discord.FFmpegPCMAudio(song_url, executable="ffmpeg", **ffmpeg_options),
            after=lambda e: check_queue(interaction.guild)
        )
        await interaction.followup.send(f"🎶 En train de jouer : **{track_name}** de **{artist_name}**")


@bot.tree.command(name="pause", description="Met la musique en pause")
async def pause(interaction: discord.Interaction):
    if interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.pause()
        await interaction.response.send_message("⏸️ Musique en pause.")


@bot.tree.command(name="resume", description="Reprend la musique mise en pause")
async def resume(interaction: discord.Interaction):
    if interaction.guild.voice_client.is_paused():
        interaction.guild.voice_client.resume()
        await interaction.response.send_message("▶️ Musique reprise.")


@bot.tree.command(name="skip", description="Passe à la musique suivante")
async def skip(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    voice_client = interaction.guild.voice_client

    if not voice_client or not voice_client.is_playing():
        await interaction.response.send_message("❌ Aucune musique en cours de lecture.")
        return

    voice_client.stop()

    # Vérifier la file d'attente et jouer la musique suivante si disponible
    if guild_id in queues and "queue" in queues[guild_id] and queues[guild_id]["queue"]:
        next_song = queues[guild_id]["queue"].pop(0)
        queues[guild_id]["now_playing"] = next_song
        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn -loglevel quiet'
        }
        voice_client.play(
            discord.FFmpegPCMAudio(next_song['url'], executable="ffmpeg", **ffmpeg_options),
            after=lambda e: skip(interaction)
        )
        await interaction.response.send_message(
            f"⏭️ Musique suivante : **{next_song['title']}** de **{next_song['artist']}**")
    else:
        queues[guild_id]["now_playing"] = None
        await interaction.response.send_message("📜 Plus de musique dans la file d'attente.")


@bot.tree.command(name="queue", description="Affiche la musique en cours et la liste des musiques en attente")
async def queue(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    voice_client = interaction.guild.voice_client

    now_playing = "🎶 Aucune musique en cours de lecture."

    # Vérifier si une musique est en cours de lecture
    if guild_id in queues and "now_playing" in queues[guild_id]:
        song = queues[guild_id]["now_playing"]
        now_playing = f"🎶 **En cours de lecture :** \n" + f" {song['title']} - {song['artist']}"

    # Vérifier la file d'attente
    if guild_id in queues and "queue" in queues[guild_id] and queues[guild_id]["queue"]:
        queue_list = "\n".join(
            [f"{i + 1}. {song['title']} - {song['artist']}" for i, song in enumerate(queues[guild_id]["queue"])]
        )
        queue_message = f"\n📜 **File d'attente :**\n" + f"{queue_list}"
    else:
        queue_message = "📜 Aucune musique en attente."

    await interaction.response.send_message(f"{now_playing}\n{queue_message}")


@bot.tree.command(name="clear", description="Vide la file d’attente")
async def clear(interaction: discord.Interaction):
    queues[interaction.guild.id] = []
    await interaction.response.send_message("🗑️ File d'attente vidée !")


# Lancer le bot
bot.run(TOKEN)