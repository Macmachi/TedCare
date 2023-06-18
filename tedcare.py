'''
### INFOS PROJET ####
# Nom du projet : TedCare   
# Auteur du projet et du code : Arnaud Ricci
# Version 1.0.0
### PRÉREQUIS & DOCUMENTATION ####
* Installer FFmpeg sur l'ordinateur pour Azure speech et la conversion des audios telegram (avoir une voix système FR installé pour pyttsx3 qui sert pour le debug)
* Nouvelle fonctionnalité de GPT4 (14.06.2023) : https://github.com/openai/openai-cookbook/blob/main/examples/How_to_call_functions_with_chat_models.ipynb 
### FONCTIONNALITÉS A IMPLEMÉNTER ####
* None 
### FONCTIONNALITÉS NICE-TO-HAVE ####
* Voir Diagramme V2 dans Figjam !
'''
# Bibliothèques aiogram pour Telegram
from aiogram import Bot, types, Dispatcher, executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
# Bibliothèque de reconnaissance vocale 
import speech_recognition as sr
# Pour la gestion de l'IA d'OPENAI (GPT4) - Payante
import openai
# Bibliothèque Python pour la synthèse vocale (Gratuite)
import pyttsx3
# Bibliothèque pour la gestion des mémoires avec des fichiers json 
import json
# Pour avoir la date et l'heure notamment pour les logs
from datetime import datetime
# Pour les expressions régulières
import re
# Bibliotèque pour la synthèse vocal Azure (synthèse vocale dernière génération - Payante)
import azure.cognitiveservices.speech as speechsdk
# Bibliotèque pour générer des PDFs
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
# Bibliotèque pour convertir les fichiers audios ogg de Telegram pour les utiliser avec la reconnaissance vocale
from pydub import AudioSegment
# Bibliotèque pour les expressions régulières utilisées pour la génération du PDF
import re
# Bibliotèque pour les interagir avec les fichiers sur le système
import os 
# Gérer les clés APIs et paramètres à l'extérieur du fichier python dans un fichier config.ini
import configparser

# Créer un objet ConfigParser pour gérer les clés d'API et paramètres en dehors du fichier python
config = configparser.ConfigParser()

### Récupération des informations du fichier config.INI ###
# Lire le fichier ini
config.read('config.ini')
# Définition du Token Telegram
telegram_token = config['TELEGRAM_BOT']['TelegramBot']
# Définition et configuration des clés d'API tierces(OpenAI, Azure Speech)
openai_api_key = config['OPEN_AI']['OpenAI']
azure_subscription = config['AZURE_SPEECH']['Subscription']
azure_region = config['AZURE_SPEECH']['Region']
# Configuration de la longueur de la mémoire court-terme
MAX_HISTORY_MESSAGES = int(config['SETTINGS']['MaxHistoryMessages'])
# Configuration du modèle de langage GPT4
MAX_TOKENS = int(config['MODEL_CONFIG']['MaxTokens'])
N = int(config['MODEL_CONFIG']['N'])
TEMPERATURE = float(config['MODEL_CONFIG']['Temperature'])
### Fin de la Récupération des informations du fichier config.INI ###

# Initialisation d'OpenAI avec ce qu'on a récupéré dans le fichier config.ini
openai.api_key = openai_api_key  

# On définit une session pour garantir des sessions privés pour chaque utilisateur au niveau des messages sur Telegram
class UserSession:
    def __init__(self):
        # Initialise la variable conversation_history comme une liste vide pour stocker l'historique des conversations.
        self.conversation_history = []
        # Initialise la variable questionnaire_status comme un dictionnaire avec deux clés : 'answers' (une liste vide)
        # et 'current_question' (la valeur initiale est 0) pour suivre l'état du questionnaire.
        self.questionnaire_status = {
            'answers': [],
            'current_question': 0
        }
        # Initialise la variable vocal_system_enabled à True pour indiquer que le système vocal est activé par défaut.
        self.vocal_system_enabled = True  

# Permet de stocker nos sessions mais est reset à chaque redémarrage car pas sauvegardé dans une base de données.
sessions = {}
# Initialise le stockage en mémoire.
storage = MemoryStorage()
# Crée une instance du bot en utilisant le jeton Telegram fourni.
bot = Bot(telegram_token)
# Crée un gestionnaire de dispatcher en utilisant le bot et le stockage spécifié.
dp = Dispatcher(bot, storage=storage)
# Initialise l'identifiant de discussion à la valeur null.
chat_id = None

# Attention cela ne semble plus être utilisé par le code depuis l'instauration des sessions Telegram mais garder quand même (au cas ou)
# Essaie d'ouvrir le fichier 'chat_ids.json' en mode lecture.
# Si le fichier existe, charge les données JSON dans la variable chat_ids.
# Si le fichier n'existe pas, initialise chat_ids comme une liste vide
try:
    with open('chat_ids.json', 'r') as file:
        chat_ids = json.load(file)
except FileNotFoundError:
    chat_ids = []

# Liste python pour stocker nos questions pour le questionnaire PSS-10
questions = [
    "1. Au cours du dernier mois, dans quelle mesure avez-vous eu l'impression que les choses échappaient à votre contrôle ?",
    "2. Au cours du dernier mois, vous êtes-vous senti nerveux ou stressé ?",
    "3. Au cours du dernier mois, dans quelle mesure avez-vous réussi à gérer les problèmes importants de votre vie ?",
    "4. Au cours du dernier mois, avez-vous estimé que vous ne pouviez pas faire face à toutes les choses que vous aviez à faire ?",
    "5. Au cours du dernier mois, avez-vous ressenti de la confiance en votre capacité à gérer vos problèmes personnels ?",
    "6. Au cours du dernier mois, avez-vous senti que les choses allaient comme vous le vouliez ?",
    "7. Au cours du dernier mois, avez-vous été en mesure de contrôler les irritations dans votre vie ?",
    "8. Au cours du dernier mois, avez-vous trouvé que vous aviez raisonnablement bien géré les changements importants qui ont eu lieu dans votre vie ?",
    "9. Au cours du dernier mois, avez-vous été contrarié par des événements imprévus ?",
    "10. Au cours du dernier mois, avez-vous estimé que les difficultés s'accumulaient au point que vous ne pouviez pas les surmonter ?",
]
# ATTENTION ! Si les termes ici sont changées il faut les changer aussi dans les gestionnaires de callbacks !!!
# Définition des choix possibles
choices = ["Jamais", "Presque jamais", "Parfois", "Assez souvent", "Très souvent"]
# Statut du questionnaire de l'utilisateur (initialisé comme un dictionnaire vide)
user_questionnaire_status = {}
# Création du clavier en ligne avec des boutons pour les options radios
radios = ['Évaluer son stress (PSS-10)', 'Poser une question en lien avec le stress', 'Demander des conseils en lien avec son stress', 'Paramètres']
keyboard = InlineKeyboardMarkup(row_width=1)
keyboard.add(*[InlineKeyboardButton(text=radio, callback_data=radio) for radio in radios])  # type: ignore
# Création du clavier en ligne avec des boutons pour les options de choix
choice_keyboard = InlineKeyboardMarkup(row_width=1)
choice_keyboard.add(*[InlineKeyboardButton(text=choice, callback_data=f"choice:{choice}") for choice in choices]) # type: ignore
# Options médicales possibles
medical_options = ['Continuer à discuter', 'Retourner au menu principal']
medical_keyboard = InlineKeyboardMarkup(row_width=1)
medical_keyboard.add(*[InlineKeyboardButton(text=option, callback_data=option) for option in medical_options]) # type: ignore
# Options de paramètres possibles
parameter_options = ['Désactiver/Activer le système vocal', 'Réinitialiser la mémoire court terme', 'Retourner au menu principal']
parameter_keyboard = InlineKeyboardMarkup(row_width=1)
parameter_keyboard.add(*[InlineKeyboardButton(text=option, callback_data=option) for option in parameter_options]) # type: ignore

# La fonction create_choice_keyboard() crée un clavier d'options pour les utilisateurs. 
def create_choice_keyboard():
    choice_keyboard = InlineKeyboardMarkup(row_width=1)
    choice_keyboard.add(*[InlineKeyboardButton(text=choice, callback_data=f"choice:{choice}") for choice in choices]) # type: ignore
    return choice_keyboard    

# Gérer les différents états d'un bot conversationnel
class Form(StatesGroup):
    # état d'attente d'une question de l'utilisateur
    waiting_for_question = State()  

# Fonction qui définit ce qu'il se passe quand on /start le bot
async def start(message: types.Message):
    global chat_id
    chat_id = message.chat.id
    # Récupéré pour speak_text
    user_id = message.from_user.id
    # Vérifier si une session utilisateur existe déjà, sinon en créer une nouvelle
    if user_id not in sessions:
        sessions[user_id] = UserSession()
    # On envoit le message du bot lors du start
    await bot.send_message(chat_id=message.chat.id, text="Salut, c'est Ted l'ourson en peluche ! Je suis là pour te donner un coup de patte avec la gestion du stress. Comment puis-je faire pour t'aider, mon ami ?", reply_markup=keyboard)
    #DEBUG avec la lecture des options du menu (non nécessaire)
    #speak_text(user_id, "Salut, c'est Ted l'ourson en peluche ! Je suis là pour te donner un coup de patte avec la gestion du stress. Comment puis-je faire pour t'aider, mon ami ? Voici vos options: " + ', '.join(radios))
    speak_text(user_id, "Salut, c'est Ted l'ourson en peluche ! Je suis là pour te donner un coup de patte avec la gestion du stress. Comment puis-je faire pour t'aider, mon ami ?")

# Enregistrement de la fonction `start` en tant que gestionnaire pour la commande /start
dp.register_message_handler(start, commands=['start'])

# Gestionnaire pour la requête de callback concernant le PSS-10
@dp.callback_query_handler(text="Évaluer son stress (PSS-10)")
async def evaluate_stress_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    await bot.delete_message(chat_id=callback_query.from_user.id, message_id=callback_query.message.message_id)
    selected_radio = callback_query.data
    await bot.send_message(chat_id=callback_query.from_user.id, text=f"Vous avez sélectionné : [{selected_radio}]")
    speak_text(user_id, f"Vous avez sélectionné {selected_radio}")
    # On réinitialise sa mémoire
    reset_memory(user_id)
    user_questionnaire_status[callback_query.from_user.id] = {
        'current_question': 0,
        'answers': []
    }
    await bot.send_message(chat_id=callback_query.from_user.id, text=questions[0], reply_markup=choice_keyboard)

# Gestionnaire pour la requête de callback concernant une question en lien avec le stress
@dp.callback_query_handler(text="Poser une question en lien avec le stress")
async def ask_question_handler(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    await bot.delete_message(chat_id=callback_query.from_user.id, message_id=callback_query.message.message_id)
    selected_radio = callback_query.data
    await bot.send_message(chat_id=callback_query.from_user.id, text=f"Vous avez sélectionné : [{selected_radio}]\nVeuillez saisir votre question maintenant.")
    speak_text(user_id, f"Vous avez sélectionné {selected_radio}. Veuillez saisir votre question maintenant.")
    # On réinitialise sa mémoire
    reset_memory(user_id)
    await state.set_data({"origin": "question"})
    await Form.waiting_for_question.set()

# Gestionnaire pour la requête de callback concernant des conseils avec son stress
@dp.callback_query_handler(text="Demander des conseils en lien avec son stress")
async def ask_advice_handler(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    await bot.delete_message(chat_id=user_id, message_id=callback_query.message.message_id)
    selected_radio = callback_query.data
    await bot.send_message(chat_id=user_id, text=f"Vous avez sélectionné : [{selected_radio}]\nVeuillez saisir votre question maintenant.")
    speak_text(user_id, f"Vous avez sélectionné {selected_radio}. Veuillez saisir votre question maintenant.")
    # On réinitialise sa mémoire
    reset_memory(user_id)
    await state.set_data({"origin": "advice"})
    await Form.waiting_for_question.set()  

# Gestionnaire pour la requête de callback concernant les paramètres
@dp.callback_query_handler(text="Paramètres")
async def ask_parameter_handler(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    await bot.delete_message(chat_id=callback_query.from_user.id, message_id=callback_query.message.message_id)
    selected_radio = callback_query.data
    await bot.send_message(chat_id=callback_query.from_user.id, text=f"Vous avez sélectionné : [{selected_radio}]\nVeuillez saisir une option ou retourner au menu.", reply_markup=parameter_keyboard)
    speak_text(user_id, f"Vous avez sélectionné {selected_radio}. Veuillez saisir une option ou retourner au menu.")

# Gestionnaire pour la requête de callback concernant le reset de la mémoire court terme
@dp.callback_query_handler(text="Réinitialiser la mémoire court terme")
async def ask_reset_handler(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    await bot.delete_message(chat_id=callback_query.from_user.id, message_id=callback_query.message.message_id)
    reset_memory(user_id)
    await bot.send_message(chat_id=callback_query.from_user.id, text="Mémoire court terme réinitialisée avec succès")
    await bot.send_message(chat_id=callback_query.from_user.id, text="Choisis une option:", reply_markup=keyboard)

# Gestionnaire pour la requête de callback concernant l'activation ou non de la synthèse vocale
@dp.callback_query_handler(text="Désactiver/Activer le système vocal")
async def ask_speakoption_handler(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    session = sessions[user_id]
    session.vocal_system_enabled = not session.vocal_system_enabled  # bascule entre True et False
    await bot.delete_message(chat_id=callback_query.from_user.id, message_id=callback_query.message.message_id)
    if session.vocal_system_enabled:
        await bot.send_message(chat_id=user_id, text="Le système vocal a été activé.")
    else:
        await bot.send_message(chat_id=user_id, text="Le système vocal a été désactivé.")
    await bot.send_message(chat_id=user_id, text="Choisis une option:", reply_markup=keyboard)  

# Gestionnaire de message qui attend une entrée utilisateur sous forme de texte ou de voix, puis effectue différentes actions en fonction du type de contenu.
@dp.message_handler(state=Form.waiting_for_question, content_types=['text', 'voice'])
async def get_user_input(message: types.Message, state: FSMContext):
    user_input=None
    if message.content_type == 'text':
        user_input = message.text
        # Traitement du texte ici
    elif message.content_type == 'voice':
        await bot.download_file_by_id(
            message.voice.file_id, 
            destination='temp_voice.ogg'
        )
        # Convertir le fichier ogg en wav
        ogg_audio = AudioSegment.from_ogg("temp_voice.ogg")
        ogg_audio.export("temp_voice.wav", format="wav")
        try:
            os.remove('temp_voice.ogg')
        except OSError as e:
            print(f"Error: {e.filename} - {e.strerror}.")

        # Convertir l'audio en texte
        r = sr.Recognizer()
        try:
            with sr.AudioFile('temp_voice.wav') as source:
                audio_data = r.record(source)
                user_input = r.recognize_google(audio_data, language="fr-FR")
                #DEBUG
                print(f"user_input : {user_input}")
        except sr.UnknownValueError:
            print("La reconnaissance vocale de Google n'a pas pu comprendre l'audio.")
        except sr.RequestError as e:
            print("Impossible de demander les résultats du service de reconnaissance vocale de Google.; {0}".format(e))
        try:
            os.remove('temp_voice.wav')
        except OSError as e:
            print(f"Error: {e.filename} - {e.strerror}.")

    if user_input is None or user_input.strip() == "": # type: ignore
        # Demander à l'utilisateur d'envoyer un message à nouveau
        await message.reply("Veuillez envoyer un message ou un enregistrement vocal valide.")
        # Remettre l'utilisateur dans l'état d'attente d'une question
        await Form.waiting_for_question.set()
    else:
        # Avant finish sinon mémoire state rénitialisée !
        user_data = await state.get_data()
        await state.finish()
        # Debug
        print(f"user_data : {user_data}")
        if user_data.get("origin") == "question":
            await execute_medical_mode(user_input, message.chat.id)
        elif user_data.get("origin") == "advice":
            await execute_advice_mode(user_input, message.chat.id) 

# Cette fonction gère les actions à effectuer lorsque l'utilisateur sélectionne une option dans le clavier d'options quand il a le questionnaire PSS-10 lancé.
@dp.callback_query_handler(lambda c: c.data.startswith("choice:"))
async def choice_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    if user_id not in sessions:
        sessions[user_id] = UserSession()
    session = sessions[user_id]

    await bot.delete_message(chat_id=user_id, message_id=callback_query.message.message_id)

    session.questionnaire_status['answers'].append(callback_query.data.split(':')[1])
    session.questionnaire_status['current_question'] += 1

    if session.questionnaire_status['current_question'] >= len(questions):
        total_score = calculate_score(session.questionnaire_status['answers'])
        
        await bot.send_message(chat_id=user_id, text=f"Je suis en train d'analyser le score de ton questionnaire PSS-10 qui est de {total_score}.")
        speak_text(user_id, f"Je suis en train d'analyser le score de ton questionnaire PSS-10 qui est de {total_score}.")
        
        prompt = f"Mon score total au questionnaire PSS-10 est {total_score}. Quelle est ton analyse ?"
        system_message = f"En tant qu'expert psychologue, tu as pour tâche d'analyser mon score de {total_score} obtenue au PSS-10. Je souhaite que tu me fournisses une évaluation précise et claire. Sur la base de cette évaluation, indique-moi si une consultation avec un psychologue serait conseillée. Il n'est pas nécessaire de détailler ce qu'est le questionnaire PSS-10."
        
        long_term_memory = load_long_term_memory()
        # Non utilisé car directement récupéré depuis ma fonction get_response
        #conversation_history = session.conversation_history
        analysis_response = await get_response(prompt, session=session, system_message=system_message, chat_id=user_id, long_term_memory=long_term_memory, include_history=True)
        
        #DEBUG
        print("IA analyse:", analysis_response)
        
        session.conversation_history.append({"role": "user", "content": prompt})
        session.conversation_history.append({"role": "assistant", "content": analysis_response})
        
        save_conversation_history(session.conversation_history, user_id)

        if len(session.conversation_history) > MAX_HISTORY_MESSAGES * 2:
            session.conversation_history = session.conversation_history[-MAX_HISTORY_MESSAGES * 2:]

        session.questionnaire_status = {
            'answers': [],
            'current_question': 0
        }
        await bot.send_message(chat_id=user_id, text="Choisis une option:", reply_markup=keyboard)
    else:
        next_question = session.questionnaire_status['current_question']
        await bot.send_message(chat_id=user_id, text=questions[next_question], reply_markup=create_choice_keyboard())

# Cette fonction gère les actions à effectuer lorsque l'utilisateur a posé sa question en lien avec le stress, il peut continuer à converser s'il le souhaite.
@dp.callback_query_handler(lambda c: c.data == 'Continuer à discuter')
async def continue_discussion(callback_query: types.CallbackQuery, state: FSMContext):
    # Supprimer le message précédent
    await bot.delete_message(chat_id=callback_query.from_user.id, message_id=callback_query.message.message_id)
    # Demander à l'utilisateur de fournir une nouvelle entrée
    await bot.send_message(chat_id=callback_query.from_user.id, text="Veuillez entrer votre nouveau message:")
    # speak_text(f"Veuillez entrer votre nouveau message:") # je ne suis pas sûr de ce que fait cette ligne
    await state.set_data({"origin": "question"})
    await Form.waiting_for_question.set()

# Cette fonction gère l'action de retour au menu principal sur telegram (clavier principal du coup)
@dp.callback_query_handler(lambda c: c.data == 'Retourner au menu principal')
async def return_to_main_menu(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    # Supprimer le message précédent
    await bot.delete_message(chat_id=callback_query.from_user.id, message_id=callback_query.message.message_id)
    # Renvoyer l'utilisateur au menu principal
    await bot.send_message(chat_id=callback_query.from_user.id, text="Choisis une option:", reply_markup=keyboard)
    speak_text(user_id, f"Choisis une option:")

# Cette fonction gère le mode médical où l'assistant joue le rôle d'un assistant psychologue empathique spécialisé dans la gestion du stress et donne des conseils NON élaborés
async def execute_medical_mode(user_input, user_id):
    if user_id not in sessions:
        sessions[user_id] = UserSession()
    session = sessions[user_id]

    long_term_memory = load_long_term_memory()
    # Non utilisé car directement récupéré depuis ma fonction get_response
    #conversation_history = session.conversation_history
    medical_system_message = "Tu t'appelles Ted. Tu es un assistant psychologue empathique, spécialisé dans la gestion du stress et spécialement et uniquement formé pour discuter des problèmes de stress. Ton rôle est d'aider les gens à comprendre et à gérer leur stress. Tu es ici pour offrir des 2-3 conseils pertinents et pour aider à déterminer si une consultation avec un psychologue pourrait être bénéfique en fonction de ce que l'utilisateur te partage."
    response = await get_response(prompt=user_input, session=session, system_message=medical_system_message, chat_id=user_id, long_term_memory=long_term_memory, include_history=True)
    
    #DEBUG
    print("IA analyse :", response)

    session.conversation_history.append({"role": "user", "content": user_input})
    session.conversation_history.append({"role": "assistant", "content": response})
    save_conversation_history(session.conversation_history, user_id)

    if len(session.conversation_history) > MAX_HISTORY_MESSAGES * 2:
        session.conversation_history = session.conversation_history[-MAX_HISTORY_MESSAGES * 2:]

    # Envoyer le menu à l'utilisateur
    await bot.send_message(chat_id=user_id, text="Choisis une option:", reply_markup=medical_keyboard)   

# Fonction qui fournit des conseils élaborées. On utilise la technique du Tot dans cette fonction ! (Théorisé en mai 2023 par des experts en IA)
async def execute_advice_mode(user_input, user_id):
    if user_id not in sessions:
        sessions[user_id] = UserSession()
    session = sessions[user_id]

    long_term_memory = load_long_term_memory()
    # Non utilisé car directement récupéré depuis ma fonction get_response
    #conversation_history = session.conversation_history
    psychologue_system_message = "Tu es un expert psychologue, spécialisé dans la gestion du stress. Je souhaite que tu m'aides à gérer mon stress qui est un problème crucial pour moi, réponds par 'Ok' si c'est bon pour toi."

    # On ne définit pas de prompt !
    response = await get_response(prompt="", session=session, system_message=psychologue_system_message, chat_id=user_id, long_term_memory=long_term_memory, include_history=True)
    # Sauvegarde l'historique de conversation le prompt initial donné au bot et sa réponse!
    session.conversation_history.append({"role": "user", "content": psychologue_system_message})
    session.conversation_history.append({"role": "assistant", "content": response})
    save_conversation_history(session.conversation_history, user_id)
    if len(session.conversation_history) > MAX_HISTORY_MESSAGES * 2:
        session.conversation_history = session.conversation_history[-MAX_HISTORY_MESSAGES * 2:]  

    # On dit que la consigne a commencé et on dit que le contenu sera accessible dans un PDF
    await bot.send_message(chat_id=user_id, text="Etape 1 : je vais vous donner 3 propositions pour vous aider. Vous pourrez retrouver l'ensemble de mes conseils dans un fichier PDF à la fin.")
    speak_text(user_id, "Etape 1 : je vais vous donner 3 propositions pour vous aider. Vous pourrez retrouver l'ensemble de mes conseils dans un fichier PDF à la fin.")
    # On efface la mémoire pour repartir à 0 pour la scéance pour simplifier sans devoir recreer une nouvelle structure
    psychologue_system_message = "En tant qu'expert psychologue, peux-tu me donner 3 propositions pertinentes et vraiment différentes des unes des autres pour faire face à ma problématique de la meilleure façon possible."
    # On ne définit pas de prompt !
    response = await get_response(prompt=user_input, session=session, system_message=psychologue_system_message, chat_id=user_id, long_term_memory=long_term_memory, include_history=True)

    # Sauvegarde l'historique de conversation le prompt de l'utilisateur donné au bot et sa réponse!
    session.conversation_history.append({"role": "user", "content": user_input})
    session.conversation_history.append({"role": "assistant", "content": response})
    save_conversation_history(session.conversation_history, user_id)
    if len(session.conversation_history) > MAX_HISTORY_MESSAGES * 2:
        session.conversation_history = session.conversation_history[-MAX_HISTORY_MESSAGES * 2:] 

    await bot.send_message(chat_id=user_id, text="Etape 2 : je vais vous donner 3 propositions pour vous aider. Vous pourrez retrouver l'ensemble de mes conseils dans un fichier PDF à la fin de la séance")
    speak_text(user_id, "Etape 2 : Je vais maintenant vous donner une évaluation de chaque option, merci de patienter pendant que je réfléchis.")
    psychologue_system_message = "En tant qu'expert psychologue, pour chaque proposition que tu m'as faite tu vas me donner les avantages et les inconvénients et le niveau d'effort selon ma problématique, les problématiques que je pourrais rencontrer dans la mise en oeuvre de ces propositions. Donne moi aussi une probabilité de succès pour chaque proposition."
    # On ne définit pas de prompt !
    response = await get_response(prompt="", session=session, system_message=psychologue_system_message, chat_id=user_id, long_term_memory=long_term_memory, include_history=True)
    # Sauvegarde l'historique de conversation le prompt initial donné au bot et sa réponse!
    session.conversation_history.append({"role": "user", "content": psychologue_system_message})
    session.conversation_history.append({"role": "assistant", "content": response})
    save_conversation_history(session.conversation_history, user_id)
    if len(session.conversation_history) > MAX_HISTORY_MESSAGES * 2:
        session.conversation_history = session.conversation_history[-MAX_HISTORY_MESSAGES * 2:]  

    await bot.send_message(chat_id=user_id, text="Étape 3 : Je vais maintenant vous dire comment mettre en application ces propositions, merci de patienter pendant que je réfléchis")
    speak_text(user_id, "Etape 3 : Je vais maintenant vous dire comment mettre en application ces propositions, merci de patienter pendant que je réfléchis.")
    psychologue_system_message = "En tant qu'expert psychologue, fait moi une liste des ressources et aides que je pourrais exploiter et enfin, identifie les potentiels résultats inattendus et une bonne manière de les gérer."
    # On définit un  prompt sinon créé des problèmes!
    response = await get_response(prompt="Pour chaque proposition j'aimerai que tu m'aides à réfléchir à leur application", session=session, system_message=psychologue_system_message, chat_id=user_id, long_term_memory=long_term_memory, include_history=True)
    # Sauvegarde l'historique de conversation le prompt initial donné au bot et sa réponse!
    session.conversation_history.append({"role": "user", "content": psychologue_system_message})
    session.conversation_history.append({"role": "assistant", "content": response})
    save_conversation_history(session.conversation_history, user_id)
    if len(session.conversation_history) > MAX_HISTORY_MESSAGES * 2:
        session.conversation_history = session.conversation_history[-MAX_HISTORY_MESSAGES * 2:]

    await bot.send_message(chat_id=user_id, text="Etape 4 : Je vais maintenant faire un classement de ces 3 options de la plus prometteuse à la moins prometteuse, en vous donnant mes dernières réfléxions.")
    speak_text(user_id, "Etape 4 : Je vais maintenant faire un classement de ces 3 options de la plus prometteuse à la moins prometteuse, en vous donnant mes dernières réfléxions.")
    psychologue_system_message = "Pour finir en te basant sur tous ces éléments, peux-tu me faire un classement des 3 options, de la plus prometteuses à la moins prometteuses."
    # On définit un  prompt sinon créé des problèmes!
    response = await get_response(prompt="Pour chaque option, explique moi précisément pourquoi elle obtient ce classement et donne moi tes dernières réflexions qui pourrait être utile à ma réfléxion.", session=session, system_message=psychologue_system_message, chat_id=user_id, long_term_memory=long_term_memory, include_history=True)
    # Sauvegarde l'historique de conversation le prompt initial donné au bot et sa réponse!
    session.conversation_history.append({"role": "user", "content": psychologue_system_message})
    session.conversation_history.append({"role": "assistant", "content": response})
    save_conversation_history(session.conversation_history, user_id)
    if len(session.conversation_history) > MAX_HISTORY_MESSAGES * 2:
        session.conversation_history = session.conversation_history[-MAX_HISTORY_MESSAGES * 2:]    
    await bot.send_message(chat_id=user_id, text="J'ai terminé ! j'espère que cela vous sera utile.")   
    speak_text(user_id, "J'ai terminé ! j'espère que cela vous sera utile.")
    
    # Création du PDF  
    await create_pdf_from_conversation(session.conversation_history, chat_id)
    # Réafficher le menu
    await bot.send_message(chat_id=user_id, text="Choisissez une option:", reply_markup=keyboard)

# Fonction qui permet d'intéragir avec l'api d'Open AI et de retourner la réponse en stream pour éviter d'attendre réponse complète 
# (on passe chat_id en paramètre qui est le user_id avec la session pour éviter d'envoyer à plusieurs instance du bot les messages)
async def get_response(prompt, session, system_message, chat_id, long_term_memory=None, max_tokens=MAX_TOKENS, temperature=TEMPERATURE, n=N, include_history=True):
    log_message(f"Prompt de l'utilisateur : {prompt}")
    messages = [{"role": "system", "content": system_message}]
    if long_term_memory and include_history:
        messages.append({"role": "user", "content": long_term_memory})
    if include_history:
        messages.extend(session.conversation_history)
    messages.append({"role": "user", "content": prompt})

    #DEBUG
    print(f"\nMessage envoyé a l'api d'Open AI (avec mémoire) : {messages}\n")
    #log_message(f"\nMessage envoyé a l'api d'Open AI (avec mémoire) : {messages}\n")

    try:
        response = openai.ChatCompletion.create(
        #gpt-4 
        model="gpt-4-0613",
        messages=messages,
        max_tokens=max_tokens,
        n=n,
        temperature=temperature,
        stop=None,
        stream=True  
        )

        message = ""
        buffer = ""

        for chunk in response:
            if 'choices' in chunk and len(chunk['choices']) > 0: # type: ignore
                delta = chunk['choices'][0]['delta'] # type: ignore
                if 'content' in delta:
                    content = delta['content']
                    message += content
                    buffer += content
                    
                    if "." in buffer:
                        sentences = re.split(r'(?<!\d)\.(?=\s|$)', buffer)
                        buffer = sentences.pop()
                        
                        for sentence in sentences:
                            await bot.send_message(chat_id=chat_id, text=sentence, disable_web_page_preview=True)
                            speak_text(chat_id, sentence)

        if buffer:
            speak_text(chat_id, buffer)

        log_message(f"Réponse du chatbot : {message}")
        return message

    except Exception as e:
        error_message = "Désolé, une erreur s'est produite lors du traitement de votre demande. Veuillez réessayer plus tard."
        log_message(f"Erreur lors du traitement du message : {e}")
        await bot.send_message(chat_id=chat_id, text=error_message) # type: ignore
        log_message(f"Message d'erreur envoyé à l'utilisateur {chat_id} : {error_message}")

# Fonction pour pouvoir loguer nos informations
def log_message(message: str):
    with open("tedcare-log.log", "a") as log_file:
        log_file.write(f"{datetime.now()} - {message}\n")
        print(f"{datetime.now()} - {message}")

# Fonction pour le calcul du score du questionnaire PSS-10
# (DEBUG) Calculs à vérifier ! 
def calculate_score(answers):
    scores = {'Jamais': 0, 'Presque jamais': 1, 'Parfois': 2, 'Assez souvent': 3, 'Très souvent': 4}
    reverse_scores = {'Jamais': 4, 'Presque jamais': 3, 'Parfois': 2, 'Assez souvent': 1, 'Très souvent': 0}
    total_score = 0
    for i, response in enumerate(answers):
        if i+1 in [4, 5, 7, 8]:
            total_score += reverse_scores[response]
        else:
            total_score += scores[response]
    return total_score

# Fonction pour gérer le mémoire long terme (Partiellement implémenter mais non utilisée dans le code car pas possible de définir via Telegram pour l'instant)
def load_long_term_memory(filename="long_term_memory.json"):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            memory_list = json.load(f)
            # Concaténer les éléments de la liste en une seule chaîne de caractères
            return ". ".join(memory_list)  
    except FileNotFoundError:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=4)
        return ""

# Fonction pour effacer la mémoire court terme
def reset_memory(user_id):
    if user_id in sessions:
        sessions[user_id].conversation_history = []
        save_conversation_history(sessions[user_id].conversation_history, user_id)
        print(f"Mémoire effacée pour l'utilisateur {user_id}")
        log_message(f"Mémoire court terme effacée pour l'utilisateur {user_id}\n") 
    else:
        print(f"Aucune session active pour l'utilisateur {user_id}")
        log_message(f"Aucune session active pour l'utilisateur {user_id}\n") 

# Fonction pour sauvegarder notre mémoire court terme
def save_conversation_history(conversation_history, user_id, filename="short_term_memory.json"):
    filename = f"{user_id}_{filename}"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(conversation_history, f, ensure_ascii=False, indent=4)

# Fonction pour charger notre mémoire court terme
def load_conversation_history(user_id, filename="short_term_memory.json"):
    filename = f"{user_id}_{filename}"
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []
'''
#  Pour faire parler l'ours en utilisant la synthèse vocale gratuite pyttsx3
def speak_text(user_id, text):
    # Vérifiez si l'utilisateur a une session. Sinon, créez-en une. Pas forcément nécessaire comme cela est fait avec la commande /start mais peut être utile si bot est relancé sans passé par la commande /start
    if user_id not in sessions:
        sessions[user_id] = UserSession()
    session = sessions[user_id]
    if session.vocal_system_enabled:
        engine = pyttsx3.init()
        engine.setProperty("rate", 200)
        engine.say(text)
        engine.runAndWait()
'''
# Fonction pour faire parler l'ours en utilisant l'api Azure de Miscrosoft
def speak_text(user_id, text):
    # Vérifiez si l'utilisateur a une session. Sinon, créez-en une. Pas forcément nécessaire comme cela est fait avec la commande /start mais peut être utile si bot est relancé sans passé par la commande /start
    if user_id not in sessions:
        sessions[user_id] = UserSession()
    session = sessions[user_id]
    if session.vocal_system_enabled:
        speech_config = speechsdk.SpeechConfig(subscription=azure_subscription, region=azure_region)
        # Définir la langue à Français
        speech_config.speech_synthesis_language = "fr-FR"
        # Définir la voix 
        speech_config.speech_synthesis_voice_name = "fr-FR-EloiseNeural"

        speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config)

        result = speech_synthesizer.speak_text_async(text).get()

        # vérifiez le résultat
        # C'est erreurs sont dus à Pylance mais ne sont pas bloquantes !
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            print("Text spoken successfully.")
        elif result.reason == speechsdk.ResultReason.Canceled:
            if result.cancellation_details is not None:
                print("Speech synthesis canceled: {}".format(result.cancellation_details.reason))
                if result.cancellation_details.reason == speechsdk.CancellationReason.Error:
                    print("Error details: {}".format(result.cancellation_details.error_details))
# Fonction pour générer un PDF
async def create_pdf_from_conversation(conversation_history, chat_id, filename_prefix="conseils"):
    # Obtenir la date et l'heure actuelles
    now = datetime.now()
    # Créer une chaîne de caractères représentant la date et l'heure dans le format souhaité
    date_string = now.strftime("%Y-%m-%d_%H-%M-%S")
    title_string = now.strftime("%Y-%m-%d %H:%M:%S")
    # Ajouter la date et l'heure au nom de fichier
    filename = f"{filename_prefix}_{date_string}.pdf"
    # Créez un nouveau PDF avec Reportlab.
    doc = SimpleDocTemplate(filename, pagesize=letter)
    # Créez une liste pour stocker les éléments du document
    doc_elements = []
    # Définir les styles
    styles = getSampleStyleSheet()
    # Créer un style de sous-titre
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Title'],
        fontSize=14,
        leading=18,
        alignment=TA_CENTER,
        spaceAfter=6,
    )
    # Ajouter le titre principal
    doc_elements.append(Paragraph("Projet TedCare", styles['Title']))
    # Ajouter le sous-titre
    doc_elements.append(Paragraph(f"Conseils du {title_string}", subtitle_style))
    # Ajouter un espace
    doc_elements.append(Spacer(1, 12))
    # Ajouter le texte au PDF
    for item in conversation_history:
        if item["role"] == "assistant" and item["content"] != "Ok":
            text = item["content"]
            # Text formatting
            text = re.sub(r'(?<=\s)(\d+\.|-)', r'<br/>\1', text)
            doc_elements.append(Paragraph(text, styles['Normal']))
            doc_elements.append(Spacer(1, 12))
    # Construire le PDF
    doc.build(doc_elements)
    # Envoyer le fichier PDF en tant que document
    try:
        with open(filename, 'rb') as file:
            await bot.send_document(chat_id, file)
    finally:
        # Supprimer le fichier en toute sécurité après l'avoir envoyé
        os.remove(filename)

async def on_startup(dp):
    print("Le bot a été démarré")

async def on_shutdown(dp):
     print("Le bot a été arrêté")

if __name__ == '__main__':
    executor.start_polling(dp, on_startup=on_startup, on_shutdown=on_shutdown)