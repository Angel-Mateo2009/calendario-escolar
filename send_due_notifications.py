"""Send push reminders for student tasks due tomorrow in Ecuador local time.

Run once daily from a Render Cron Job at 13:00 UTC (08:00 America/Guayaquil).
"""
import json
import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pywebpush import WebPushException, webpush

from app import get_db_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOCAL_ZONE = ZoneInfo("America/Guayaquil")


def main():
    private_key = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
    claims_email = os.environ.get("VAPID_CLAIMS_EMAIL", "").strip()
    if not private_key or not claims_email:
        raise RuntimeError("Configura VAPID_PRIVATE_KEY y VAPID_CLAIMS_EMAIL en el Cron Job de Render.")

    tomorrow = datetime.now(LOCAL_ZONE).date() + timedelta(days=1)
    due_date = tomorrow.isoformat()
    vapid_subject = claims_email if claims_email.startswith(("mailto:", "https://")) else f"mailto:{claims_email}"
    conn = get_db_connection()
    cur = conn.cursor()
    ph = "%s" if os.environ.get("DATABASE_URL") else "?"
    cur.execute(f"SELECT id, subject, title FROM tasks WHERE due_date={ph}", (due_date,))
    tasks = cur.fetchall()
    cur.execute("SELECT email, endpoint, p256dh, auth FROM push_subscriptions")
    subscriptions = cur.fetchall()
    sent = 0

    for subscription in subscriptions:
        email, endpoint, p256dh, auth = subscription
        for task_id, subject, title in tasks:
            # Do not remind students about work they already marked complete.
            cur.execute(
                f"SELECT 1 FROM progress WHERE email={ph} AND task_id={ph} AND status='COMPLETADO' LIMIT 1",
                (email, task_id)
            )
            if cur.fetchone():
                continue
            cur.execute(
                f"SELECT 1 FROM task_push_notifications WHERE email={ph} AND task_id={ph} AND due_date={ph} AND endpoint={ph}",
                (email, task_id, due_date, endpoint)
            )
            if cur.fetchone():
                continue

            payload = {
                "title": f"Mañana vence · {subject}",
                "body": title,
                "tag": f"tarea-{task_id}-{due_date}",
                "url": "/"
            }
            try:
                webpush(
                    subscription_info={"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}},
                    data=json.dumps(payload, ensure_ascii=False),
                    vapid_private_key=private_key,
                    vapid_claims={"sub": vapid_subject},
                    ttl=60 * 60 * 24
                )
            except WebPushException as error:
                response = getattr(error, "response", None)
                status = getattr(response, "status_code", None)
                logging.warning("Push falló para %s (HTTP %s): %s", email, status, error)
                if status in (404, 410):
                    cur.execute(f"DELETE FROM push_subscriptions WHERE endpoint={ph}", (endpoint,))
                    conn.commit()
                continue

            cur.execute(
                f"INSERT INTO task_push_notifications(email,task_id,due_date,endpoint,sent_at) VALUES({ph},{ph},{ph},{ph},{ph}) ON CONFLICT(email,task_id,due_date,endpoint) DO NOTHING",
                (email, task_id, due_date, endpoint, datetime.now(LOCAL_ZONE).isoformat(timespec="seconds"))
            )
            conn.commit()
            sent += 1

    conn.close()
    logging.info("Avisos enviados: %s; fecha límite: %s", sent, due_date)


if __name__ == "__main__":
    main()
