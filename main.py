import asyncio
import discord
from discord.ext import commands
import requests
import os
import configparser
from datetime import datetime

config = configparser.ConfigParser()

# Ensure config file exists
if not os.path.exists('config.ini'):
    config['Discord'] = {
        'token': 'token_de_votre_bot',
        'channel_id': 'id_du_salon_dinfos',
        'alert_channel_id': 'id_du_salon_dalertes'
    }
    config['Pterodactyl'] = {
        'api_url': 'url_du_panel',
        'api_key': 'clé_dapi_du_panel',
        'server_ids': 'identifiant_des_serveurs_séparés_par_une_virgule'
    }
    config['Settings'] = {
        'refresh_interval': '300 #par défaut la valeur est à 300 secondes (5 minutes)',
        'note': 'Please delete all :)'
    }
    with open('config.ini', 'w') as configfile:
        config.write(configfile)
else:
    config.read('config.ini')

TOKEN = config['Discord']['token']
DISCORD_CHANNEL_ID = int(config['Discord']['channel_id'])
ALERT_CHANNEL_ID = int(config['Discord']['alert_channel_id'])  # Vérifier l'id du salon d'alertes dans la config

PTERODACTYL_API_URL = config['Pterodactyl']['api_url']
PTERODACTYL_API_KEY = config['Pterodactyl']['api_key']
SERVER_IDS = config['Pterodactyl']['server_ids'].split(',')  # séparer les ID de serveurs

refresh_interval = config['Settings']['refresh_interval']

intents = discord.Intents.default()
intents.typing = False
intents.presences = False
intents.members = False

bot = commands.Bot(command_prefix='/', intents=intents)


async def fetch_server_stats(server_id):
    url = f"{PTERODACTYL_API_URL}/api/client/servers/{server_id}/resources"
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {PTERODACTYL_API_KEY}'
    }
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            print(f"Successfully fetched data for server ID: {server_id}")
            return response.json()['attributes']  # Retourner les valeurs des stats de serveur
        else:
            print(f"❎ Échec de l'extraction des données pour l'ID du serveur: {server_id}. Status code: {response.status_code}")
            return None
    except Exception as e:
        print(f"❎ Erreur dans l'extraction des données pour l'ID du serveur: {server_id}. Exception: {e}")
        return None


async def fetch_server_info(server_id):
    url = f"{PTERODACTYL_API_URL}/api/client/servers/{server_id}"
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {PTERODACTYL_API_KEY}'
    }
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            print(f"✅ Les informations relatives à l'ID du serveur ont été récupérées avec succès: {server_id}")
            attributes = response.json().get('attributes')
            if attributes:
                return attributes.get('name')  # Retourner le nom du serveur
            else:
                print(f"❎ Attributs non trouvés pour l'ID du serveur: {server_id}")
                return None
        else:
            print(f"❎ Échec de la recherche d'informations pour l'ID du serveur: {server_id}. Code d'érreur: {response.status_code}")
            return None
    except Exception as e:
        print(f"❎ Erreur dans la recherche d'informations sur l'ID du serveur: {server_id}. Exception: {e}")
        return None


async def update_status():
    await asyncio.sleep(5)  # Mise en veille initiale pour s'assurer que le robot est prêt

    channel = bot.get_channel(DISCORD_CHANNEL_ID)
    alert_channel = bot.get_channel(ALERT_CHANNEL_ID)  # Récupérer le salon d'alertes

    previous_messages = load_previous_messages()
    servers_down = {}  # Modification de l'heure de début du temps d'arrêt du store
    counter = 0

    while True:
        try:
            for server_id in SERVER_IDS:
                server_stats = await fetch_server_stats(server_id)
                server_name = await fetch_server_info(server_id)

                if server_stats and server_name:
                    online_status = "🟢 Online" if server_stats['current_state'] == "running" else "🔴 Offline"
                    color = 0x00ff00 if server_stats['current_state'] == "running" else 0xff0000
                    cpu_usage = server_stats['resources']['cpu_absolute']
                    ram_usage = round(server_stats['resources']['memory_bytes'] / (1024 * 1024),
                                      2)  # Arrondir à 2 décimales et convertir en MB
                    disk_usage = round(server_stats['resources']['disk_bytes'] / (1024 * 1024),
                                       2)  #  Arrondir à 2 décimales et convertir en MB

                    embed_description = f"Server: {server_name}\nStatus: {online_status}\nDisk Usage: {disk_usage} MB\nCPU Usage: {cpu_usage}%\nRAM Usage: {ram_usage} MB\nCredits: Made with love by Wrexik"

                    if server_stats['current_state'] != "running":
                        if server_id not in servers_down:
                            async with channel.typing():  # Insiquer que le bot écrit
                                servers_down[server_id] = datetime.now()  # Enregistrement du temps de fonctionnement
                                alert_delay = int(refresh_interval) * 5
                                info = f"Server {server_name} down! Another alert in {alert_delay} seconds!"
                                log = f"[{datetime.now()}]: {info}"
                                add_to_log(log)
                                await alert_channel.send(log) 

                    if server_id in previous_messages:
                        message_id = previous_messages[server_id]
                        async with channel.typing(): 
                            message = await channel.fetch_message(message_id)
                            embed = discord.Embed(title='Server Status', description=embed_description, color=color)
                            await message.edit(embed=embed)
                    else: 
                        async with channel.typing(): 
                            embed = discord.Embed(title='Server Status', description=embed_description, color=color)
                            message = await channel.send(embed=embed)
                            previous_messages[server_id] = message.id
                            save_previous_messages(previous_messages)
                else:
                    print(f"❎ Aucune donnée récupérée pour l'ID du serveur: {server_id}")

            counter += 1
            if counter >= 5:
                servers_down.clear()
                counter = 0

        except Exception as e:
            print(f'❎ Erreur lors de la mise à jour du status: {e}')

        await asyncio.sleep(int(refresh_interval))


def load_previous_messages():
    previous_messages = {}
    if os.path.exists("message_ids.txt"):
        with open("message_ids.txt", 'r') as file:
            lines = file.readlines()
            for line in lines:
                server_id, message_id = line.strip().split(',')
                previous_messages[server_id] = int(message_id)
    return previous_messages


def save_previous_messages(previous_messages):
    with open("message_ids.txt", 'w') as file:
        for server_id, message_id in previous_messages.items():
            file.write(f"{server_id},{message_id}\n")

def add_to_log(text):
    # Get the current date
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    # Construct the log file name
    log_file_name = f"log_{current_date}.txt"
    
    # Check if the log file exists, create it if not
    if not os.path.exists(log_file_name):
        print(f"Création du fichier de logs: {log_file_name}")
        with open(log_file_name, "w") as log_file:
            log_file.write(f"{datetime.now()} - Log file created\n")
    
    # Append the log message to the file
    with open(log_file_name, "a") as log_file:
        log_file.write(f"{text}\n")
        log_file.flush()  # Ensure immediate write to file
        print(f"Ajouté aux logs: {text}")


@bot.event
async def on_ready():
    print(f'🤖 Connecté en tant que {bot.user}')
    asyncio.create_task(update_status())

bot.run(TOKEN)