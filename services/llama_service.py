from groq import Groq
import os
from dotenv import load_dotenv

load_dotenv()

_groq_api_key = os.getenv("GROQ_API_KEY")
client = Groq(api_key=_groq_api_key) if _groq_api_key else None

# Batas karakter input untuk menghindari error 413 dari Groq (TPM limit)
# ~2000 karakter ≈ ~500 token, aman untuk llama-3.1-8b-instant
_MAX_INPUT_CHARS = 2000


def chat_with_llama(message: str, system_prompt: str = "", max_tokens: int = 1024) -> str:
    if not client:
        raise RuntimeError("GROQ_API_KEY tidak dikonfigurasi. Chatbot tidak tersedia.")

    # Truncate message jika terlalu panjang agar tidak melebihi batas TPM Groq
    if len(message) > _MAX_INPUT_CHARS:
        message = message[:_MAX_INPUT_CHARS]

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ],
            max_tokens=max_tokens,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        raise RuntimeError(f"LLM API error: {str(e)}")
