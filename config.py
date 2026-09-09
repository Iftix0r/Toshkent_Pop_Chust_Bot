import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
DRIVERS_GROUP_ID = int(os.environ["DRIVERS_GROUP_ID"])
