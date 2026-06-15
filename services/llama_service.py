from groq import Groq
import os
from dotenv import load_dotenv

load_dotenv()

_groq_api_key = os.getenv("GROQ_API_KEY")
client = Groq(api_key=_groq_api_key) if _groq_api_key else None

def chat_with_llama(message: str, system_prompt: str = "") -> str:
    if not client:
        raise RuntimeError("GROQ_API_KEY tidak dikonfigurasi. Chatbot tidak tersedia.")
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ],
            max_tokens=1024,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        raise RuntimeError(f"LLM API error: {str(e)}")