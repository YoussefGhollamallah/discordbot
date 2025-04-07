import discord
import os
from datetime import datetime
from dotenv import load_dotenv
import mysql.connector
import requests
import asyncio

load_dotenv()

# Charger les intents
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.guild_messages = True
intents.members = True  # Correction ici : 'menbers' -> 'members'

bot = discord.Client(intents=intents)

ANNONCE_CHANNEL = int(os.getenv("ANNONCE_CHANNEL"))

# Informations de connexion à la base de données
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

# Informations d'identification Twitch
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_ACCESS_TOKEN = os.getenv("TWITCH_ACCESS_TOKEN")

# Fonction pour établir une connexion à la base de données
def connect_db():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )

# Fonction pour obtenir le mois en toutes lettres (inchangée)
def get_month_name(month_number):
    months = {
        1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril",
        5: "Mai", 6: "Juin", 7: "Juillet", 8: "Août",
        9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"
    }
    return months.get(month_number, "Inconnu")

# Fonction pour vérifier si un streamer Twitch est en live
async def check_twitch_live(streamer_username):
    headers = {
        'Client-ID': TWITCH_CLIENT_ID,
        'Authorization': f'Bearer {TWITCH_ACCESS_TOKEN}'
    }
    url = f'https://api.twitch.tv/helix/streams?user_login={streamer_username}'
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Lève une exception pour les codes d'erreur HTTP
        data = response.json()
        return data['data'][0] if data['data'] else None
    except requests.exceptions.RequestException as e:
        print(f"Erreur lors de la vérification du statut Twitch de {streamer_username}: {e}")
        return None

# Dictionnaire pour stocker l'état des lives déjà annoncés
announced_streams = {}

async def announce_live(guild_id, channel_id, streamer_url, username, stream_info):
    if stream_info["is_live"] and not announced_streams.get(username, False):
        channel = bot.get_channel(int(channel_id))
        if channel:
            embed = discord.Embed(
                title=f"{username} est en live sur Twitch !",
                url=streamer_url,
                description=f"🎮 **{stream_info['category']}**\n📢 {stream_info['title']}",
                color=discord.Color.purple()
            )
            embed.add_field(name="Cliquez ici pour regarder", value=streamer_url)
            await channel.send(f"🔴 Alerte live ! @everyone {username} est en direct :", embed=embed)

        announced_streams[username] = True
    elif not stream_info["is_live"] and announced_streams.get(username, False):
        announced_streams[username] = False


async def twitch_live_checker():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            db = connect_db()
            cursor = db.cursor()
            cursor.execute("SELECT guild_id, channel_id, streamer_url, username FROM streamers")
            streamers = cursor.fetchall()
            db.close()

            for guild_id, channel_id, streamer_url, username in streamers:
                stream_data = await check_twitch_live(username)
                if stream_data:
                    # Vérifiez si une annonce a déjà été faite récemment (pour éviter les spams)
                    # Vous pouvez implémenter une logique de cache ou une autre table pour cela
                    await announce_live(guild_id, channel_id, streamer_url, username)
                await asyncio.sleep(60)  # Vérifier toutes les minutes (ajustez selon vos besoins)
        except mysql.connector.Error as err:
            print(f"Erreur de base de données dans le checker Twitch: {err}")
        except Exception as e:
            print(f"Erreur inattendue dans le checker Twitch: {e}")
        await asyncio.sleep(60)

@bot.event
async def on_ready():
    print(f"Bot connecté en tant que {bot.user}")
    bot.loop.create_task(twitch_live_checker())

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.guild is None:
        return  # Ignore les messages des bots et les DM

    guild_id = str(message.guild.id)
    user_id = str(message.author.id)
    now = datetime.now()
    current_month = now.month
    current_year = now.year
    month_name = get_month_name(current_month)
    previous_month = current_month - 1 if current_month > 1 else 12
    previous_year = current_year if current_month > 1 else current_year - 1
    previous_month_name = get_month_name(previous_month)

    try:
        db = connect_db()
        cursor = db.cursor()

        if message.content not in ["!nb_messages", "!top", "!reset", "!help", "!historique", "!add_streamer", "!list_streamers", "!remove_streamer"] and not message.author.id == 310788228368039937:
            # Incrémenter le compteur de messages
            query = """
            INSERT INTO messages (guild_id, user_id, month, year)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE message_count = message_count + 1, updated_at = CURRENT_TIMESTAMP
            """
            values = (guild_id, user_id, current_month, current_year)
            cursor.execute(query, values)
            db.commit()

        # Récupérer le nombre de messages de l'utilisateur pour ce mois
        if message.content == "!nb_messages":
            query = "SELECT message_count FROM messages WHERE guild_id = %s AND user_id = %s AND month = %s AND year = %s"
            values = (guild_id, user_id, current_month, current_year)
            cursor.execute(query, values)
            result = cursor.fetchone()
            message_count = result[0] if result else 0
            await message.channel.send(f"{message.author.mention}, tu as envoyé {message_count} message(s) en {month_name} !")

        # Afficher le top 10 des membres les plus actifs ce mois
        elif message.content == "!top":
            query = """
            SELECT user_id, message_count
            FROM messages
            WHERE guild_id = %s AND month = %s AND year = %s
            ORDER BY message_count DESC
            LIMIT 10
            """
            values = (guild_id, current_month, current_year)
            cursor.execute(query, values)
            top_users = cursor.fetchall()

            if not top_users:
                await message.channel.send(f"Aucune donnée pour {month_name}.")
            else:
                top_message = f"Voici le top 10 des membres les plus actifs en {month_name} :\n"
                for index, (user_id, message_count) in enumerate(top_users):
                    member = message.guild.get_member(int(user_id))
                    user_name = member.display_name if member else "Utilisateur inconnu"
                    top_message += f"{index + 1}. {user_name}: {message_count} messages\n"
                await message.channel.send(top_message)

        # Afficher l'historique du mois précédent
        elif message.content == "!historique":
            query = """
            SELECT user_id, message_count
            FROM message_history
            WHERE guild_id = %s AND month = %s AND year = %s
            ORDER BY message_count DESC
            LIMIT 10
            """
            values = (guild_id, previous_month, previous_year)
            cursor.execute(query, values)
            top_previous = cursor.fetchall()

            if not top_previous:
                await message.channel.send(f"Aucune donnée enregistrée pour {previous_month_name}.")
            else:
                top_message_prev = f"Voici le top 10 des membres les plus actifs en {previous_month_name} :\n"
                for index, (user_id, message_count) in enumerate(top_previous):
                    member = message.guild.get_member(int(user_id))
                    user_name = member.display_name if member else "Utilisateur inconnu"
                    top_message_prev += f"{index + 1}. {user_name}: {message_count} messages\n"
                await message.channel.send(top_message_prev)

        # Réinitialiser les statistiques (nécessite des modifications pour la base de données)
        elif message.content == "!reset" and message.author.guild_permissions.administrator:
            # Déplacer les données actuelles vers l'historique
            insert_history_query = """
            INSERT INTO message_history (guild_id, user_id, message_count, month, year)
            SELECT guild_id, user_id, message_count, month, year
            FROM messages
            WHERE guild_id = %s AND month = %s AND year = %s
            """
            insert_history_values = (guild_id, current_month, current_year)
            cursor.execute(insert_history_query, insert_history_values)

            # Supprimer les données actuelles
            delete_query = "DELETE FROM messages WHERE guild_id = %s AND month = %s AND year = %s"
            delete_values = (guild_id, current_month, current_year)
            cursor.execute(delete_query, delete_values)

            db.commit()
            await message.channel.send("Les statistiques du mois actuel ont été réinitialisées pour ce serveur !")

        elif message.content == "!help":
            help_message = (
                "Voici la liste des commandes disponibles :\n"
                "!nb_messages : Affiche ton nombre de messages du mois\n"
                "!top : Affiche le top 10 des membres les plus actifs\n"
                "!historique : Affiche les scores du mois précédent\n"
                "!add_streamer <url_twitch> <nom_utilisateur_twitch> : Ajoute un streamer à suivre\n"
                "!list_streamers : Liste les streamers suivis\n"
                "!remove_streamer <nom_utilisateur_twitch> : Supprime un streamer suivi\n"
            )
            if message.author.guild_permissions.administrator:
                help_message += "!reset : Réinitialise les statistiques du mois actuel\n"
            await message.channel.send(help_message)

        # Exemple de commande pour ajouter un streamer à suivre
        if message.content.startswith("!add_streamer"):
            parts = message.content.split()
            if len(parts) == 3:
                streamer_url = parts[1]
                username = parts[2]
                if "twitch.tv/" in streamer_url:
                    try:
                        db = connect_db()
                        cursor = db.cursor()
                        query = "INSERT INTO streamers (guild_id, channel_id, streamer_url, username) VALUES (%s, %s, %s, %s)"
                        values = (guild_id, str(message.channel.id), streamer_url, username)
                        cursor.execute(query, values)
                        db.commit()
                        await message.channel.send(f"Streamer {username} ajouté pour les annonces de live.")
                    except mysql.connector.Error as err:
                        await message.channel.send(f"Erreur lors de l'ajout du streamer: {err}")
                    finally:
                        if db.is_connected():
                            cursor.close()
                            db.close()
                else:
                    await message.channel.send("L'URL du streamer doit contenir 'twitch.tv/'.")
            else:
                await message.channel.send("Utilisation: !add_streamer <url_twitch> <nom_utilisateur_twitch>")

        # Exemple de commande pour lister les streamers suivis
        if message.content == "!list_streamers":
            try:
                db = connect_db()
                cursor = db.cursor()
                query = "SELECT username FROM streamers WHERE guild_id = %s"
                cursor.execute(query, (guild_id,))
                streamers = cursor.fetchall()
                db.close()
                if streamers:
                    streamer_list = "\n".join([s[0] for s in streamers])
                    await message.channel.send(f"Streamers suivis sur ce serveur:\n{streamer_list}")
                else:
                    await message.channel.send("Aucun streamer suivi sur ce serveur.")
            except mysql.connector.Error as err:
                await message.channel.send(f"Erreur lors de la récupération des streamers: {err}")
            finally:
                if db.is_connected():
                    cursor.close()
                    db.close()

        # Exemple de commande pour supprimer un streamer suivi
        if message.content.startswith("!remove_streamer"):
            parts = message.content.split()
            if len(parts) == 2:
                username_to_remove = parts[1]
                try:
                    db = connect_db()
                    cursor = db.cursor()
                    query = "DELETE FROM streamers WHERE guild_id = %s AND username = %s"
                    values = (guild_id, username_to_remove)
                    cursor.execute(query, values)
                    db.commit()
                    if cursor.rowcount > 0:
                        await message.channel.send(f"Streamer {username_to_remove} supprimé des annonces.")
                    else:
                        await message.channel.send(f"Le streamer {username_to_remove} n'est pas suivi sur ce serveur.")
                except mysql.connector.Error as err:
                    await message.channel.send(f"Erreur lors de la suppression du streamer: {err}")
                finally:
                    if db.is_connected():
                        cursor.close()
                        db.close()
            else:
                await message.channel.send("Utilisation: !remove_streamer <nom_utilisateur_twitch>")

    except mysql.connector.Error as err:
        print(f"Erreur de base de données: {err}")
    except requests.exceptions.RequestException as twitch_err:
        print(f"Erreur lors de la requête Twitch: {twitch_err}")
    except Exception as e:
        print(f"Erreur inattendue: {e}")
    finally:
        if db and db.is_connected():
            cursor.close()
            db.close()

bot.run(os.getenv("DISCORD_ENV"))