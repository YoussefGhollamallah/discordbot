import discord
import os
import json
import asyncio
from datetime import datetime
from discord.ext import tasks
from dotenv import load_dotenv

load_dotenv()

# Activer les intents
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True  # Pour récupérer les salons
intents.members = True  # Pour mentionner les utilisateurs

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

# Charger les données du fichier JSON
def load_message_data():
    if not os.path.exists(MESSAGE_FILE):
        return {"users": {}, "month": datetime.now().month}
    with open(MESSAGE_FILE, "r", encoding="utf-8") as file:
        return json.load(file)

# Sauvegarder les données
def save_message_data(data):
    with open(MESSAGE_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)

# Tâche pour envoyer le top 10 tous les 1ers du mois
@tasks.loop(hours=24)  # Vérifie une fois par jour
async def monthly_top():
    now = datetime.now()
    if now.day != 1:
        return  # Ne s'exécute que le 1er du mois

    await bot.wait_until_ready()
    guild = discord.utils.get(bot.guilds)  # Récupère le serveur
    channel = bot.get_channel(ANNONCE_CHANNEL)

    if channel is None:
        print("⚠️ Salon d'annonce introuvable ! Vérifie ANNOUNCE_CHANNEL dans .env")
        return

    data = load_message_data()
    month_name = get_month_name(now.month - 1)  # Mois précédent

    if not data["users"]:
        await channel.send(f"📢 Le top 10 de {month_name} est vide, aucun message n'a été enregistré !")
        return

    # Trier les utilisateurs par nombre de messages
    top_users = sorted(data["users"].items(), key=lambda x: x[1], reverse=True)[:10]

    top_message = "\n".join([f"**{index + 1}. <@{user_id}>** - {count} messages"
                              for index, (user_id, count) in enumerate(top_users)])

    await channel.send(f"🏆 **Top 10 des membres les plus actifs de {month_name} :**\n{top_message}")

    # Réinitialisation pour le nouveau mois
    data["users"] = {}
    data["month"] = now.month
    save_message_data(data)
    print(f"✅ Top 10 de {month_name} envoyé et stats réinitialisées.")

@bot.event
async def on_ready():
    print(f"Bot connecté en tant que {bot.user}")
    monthly_top.start()  # Démarrer la tâche de top mensuel

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return  # Ignore les bots

    data = load_message_data()
    current_month = datetime.now().month
    month_name = get_month_name(current_month)

    # Réinitialisation automatique si changement de mois
    if data["month"] != current_month:
        data = {"users": {}, "month": current_month}

    user_id = str(message.author.id)
    if message.content not in ["!nb_messages", "!top", "!reset"]:
        data["users"][user_id] = data["users"].get(user_id, 0) + 1

    save_message_data(data)

    # Commandes
    if message.content == "!help":
        help_message = ("📌 **Commandes disponibles :**\n"
                        "🔹 `!nb_messages` - Voir ton nombre de messages\n"
                        "🔹 `!top` - Voir le top 10 des membres\n")
        if message.author.guild_permissions.administrator:
            help_message += "🔹 `!reset` - Réinitialiser les stats (Admin)\n"
        await message.channel.send(help_message)

    elif message.content == "!nb_messages":
        await message.channel.send(f"{message.author.mention}, tu as envoyé {data['users'].get(user_id, 0)} messages en {month_name} !")

    elif message.content == "!top":
        top_users = sorted(data["users"].items(), key=lambda x: x[1], reverse=True)[:10]
        if not top_users:
            await message.channel.send("Aucun message enregistré ce mois-ci !")
            return
        top_message = "\n".join([f"**{index + 1}. <@{user_id}>** - {count} messages"
                                  for index, (user_id, count) in enumerate(top_users)])
        await message.channel.send(f"🏆 **Top 10 des membres les plus actifs de {month_name} :**\n{top_message}")

    elif message.content == "!reset" and message.author.guild_permissions.administrator:
        data["users"] = {}
        save_message_data(data)
        await message.channel.send("✅ Statistiques réinitialisées !")

bot.run(os.getenv("DISCORD_ENV"))
