import asyncio
import os
from datetime import datetime

import discord
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.guild_messages = True
intents.members = True

bot = discord.Client(intents=intents)

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")


def connect_db():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
    )


def get_month_name(month_number):
    months = {
        1: "Janvier",
        2: "Février",
        3: "Mars",
        4: "Avril",
        5: "Mai",
        6: "Juin",
        7: "Juillet",
        8: "Août",
        9: "Septembre",
        10: "Octobre",
        11: "Novembre",
        12: "Décembre",
    }
    return months.get(month_number, "Inconnu")


async def monthly_score_backup():
    await bot.wait_until_ready()
    last_checked_month = datetime.now().month

    while not bot.is_closed():
        now = datetime.now()
        current_month = now.month

        if current_month != last_checked_month:
            db = None
            cursor = None
            try:
                db = connect_db()
                cursor = db.cursor()

                insert_query = """
                INSERT INTO message_history (guild_id, user_id, message_count, month, year)
                SELECT guild_id, user_id, message_count, month, year FROM messages
                """
                cursor.execute(insert_query)

                cursor.execute("DELETE FROM messages")
                db.commit()
                print(f"[Sauvegarde mensuelle] Données sauvegardées pour le mois {last_checked_month}.")
                last_checked_month = current_month
            except mysql.connector.Error as err:
                print(f"Erreur lors de la sauvegarde mensuelle des scores : {err}")
            finally:
                if cursor is not None:
                    cursor.close()
                if db is not None and db.is_connected():
                    db.close()

        await asyncio.sleep(3600)


@bot.event
async def on_ready():
    print(f"Bot connecté en tant que {bot.user}")
    bot.loop.create_task(monthly_score_backup())


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.guild is None:
        return

    content = message.content.strip()
    guild_id = str(message.guild.id)
    user_id = str(message.author.id)
    now = datetime.now()
    current_month = now.month
    current_year = now.year
    month_name = get_month_name(current_month)
    previous_month = current_month - 1 if current_month > 1 else 12
    previous_year = current_year if current_month > 1 else current_year - 1
    previous_month_name = get_month_name(previous_month)

    if content == "!help":
        help_message = (
            "Voici la liste des commandes disponibles :\n"
            "!nb_messages : Affiche ton nombre de messages du mois\n"
            "!top : Affiche le top 10 des membres les plus actifs\n"
            "!historique : Affiche les scores du mois précédent\n"
        )
        if message.author.guild_permissions.administrator:
            help_message += "!reset : Réinitialise les statistiques du mois actuel\n"
        await message.channel.send(help_message)
        return

    db = None
    cursor = None
    try:
        db = connect_db()
        cursor = db.cursor()

        if content not in ["!nb_messages", "!top", "!reset", "!historique"] and message.author.id != 310788228368039937:
            query = """
            INSERT INTO messages (guild_id, user_id, month, year)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE message_count = message_count + 1, updated_at = CURRENT_TIMESTAMP
            """
            values = (guild_id, user_id, current_month, current_year)
            cursor.execute(query, values)
            db.commit()

        if message.content == "!nb_messages":
            query = "SELECT message_count FROM messages WHERE guild_id = %s AND user_id = %s AND month = %s AND year = %s"
            values = (guild_id, user_id, current_month, current_year)
            cursor.execute(query, values)
            result = cursor.fetchone()
            message_count = result[0] if result else 0
            await message.channel.send(f"{message.author.mention}, tu as envoyé {message_count} message(s) en {month_name} !")

        elif content == "!top":
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
                for index, (top_user_id, message_count) in enumerate(top_users):
                    member = message.guild.get_member(int(top_user_id))
                    user_name = member.display_name if member else "Utilisateur inconnu"
                    top_message += f"{index + 1}. {user_name}: {message_count} messages\n"
                await message.channel.send(top_message)

        elif content == "!historique":
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
                for index, (top_user_id, message_count) in enumerate(top_previous):
                    member = message.guild.get_member(int(top_user_id))
                    user_name = member.display_name if member else "Utilisateur inconnu"
                    top_message_prev += f"{index + 1}. {user_name}: {message_count} messages\n"
                await message.channel.send(top_message_prev)

        elif content == "!reset" and message.author.guild_permissions.administrator:
            insert_history_query = """
            INSERT INTO message_history (guild_id, user_id, message_count, month, year)
            SELECT guild_id, user_id, message_count, month, year
            FROM messages
            WHERE guild_id = %s AND month = %s AND year = %s
            """
            insert_history_values = (guild_id, current_month, current_year)
            cursor.execute(insert_history_query, insert_history_values)

            delete_query = "DELETE FROM messages WHERE guild_id = %s AND month = %s AND year = %s"
            delete_values = (guild_id, current_month, current_year)
            cursor.execute(delete_query, delete_values)

            db.commit()
            await message.channel.send("Les statistiques du mois actuel ont été réinitialisées pour ce serveur !")

    except mysql.connector.Error as err:
        print(f"Erreur de base de données: {err}")
    except Exception as e:
        print(f"Erreur inattendue: {e}")
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None and db.is_connected():
            db.close()


discord_token = os.getenv("DISCORD_TOKEN") or os.getenv("DISCORD_ENV")

if not discord_token:
    raise RuntimeError("Missing Discord token. Set DISCORD_TOKEN (preferred) or DISCORD_ENV.")

bot.run(discord_token)
