import json
import psycopg2
import time

DB_HOST     = "192.168.11.130"
DB_PORT     = 5432
DB_NAME     = "smartbin"
DB_USER     = "postgres"
DB_PASSWORD = "dG8tclqynj"

def update_from_json():
    with open("point.json", "r") as f:
        data = json.load(f)

    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    cur = conn.cursor()

    for rfid, info in data.items():
        name = info["name"]
        points = info["points"]

        cur.execute("SELECT id FROM users WHERE rfid_code = %s;", (rfid,))
        row = cur.fetchone()

        if row:
            cur.execute(
                "UPDATE users SET name = %s, total_points = %s WHERE rfid_code = %s;",
                (name, points, rfid)
            )
            print(f"Updated {name}")
        else:
            cur.execute(
                "INSERT INTO users (name, rfid_code, total_points) VALUES (%s, %s, %s);",
                (name, rfid, points)
            )
            print(f"Inserted {name}")

    conn.commit()
    cur.close()
    conn.close()

while True:
    print("=== Updating from point.json ===")
    update_from_json()
    print("Done. Waiting 10 seconds...\n")
    time.sleep(10)
