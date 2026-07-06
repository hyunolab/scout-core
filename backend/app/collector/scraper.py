import re
import requests
from bs4 import BeautifulSoup


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def get_article_content(url: str, max_chars: int = 1200) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(url, headers=headers, timeout=10)

    if response.status_code != 200:
        return ""

    soup = BeautifulSoup(response.text, "html.parser")

    paragraphs = soup.find_all("p")

    text = " ".join(p.get_text(strip=True) for p in paragraphs)
    text = clean_text(text)

    return text[:max_chars]