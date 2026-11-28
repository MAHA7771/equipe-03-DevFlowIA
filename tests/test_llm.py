import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv(".env")

api_key = os.getenv("GROQ_API_KEY")
model = os.getenv("GROQ_MODEL")

if not api_key:
    raise ValueError("GROQ_API_KEY not found. Check your .env file.")

if not model:
    raise ValueError("GROQ_MODEL not found. Check your .env file.")

client = Groq(api_key=api_key)

print("Groq API configured successfully!")
print("Selected model:", model)
