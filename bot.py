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

# Fichier de stockage des messages
MESSAGE_FILE = "message_count.json"

# Fonction pour obtenir le mois en toutes lettres (ex: "Janvier")
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
        return {"users": {}, "month": datetime.now().month}
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
    if message.author.bot:
        return  # Ignore les messages des bots

    # Charger les données du fichier
    data = load_message_data()
    current_month = datetime.now().month
    month_name = get_month_name(current_month)  # Récupérer le nom du mois

    # Vérifier si on doit réinitialiser le compteur
    if data["month"] != current_month:
        data = {"users": {}, "month": current_month}

    # Mettre à jour le nombre de messages de l'utilisateur
    user_id = str(message.author.id)  # Stocker en tant que string pour JSON
    data["users"][user_id] = data["users"].get(user_id, 0) + 1

    # Sauvegarder les données
    save_message_data(data)

    # Récupérer le nombre de messages envoyés par l'utilisateur
    message_count = data["users"][user_id]

    if message.content == "!nb_messages" or message.content == "!nb_messages":
        await message.channel.send(f"{message.author.mention}, tu as envoyé {message_count} message(s) au mois de {month_name} !")

    if message.content == "!top":
        top_users = sorted(data["users"].items(), key=lambda x: x[1], reverse=True)
        top_message = "\n".join([f"{index + 1}. <@{user_id}>: {message_count} messages" for index, (user_id, message_count) in enumerate(top_users[:5])])
        await message.channel.send(f"Voici le top 5 des membres les plus actifs au mois de {month_name}:\n{top_message}")

    if message.content == "!reset" and message.author.guild_permissions.administrator:
        data["users"] = {}
        save_message_data(data)
        await message.channel.send("Les statistiques ont été réinitialisées !")

    if message.content == "!clear10" and message.author.guild_permissions.administrator:
        await message.channel.purge(limit=10)
        await message.channel.send("Le chat a été nettoyé des 10 dernier messages !")

bot.run(os.getenv("DISCORD_ENV"))
