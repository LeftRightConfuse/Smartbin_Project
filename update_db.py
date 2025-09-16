import json
import psycopg2
import time
from datetime import datetime
from psycopg2 import sql

DB_HOST     = "192.168.11.154"
DB_PORT     = 5432
DB_NAME     = "smartbin"
DB_USER     = "postgres"
DB_PASSWORD = "dG8tclqynj"

# ตั้งให้ตรงกับชื่อตารางจริง
TRASH_TABLE = "waste_log"

def _connect():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD
    )

def update_users_from_points_json():
    """อัปเดต/เพิ่มผู้ใช้จาก point.json"""
    with open("point.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    conn = _connect()
    cur = conn.cursor()

    for rfid, info in data.items():
        name = info.get("name")
        points = info.get("points", 0)
        print("Processing user:", rfid, name, points)

        cur.execute("SELECT id FROM users WHERE rfid_code = %s;", (rfid,))
        row = cur.fetchone()

        if row:
            cur.execute(
                "UPDATE users SET name = %s, total_points = %s WHERE rfid_code = %s;",
                (name, points, rfid),
            )
            print("Updated", name)
        else:
            cur.execute(
                "INSERT INTO users (name, rfid_code, total_points) VALUES (%s, %s, %s);",
                (name, rfid, points),
            )
            print("Inserted", name)

    conn.commit()
    cur.close()
    conn.close()

def _parse_iso_ts(val):
    """แปลง timestamp จากสตริง ISO → datetime (รองรับ Z/epoch)"""
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(val)
    if isinstance(val, str):
        v = val.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(v)
        except Exception:
            pass
    return None  # ถ้าไม่มีให้ DB ใส่ NOW()

def _ensure_user_and_get_id(cur, *, user_id=None, rfid=None, name=None):
    """คืนค่า users.id จาก user_id หรือ rfid (ถ้าไม่เจอ rfid จะสร้างผู้ใช้ใหม่)"""
    if user_id:
        return int(user_id)

    if rfid:
        cur.execute("SELECT id FROM users WHERE rfid_code = %s;", (rfid,))
        row = cur.fetchone()
        if row:
            return row[0]
        display_name = name or f"Unknown {rfid}"
        cur.execute(
            "INSERT INTO users (name, rfid_code, total_points) VALUES (%s, %s, %s) RETURNING id;",
            (display_name, rfid, 0),
        )
        new_id = cur.fetchone()[0]
        print(f"Created user for rfid={rfid} -> id={new_id}")
        return new_id

    raise ValueError("ต้องมี user_id หรือ rfid อย่างน้อยหนึ่งใน trash.json")

def insert_trash_from_json():
    """อ่าน trash.json แล้ว INSERT เพิ่มลงตาราง waste_log"""
    with open("trash.json", "r", encoding="utf-8") as f:
        raw = json.load(f)

    records = list(raw.values()) if isinstance(raw, dict) else raw
    if not isinstance(records, list):
        raise ValueError("trash.json ต้องเป็น list หรือ dict ของรายการ")

    conn = _connect()
    cur = conn.cursor()
    inserted = 0

    for idx, rec in enumerate(records, start=1):
        try:
            uid = _ensure_user_and_get_id(
                cur,
                user_id=rec.get("user_id"),
                rfid=rec.get("rfid"),
                name=rec.get("name"),
            )
            waste_type = rec.get("waste_type") or rec.get("type") or rec.get("waste")
            amount = rec.get("amount", 0)
            points = rec.get("points", 0)
            ts = _parse_iso_ts(rec.get("timestamp"))

            if ts is None:
                q = sql.SQL("""
                    INSERT INTO {tbl} (user_id, waste_type, amount, points, timestamp)
                    VALUES (%s, %s, %s, %s, NOW())
                """).format(tbl=sql.Identifier(TRASH_TABLE))
                cur.execute(q, (uid, waste_type, amount, points))
            else:
                q = sql.SQL("""
                    INSERT INTO {tbl} (user_id, waste_type, amount, points, timestamp)
                    VALUES (%s, %s, %s, %s, %s)
                """).format(tbl=sql.Identifier(TRASH_TABLE))
                cur.execute(q, (uid, waste_type, amount, points, ts))

            inserted += 1
        except Exception as e:
            print(f"[WARN] skip record #{idx} due to error: {e}")

    conn.commit()
    cur.close()
    conn.close()
    print(f"Inserted trash rows: {inserted}")

def main_loop():
    while True:
        print("\n=== Updating users from point.json ===")
        update_users_from_points_json()
        print("=== Inserting trash from trash.json ===")
        insert_trash_from_json()
        print("Done. Waiting 10 seconds...\n")
        time.sleep(10)

if __name__ == "__main__":
    main_loop()
