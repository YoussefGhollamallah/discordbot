import discord
import os
import json
from datetime import datetime
from dotenv import load_dotenv
import asyncio
import aiohttp
import re
import sqlite3
from sqlite3 import Error

load_dotenv()

# Charger les intents
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

bot = discord.Client(intents=intents)

TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")

DB_FILE = "bot.db"

# Dictionnaire pour suivre l'état des streams
live_status = {}

def create_database():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Table des streamers
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS streamers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            streamer_url TEXT NOT NULL,
            username TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # Table des messages
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            message_count INTEGER DEFAULT 0,
            month INTEGER NOT NULL,
            year INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(guild_id, user_id, month, year)
        )
        ''')

        # Table de l'historique
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS message_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            message_count INTEGER NOT NULL,
            month INTEGER NOT NULL,
            year INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        conn.commit()
        conn.close()
        print("Base de données créée avec succès!")
    except Error as e:
        print(f"Erreur lors de la création de la base de données: {e}")

def update_message_count(guild_id, user_id, month, year):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO messages (guild_id, user_id, message_count, month, year)
        VALUES (?, ?, 1, ?, ?)
        ON CONFLICT(guild_id, user_id, month, year) 
        DO UPDATE SET message_count = message_count + 1, updated_at = CURRENT_TIMESTAMP
        ''', (guild_id, user_id, month, year))
        
        conn.commit()
        conn.close()
        return True
    except Error as e:
        print(f"Erreur lors de la mise à jour du compteur de messages: {e}")
        return False

def save_month_history(guild_id, month, year):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Récupérer les messages du mois
        cursor.execute('''
        SELECT user_id, message_count 
        FROM messages 
        WHERE guild_id = ? AND month = ? AND year = ?
        ''', (guild_id, month, year))
        
        messages = cursor.fetchall()
        
        # Sauvegarder dans l'historique
        for user_id, message_count in messages:
            cursor.execute('''
            INSERT INTO message_history (guild_id, user_id, message_count, month, year)
            VALUES (?, ?, ?, ?, ?)
            ''', (guild_id, user_id, message_count, month, year))
        
        # Réinitialiser les compteurs
        cursor.execute('''
        DELETE FROM messages 
        WHERE guild_id = ? AND month = ? AND year = ?
        ''', (guild_id, month, year))
        
        conn.commit()
        conn.close()
        return True
    except Error as e:
        print(f"Erreur lors de la sauvegarde de l'historique: {e}")
        return False

def get_user_message_count(guild_id, user_id, month, year):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT message_count 
        FROM messages 
        WHERE guild_id = ? AND user_id = ? AND month = ? AND year = ?
        ''', (guild_id, user_id, month, year))
        
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0
    except Error as e:
        print(f"Erreur lors de la récupération du compteur de messages: {e}")
        return 0

def get_top_users(guild_id, month, year, limit=10):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT user_id, message_count 
        FROM messages 
        WHERE guild_id = ? AND month = ? AND year = ?
        ORDER BY message_count DESC 
        LIMIT ?
        ''', (guild_id, month, year, limit))
        
        results = cursor.fetchall()
        conn.close()
        return results
    except Error as e:
        print(f"Erreur lors de la récupération du top: {e}")
        return []

def get_month_history(guild_id, month, year, limit=10):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT user_id, message_count 
        FROM message_history 
        WHERE guild_id = ? AND month = ? AND year = ?
        ORDER BY message_count DESC 
        LIMIT ?
        ''', (guild_id, month, year, limit))
        
        results = cursor.fetchall()
        conn.close()
        return results
    except Error as e:
        print(f"Erreur lors de la récupération de l'historique: {e}")
        return []

def reset_stats(guild_id):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute('''
        DELETE FROM messages 
        WHERE guild_id = ?
        ''', (guild_id,))
        
        conn.commit()
        conn.close()
        return True
    except Error as e:
        print(f"Erreur lors de la réinitialisation des stats: {e}")
        return False

# Fonction pour obtenir le mois en toutes lettres
def get_month_name(month_number):
    months = {
        1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril",
        5: "Mai", 6: "Juin", 7: "Juillet", 8: "Août",
        9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"
    }
    return months.get(month_number, "Inconnu")

def extract_username_from_url(url):
    # Extraire le nom d'utilisateur de l'URL Twitch
    patterns = [
        r"twitch\.tv/([a-zA-Z0-9_]+)",
        r"www\.twitch\.tv/([a-zA-Z0-9_]+)"
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

async def get_twitch_token():
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://id.twitch.tv/oauth2/token",
            params={
                "client_id": TWITCH_CLIENT_ID,
                "client_secret": TWITCH_CLIENT_SECRET,
                "grant_type": "client_credentials"
            }
        ) as response:
            data = await response.json()
            return data.get("access_token")

async def check_stream_status(username):
    token = await get_twitch_token()
    
    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {token}"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://api.twitch.tv/helix/streams?user_login={username}",
            headers=headers
        ) as response:
            data = await response.json()
            return len(data.get("data", [])) > 0, data.get("data", [{}])[0] if data.get("data") else None

async def check_streams():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            
            # Récupérer tous les streamers
            cursor.execute('''
            SELECT guild_id, channel_id, streamer_url, username 
            FROM streamers
            ''')
            
            streamers = cursor.fetchall()
            conn.close()
            
            for guild_id, channel_id, streamer_url, username in streamers:
                guild = bot.get_guild(int(guild_id))
                if not guild:
                    continue

                notification_channel = guild.get_channel(int(channel_id))
                if not notification_channel:
                    continue

                is_live, stream_data = await check_stream_status(username)
                
                # Si le streamer est en live et n'a pas déjà été annoncé
                if is_live and not live_status.get(f"{guild_id}_{username}", False):
                    embed = discord.Embed(
                        title=f"🔴 {username} est en live !",
                        description=f"**{stream_data['title']}**\nJeu : {stream_data['game_name']}",
                        url=f"https://twitch.tv/{username}",
                        color=0x6441A4
                    )
                    if stream_data.get("thumbnail_url"):
                        thumbnail_url = stream_data["thumbnail_url"].replace("{width}", "320").replace("{height}", "180")
                        embed.set_image(url=thumbnail_url)
                    
                    await notification_channel.send(embed=embed)
                    live_status[f"{guild_id}_{username}"] = True
                elif not is_live:
                    live_status[f"{guild_id}_{username}"] = False

        except Exception as e:
            print(f"Erreur lors de la vérification des streams : {e}")
        
        await asyncio.sleep(60)  # Vérifier toutes les minutes

@bot.event
async def on_ready():
    print(f"Bot connecté en tant que {bot.user}")
    bot.loop.create_task(check_streams())

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.guild is None:
        return

    guild_id = str(message.guild.id)
    user_id = str(message.author.id)
    current_date = datetime.now()
    current_month = current_date.month
    current_year = current_date.year
    previous_month = current_month - 1 if current_month > 1 else 12
    previous_year = current_year - 1 if current_month == 1 else current_year

    # Vérifier si le mois a changé
    if current_date.day == 1 and current_date.hour == 0:
        save_month_history(guild_id, previous_month, previous_year)

    # Mettre à jour le compteur de messages
    if message.content not in ["!nb_messages", "!top", "!reset", "!help", "!historique", "!stream"] and not message.author.id == 310788228368039937:
        update_message_count(guild_id, user_id, current_month, current_year)

    # Récupérer le nombre de messages de l'utilisateur
    message_count = get_user_message_count(guild_id, user_id, current_month, current_year)

    # Commandes pour la gestion des streams
    if message.content.startswith("!stream"):
        if not message.author.guild_permissions.administrator:
            await message.channel.send("Vous devez être administrateur pour utiliser cette commande.")
            return

        args = message.content.split()
        if len(args) < 2:
            await message.channel.send("Usage: !stream add/remove/list <url_twitch>")
            return

        if args[1] == "add" and len(args) == 3:
            url = args[2].lower()
            username = extract_username_from_url(url)
            
            if not username:
                await message.channel.send("URL Twitch invalide. Format attendu : https://twitch.tv/nomdustreamer")
                return
                
            # Vérifier si le streamer existe déjà
            try:
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                cursor.execute('''
                SELECT id FROM streamers 
                WHERE guild_id = ? AND streamer_url = ?
                ''', (guild_id, url))
                
                if cursor.fetchone():
                    await message.channel.send("Ce streamer est déjà dans la liste.")
                    conn.close()
                    return
                
                # Vérifier si le streamer existe sur Twitch
                try:
                    token = await get_twitch_token()
                    if not token:
                        await message.channel.send("Erreur : Impossible d'obtenir le token Twitch. Vérifiez vos identifiants Twitch.")
                        conn.close()
                        return

                    headers = {
                        "Client-ID": TWITCH_CLIENT_ID,
                        "Authorization": f"Bearer {token}"
                    }
                    
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            f"https://api.twitch.tv/helix/users?login={username}",
                            headers=headers
                        ) as response:
                            if response.status != 200:
                                await message.channel.send(f"Erreur Twitch API : {response.status}")
                                conn.close()
                                return
                                
                            data = await response.json()
                            if not data.get("data"):
                                await message.channel.send("Ce streamer n'existe pas sur Twitch.")
                                conn.close()
                                return
                except Exception as e:
                    print(f"Erreur lors de la vérification Twitch : {e}")
                    await message.channel.send("Erreur lors de la vérification du streamer sur Twitch.")
                    conn.close()
                    return
                
                # Ajouter le streamer
                try:
                    cursor.execute('''
                    INSERT INTO streamers (guild_id, channel_id, streamer_url, username)
                    VALUES (?, ?, ?, ?)
                    ''', (guild_id, message.channel.id, url, username))
                    
                    conn.commit()
                    conn.close()
                    await message.channel.send(f"Le streamer {username} a été ajouté à la liste de suivi.")
                except Error as e:
                    print(f"Erreur SQL lors de l'ajout du streamer : {e}")
                    await message.channel.send("Erreur lors de l'enregistrement du streamer dans la base de données.")
                    conn.close()
                    return
                
            except Error as e:
                print(f"Erreur lors de l'ajout du streamer : {e}")
                await message.channel.send("Une erreur est survenue lors de l'ajout du streamer. Vérifiez les logs pour plus de détails.")

        elif args[1] == "remove" and len(args) == 3:
            url = args[2].lower()
            try:
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                
                cursor.execute('''
                DELETE FROM streamers 
                WHERE guild_id = ? AND streamer_url = ?
                ''', (guild_id, url))
                
                if cursor.rowcount > 0:
                    username = extract_username_from_url(url)
                    await message.channel.send(f"Le streamer {username} a été retiré de la liste de suivi.")
                else:
                    await message.channel.send("Ce streamer n'est pas dans la liste.")
                
                conn.commit()
                conn.close()
                
            except Error as e:
                print(f"Erreur lors de la suppression du streamer: {e}")
                await message.channel.send("Une erreur est survenue lors de la suppression du streamer.")

        elif args[1] == "list":
            try:
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                
                cursor.execute('''
                SELECT streamer_url 
                FROM streamers 
                WHERE guild_id = ?
                ''', (guild_id,))
                
                streamers = cursor.fetchall()
                conn.close()
                
                if streamers:
                    streamer_list = "\n".join([f"- {url[0]}" for url in streamers])
                    await message.channel.send(f"Liste des streamers suivis :\n{streamer_list}")
                else:
                    await message.channel.send("Aucun streamer n'est suivi actuellement.")
                    
            except Error as e:
                print(f"Erreur lors de la récupération des streamers: {e}")
                await message.channel.send("Une erreur est survenue lors de la récupération de la liste des streamers.")

    if message.content == "!help":
        help_message = (
            "Voici la liste des commandes disponibles :\n"
            "!nb_messages : Affiche ton nombre de messages du mois\n"
            "!top : Affiche le top 10 des membres les plus actifs\n"
            "!historique : Affiche les scores du mois précédent\n"
        )
        if message.author.guild_permissions.administrator:
            help_message += (
                "!reset : Réinitialise les statistiques\n"
                "!stream add <url_twitch> : Ajoute un streamer à suivre\n"
                "!stream remove <url_twitch> : Retire un streamer de la liste\n"
                "!stream list : Affiche la liste des streamers suivis\n"
            )
        await message.channel.send(help_message)

    if message.content == "!nb_messages":
        await message.channel.send(f"{message.author.mention}, tu as envoyé {message_count} message(s) en {get_month_name(current_month)} !")

    if message.content == "!top":
        top_users = get_top_users(guild_id, current_month, current_year)
        if not top_users:
            await message.channel.send("Aucune donnée pour ce mois.")
            return

        top_message = "\n".join([f"{index + 1}. <@{user_id}>: {message_count} messages" for index, (user_id, message_count) in enumerate(top_users)])
        await message.channel.send(f"Voici le top 10 des membres les plus actifs en {get_month_name(current_month)} :\n{top_message}")

    if message.content == "!historique":
        history_users = get_month_history(guild_id, previous_month, previous_year)
        if not history_users:
            await message.channel.send(f"Aucune donnée enregistrée pour {get_month_name(previous_month)}.")
            return

        top_message_prev = "\n".join([f"{index + 1}. <@{user_id}>: {message_count} messages" for index, (user_id, message_count) in enumerate(history_users)])
        await message.channel.send(f"Voici le top 10 des membres les plus actifs en {get_month_name(previous_month)} :\n{top_message_prev}")

    if message.content == "!reset" and message.author.guild_permissions.administrator:
        if reset_stats(guild_id):
            await message.channel.send("Les statistiques ont été réinitialisées pour ce serveur !")
        else:
            await message.channel.send("Une erreur est survenue lors de la réinitialisation des statistiques.")

bot.run(os.getenv("DISCORD_ENV"))
