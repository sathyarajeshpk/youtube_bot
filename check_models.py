"""
Run this to see exactly which Groq models are available for your API key,
and which one the bot will pick.

Usage:
  export GROQ_API_KEY="your-key-here"     (PowerShell: $env:GROQ_API_KEY="...")
  python check_models.py
"""
import os
from groq import Groq

from main import PREFERRED_MODELS, pick_groq_model

client = Groq(api_key=os.environ["GROQ_API_KEY"])

print("\nAvailable models for your API key:\n")
for model in sorted(m.id for m in client.models.list().data):
    print(f"  {model}")

print(f"\nThe bot will use: {pick_groq_model(client)}\n")
