from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")

try:
    client = MongoClient(MONGO_URI)
    db = client.smart_water
except Exception as e:
    print(f"Failed to connect to MongoDB: {e}")
    db = None

def get_db():
    return db
