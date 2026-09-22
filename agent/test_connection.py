from dotenv import load_dotenv
import os
import pyTigerGraph as tg

load_dotenv()

conn = tg.TigerGraphConnection(
    host=os.getenv("TG_HOST"),
    username=os.getenv("TG_USERNAME"),
    password=os.getenv("TG_PASSWORD")
)

print("Connected. TigerGraph version:", conn.getVer())
