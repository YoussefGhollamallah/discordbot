import discord
import os
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Charger les intents
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

bot = discord.Client(intents=intents)

ANNONCE_CHANNEL = int(os.getenv("ANNONCE_CHANNEL"))

MESSAGE_FILE = "message_count.json"

# Fonction pour obtenir le mois en toutes lettres
def get_month_name(month_number):
    months = {
        1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril",
        5: "Mai", 6: "Juin", 7: "Juillet", 8: "Août",
        9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"
    }
    return months.get(month_number, "Inconnu")

# Fonction pour charger les données depuis le fichier JSON
def load_message_data():
    if not os.path.exists(MESSAGE_FILE):
        return {"guilds": {}}
    with open(MESSAGE_FILE, "r", encoding="utf-8") as file:
        return json.load(file)

# Fonction pour sauvegarder les données dans le fichier JSON
def save_message_data(data):
    with open(MESSAGE_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)

@bot.event
async def on_ready():
    print(f"Bot connecté en tant que {bot.user}")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.guild is None:
        return  # Ignore les messages des bots et les DM

    # Charger les données du fichier
    data = load_message_data()
    guild_id = str(message.guild.id)  # Stocker en tant que string
    current_month = datetime.now().month
    month_name = get_month_name(current_month)

    # Initialiser la structure pour le serveur si elle n'existe pas
    if guild_id not in data["guilds"]:
        data["guilds"][guild_id] = {"users": {}, "month": current_month}

    # Vérifier si on doit réinitialiser le compteur pour ce serveur
    if data["guilds"][guild_id]["month"] != current_month:
        data["guilds"][guild_id] = {"users": {}, "month": current_month}

    # Mettre à jour le nombre de messages de l'utilisateur
    user_id = str(message.author.id)
    if message.content not in ["!nb_messages", "!top", "!reset", "!help"] and not message.author.id == 310788228368039937:
        data["guilds"][guild_id]["users"][user_id] = data["guilds"][guild_id]["users"].get(user_id, 0) + 1

    # Sauvegarder les données
    save_message_data(data)

    # Récupérer le nombre de messages envoyés par l'utilisateur
    message_count = data["guilds"][guild_id]["users"].get(user_id, 0)

    # Traiter les commandes
    if message.content == "!help":
        help_message = (
            "Voici la liste des commandes disponibles :\n"
            "!nb_messages : Affiche ton nombre de messages du mois\n"
            "!top : Affiche le top 10 des membres les plus actifs\n"
        )
        if message.author.guild_permissions.administrator:
            help_message += "!reset : Réinitialise les statistiques\n"
        await message.channel.send(help_message)

    if message.content == "!nb_messages":
        await message.channel.send(f"{message.author.mention}, tu as envoyé {message_count} message(s) en {month_name} !")

    if message.content == "!top" or datetime.now().day == 1:
        top_users = sorted(data["guilds"][guild_id]["users"].items(), key=lambda x: x[1], reverse=True)
        if not top_users:
            await message.channel.send("Aucune donnée pour ce mois.")
            return

        top_message = "\n".join([f"{index + 1}. <@{user_id}>: {message_count} messages" for index, (user_id, message_count) in enumerate(top_users[:10])])
        await message.channel.send(f"Voici le top 10 des membres les plus actifs en {month_name} :\n{top_message}")

    if message.content == "!reset" and message.author.guild_permissions.administrator:
        data["guilds"][guild_id]["users"] = {}
        save_message_data(data)
        await message.channel.send("Les statistiques ont été réinitialisées pour ce serveur !")

bot.run(os.getenv("DISCORD_ENV"))
