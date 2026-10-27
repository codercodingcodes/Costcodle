"""
One-off script: create public.games in Neon and load it from games.json.

Images are served by the frontend from /games/<year>/<month>/<file>, so
costcofdb.com upload URLs are stored as that relative path. Games whose
image is not on costcofdb.com get a NULL image (the frontend shows its
placeholder).

Usage: DB_URL=postgres://... python seed_games.py
"""
import json
import os
from urllib.parse import urlparse

import psycopg2
from psycopg2.extras import execute_values

UPLOADS_PREFIX = "/wp-content/uploads/"


def local_image_path(url):
    parsed = urlparse(url)
    if parsed.hostname == "costcofdb.com" and parsed.path.startswith(UPLOADS_PREFIX):
        return "/games/" + parsed.path[len(UPLOADS_PREFIX):]
    return None


def main():
    with open("games.json", "r") as file:
        game_data = json.load(file)

    rows = []
    for key, game in game_data.items():
        rows.append((int(key.split("-")[1]), game["name"], game["price"], local_image_path(game["image"])))

    conn = psycopg2.connect(os.environ["DB_URL"], connect_timeout=10)
    with conn, conn.cursor() as curr:
        curr.execute('''
            CREATE TABLE IF NOT EXISTS public.games (
                id integer PRIMARY KEY,
                name text NOT NULL,
                price text NOT NULL,
                image text
            )
        ''')
        execute_values(curr, '''
            INSERT INTO public.games (id, name, price, image) VALUES %s
            ON CONFLICT (id) DO UPDATE
            SET name = EXCLUDED.name, price = EXCLUDED.price, image = EXCLUDED.image
        ''', rows)
        curr.execute("SELECT count(*), count(image) FROM public.games")
        total, with_image = curr.fetchone()
    conn.close()
    print("games rows: {total}, with image: {with_image}".format(total=total, with_image=with_image))


if __name__ == "__main__":
    main()
