import json
import os

from dotenv import load_dotenv

from app.ai.prompts import SCOUT_SYSTEM_PROMPT

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")

client = None

if api_key and api_key.startswith("sk-"):
    from openai import OpenAI

    client = OpenAI(api_key=api_key)


def mock_analysis(title: str):
    return {
        "title": title,
        "country": "Unknown",
        "organization": "Unknown",
        "technology": "Unknown",
        "category": "Unknown",
        "importance": 3,
        "summary": title,
        "impact": "OpenAI API key is not set or invalid."
    }


def analyze(title: str):
    if client is None:
        return mock_analysis(title)

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": SCOUT_SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": f"Analyze this nuclear industry news title: {title}"
                }
            ],
            temperature=0.2,
            response_format={"type": "json_object"}
        )

        content = response.choices[0].message.content

        return json.loads(content)

    except Exception as error:
        return {
            "title": title,
            "country": "Unknown",
            "organization": "Unknown",
            "technology": "Unknown",
            "category": "Unknown",
            "importance": 3,
            "summary": title,
            "impact": f"AI analysis failed: {str(error)}"
        }