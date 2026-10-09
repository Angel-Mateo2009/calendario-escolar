"""Send scheduled push reminders for tasks due tomorrow in Ecuador local time."""
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
    run_key = os.environ.get("REMINDER_RUN_KEY", "").strip()
    if not run_key:
        run_key = f"manual-{datetime.now(LOCAL_ZONE).strftime('%Y-%m-%d-%H%M')}"
    conn = get_db_connection()
    cur = conn.cursor()
    ph = "%s" if os.environ.get("DATABASE_URL") else "?"
    cur.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_task_push_notifications (
            email TEXT NOT NULL,
            task_id INTEGER NOT NULL,
            due_date TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            run_key TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            PRIMARY KEY (email, task_id, due_date, endpoint, run_key)
        )
    """)
    conn.commit()
    cur.execute(f"SELECT id, subject, title FROM tasks WHERE due_date={ph}", (due_date,))
    tasks = cur.fetchall()
    cur.execute("SELECT email, endpoint, p256dh, auth FROM push_subscriptions")
    subscriptions = cur.fetchall()
    sent = 0

    for subscription in subscriptions:
        email, endpoint, p256dh, auth = subscription
        pending_tasks = 0
        for task_id, subject, title in tasks:
            # Do not remind students about work they already marked complete.
            cur.execute(
                f"SELECT 1 FROM progress WHERE email={ph} AND task_id={ph} AND status='COMPLETADO' LIMIT 1",
                (email, task_id)
            )
            if cur.fetchone():
                continue
            pending_tasks += 1
            cur.execute(
                f"SELECT 1 FROM scheduled_task_push_notifications WHERE email={ph} AND task_id={ph} AND due_date={ph} AND endpoint={ph} AND run_key={ph}",
                (email, task_id, due_date, endpoint, run_key)
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
                f"INSERT INTO scheduled_task_push_notifications(email,task_id,due_date,endpoint,run_key,sent_at) VALUES({ph},{ph},{ph},{ph},{ph},{ph}) ON CONFLICT(email,task_id,due_date,endpoint,run_key) DO NOTHING",
                (email, task_id, due_date, endpoint, run_key, datetime.now(LOCAL_ZONE).isoformat(timespec="seconds"))
            )
            conn.commit()
            sent += 1

        # Send a daily status update when the student has no work due tomorrow.
        # task_id=0 is reserved as the daily no-tasks marker (real task IDs start at 1).
        if pending_tasks == 0:
            cur.execute(
                f"SELECT 1 FROM scheduled_task_push_notifications WHERE email={ph} AND task_id=0 AND due_date={ph} AND endpoint={ph} AND run_key={ph}",
                (email, due_date, endpoint, run_key)
            )
            if not cur.fetchone():
                payload = {
                    "title": "Sin tareas pendientes mañana",
                    "body": "No tienes tareas por entregar mañana. ¡Que tengas un buen día!",
                    "tag": f"sin-tareas-{due_date}",
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
                    logging.warning("Push diario falló para %s (HTTP %s): %s", email, status, error)
                    if status in (404, 410):
                        cur.execute(f"DELETE FROM push_subscriptions WHERE endpoint={ph}", (endpoint,))
                        conn.commit()
                    continue

                cur.execute(
                    f"INSERT INTO scheduled_task_push_notifications(email,task_id,due_date,endpoint,run_key,sent_at) VALUES({ph},0,{ph},{ph},{ph},{ph}) ON CONFLICT(email,task_id,due_date,endpoint,run_key) DO NOTHING",
                    (email, due_date, endpoint, run_key, datetime.now(LOCAL_ZONE).isoformat(timespec="seconds"))
                )
                conn.commit()
                sent += 1

    conn.close()
    logging.info("Avisos enviados: %s; fecha límite: %s; ejecución: %s", sent, due_date, run_key)


if __name__ == "__main__":
    main()
