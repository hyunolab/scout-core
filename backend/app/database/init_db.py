from app.database.database import get_connection

conn = get_connection()

cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS articles (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    title TEXT,
    link TEXT UNIQUE,
    published TEXT,

    content TEXT,

    country TEXT,
    organization TEXT,
    technology TEXT,
    category TEXT,

    importance INTEGER,

    summary TEXT,
    impact TEXT
)
""")

conn.commit()
conn.close()

print("Database initialized.")