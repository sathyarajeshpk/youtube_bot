"""
Run this to see exactly which models are available for your API key.
Usage:
  $env:GEMINI_API_KEY="your-key-here"
  python check_models.py
"""
import os
from google import genai

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

print("\nAvailable models for your API key:\n")
for model in client.models.list():
    print(f"  {model.name}")
print()
