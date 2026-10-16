from dotenv import load_dotenv
from openai import OpenAI
import os

load_dotenv(override=True)
client = OpenAI(
    base_url="https://apim-rakathon-q7146n.azure-api.net/openai/v1/",
    api_key="unused",
    default_headers={"api-key": os.environ["API_KEY"].strip()},
)

deployments = [
    "gpt-6-luna-dz-eu",
    "gpt-6-1-sol-dz-eu",
    "gpt-6-astra-global",
    "deepseek-v4-pro-global",
    "grok-4-7-global",
    "kimi-k2-7-code-global",
    "mai-thinking-1-global",
]

for name in deployments:
    try:
        r = client.chat.completions.create(
            model=name,
            messages=[{"role": "user", "content": "Ahoj"}],
            max_completion_tokens=500,
        )
        print("OK  ", name, "->", r.choices[0].message.content)
    except Exception as e:
        print("FAIL", name, "->", type(e).__name__, str(e)[:150])