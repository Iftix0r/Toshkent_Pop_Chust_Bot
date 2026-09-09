import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
DRIVERS_GROUP_ID = int(os.environ["DRIVERS_GROUP_ID"])
ADMIN_IDS = [
    int(admin_id)
    for admin_id in os.environ.get("ADMIN_IDS", "").split(",")
    if admin_id.strip()
]
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "")
