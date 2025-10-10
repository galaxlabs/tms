import requests, os
GREEN_ID = os.getenv("GREEN_ID")
GREEN_TOKEN = os.getenv("GREEN_TOKEN")

def send_whatsapp_message(chat_id, message):
    url = f"https://api.green-api.com/waInstance{GREEN_ID}/sendMessage/{GREEN_TOKEN}"
    requests.post(url, json={"chatId": chat_id, "message": message})
