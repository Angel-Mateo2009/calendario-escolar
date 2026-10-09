import os
import json
import psycopg2
import logging
from html import escape
import hashlib
from datetime import date, datetime
from flask import Flask, render_template_string, request, redirect, url_for, session, flash, jsonify, send_from_directory

app = Flask(__name__)
app.secret_key = "tu_clave_secreta_aqui"  # Mantén tu clave secreta

# Lista oficial de Administradores
ADMIN_EMAILS = [
    "masalazar@ladolorosa-loja.edu.ec",
    "amchamba@ladolorosa-loja.edu.ec",
    "angel.mateochamba2011@gmail.com"
]

# Función centralizada para conectar a PostgreSQL (en Render) o SQLite (en local si estás probando en tu PC)
def get_db_connection():
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        return psycopg2.connect(database_url)
    else:
        import sqlite3
        conn = sqlite3.connect("database.db")
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Detectar si estamos usando PostgreSQL o SQLite para definir el autoincremento correcto
    is_postgres = bool(os.environ.get("DATABASE_URL"))

    if is_postgres:
        task_id_pk = "SERIAL PRIMARY KEY"
        progress_id_pk = "SERIAL PRIMARY KEY"
    else:
        task_id_pk = "INTEGER PRIMARY KEY AUTOINCREMENT"
        progress_id_pk = "INTEGER PRIMARY KEY AUTOINCREMENT"

    # --- LÍNEA TEMPORAL PARA RECREAR LA TABLA CON ON DELETE CASCADE EN RENDER ---
    #if is_postgres:
        #cursor.execute("DROP TABLE IF EXISTS progress CASCADE;")
        #conn.commit()
    # ---------------------------------------------------------------------------

    # Tabla de Tareas y Exámenes
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS tasks (
            id {task_id_pk},
            subject TEXT NOT NULL,
            title TEXT NOT NULL,
            due_date TEXT,
            item_type TEXT DEFAULT 'Tarea'
        )
    """)

    # Tabla de Progreso de Estudiantes (con ON DELETE CASCADE integrado)
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS progress (
            id {progress_id_pk},
            email TEXT NOT NULL,
            task_id INTEGER,
            status TEXT DEFAULT 'PENDIENTE',
            FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
        )
    """)

    # Tabla para Registro de Usuarios Activos en Tiempo Real
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS active_users (
            email TEXT PRIMARY KEY,
            last_active TEXT
        )
    """)

    # Perfil y economía de juego. CREATE TABLE IF NOT EXISTS también migra
    # instalaciones ya existentes sin tocar sus tareas ni progreso.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS student_stats (
            email TEXT PRIMARY KEY,
            xp INTEGER NOT NULL DEFAULT 0,
            coins INTEGER NOT NULL DEFAULT 0,
            gems INTEGER NOT NULL DEFAULT 0,
            logins INTEGER NOT NULL DEFAULT 0,
            avatar TEXT NOT NULL DEFAULT '🧑🏻‍🎓',
            accessory TEXT NOT NULL DEFAULT '',
            pet TEXT NOT NULL DEFAULT '',
            phrase TEXT NOT NULL DEFAULT ''
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shop_purchases (
            email TEXT NOT NULL,
            item_id TEXT NOT NULL,
            PRIMARY KEY (email, item_id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS student_equipment (
            email TEXT NOT NULL,
            slot TEXT NOT NULL,
            item_id TEXT NOT NULL,
            PRIMARY KEY (email, slot)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_xp_rewards (
            email TEXT NOT NULL,
            task_id INTEGER NOT NULL,
            PRIMARY KEY (email, task_id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rank_rewards (
            email TEXT NOT NULL,
            rank INTEGER NOT NULL,
            awarded_at TEXT NOT NULL,
            PRIMARY KEY (email, rank)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            endpoint TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_push_notifications (
            email TEXT NOT NULL,
            task_id INTEGER NOT NULL,
            due_date TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            PRIMARY KEY (email, task_id, due_date, endpoint)
        )
    """)
    
    conn.commit()

    # Insertar elementos iniciales si la tabla está vacía
    cursor.execute("SELECT COUNT(*) FROM tasks")
    count = cursor.fetchone()[0]
    if count == 0:
        hoy_str = datetime.now().strftime("%Y-%m-")
        initial_tasks = [
            ("Biologia", "Completar trabajo en clase de los tipos de fases de la lectura", hoy_str + "05", "Tarea"),
            ("FOL", "Corrección de la leccion diagnostica", hoy_str + "06", "Examen"),
            ("Ofimática", "Corrección de Lección", hoy_str + "07", "Tarea"),
            ("Historia", "Pasar materia y dibujar el mapa del classrrom y correccion de prueba diagnostica", hoy_str + "10", "Tarea"),
            ("Matemática", "Evaluación de la plataforma", hoy_str + "04", "Examen"),
            ("Lengua", "Realizar las exposiciones segun los temas a cada grupo", hoy_str + "12", "Tarea"),
            ("Química", " 4 dolares los que faltan", hoy_str + "15", "Examen"),
            ("Física", "Deberes (2) y materia en el cuaderno", hoy_str + "18", "Tarea"),
            ("Ed. Física", "Del libro página 51-63", hoy_str + "20", "Tarea"),
            ("Aseo y Soporte de celulares", "Llevar un 2 dolares para materiales de aseo en el aula y para soporte de celulares", hoy_str + "20", "Examen"),
            ("Fisica", "Leccion (1)", hoy_str + "06", "Examen"),
            ("Matemática", "Tarea de la plataforma", hoy_str + "04", "Tarea"),
            ("Inglés", "Tarea hojas de actividades para el día Miércoles entregar al presidente del curso", hoy_str + "04", "Tarea"),
            ("Inglés", "Tarea en la plataforma Verb To Be: Affirmative, Negative and interrogative", hoy_str + "04", "Tarea"),
            ("Inglés", "Tarea en la plataforma Simple Past Other Verbs Exercise", hoy_str + "04", "Tarea")
            
        ]
        
        # Sintaxis adaptada para inserción masiva segura (psycopg2 usa %s, sqlite3 usa ?)
        placeholder = "%s" if is_postgres else "?"
        cursor.executemany(
            f"INSERT INTO tasks (subject, title, due_date, item_type) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder})",
            initial_tasks,
        )

    conn.commit()
    cursor.close()
    conn.close()
    print("Base de datos inicializada correctamente.")

def update_user_activity(email):
    if not email:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    is_postgres = bool(os.environ.get("DATABASE_URL"))
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if is_postgres:
        cursor.execute("""
            INSERT INTO active_users (email, last_active) VALUES (%s, %s)
            ON CONFLICT (email) DO UPDATE SET last_active = EXCLUDED.last_active
        """, (email, now_str))
    else:
        cursor.execute("""
            INSERT INTO active_users (email, last_active) VALUES (?, ?)
            ON CONFLICT(email) DO UPDATE SET last_active = ?
        """, (email, now_str, now_str))

    conn.commit()
    cursor.close()
    conn.close()

# Plantilla HTML Unificada (aquí mantienes tu HTML tal cual lo tienes)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.186.0/build/three.module.js"}}</script>
    <title>Mi Escuelita // Calendario de Rompecabezas Dinámico</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Quicksand:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Quicksand', sans-serif; background-color: #fdfbf7; color: #4a403b; overflow-x: hidden; }
        .avatar-3d-stage { position: relative; perspective: 900px; isolation: isolate; filter: drop-shadow(0 16px 16px rgba(120, 53, 15, .18)); }
        .avatar-3d-stage::before { content: ''; position: absolute; inset: 18% -20% 5%; border-radius: 50%; background: radial-gradient(ellipse, rgba(253, 224, 71, .34), rgba(220, 38, 38, .04) 65%, transparent 72%); z-index: -1; }
        .avatar-3d-turn { height: 100%; transform-style: preserve-3d; animation: avatar-turn 7s ease-in-out infinite alternate; }
        .avatar-3d-bob { height: 100%; animation: avatar-breathe 2.8s ease-in-out infinite; transform-origin: 50% 100%; }
        .avatar-model { overflow: visible; filter: drop-shadow(0 5px 4px rgba(15, 23, 42, .17)); }
        .avatar-arm { transform-box: fill-box; transform-origin: 50% 12%; }
        .avatar-arm-right { animation: avatar-wave 3.4s ease-in-out infinite; }
        @keyframes avatar-turn { 0% { transform: rotateY(-8deg) rotateZ(-1deg); } 100% { transform: rotateY(8deg) rotateZ(1deg); } }
        @keyframes avatar-breathe { 0%, 100% { transform: translateY(0) scale(1); } 50% { transform: translateY(-5px) scale(1.012); } }
        @keyframes avatar-wave { 0%, 72%, 100% { transform: rotate(0deg); } 82% { transform: rotate(-7deg); } 90% { transform: rotate(3deg); } }
        @media (prefers-reduced-motion: reduce) { .avatar-3d-turn, .avatar-3d-bob, .avatar-arm-right { animation: none; } }
        @media (max-width: 640px) {
            html { -webkit-text-size-adjust: 100%; }
            body { overflow-x: clip; }
            header nav { flex-wrap: nowrap !important; overflow-x: auto; overscroll-behavior-x: contain; scrollbar-width: thin; padding: 0 0 6px; }
            header nav a { flex: 0 0 auto; min-height: 42px; display: inline-flex; align-items: center; }
            main { min-width: 0; }
            .calendar-desk { border-width: 2px; border-radius: 1.25rem; }
            .calendar-header-bar { padding: 1rem; }
            .avatar-3d-stage { max-width: 100%; }
            button, input, select, textarea { font-size: 16px; }
            button, a { touch-action: manipulation; }
            .overflow-x-auto { -webkit-overflow-scrolling: touch; }
        }
        .school-card-admin { background: #ffffff; border: 2px solid #fdba74; box-shadow: 0 10px 25px -5px rgba(249, 115, 22, 0.15); }
        .calendar-desk {
            background: #ffffff; border: 4px solid #38bdf8; border-radius: 2rem; box-shadow: 0 20px 35px -10px rgba(56, 189, 248, 0.2); position: relative; overflow: hidden;
        }
        .calendar-header-bar {
            background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%); border-bottom: 4px solid #38bdf8; padding: 1.5rem;
        }
        .binder-ring {
            width: 24px; height: 48px; background: linear-gradient(90deg, #cbd5e1, #f8fafc, #94a3b8); border: 3px solid #64748b; border-radius: 12px; position: absolute; top: -30px; box-shadow: 0 4px 6px rgba(0,0,0,0.15);
        }
        .puzzle-transition { animation: puzzleEffect 0.7s cubic-bezier(0.25, 1, 0.5, 1) forwards; }
        @keyframes puzzleEffect {
            0% { transform: scale(1) rotate(0deg); opacity: 1; }
            50% { transform: scale(0.92) rotate(-2deg) translateY(-10px); opacity: 0.4; }
            100% { transform: scale(1) rotate(0deg) translateY(0); opacity: 1; }
        }
        .avatar-talking { animation: speak 0.6s ease-in-out infinite alternate, float 3s ease-in-out infinite; }
        @keyframes speak {
            0% { transform: scale(1) rotate(0deg); }
            100% { transform: scale(1.08) translateY(-4deg) rotate(-2deg); }
        }
        @keyframes float {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-6px); }
        }
        .speech-bubble {
            position: relative; background: #ffffff; border: 3px solid #fde047; border-radius: 1.5rem; padding: 1.25rem; box-shadow: 0 10px 25px -5px rgba(251, 191, 36, 0.2);
        }
        .speech-bubble::after {
            content: ''; position: absolute; left: 30px; bottom: -15px; border-width: 15px 15px 0; border-style: solid; border-color: #fde047 transparent; display: block; width: 0;
        }
        .bubble {
            position: absolute; bottom: -50px; background: rgba(56, 189, 248, 0.15); border-radius: 50%; animation: rise 12s infinite ease-in-out; z-index: -1; pointer-events: none;
        }
        .bubble:nth-child(1) { width: 45px; height: 45px; left: 10%; animation-duration: 10s; }
        .bubble:nth-child(2) { width: 75px; height: 75px; left: 28%; animation-duration: 14s; background: rgba(251, 191, 36, 0.15); }
        .bubble:nth-child(3) { width: 50px; height: 50px; left: 75%; animation-duration: 9s; }
        @keyframes rise {
            0% { transform: translateY(0) scale(1); opacity: 0.8; }
            100% { transform: translateY(-110vh) scale(1.2); opacity: 0; }
        }
    </style>
    <script>
        function triggerPuzzleAnimation(url) {
            const desk = document.getElementById('calendar-desk-container');
            if (desk) {
                desk.classList.add('puzzle-transition');
                setTimeout(() => { window.location.href = url; }, 600);
            } else {
                window.location.href = url;
            }
        }
    </script>
</head>
<body class="min-h-screen flex flex-col justify-between bg-gradient-to-br from-sky-50 via-amber-50 to-orange-50 relative">

    <div class="bubbles-container">
        <div class="bubble"></div><div class="bubble"></div><div class="bubble"></div>
    </div>

    <!-- PANTALLA DE TRANSICIÓN -->
    {% if session.get('show_transition') %}
    <div class="fixed inset-0 z-50 flex items-center justify-center bg-amber-950/50 backdrop-blur-md p-4">
        <div class="bg-white rounded-3xl p-8 max-w-md w-full text-center shadow-2xl border-4 border-amber-300">
            <div class="w-32 h-32 mx-auto mb-4 bg-amber-100 rounded-full flex items-center justify-center border-4 border-amber-200 shadow-inner">
                <span class="text-6xl avatar-talking">👦🏽🗣️</span>
            </div>
            <h2 class="text-2xl font-bold text-amber-900 mb-2">¡Armando tu Calendario!</h2>
            <p class="text-amber-700 font-semibold text-sm mb-6">Organizando tareas, exámenes y materias... 🧩✨</p>
            <a href="/dismiss_transition" class="inline-block w-full bg-amber-500 hover:bg-amber-400 text-white font-bold py-3.5 px-6 rounded-2xl shadow-lg transition">
                ¡Comenzar! 🚀
            </a>
        </div>
    </div>
    {% endif %}

    <!-- ENCABEZADO -->
    <header class="bg-white/90 backdrop-blur-md border-b border-sky-200 p-4 sticky top-0 z-40 shadow-sm">
        <div class="max-w-6xl mx-auto flex flex-col sm:flex-row justify-between items-center gap-4">
            <div class="flex items-center gap-3">
                <span class="text-2xl">🧩</span>
                <h1 class="text-base font-bold text-sky-900 tracking-wide">Academia La Dolorosa · Calendario Escolar</h1>
            </div>
            {% if session.get('user') %}
            <div class="flex items-center gap-3">
                <span class="text-xs font-semibold text-sky-800 bg-sky-100 px-3 py-1.5 rounded-full hidden md:inline">
                    👤 {{ session.user }}
                </span>
                <a href="/logout" class="text-xs font-bold text-rose-600 bg-rose-50 border border-rose-200 px-3 py-1.5 rounded-xl transition">Salir 🚪</a>
            </div>
            {% endif %}
        </div>
        {% if session.get('role') == 'STUDENT' %}
        <nav class="max-w-6xl mx-auto flex flex-wrap gap-2 mt-3">
            <a href="/" class="text-xs font-bold bg-sky-100 text-sky-900 px-3 py-2 rounded-xl">📚 Calendario</a>
            <a href="/shop" class="text-xs font-bold bg-amber-100 text-amber-900 px-3 py-2 rounded-xl">🛍️ Tienda</a>
            <a href="/ranking" class="text-xs font-bold bg-yellow-100 text-yellow-900 px-3 py-2 rounded-xl">🏆 Ranking</a>
            <a href="/profile" class="text-xs font-bold bg-purple-100 text-purple-900 px-3 py-2 rounded-xl">👤 Mi perfil</a>
            <a href="/customize" class="text-xs font-bold bg-red-100 text-red-900 px-3 py-2 rounded-xl">🎨 Personalizar avatar</a>
            <button id="push-notification-control" type="button" class="text-xs font-bold bg-emerald-100 text-emerald-900 px-3 py-2 rounded-xl">🔔 Activar recordatorios</button>
        </nav>
        {% endif %}
    </header>

    <!-- CONTENIDO -->
    <main class="max-w-6xl mx-auto p-4 md:p-8 w-full flex-grow space-y-8">
        {% with messages = get_flashed_messages() %}
          {% if messages %}
            <div class="mb-6 p-4 rounded-2xl bg-sky-100 border border-sky-300 text-sky-900 text-sm shadow-sm text-center font-medium">
              {% for message in messages %}<p>✨ {{ message }}</p>{% endfor %}
            </div>
          {% endif %}
        {% endwith %}

        {% if not session.get('user') %}
        <!-- LOGIN -->
        <div class="max-w-md mx-auto mt-8 space-y-6">
            <div class="flex items-end gap-3">
                <div class="w-20 h-20 bg-sky-100 rounded-full flex items-center justify-center border-4 border-sky-300 shadow-md flex-shrink-0">
                    <span class="text-4xl avatar-talking">👦🏽🗣️</span>
                </div>
                <div class="speech-bubble flex-grow">
                    <h3 class="text-sm font-bold text-sky-900 mb-1">¡Hola amiguito(a)! 👋</h3>
                    <p class="text-xs text-sky-800">Ingresa tu correo institucional para abrir tu calendario escolar.</p>
                </div>
            </div>
            <div class="bg-white p-8 rounded-3xl shadow-xl border-4 border-sky-200 text-center">
                <h2 class="text-xl font-bold text-sky-900 mb-4">Iniciar Sesión</h2>
                <form action="/login" method="POST" class="space-y-4 text-left">
                    <div>
                        <label class="block text-xs font-bold text-sky-800 mb-1">CORREO ELECTRÓNICO</label>
                        <input type="email" name="email" required placeholder="correo@ladolorosa-loja.edu.ec" class="w-full bg-sky-50/50 border-2 border-sky-200 rounded-xl p-3.5 text-sky-900 focus:outline-none text-sm font-medium">
                    </div>
                    <button type="submit" class="w-full bg-sky-500 hover:bg-sky-400 text-white font-bold py-3.5 rounded-xl transition shadow-lg text-base">
                        Ingresar al Calendario 🧩
                    </button>
                </form>
            </div>
        </div>

        {% elif session.role == 'ADMIN' %}
        <!-- PANEL DE ADMINISTRADORES -->
        <div class="space-y-6">
            <div class="flex items-center gap-4 bg-white p-6 rounded-3xl shadow-md border-2 border-orange-200">
                <div class="w-20 h-20 bg-orange-100 rounded-full flex items-center justify-center border-4 border-orange-300 shadow-md flex-shrink-0">
                    <span class="text-4xl avatar-talking">🦉💬</span>
                </div>
                <div class="speech-bubble !border-orange-300 flex-grow">
                    <h2 class="text-base font-bold text-orange-900 mb-1">¡Panel de Profesores y Administradores! 🦉✨</h2>
                    <p class="text-xs text-orange-800">Gestiona tareas o exámenes, edita publicaciones y supervisa la actividad en tiempo real.</p>
                </div>
            </div>

            <!-- USUARIOS ACTIVOS EN TIEMPO REAL -->
            <div class="school-card-admin p-6 rounded-3xl bg-gradient-to-r from-amber-50 to-orange-50">
                <h3 class="text-sm font-bold text-orange-900 mb-3 flex items-center gap-2">🟢 Alumnos y Usuarios Activos en Tiempo Real</h3>
                {% if active_users %}
                <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
                    {% for user in active_users %}
                    <div class="bg-white p-3 rounded-2xl border border-orange-200 shadow-sm flex items-center gap-3">
                        <span class="w-3 h-3 bg-emerald-500 rounded-full animate-pulse"></span>
                        <div class="overflow-hidden">
                            <p class="text-xs font-bold text-orange-900 truncate">{{ user[0] }}</p>
                            <p class="text-[10px] text-orange-700">Activo: {{ user[1] }}</p>
                        </div>
                    </div>
                    {% endfor %}
                </div>
                {% else %}
                <p class="text-xs text-orange-800">No hay usuarios activos registrados recientemente.</p>
                {% endif %}
            </div>

            <!-- FORMULARIO EDITAR O AGREGAR TAREA/EXAMEN -->
            <div class="school-card-admin p-6 rounded-3xl">
                <h3 class="text-sm font-bold text-orange-900 mb-4">
                    {% if edit_task %}✏️ Editando: {{ edit_task[1] }} ({{ edit_task[4] }}){% else %}📌 Agregar Tarea o Examen al Calendario{% endif %}
                </h3>
                <form action="{% if edit_task %}/admin/edit/{{ edit_task[0] }}{% else %}/admin/add{% endif %}" method="POST" class="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <input type="text" name="subject" required value="{% if edit_task %}{{ edit_task[1] }}{% endif %}" placeholder="Materia (ej. Matemática)" class="bg-orange-50/40 border-2 border-orange-200 rounded-xl p-3 text-orange-900 text-sm font-medium">
                    <input type="text" name="title" required value="{% if edit_task %}{{ edit_task[2] }}{% endif %}" placeholder="Descripción de la tarea o examen" class="bg-orange-50/40 border-2 border-orange-200 rounded-xl p-3 text-orange-900 text-sm font-medium md:col-span-2">
                    <input type="date" name="due_date" required value="{% if edit_task %}{{ edit_task[3] }}{% endif %}" class="bg-orange-50/40 border-2 border-orange-200 rounded-xl p-3 text-orange-900 text-sm font-medium">
                    
                    <div class="md:col-span-2 flex items-center gap-4 bg-orange-50/30 p-3 rounded-xl border border-orange-200">
                        <span class="text-xs font-bold text-orange-900">Tipo:</span>
                        <label class="flex items-center gap-1 text-xs font-semibold text-orange-900 cursor-pointer">
                            <input type="radio" name="item_type" value="Tarea" {% if not edit_task or edit_task[4] == 'Tarea' %}checked{% endif %} class="accent-orange-500"> 📚 Tarea
                        </label>
                        <label class="flex items-center gap-1 text-xs font-semibold text-rose-800 cursor-pointer">
                            <input type="radio" name="item_type" value="Examen" {% if edit_task and edit_task[4] == 'Examen' %}checked{% endif %} class="accent-rose-500"> 📝 Examen
                        </label>
                    </div>

                    <div class="md:col-span-2 flex gap-2">
                        {% if edit_task %}
                        <a href="/" class="w-1/3 bg-slate-300 hover:bg-slate-400 text-slate-800 font-bold py-3 rounded-xl transition text-sm text-center">Cancelar</a>
                        <button type="submit" class="w-2/3 bg-amber-600 hover:bg-amber-500 text-white font-bold py-3 rounded-xl transition text-sm shadow-md">Guardar Cambios 💾</button>
                        {% else %}
                        <button type="submit" class="w-full bg-orange-500 hover:bg-orange-400 text-white font-bold py-3 rounded-xl transition text-sm shadow-md">Publicar en el Calendario ✏️</button>
                        {% endif %}
                    </div>
                </form>
            </div>

            <!-- TABLA DE GESTIÓN PROFESOR -->
            <div class="school-card-admin p-6 rounded-3xl overflow-x-auto">
                <h3 class="text-sm font-bold text-orange-900 mb-4">📋 Elementos Registrados (Tareas y Exámenes)</h3>
                <table class="w-full text-left border-collapse">
                    <thead>
                        <tr class="border-b-2 border-orange-100 text-xs font-bold text-orange-800">
                            <th class="p-3">Tipo</th><th class="p-3">Materia</th><th class="p-3">Descripción</th><th class="p-3">Fecha Límite</th><th class="p-3 text-center">Acciones</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-orange-100 text-sm">
                        {% for task in tasks %}
                        <tr>
                            <td class="p-3">
                                <span class="text-[10px] font-bold px-2.5 py-1 rounded-full {% if task[4] == 'Examen' %}bg-rose-100 text-rose-800 border border-rose-300{% else %}bg-sky-100 text-sky-800{% endif %}">
                                    {{ task[4] }}
                                </span>
                            </td>
                            <td class="p-3 font-bold text-orange-900">{{ task[1] }}</td>
                            <td class="p-3 text-amber-900/80">{{ task[2] }}</td>
                            <td class="p-3 text-amber-700 text-xs font-semibold">📅 {{ task[3] }}</td>
                            <td class="p-3 text-center flex justify-center gap-2">
                                <a href="/admin/edit/{{ task[0] }}" class="text-amber-700 bg-amber-50 border border-amber-200 px-3 py-1.5 rounded-xl font-bold text-xs transition">Editar ✏️</a>
                                <a href="/admin/delete/{{ task[0] }}" class="text-rose-600 bg-rose-50 border border-rose-200 px-3 py-1.5 rounded-xl font-bold text-xs transition">Borrar 🗑️</a>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

        {% else %}
        <!-- PANEL DE ESTUDIANTE -->
        <div class="space-y-10">
            <!-- Bienvenida -->
            <div class="flex items-center gap-4 bg-white p-6 rounded-3xl shadow-md border-2 border-sky-200">
                <div class="w-36 min-h-44 bg-sky-50 rounded-3xl flex items-center justify-center border-2 border-sky-200 shadow-md flex-shrink-0 overflow-visible">
                    {{ avatar_visual|safe }}
                </div>
                <div class="speech-bubble flex-grow">
                    <h2 class="text-base font-bold text-sky-900 mb-1">¡Selecciona un día y revisa tus pendientes y exámenes!<br>Derechos Reservados <br> Autor: Angel Mateo Chamba Albito<br> 🧩✨</h2>
                    <p class="text-xs text-sky-800">Tu personaje ya está listo. Consulta tus logros y colección en Mi perfil · ⭐ {{ student_stats[0] if student_stats else 0 }} XP · 🪙 {{ student_stats[1] if student_stats else 0 }} · 💎 {{ student_stats[2] if student_stats else 0 }}</p>
                </div>
            </div>

            <!-- APARTADO APARTE: EXÁMENES PRÓXIMOS -->
            {% set exam_list = tasks | selectattr('item_type', 'equalto', 'Examen') | list %}
            {% if exam_list %}
            <div class="bg-gradient-to-r from-rose-50 to-orange-50 border-4 border-rose-300 rounded-3xl p-6 md:p-8 shadow-md">
                <div class="flex items-center gap-3 mb-6">
                    <span class="text-3xl">📝🚨</span>
                    <div>
                        <h3 class="text-base font-bold text-rose-900">Sección de Exámenes Próximos</h3>
                        <p class="text-xs text-rose-700">Atención: Estos son tus próximos exámenes oficiales agendados por los profesores.</p>
                    </div>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {% for exam in exam_list %}
                    <div class="bg-white border-2 {% if exam.is_completed %}border-emerald-400 bg-emerald-50/30{% else %}border-rose-300{% endif %} rounded-2xl p-4 flex flex-col justify-between shadow-sm">
                        <div>
                            <div class="flex justify-between items-start mb-2">
                                <span class="text-xs font-bold px-2.5 py-0.5 rounded-full bg-rose-100 text-rose-900 border border-rose-200">📝 Examen: {{ exam.subject }}</span>
                            </div>
                            <div class="mb-2 bg-rose-50/60 border border-rose-200 px-3 py-2 rounded-xl">
                                <span class="text-[10px] font-bold text-rose-800 uppercase block">📅 Fecha de Examen:</span>
                                <span class="text-sm font-black text-rose-950">{{ exam.due_date }} <span class="text-xs font-bold text-indigo-800">({{ exam.day_name }})</span></span>
                            </div>
                            <p class="text-slate-900 font-bold text-xs {% if exam.is_completed %}line-through text-slate-400 font-normal{% endif %} mb-3">
                                {{ exam.title }}
                            </p>
                        </div>
                        <div class="pt-2 border-t border-slate-100 flex justify-between items-center">
                            <span class="text-[11px] font-bold {% if exam.is_completed %}text-emerald-700{% else %}text-rose-800{% endif %}">
                                {% if exam.is_completed %}¡Repasado / Hecho! ✅{% else %}Pendiente de Estudio ⏳{% endif %}
                            </span>
                            <a href="/toggle/{{ exam.id }}{% if selected_day %}?day={{ selected_day }}{% endif %}" class="w-8 h-8 rounded-xl border-2 {% if exam.is_completed %}bg-emerald-500 border-emerald-600 text-white shadow-md{% else %}bg-white border-rose-300 hover:bg-rose-50 text-rose-600{% endif %} flex items-center justify-center font-bold text-sm transition" title="Marcar examen">
                                {% if exam.is_completed %}✔{% else %}✓{% endif %}
                            </a>
                        </div>
                    </div>
                    {% endfor %}
                </div>
            </div>
            {% endif %}

            <!-- BOTONES DE FILTRO POR DÍA -->
            <div class="bg-white p-4 md:p-6 rounded-3xl shadow-sm border-2 border-sky-200 flex flex-wrap justify-center items-center gap-3">
                <span class="text-xs font-bold text-sky-900 mr-2">📅 Filtrar por Día:</span>
                <button onclick="triggerPuzzleAnimation('/')" class="px-4 py-2 rounded-xl text-xs font-bold transition {% if not selected_day %}bg-sky-500 text-white shadow-md scale-105{% else %}bg-sky-50 hover:bg-sky-100 text-sky-800{% endif %}">🌟 Todos</button>
                <button onclick="triggerPuzzleAnimation('/day/Lunes')" class="px-4 py-2 rounded-xl text-xs font-bold transition {% if selected_day == 'Lunes' %}bg-amber-500 text-white shadow-md scale-105{% else %}bg-amber-50 hover:bg-amber-100 text-amber-900{% endif %}">🧩 Lunes</button>
                <button onclick="triggerPuzzleAnimation('/day/Martes')" class="px-4 py-2 rounded-xl text-xs font-bold transition {% if selected_day == 'Martes' %}bg-amber-500 text-white shadow-md scale-105{% else %}bg-amber-50 hover:bg-amber-100 text-amber-900{% endif %}">🧩 Martes</button>
                <button onclick="triggerPuzzleAnimation('/day/Miércoles')" class="px-4 py-2 rounded-xl text-xs font-bold transition {% if selected_day == 'Miércoles' %}bg-amber-500 text-white shadow-md scale-105{% else %}bg-amber-50 hover:bg-amber-100 text-amber-900{% endif %}">🧩 Miércoles</button>
                <button onclick="triggerPuzzleAnimation('/day/Jueves')" class="px-4 py-2 rounded-xl text-xs font-bold transition {% if selected_day == 'Jueves' %}bg-amber-500 text-white shadow-md scale-105{% else %}bg-amber-50 hover:bg-amber-100 text-amber-900{% endif %}">🧩 Jueves</button>
                <button onclick="triggerPuzzleAnimation('/day/Viernes')" class="px-4 py-2 rounded-xl text-xs font-bold transition {% if selected_day == 'Viernes' %}bg-amber-500 text-white shadow-md scale-105{% else %}bg-amber-50 hover:bg-amber-100 text-amber-900{% endif %}">🧩 Viernes</button>
            </div>

            <!-- CALENDARIO PRINCIPAL DE TAREAS Y EXÁMENES -->
            <div id="calendar-desk-container" class="calendar-desk p-6 md:p-8">
                <div class="absolute top-0 left-1/4 binder-ring"></div>
                <div class="absolute top-0 left-1/2 binder-ring" style="transform: translateX(-50%);"></div>
                <div class="absolute top-0 right-1/4 binder-ring"></div>

                <div class="calendar-header-bar rounded-2xl mb-6 flex justify-between items-center text-white shadow-inner">
                    <div>
                        <h3 class="text-lg font-bold">{% if selected_day %}Día: {{ selected_day }}{% else %}Agenda General de Actividades{% endif %}</h3>
                        <p class="text-xs text-amber-100">Tareas y Evaluaciones ordenadas</p>
                    </div>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                    {% for task in tasks %}
                    <div class="bg-white border-2 {% if task.is_completed %}border-emerald-400 bg-emerald-50/30{% else %}{% if task.item_type == 'Examen' %}border-rose-300{% else %}border-sky-200{% endif %}{% endif %} rounded-2xl p-5 flex flex-col justify-between shadow-sm transition-all">
                        <div>
                            <div class="flex justify-between items-start mb-3">
                                <span class="text-xs font-bold px-3 py-1 rounded-full {% if task.item_type == 'Examen' %}bg-rose-100 text-rose-900{% else %}{% if task.is_completed %}bg-emerald-200 text-emerald-900{% else %}bg-indigo-100 text-indigo-900{% endif %}{% endif %}">
                                    {% if task.item_type == 'Examen' %}📝 Examen: {% else %}📚 {% endif %}{{ task.subject }}
                                </span>
                            </div>
                            <!-- FECHA -->
                            <div class="mb-3 bg-gradient-to-r from-amber-100 to-yellow-50 border-2 border-amber-300 px-3.5 py-2.5 rounded-xl">
                                <span class="text-[11px] font-bold text-amber-800 uppercase block">📅 Fecha Límite:</span>
                                <span class="text-base font-black text-amber-950">{{ task.due_date }} <span class="text-xs font-bold text-indigo-800">({{ task.day_name }})</span></span>
                            </div>
                            <!-- DESCRIPCIÓN -->
                            <div class="bg-slate-50 border border-slate-200 p-3 rounded-xl mb-4">
                                <span class="text-[10px] font-bold text-slate-500 uppercase block mb-1">📝 Detalle:</span>
                                <p class="text-slate-900 font-bold text-sm {% if task.is_completed %}line-through text-slate-400 font-normal{% endif %}">
                                    {{ task.title }}
                                </p>
                            </div>
                        </div>
                        <div class="pt-3 border-t border-slate-100 flex justify-between items-center">
                            <span class="text-xs font-bold {% if task.is_completed %}text-emerald-700{% else %}text-amber-800{% endif %}">
                                {% if task.is_completed %}¡Completado! ✅{% else %}Pendiente ⏳{% endif %}
                            </span>
                            <a href="/toggle/{{ task.id }}{% if selected_day %}?day={{ selected_day }}{% endif %}" class="w-9 h-9 rounded-xl border-2 {% if task.is_completed %}bg-emerald-500 border-emerald-600 text-white shadow-md{% else %}bg-white border-sky-300 hover:bg-sky-50 text-sky-600{% endif %} flex items-center justify-center font-bold text-base transition transform active:scale-95" title="Marcar como completada">
                                {% if task.is_completed %}✔{% else %}✓{% endif %}
                            </a>
                        </div>
                    </div>
                    {% endfor %}
                </div>
            </div>

            <!-- CALENDARIO VISUAL DE MATERIAS Y DÍAS (DINÁMICO) -->
<div class="bg-white border-4 border-amber-300 rounded-3xl p-6 md:p-8 shadow-md">
    <div class="flex items-center gap-3 mb-6">
        <span class="text-3xl">🎨 📅</span>
        <div>
            <h3 class="text-base font-bold text-amber-900">Calendario Visual de Materias por Día</h3>
            <p class="text-xs text-amber-700">Guía rápida de tus materias diarias con ilustraciones y sin textos largos.</p>
        </div>
    </div>

    <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 text-center">
        <!-- LUNES -->
        <a href="/day/Lunes" class="bg-amber-50 border-2 border-amber-200 p-4 rounded-2xl shadow-sm hover:scale-105 transition block">
            <span class="text-3xl block mb-2">🎒 📘</span>
            <h4 class="font-bold text-amber-900 text-xs uppercase">Lunes</h4>
            <p class="text-xs font-semibold text-slate-700 mt-2">{{ calendar_subjects.get('LUNES', 'Sin actividades') }}</p>
        </a>

        <!-- MARTES -->
        <a href="/day/Martes" class="bg-sky-50 border-2 border-sky-200 p-4 rounded-2xl shadow-sm hover:scale-105 transition block">
            <span class="text-3xl block mb-2">💻 ✏️</span>
            <h4 class="font-bold text-sky-900 text-xs uppercase">Martes</h4>
            <p class="text-xs font-semibold text-slate-700 mt-2">{{ calendar_subjects.get('MARTES', 'Sin actividades') }}</p>
        </a>

        <!-- MIÉRCOLES -->
        <a href="/day/Miercoles" class="bg-emerald-50 border-2 border-emerald-200 p-4 rounded-2xl shadow-sm hover:scale-105 transition block">
            <span class="text-3xl block mb-2">📜 🗺️</span>
            <h4 class="font-bold text-emerald-900 text-xs uppercase">Miércoles</h4>
            <p class="text-xs font-semibold text-slate-700 mt-2">{{ calendar_subjects.get('MIÉRCOLES', 'Sin actividades') }}</p>
        </a>

        <!-- JUEVES -->
        <a href="/day/Jueves" class="bg-purple-50 border-2 border-purple-200 p-4 rounded-2xl shadow-sm hover:scale-105 transition block">
            <span class="text-3xl block mb-2">🧪 🔬</span>
            <h4 class="font-bold text-purple-900 text-xs uppercase">Jueves</h4>
            <p class="text-xs font-semibold text-slate-700 mt-2">{{ calendar_subjects.get('JUEVES', 'Sin actividades') }}</p>
        </a>

        <!-- VIERNES -->
        <a href="/day/Viernes" class="bg-rose-50 border-2 border-rose-200 p-4 rounded-2xl shadow-sm hover:scale-105 transition col-span-2 sm:col-span-1 block">
            <span class="text-3xl block mb-2">🏀 🏆</span>
            <h4 class="font-bold text-rose-900 text-xs uppercase">Viernes</h4>
            <p class="text-xs font-semibold text-slate-700 mt-2">{{ calendar_subjects.get('VIERNES', 'Sin actividades') }}</p>
        </a>
    </div>
</div>
            </div>

            <!-- SECCIÓN HISTORIAL DE TAREAS COMPLETADAS -->
            <div id="section-completed" class="bg-emerald-50/90 border-2 border-emerald-300 rounded-3xl p-6 shadow-sm">
                <div class="flex items-center gap-2 mb-4">
                    <span class="text-2xl">🏆</span>
                    <h3 class="text-base font-bold text-emerald-900">Historial de Materias y Exámenes Terminados</h3>
                </div>

                {% set completed_tasks = all_tasks | selectattr('is_completed') | list %}
                {% if completed_tasks %}
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {% for task in completed_tasks %}
                    <div class="bg-white border-2 border-emerald-300 p-4 rounded-2xl flex justify-between items-center shadow-sm">
                        <div>
                            <span class="text-xs font-bold text-emerald-800 bg-emerald-100 px-2.5 py-0.5 rounded-full">{{ task.item_type }}: {{ task.subject }}</span>
                            <p class="text-amber-800 font-extrabold text-xs mt-1">📅 {{ task.due_date }}</p>
                            <p class="text-slate-400 font-medium text-xs line-through mt-0.5">{{ task.title }}</p>
                        </div>
                        <a href="/toggle/{{ task.id }}{% if selected_day %}?day={{ selected_day }}{% endif %}" class="text-xs font-bold bg-amber-100 hover:bg-amber-200 text-amber-900 px-3 py-1.5 rounded-xl transition">
                            Deshacer ↩️
                        </a>
                    </div>
                    {% endfor %}
                </div>
                {% else %}
                <p class="text-xs text-emerald-800 bg-white/60 p-4 rounded-2xl font-medium">📌 Haz clic en el botón verde de tus tareas o exámenes para marcarlos como terminados y verlos aquí.</p>
                {% endif %}
            </div>
        </div>
        {% endif %}
    </main>

    <footer class="text-center p-4 text-xs font-medium text-sky-800/70 border-t border-sky-200">
        Academia La Dolorosa · Calendario Escolar  Hecho por Angel Mateo Chamba Albito🍎🧩
    </footer>
    <script src="{{ url_for('static', filename='push.js') }}" defer></script>
    <script type="module" src="{{ url_for('static', filename='avatar3d.js') }}"></script>
</body>
</html>
"""

DIAS_SEMANA = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}

def process_tasks_with_days(rows):
    tasks = []
    for r in rows:
        task_id, subject, title, due_date_str, item_type, status = r[0], r[1], r[2], r[3], r[4], r[5]
        is_completed = (status == "COMPLETADO")
        day_name = "Desconocido"
        try:
            dt = datetime.strptime(due_date_str, "%Y-%m-%d")
            day_name = DIAS_SEMANA[dt.weekday()]
        except Exception:
            pass
        tasks.append({
            "id": task_id, "subject": subject, "title": title,
            "due_date": due_date_str, "day_name": day_name,
            "item_type": item_type if item_type else "Tarea",
            "status": status, "is_completed": is_completed
        })
    tasks.sort(key=lambda x: x["due_date"])
    return tasks

@app.route("/")
def index():
    user = session.get("user")
    if not user:
        return render_template_string(HTML_TEMPLATE)

    update_user_activity(user)
    conn = get_db_connection()
    cursor = conn.cursor()

    if session.get("role") == "ADMIN":
        cursor.execute("SELECT id, subject, title, due_date, item_type FROM tasks ORDER BY due_date ASC")
        tasks = cursor.fetchall()
        
        cursor.execute("SELECT email, last_active FROM active_users ORDER BY last_active DESC")
        active_users = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template_string(HTML_TEMPLATE, tasks=tasks, active_users=active_users, edit_task=None)
    else:
        is_postgres = bool(os.environ.get("DATABASE_URL"))
        ph = "%s" if is_postgres else "?"
        
        cursor.execute(f"""
            SELECT T1.id, T1.subject, T1.title, T1.due_date, T1.item_type,
            COALESCE(P.status, 'PENDIENTE') as status
            FROM tasks T1
            LEFT JOIN progress P ON T1.id = P.task_id AND P.email = {ph}
            ORDER BY T1.due_date ASC
        """, (user,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        
        tasks = process_tasks_with_days(rows)
        
        dias_semana = {"LUNES": set(), "MARTES": set(), "MIÉRCOLES": set(), "JUEVES": set(), "VIERNES": set()}
        for t in tasks:
            d_name = t.get("day_name", "").upper()
            if d_name in dias_semana and t.get("subject"):
                dias_semana[d_name].add(t["subject"])
                
        calendar_subjects = {
            day: " & ".join(list(subjects)[:2]) if subjects else "Sin actividades"
            for day, subjects in dias_semana.items()
        }

        stats=get_student_stats(user)
        return render_template_string(HTML_TEMPLATE, tasks=tasks, all_tasks=tasks, selected_day=None, calendar_subjects=calendar_subjects, student_stats=stats, avatar_visual=avatar_figure(stats[4], equipment_with_legacy(get_student_equipment(user),stats[5]), stats[6], stats[7], compact=True))

@app.route("/day/<string:day_name>")
def filter_by_day(day_name):
    user = session.get("user")
    if not user or session.get("role") != "STUDENT":
        return redirect(url_for("index"))

    update_user_activity(user)
    conn = get_db_connection()
    cursor = conn.cursor()
    
    is_postgres = bool(os.environ.get("DATABASE_URL"))
    ph = "%s" if is_postgres else "?"

    cursor.execute(f"""
        SELECT T1.id, T1.subject, T1.title, T1.due_date, T1.item_type,
        COALESCE(P.status, 'PENDIENTE') as status
        FROM tasks T1
        LEFT JOIN progress P ON T1.id = P.task_id AND P.email = {ph}
        ORDER BY T1.due_date ASC
    """, (user,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    
    all_tasks = process_tasks_with_days(rows)
    filtered_tasks = [t for t in all_tasks if t["day_name"].lower() == day_name.lower()]
    
    dias_semana = {"LUNES": set(), "MARTES": set(), "MIÉRCOLES": set(), "JUEVES": set(), "VIERNES": set()}
    for t in all_tasks:
        d_name = t.get("day_name", "").upper()
        if d_name in dias_semana and t.get("subject"):
            dias_semana[d_name].add(t["subject"])
            
    calendar_subjects = {
        day: " & ".join(list(subjects)[:2]) if subjects else "Sin actividades"
        for day, subjects in dias_semana.items()
    }

    stats=get_student_stats(user)
    return render_template_string(HTML_TEMPLATE, tasks=filtered_tasks, all_tasks=all_tasks, selected_day=day_name, calendar_subjects=calendar_subjects, student_stats=stats, avatar_visual=avatar_figure(stats[4], equipment_with_legacy(get_student_equipment(user),stats[5]), stats[6], stats[7], compact=True))

@app.route("/login", methods=["POST"])
def login():
    email = request.form.get("email").strip().lower()
    session["user"] = email
    session["show_transition"] = True
    update_user_activity(email)

    if email in [admin.lower() for admin in ADMIN_EMAILS]:
        session["role"] = "ADMIN"
        flash("¡Bienvenido al panel de profesores y administradores!")
    else:
        session["role"] = "STUDENT"
        conn = get_db_connection()
        cursor = conn.cursor()
        ph = "%s" if os.environ.get("DATABASE_URL") else "?"
        # Cada inicio suma 10 XP y cuenta una vez para el ranking.
        cursor.execute(f"INSERT INTO student_stats (email, xp, logins) VALUES ({ph}, 10, 1) ON CONFLICT(email) DO UPDATE SET xp = student_stats.xp + 10, logins = student_stats.logins + 1", (email,))
        conn.commit()
        conn.close()
        flash("¡Bienvenido a tu calendario escolar!")
    return redirect(url_for("index"))

@app.route("/dismiss_transition")
def dismiss_transition():
    session.pop("show_transition", None)
    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear()
    flash("¡Has cerrado sesión con éxito!")
    return redirect(url_for("index"))

@app.route("/admin/add", methods=["POST"])
def admin_add():
    if session.get("role") != "ADMIN":
        return redirect(url_for("index"))
    subject = request.form.get("subject")
    title = request.form.get("title")
    due_date = request.form.get("due_date")
    item_type = request.form.get("item_type", "Tarea")

    conn = get_db_connection()
    cursor = conn.cursor()
    is_postgres = bool(os.environ.get("DATABASE_URL"))
    ph = "%s" if is_postgres else "?"

    cursor.execute(f"INSERT INTO tasks (subject, title, due_date, item_type) VALUES ({ph}, {ph}, {ph}, {ph})", (subject, title, due_date, item_type))
    conn.commit()
    cursor.close()
    conn.close()
    flash("¡Nuevo elemento agregado al calendario!")
    return redirect(url_for("index"))

@app.route("/admin/edit/<int:task_id>", methods=["GET", "POST"])
def admin_edit(task_id):
    if session.get("role") != "ADMIN":
        return redirect(url_for("index"))

    conn = get_db_connection()
    cursor = conn.cursor()
    is_postgres = bool(os.environ.get("DATABASE_URL"))
    ph = "%s" if is_postgres else "?"

    if request.method == "POST":
        subject = request.form.get("subject")
        title = request.form.get("title")
        due_date = request.form.get("due_date")
        item_type = request.form.get("item_type", "Tarea")

        cursor.execute(f"UPDATE tasks SET subject = {ph}, title = {ph}, due_date = {ph}, item_type = {ph} WHERE id = {ph}", (subject, title, due_date, item_type, task_id))
        conn.commit()
        cursor.close()
        conn.close()
        flash("Elemento actualizado correctamente.")
        return redirect(url_for("index"))

    cursor.execute(f"SELECT id, subject, title, due_date, item_type FROM tasks WHERE id = {ph}", (task_id,))
    edit_task = cursor.fetchone()

    cursor.execute("SELECT id, subject, title, due_date, item_type FROM tasks ORDER BY due_date ASC")
    tasks = cursor.fetchall()
    cursor.execute("SELECT email, last_active FROM active_users ORDER BY last_active DESC")
    active_users = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template_string(HTML_TEMPLATE, tasks=tasks, active_users=active_users, edit_task=edit_task)

@app.route("/admin/delete/<int:task_id>")
def admin_delete(task_id):
    if session.get("role") != "ADMIN":
        return redirect(url_for("index"))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    is_postgres = bool(os.environ.get("DATABASE_URL"))
    ph = "%s" if is_postgres else "?"

    cursor.execute(f"DELETE FROM tasks WHERE id = {ph}", (task_id,))
    cursor.execute(f"DELETE FROM progress WHERE task_id = {ph}", (task_id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash("Elemento eliminado correctamente.")
    return redirect(url_for("index"))

@app.route("/toggle/<int:task_id>")
def toggle_progress(task_id):
    user = session.get("user")
    if not user or session.get("role") != "STUDENT":
        return redirect(url_for("index"))

    update_user_activity(user)
    day_filter = request.args.get("day")    

    conn = get_db_connection()
    cursor = conn.cursor()
    is_postgres = bool(os.environ.get("DATABASE_URL"))
    ph = "%s" if is_postgres else "?"

    cursor.execute(f"SELECT status FROM progress WHERE email = {ph} AND task_id = {ph}", (user, task_id))
    row = cursor.fetchone()

    if row is None:
        cursor.execute(f"INSERT INTO progress (email, task_id, status) VALUES ({ph}, {ph}, {ph})", (user, task_id, "COMPLETADO"))
        cursor.execute(f"SELECT task_id FROM task_xp_rewards WHERE email={ph} AND task_id={ph}",(user,task_id))
        if not cursor.fetchone():
            cursor.execute(f"INSERT INTO task_xp_rewards(email,task_id) VALUES({ph},{ph})",(user,task_id))
            cursor.execute(f"INSERT INTO student_stats(email,xp) VALUES({ph},25) ON CONFLICT(email) DO UPDATE SET xp=student_stats.xp+25",(user,))
            flash("¡Completado! Ganaste 25 XP ⭐🏆")
        else:
            flash("¡Completado y movido al historial! 🏆")
    else:
        current_status = row[0]
        new_status = "PENDIENTE" if current_status == "COMPLETADO" else "COMPLETADO"
        cursor.execute(f"UPDATE progress SET status = {ph} WHERE email = {ph} AND task_id = {ph}", (new_status, user, task_id))
        if new_status == "COMPLETADO":
            cursor.execute(f"SELECT task_id FROM task_xp_rewards WHERE email={ph} AND task_id={ph}",(user,task_id))
            if not cursor.fetchone():
                cursor.execute(f"INSERT INTO task_xp_rewards(email,task_id) VALUES({ph},{ph})",(user,task_id))
                cursor.execute(f"INSERT INTO student_stats(email,xp) VALUES({ph},25) ON CONFLICT(email) DO UPDATE SET xp=student_stats.xp+25",(user,))
                flash("¡Tarea completada! Ganaste 25 XP ⭐")
            else:
                flash("¡Marcado como completado! 🎉")
        else:
            flash("Devuelto a pendientes ↩️")

    unlocked=grant_task_backgrounds(user,cursor,ph)
    if unlocked:
        flash("¡Recompensa desbloqueada! Recibiste dos fondos gratis; equípalos desde Personalizar avatar.")
    conn.commit()
    cursor.close()
    conn.close()

    if day_filter:
        return redirect(url_for("filter_by_day", day_name=day_filter))
    return redirect(url_for("index"))


# Artículos cosméticos; los precios se descuentan en el servidor y cada compra
# queda ligada a la cuenta para evitar compras duplicadas o saldo negativo.
SHOP_ITEMS = [
    {"id":"hat_star","name":"Gorra Estrella","emoji":"🧢","kind":"accessory","slot":"hat","coins":180,"gems":0,"description":"La gorra queda puesta sobre la cabeza."},
    {"id":"glasses","name":"Lentes Geniales","emoji":"🤓","kind":"accessory","slot":"glasses","coins":240,"gems":0,"description":"Lentes colocados sobre los ojos."},
    {"id":"scarf","name":"Bufanda Arcoíris","emoji":"🧣","kind":"accessory","slot":"scarf","coins":350,"gems":0,"description":"Bufanda alrededor del cuello."},
    {"id":"hoodie","name":"Sudadera Galaxia","emoji":"🧥","kind":"accessory","slot":"outfit","color":"#7c3aed","coins":1000,"gems":30,"description":"Sudadera puesta en tu avatar. Cuesta 1000 monedas y 30 gemas."},
    {"id":"pet_cat","name":"Mascota Gatito","emoji":"🐱","kind":"pet","coins":500,"gems":0,"description":"Un compañero para tus sesiones."},
    {"id":"pet_fox","name":"Mascota Zorrito","emoji":"🦊","kind":"pet","coins":800,"gems":5,"description":"Pequeño, curioso y veloz."},
    {"id":"pet_dragon","name":"Dragón de Cristal","emoji":"🐉","kind":"pet","coins":0,"gems":45,"description":"Una mascota poco común."},
    {"id":"phrase_courage","name":"Frase: ¡Tú puedes!","emoji":"💪","kind":"phrase","coins":120,"gems":0,"description":"Un recordatorio para seguir adelante."},
    {"id":"phrase_dream","name":"Frase: Sueña en grande","emoji":"🌟","kind":"phrase","coins":180,"gems":0,"description":"Inspírate cada vez que entres."},
    {"id":"phrase_brain","name":"Frase: Cada día aprendo","emoji":"🧠","kind":"phrase","coins":250,"gems":0,"description":"Celebra cada pequeño avance."},
    {"id":"skin_gold","name":"Skin Dorada","emoji":"👑","kind":"accessory","slot":"outfit","color":"#eab308","coins":0,"gems":70,"description":"Traje dorado y corona aplicados al avatar."},
    {"id":"pet_owl","name":"Mascota Búho Sabio","emoji":"🦉","kind":"pet","coins":0,"gems":90,"description":"Una compañía especial para estudiar."},
    {"id":"outfit_ocean","name":"Uniforme Guardián del Océano","emoji":"🌊","kind":"accessory","slot":"outfit","color":"#0891b2","coins":0,"gems":95,"description":"Conjunto azul con detalles marinos."},
    {"id":"outfit_royal","name":"Traje Real de Cristal","emoji":"💎","kind":"accessory","slot":"outfit","color":"#9333ea","coins":0,"gems":125,"description":"Traje violeta de colección con brillo de cristal."},
    {"id":"hat_crown","name":"Corona de Campeón","emoji":"👑","kind":"accessory","slot":"hat","coins":0,"gems":55,"description":"Corona visible sobre tu avatar."},
    {"id":"glasses_star","name":"Visor Estelar","emoji":"🥽","kind":"accessory","slot":"glasses","coins":0,"gems":60,"description":"Visor futurista sobre los ojos."},
    {"id":"pet_phoenix","name":"Fénix de Aurora","emoji":"🦚","kind":"pet","coins":0,"gems":135,"description":"Mascota legendaria de edición especial."},
    {"id":"phrase_legend","name":"Frase: Hoy supero mis límites","emoji":"✨","kind":"phrase","coins":0,"gems":35,"description":"Frase exclusiva que flota sobre tu avatar."},
    {"id":"shirt_scarlet","name":"Camiseta Escarlata","emoji":"👕","kind":"accessory","slot":"shirt","color":"#c62828","coins":260,"gems":0,"description":"Camiseta roja de Academia La Dolorosa."},
    {"id":"shirt_champion","name":"Camisa Campeona Dorada","emoji":"👔","kind":"accessory","slot":"shirt","color":"#eab308","coins":0,"gems":28,"description":"Camisa dorada con detalles de campeón."},
    {"id":"pants_denim","name":"Pantalón Denim","emoji":"👖","kind":"accessory","slot":"pants","color":"#31547b","coins":320,"gems":0,"description":"Pantalón azul denim con costuras visibles."},
    {"id":"pants_elite","name":"Pantalón Élite","emoji":"👖","kind":"accessory","slot":"pants","color":"#26202b","coins":0,"gems":42,"description":"Pantalón oscuro de edición premium."},
    {"id":"shoes_runner","name":"Zapatillas Ganadoras","emoji":"👟","kind":"accessory","slot":"shoes","color":"#f5c531","coins":440,"gems":0,"description":"Zapatillas rojas y doradas para tu avatar."},
    {"id":"shoes_legend","name":"Zapatillas Relámpago","emoji":"👟","kind":"accessory","slot":"shoes","color":"#d8bdff","coins":0,"gems":58,"description":"Calzado brillante de colección exclusiva."},
    {"id":"aura_black","name":"Aura Sombra","emoji":"🖤","kind":"aura","slot":"aura","color":"#17131f","coins":850,"gems":12,"description":"Energía oscura animada alrededor del avatar."},
    {"id":"aura_white","name":"Aura Celestial","emoji":"🤍","kind":"aura","slot":"aura","color":"#f8fafc","coins":0,"gems":35,"description":"Aura blanca con destellos celestiales."},
    {"id":"aura_yellow","name":"Aura Solar","emoji":"🌟","kind":"aura","slot":"aura","color":"#facc15","coins":0,"gems":38,"description":"Resplandor amarillo animado."},
    {"id":"aura_red","name":"Aura Ganadora","emoji":"❤️‍🔥","kind":"aura","slot":"aura","color":"#ef3038","coins":0,"gems":40,"description":"Energía roja de campeón."},
    {"id":"aura_crown_gold","name":"Aura Corona Dorada","emoji":"👑","kind":"aura","slot":"aura","color":"#facc15","coins":0,"gems":68,"description":"Aura solar animada con corona flotante."},
    {"id":"aura_crown_ice","name":"Aura Corona de Hielo","emoji":"❄️","kind":"aura","slot":"aura","color":"#a5f3fc","coins":0,"gems":72,"description":"Aura blanca azulada con corona brillante."},
    {"id":"entry_water","name":"Entrada Marea Real","emoji":"🌊","kind":"entry","slot":"entry","coins":0,"gems":75,"description":"Aparece caminando entre olas y gotas."},
    {"id":"entry_fire","name":"Entrada Fuego Ganador","emoji":"🔥","kind":"entry","slot":"entry","coins":0,"gems":78,"description":"Entrada con llamas y chispas estilizadas."},
    {"id":"entry_millionaire","name":"Entrada Rey del Oro","emoji":"💰","kind":"entry","slot":"entry","coins":0,"gems":82,"description":"Monedas y destellos dorados acompañan la entrada."},
    {"id":"entry_pistols","name":"Entrada Doble Impacto","emoji":"🔫","kind":"entry","slot":"entry","coins":0,"gems":78,"description":"Entrada arcade con destellos y siluetas estilizadas."},
    {"id":"entry_dance","name":"Entrada Baile de Victoria","emoji":"💃","kind":"entry","slot":"entry","coins":0,"gems":70,"description":"Pasos de baile antes de posar junto a tus estadísticas."},
    {"id":"effect_frame","name":"Marco Academia de Oro","emoji":"🖼️","kind":"effect","slot":"profile_effect","coins":650,"gems":0,"description":"Marco rojo y dorado para tu ficha pública."},
    {"id":"effect_stars","name":"Estela de Estrellas","emoji":"✨","kind":"effect","slot":"profile_effect","coins":450,"gems":0,"description":"Estrellas animadas alrededor de tu tarjeta."},
    {"id":"effect_title","name":"Título: Imparable","emoji":"🏅","kind":"effect","slot":"profile_effect","coins":0,"gems":25,"description":"Título especial visible en tu perfil."},
    {"id":"background_library","name":"Biblioteca de la Academia","emoji":"📚","kind":"background","slot":"background","coins":0,"gems":0,"unlock_tasks":2,"description":"Fondo gratis al completar dos tareas: biblioteca roja y dorada."},
    {"id":"background_andes","name":"Cielo de los Andes","emoji":"⛰️","kind":"background","slot":"background","coins":0,"gems":0,"unlock_tasks":2,"description":"Fondo gratis al completar dos tareas: montañas y cielo al amanecer."},
    {"id":"background_ocean","name":"Santuario Oceánico","emoji":"🌊","kind":"background","slot":"background","coins":420,"gems":0,"description":"Un escenario azul con corrientes de agua animadas."},
    {"id":"background_fire","name":"Coliseo de Fuego","emoji":"🔥","kind":"background","slot":"background","coins":0,"gems":52,"description":"Llamas ambientales y cenizas brillantes."},
    {"id":"background_nebula","name":"Nebulosa Galáctica","emoji":"🌌","kind":"background","slot":"background","coins":650,"gems":18,"description":"Estrellas y polvo cósmico para perfiles de nivel exclusivo."},
    {"id":"background_champion","name":"Estadio del Campeón","emoji":"🏟️","kind":"background","slot":"background","coins":1000,"gems":30,"description":"Entrada de luces doradas, confeti y ambiente de final."},
]
ITEM_BY_ID = {item["id"]: item for item in SHOP_ITEMS}
for _shop_item in SHOP_ITEMS:
    _shop_item["tier"] = "Exclusivo" if _shop_item["kind"] == "entry" or (_shop_item["kind"] == "aura" and _shop_item["gems"] >= 60) or (_shop_item["kind"] == "background" and (_shop_item["gems"] >= 50 or _shop_item["coins"] >= 1000)) or _shop_item["gems"] >= 70 or (_shop_item["coins"] >= 1000 and _shop_item["gems"] >= 30) else ("Bueno" if _shop_item["gems"] or _shop_item["coins"] >= 300 else "Casual")
    _kind_category = {"pet":"mascotas", "aura":"auras", "entry":"entradas", "background":"fondos", "phrase":"accesorios", "effect":"accesorios"}.get(_shop_item["kind"])
    _shop_item["category"] = _kind_category or ("ropa" if _shop_item.get("slot") in ("outfit", "shirt", "pants", "shoes") else "accesorios")
RANK_PRIZES = {1:(1000,100), 2:(750,75), 3:(500,50), 4:(300,30), 5:(150,15)}

def grant_task_backgrounds(email, cursor, placeholder):
    """Entrega una sola vez los dos fondos gratuitos al alcanzar dos tareas terminadas."""
    cursor.execute(f"SELECT COUNT(*) FROM progress WHERE email={placeholder} AND status='COMPLETADO'",(email,))
    if cursor.fetchone()[0] < 2:
        return 0
    granted=0
    for item_id in ("background_library","background_andes"):
        cursor.execute(f"INSERT INTO shop_purchases(email,item_id) VALUES({placeholder},{placeholder}) ON CONFLICT(email,item_id) DO NOTHING",(email,item_id))
        granted += max(cursor.rowcount,0)
    return granted

def find_equipped(value, kind=None):
    """Accepta IDs nuevos y los emojis guardados por la versión anterior."""
    if not value:
        return None
    item = ITEM_BY_ID.get(value)
    if item:
        return item
    return next((x for x in SHOP_ITEMS if x["emoji"] == value and (kind is None or x["kind"] == kind)), None)

def avatar_figure(avatar, accessory="", pet="", phrase="", compact=False, full_body=False, render_3d=True):
    equipment = accessory if isinstance(accessory, dict) else {}
    legacy_wearable = accessory if isinstance(accessory, str) else ""
    wearable = find_equipped(equipment.get("outfit", legacy_wearable), "accessory")
    head_item = find_equipped(equipment.get("hat", ""), "accessory")
    eye_item = find_equipped(equipment.get("glasses", ""), "accessory")
    neck_item = find_equipped(equipment.get("scarf", ""), "accessory")
    shirt_item = find_equipped(equipment.get("shirt", ""), "accessory")
    pants_item = find_equipped(equipment.get("pants", ""), "accessory")
    shoes_item = find_equipped(equipment.get("shoes", ""), "accessory")
    if legacy_wearable:
        old_item = find_equipped(legacy_wearable, "accessory")
        if old_item and old_item.get("slot") == "hat" and not head_item: head_item = old_item
        if old_item and old_item.get("slot") == "glasses" and not eye_item: eye_item = old_item
        if old_item and old_item.get("slot") == "scarf" and not neck_item: neck_item = old_item
    companion = find_equipped(pet, "pet")
    quote = find_equipped(phrase, "phrase")
    skin = "#e9aa7d" if "🏽" in str(avatar) else "#f3c9a5"
    shirt_color = (shirt_item or wearable or {}).get("color", "#c62828")
    pants_color = (pants_item or {}).get("color", "#334155")
    shoes_color = (shoes_item or {}).get("color", "#f1f5f9")
    aura_item = find_equipped(equipment.get("aura", ""), "aura")
    background_item = find_equipped(equipment.get("background", ""), "background")
    entry_item = find_equipped(equipment.get("entry", ""), "entry")
    profile_effect = find_equipped(equipment.get("profile_effect", ""), "effect")
    tier_rank={"Casual":1,"Bueno":2,"Exclusivo":3}
    visual_items=[wearable,head_item,eye_item,neck_item,shirt_item,pants_item,shoes_item,companion,quote,aura_item,entry_item,background_item,profile_effect]
    visual_tier=max((item.get("tier","Casual") for item in visual_items if item),key=lambda tier:tier_rank.get(tier,1),default="Casual")
    hair = "#273246"
    hat = "<span class='avatar-wearable absolute z-20 text-3xl -top-1 left-1/2 -translate-x-1/2'>" + escape(head_item["emoji"]) + "</span>" if head_item else ""
    glasses_top = "top-[45px]" if full_body else ("top-[41px]" if compact else "top-[53px]")
    scarf_top = "top-[63px]" if full_body else ("top-[58px]" if compact else "top-[91px]")
    glasses = f"<span class='avatar-wearable absolute z-20 text-xl {glasses_top} left-1/2 -translate-x-1/2'>" + escape(eye_item["emoji"]) + "</span>" if eye_item else ""
    scarf = f"<span class='avatar-wearable absolute z-20 text-2xl {scarf_top} left-1/2 -translate-x-1/2'>" + escape(neck_item["emoji"]) + "</span>" if neck_item else ""
    crown = "<path d='M62 27 L67 12 L78 23 L90 7 L102 23 L113 12 L118 28 Z' fill='#facc15' stroke='#a16207' stroke-width='2'/>" if wearable and wearable["id"] == "skin_gold" else ""
    phrase_text = (quote["name"].replace("Frase: ", "") if quote else "")
    phrase_bubble = f"<div class='absolute -top-1 left-1/2 -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-full border-2 border-amber-300 bg-white px-3 py-1 text-xs font-bold text-amber-900 shadow-md'>{escape(phrase_text)} ✨</div>" if phrase_text else ""
    if companion:
        if companion["id"]=="pet_dragon":
            pet_art="<svg viewBox='0 0 64 56' class='h-12 w-14' role='img' aria-label='Dragón de cristal animado'><defs><linearGradient id='pet-dragon-grad' x2='1' y2='1'><stop stop-color='#67e8d5'/><stop offset='1' stop-color='#087f8c'/></linearGradient></defs><path d='M23 27 6 12l6 25 15 2M42 27l16-16-5 28-14 1' fill='#54d6c4' stroke='#087f8c' stroke-width='3' stroke-linejoin='round'/><ellipse cx='32' cy='37' rx='17' ry='12' fill='url(#pet-dragon-grad)'/><path d='M38 31c-1-14 7-21 17-17 7 3 4 14-2 17l-6 4' fill='url(#pet-dragon-grad)' stroke='#087f8c' stroke-width='2'/><path d='m48 15 4-9 4 8m-12 1 1-8 5 7' fill='#facc15'/><circle cx='51' cy='20' r='2' fill='#10253b'/><path d='M22 45q10 12 22 1' fill='none' stroke='#a5f3fc' stroke-width='3'/></svg>"
        elif companion["id"] in ("pet_owl","pet_phoenix"):
            pet_art="<svg viewBox='0 0 56 56' class='h-12 w-12' role='img' aria-label='Mascota ave animada'><ellipse cx='28' cy='32' rx='19' ry='21' fill='#b45335'/><circle cx='20' cy='27' r='9' fill='#fff7df'/><circle cx='36' cy='27' r='9' fill='#fff7df'/><circle cx='21' cy='28' r='3' fill='#172033'/><circle cx='35' cy='28' r='3' fill='#172033'/><path d='m28 32-5 7 10 0z' fill='#facc15'/><path d='m10 18 3-12 8 10m17 0 8-10 2 13' fill='#8b4a38'/></svg>"
        else:
            pet_art="<svg viewBox='0 0 56 56' class='h-12 w-12' role='img' aria-label='Mascota animada'><path d='m12 22 1-15 13 10m5 0L44 7l1 17' fill='#c9813f' stroke='#824723' stroke-width='2' stroke-linejoin='round'/><circle cx='28' cy='31' r='19' fill='#d9a56d'/><ellipse cx='21' cy='30' rx='2.7' ry='3.5' fill='#172033'/><ellipse cx='35' cy='30' rx='2.7' ry='3.5' fill='#172033'/><path d='m25 37 3-3 3 3q-3 4-6 0' fill='#8a4c48'/><path d='M11 37q-7 7-2 13' fill='none' stroke='#c9813f' stroke-width='4' stroke-linecap='round'/></svg>"
        pet_badge=f"<span class='avatar-pet-badge absolute bottom-4 -right-7 z-20 grid h-14 w-14 place-items-center rounded-full border border-yellow-200 bg-white/95 shadow-lg' title='{escape(companion['name'])}'>{pet_art}</span>"
    else: pet_badge=""
    size = "w-28 h-36 my-3" if compact else ("w-36 h-64" if full_body else "w-36 h-48")
    avatar_uid = hashlib.sha1(f"{skin}:{shirt_color}:{pants_color}:{shoes_color}:{hair}:{full_body}".encode()).hexdigest()[:10]
    defs = f"<defs><radialGradient id='skin3d-{avatar_uid}'><stop offset='0%' stop-color='#ffe4cc'/><stop offset='68%' stop-color='{skin}'/><stop offset='100%' stop-color='#a85643'/></radialGradient><linearGradient id='shirt3d-{avatar_uid}' x1='0' y1='0' x2='1' y2='1'><stop stop-color='#fff7ed'/><stop offset='22%' stop-color='{shirt_color}'/><stop offset='100%' stop-color='#422006'/></linearGradient><linearGradient id='hair3d-{avatar_uid}' x1='0' y1='0' x2='1' y2='1'><stop stop-color='#64748b'/><stop offset='25%' stop-color='{hair}'/><stop offset='100%' stop-color='#111827'/></linearGradient><linearGradient id='pants3d-{avatar_uid}' x1='0' y1='0' x2='1' y2='0'><stop stop-color='#94a3b8'/><stop offset='48%' stop-color='{pants_color}'/><stop offset='100%' stop-color='#0f172a'/></linearGradient><linearGradient id='shoes3d-{avatar_uid}'><stop stop-color='#ffffff'/><stop offset='100%' stop-color='{shoes_color}'/></linearGradient></defs>"
    shadow = "<ellipse cx='90' cy='303' rx='52' ry='7' fill='#0f172a' opacity='.28'/>" if full_body else "<ellipse cx='90' cy='205' rx='58' ry='6' fill='#0f172a' opacity='.16'/>"
    arms = f"<g class='avatar-arm avatar-arm-left'><path d='M49 108 Q38 105 32 119 L19 165 Q16 177 27 180 Q38 182 42 170 L62 131Z' fill='url(#skin3d-{avatar_uid})' stroke='#713f32' stroke-width='2'/><path d='M42 105 Q28 102 24 117 L19 136 L41 143 L54 116Z' fill='url(#shirt3d-{avatar_uid})'/></g><g class='avatar-arm avatar-arm-right'><path d='M131 108 Q142 105 148 119 L161 165 Q164 177 153 180 Q142 182 138 170 L118 131Z' fill='url(#skin3d-{avatar_uid})' stroke='#713f32' stroke-width='2'/><path d='M138 105 Q152 102 156 117 L161 136 L139 143 L126 116Z' fill='url(#shirt3d-{avatar_uid})'/></g>"
    legs = f"<path d='M48 205 L132 205 L126 281 L101 283 L90 231 L79 283 L54 281Z' fill='url(#pants3d-{avatar_uid})' stroke='#1e293b' stroke-width='3'/><path d='M53 278 L80 278 L77 294 L42 297 Q36 292 42 285Z M100 278 L127 278 L140 292 Q138 298 130 298 L103 296Z' fill='url(#shoes3d-{avatar_uid})' stroke='#64748b' stroke-width='3'/><path d='M90 220 L90 279' stroke='#cbd5e1' stroke-width='2' opacity='.65'/>" if full_body else ""
    shirt = f"<path d='M50 99 Q70 88 90 91 Q110 88 130 99 L151 207 L29 207Z' fill='url(#shirt3d-{avatar_uid})' stroke='#334155' stroke-width='3'/><path d='M53 101 L90 119 L127 101' fill='none' stroke='#fff7ed' stroke-width='4' opacity='.8'/><path d='M90 119 L90 198' stroke='#fff7ed' stroke-width='2' opacity='.7'/><circle cx='90' cy='140' r='2' fill='#fef3c7'/><circle cx='90' cy='163' r='2' fill='#fef3c7'/><circle cx='90' cy='186' r='2' fill='#fef3c7'/><path d='M42 185 Q57 176 72 184 L72 200 L42 200Z' fill='#ffffff' opacity='.14'/>"
    head = f"<path d='M72 79 L72 101 Q90 115 108 101 L108 79Z' fill='url(#skin3d-{avatar_uid})'/><ellipse cx='48' cy='61' rx='9' ry='14' fill='url(#skin3d-{avatar_uid})'/><ellipse cx='132' cy='61' rx='9' ry='14' fill='url(#skin3d-{avatar_uid})'/><ellipse cx='90' cy='55' rx='39' ry='46' fill='url(#skin3d-{avatar_uid})' stroke='#8b5140' stroke-width='2'/><path d='M51 52 Q46 12 85 8 Q127 7 130 47 Q116 31 101 30 Q83 19 67 33 Q60 40 51 52Z' fill='url(#hair3d-{avatar_uid})'/><path d='M61 43 Q72 34 84 39 M96 39 Q109 33 120 43' fill='none' stroke='#382a2a' stroke-width='5' stroke-linecap='round'/><ellipse cx='75' cy='56' rx='7' ry='9' fill='#fff'/><ellipse cx='105' cy='56' rx='7' ry='9' fill='#fff'/><ellipse cx='76' cy='57' rx='4' ry='6' fill='#253044'/><ellipse cx='104' cy='57' rx='4' ry='6' fill='#253044'/><circle cx='77' cy='55' r='1.8' fill='#fff'/><circle cx='105' cy='55' r='1.8' fill='#fff'/><path d='M90 58 Q82 70 90 72' fill='none' stroke='#b66f58' stroke-width='2.5' stroke-linecap='round'/><ellipse cx='66' cy='72' rx='8' ry='4' fill='#ef9b8c' opacity='.27'/><ellipse cx='114' cy='72' rx='8' ry='4' fill='#ef9b8c' opacity='.27'/><path d='M79 81 Q90 89 102 80' fill='none' stroke='#783f3a' stroke-width='3' stroke-linecap='round'/>"
    body = (legs + shirt + arms + head) if full_body else (shirt + arms + head)
    svg = f"<svg viewBox='0 0 180 {310 if full_body else 210}' class='avatar-model avatar-fallback w-full h-full' role='img' aria-label='Avatar personalizado'>{defs}{shadow}{body}{crown}</svg>"
    stage_classes = "avatar-3d-stage" if full_body else "avatar-3d-stage avatar-3d-stage-small"
    aura_class = f"avatar-aura aura-{aura_item['id']}" if aura_item else ""
    aura_fallback = f"<div class='{aura_class}' style='--aura-color:{escape(aura_item.get('color','#facc15'))}' aria-hidden='true'></div>" if aura_item else ""
    environment_class=f" environment-{background_item['id']}" if background_item else ""
    environment_art=f"<div class='avatar-environment{environment_class}' aria-hidden='true'></div>" if background_item else ""
    effect_class = f" effect-{profile_effect['id']}" if profile_effect else ""
    effect_badge = "<span class='profile-item-title'>🏅 Imparable</span>" if profile_effect and profile_effect["id"]=="effect_title" else ""
    webgl = f"<canvas class='avatar-webgl' data-view='{'full' if full_body else 'compact'}' data-skin='{skin}' data-shirt='{shirt_color}' data-shirt-equipped={'true' if shirt_item or wearable else 'false'}' data-pants='{pants_color}' data-pants-equipped={'true' if pants_item else 'false'}' data-shoes='{shoes_color}' data-shoes-equipped={'true' if shoes_item else 'false'}' data-hat='{escape(head_item['id'] if head_item else '')}' data-eyewear='{escape(eye_item['id'] if eye_item else '')}' data-scarf='{escape(neck_item['id'] if neck_item else '')}' data-scarf-color='{escape(neck_item.get('color','#b91c1c') if neck_item else '#b91c1c')}' data-pet='{escape(companion['id'] if companion else '')}' data-aura='{escape(aura_item['id'] if aura_item else '')}' data-aura-color='{escape(aura_item.get('color','#facc15') if aura_item else '#facc15')}' data-entry='{escape(equipment.get('entry',''))}' data-background='{escape(background_item['id'] if background_item else '')}' data-tier='{visual_tier.lower()}' data-gold={'true' if wearable and wearable['id']=='skin_gold' else 'false'} aria-label='Personaje humano 3D animado'></canvas>" if render_3d else ""
    outer_aura=f"has-aura aura-{aura_item['id']}" if aura_item else ""
    environment_outer=f"has-background background-{background_item['id']}" if background_item else ""
    tier_class=f"visual-tier-{visual_tier.lower()}"
    return f"<div class='relative {stage_classes} {size}{effect_class} {outer_aura} {environment_outer} {tier_class} mx-auto my-8' style='--aura-color:{escape(aura_item.get('color','#facc15') if aura_item else '#facc15')}'>{environment_art}{aura_fallback}{effect_badge}{phrase_bubble}<div class='avatar-3d-turn'><div class='avatar-3d-bob'>{webgl}{svg}</div></div>{hat}{glasses}{scarf}{pet_badge}</div>"

def achievement_badges(completed, logins, xp):
    achievements = []
    if completed >= 1: achievements.append(("🥇", "Primera tarea"))
    if completed >= 5: achievements.append(("📚", "Racha estudiosa"))
    if completed >= 20: achievements.append(("🏅", "Maestro de tareas"))
    if logins >= 1: achievements.append(("🚀", "Primer ingreso"))
    if logins >= 25: achievements.append(("🌟", "Visitante frecuente"))
    if xp >= 500: achievements.append(("💫", "500 XP"))
    return achievements

def collection_level(items):
    value = sum(x["coins"] + x["gems"] * 20 for x in items)
    if value >= 3000: return "Leyenda", value
    if value >= 1200: return "Coleccionista", value
    if value >= 400: return "Explorador", value
    return "Aprendiz", value

PAGE_TEMPLATE = """<!doctype html><html lang='es'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><script src='https://cdn.tailwindcss.com'></script><style>.avatar-3d-stage{position:relative;perspective:900px;isolation:isolate;filter:drop-shadow(0 16px 16px rgba(120,53,15,.18))}.avatar-3d-stage:before{content:'';position:absolute;inset:18% -20% 5%;border-radius:50%;background:radial-gradient(ellipse,rgba(253,224,71,.34),rgba(220,38,38,.04) 65%,transparent 72%);z-index:-1}.avatar-3d-turn{height:100%;transform-style:preserve-3d;animation:avatar-turn 7s ease-in-out infinite alternate}.avatar-3d-bob{position:relative;height:100%;animation:avatar-breathe 2.8s ease-in-out infinite;transform-origin:50% 100%}.avatar-model{overflow:visible;filter:drop-shadow(0 5px 4px rgba(15,23,42,.17));transition:opacity .2s}.avatar-webgl{position:absolute;inset:0;width:100%;height:100%;z-index:2}.avatar-webgl-ready .avatar-fallback,.avatar-webgl-ready .avatar-wearable,.avatar-webgl-ready .avatar-pet-badge{opacity:0}.avatar-arm{transform-box:fill-box;transform-origin:50% 12%}.avatar-arm-right{animation:avatar-wave 3.4s ease-in-out infinite}.top-intro{position:fixed;inset:0;z-index:90;display:grid;place-items:center;overflow:hidden;background:radial-gradient(circle at center,#991b1b 0,#450a0a 56%,#160606 100%);color:white;pointer-events:none;animation:top-intro-out 3.15s ease-in-out forwards}.top-intro:before,.top-intro:after{content:'';position:absolute;inset:-35%;background:conic-gradient(from 0deg,transparent 0 8deg,rgba(250,204,21,.28) 9deg 11deg,transparent 12deg 30deg);animation:top-rays 1.2s ease-out both}.top-intro:after{transform:rotate(13deg);opacity:.5}.top-intro-card{position:relative;text-align:center;animation:top-boom .65s cubic-bezier(.17,.89,.32,1.49) both}.top-intro-medal{font-size:5rem;filter:drop-shadow(0 0 24px #facc15);animation:medal-pulse .65s ease-in-out infinite alternate}.top-intro-title{color:#fde047;text-shadow:0 3px 0 #991b1b,0 0 25px #facc15}.top-bolt{position:absolute;width:100px;height:180px;color:#fff9b1;filter:drop-shadow(0 0 15px #fff) drop-shadow(0 0 30px #facc15);animation:bolt-flash .55s ease-in-out 2 both}.top-bolt-left{left:8%;top:12%}.top-bolt-right{right:8%;bottom:10%;transform:rotate(180deg)}@keyframes avatar-turn{0%{transform:rotateY(-8deg) rotateZ(-1deg)}100%{transform:rotateY(8deg) rotateZ(1deg)}}@keyframes avatar-breathe{0%,100%{transform:translateY(0) scale(1)}50%{transform:translateY(-5px) scale(1.012)}}@keyframes avatar-wave{0%,72%,100%{transform:rotate(0)}82%{transform:rotate(-7deg)}90%{transform:rotate(3deg)}}@keyframes top-rays{0%{transform:scale(.2) rotate(0);opacity:0}35%{opacity:1}100%{transform:scale(1.4) rotate(25deg);opacity:0}}@keyframes top-boom{0%{transform:scale(.08);opacity:0}70%{transform:scale(1.12);opacity:1}100%{transform:scale(1);opacity:1}}@keyframes medal-pulse{to{transform:scale(1.12) rotate(5deg)}}@keyframes bolt-flash{0%,100%{opacity:0;transform:translateY(-12px) scale(.8)}20%,55%{opacity:1;transform:translateY(0) scale(1)}}@keyframes top-intro-out{0%,76%{opacity:1;visibility:visible}100%{opacity:0;visibility:hidden}}@media(prefers-reduced-motion:reduce){.avatar-3d-turn,.avatar-3d-bob,.avatar-arm-right,.top-intro,.top-intro *{animation:none!important}}@media(max-width:640px){html{-webkit-text-size-adjust:100%}body{overflow-x:clip}header nav{flex-wrap:nowrap!important;overflow-x:auto;overscroll-behavior-x:contain;scrollbar-width:thin;padding-bottom:6px}header nav a{flex:0 0 auto;min-height:42px;display:inline-flex;align-items:center}main{min-width:0}.avatar-3d-stage{max-width:100%}button,a{touch-action:manipulation}.overflow-x-auto{-webkit-overflow-scrolling:touch}.entry-caption{max-width:90%;overflow:hidden;text-overflow:ellipsis}.profile-arrival,.profile-idle{min-width:0}} </style><title>{{ title }}</title></head><body class='min-h-screen bg-gradient-to-br from-amber-50 via-red-50 to-yellow-50 text-slate-800'>
<header class='bg-white/90 border-b border-red-200 p-4'><div class='max-w-5xl mx-auto flex justify-between items-center'><a class='font-black text-red-900' href='/'>🏫 Academia La Dolorosa</a><div class='text-sm font-bold'>🪙 {{ coins }}　💎 {{ gems }}　⭐ {{ xp }} XP</div></div><nav class='max-w-5xl mx-auto flex gap-2 mt-3 text-xs font-bold'><a class='bg-red-100 text-red-900 px-3 py-2 rounded-xl' href='/'>📚 Calendario</a><a class='bg-amber-100 px-3 py-2 rounded-xl' href='/shop'>🛍️ Tienda</a><a class='bg-yellow-100 px-3 py-2 rounded-xl' href='/ranking'>🏆 Ranking</a><a class='bg-purple-100 px-3 py-2 rounded-xl' href='/profile'>👤 Mi perfil</a></nav></header>
<main class='max-w-5xl mx-auto p-4 md:p-8'><div class='mb-5'><a href='/' class='text-sky-700 font-bold text-sm'>← Volver al calendario</a><h1 class='text-3xl font-black mt-3'>{{ title }}</h1><p class='text-sm text-slate-600'>{{ subtitle }}</p></div>{% with messages=get_flashed_messages() %}{% for message in messages %}<div class='bg-emerald-100 border border-emerald-300 rounded-xl p-3 mb-4'>{{ message }}</div>{% endfor %}{% endwith %}{{ body|safe }}</main><script type='importmap'>{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.186.0/build/three.module.js"}}</script><script type='module' src='{{ url_for("static", filename="avatar3d.js") }}'></script></body></html>"""

def student_only():
    return bool(session.get("user") and session.get("role") == "STUDENT")

@app.route("/service-worker.js")
def push_service_worker():
    response = send_from_directory(os.path.join(app.root_path, "static"), "push-sw.js", mimetype="application/javascript")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response

@app.get("/push/config")
def push_config():
    public_key = os.environ.get("VAPID_PUBLIC_KEY", "").strip()
    return jsonify({"enabled": bool(public_key), "publicKey": public_key})

@app.post("/push/subscribe")
def push_subscribe():
    if not student_only():
        return jsonify({"error": "Inicia sesión como estudiante para activar los avisos."}), 401
    payload = request.get_json(silent=True) or {}
    endpoint = str(payload.get("endpoint", ""))
    keys = payload.get("keys") or {}
    p256dh, auth = str(keys.get("p256dh", "")), str(keys.get("auth", ""))
    if not endpoint.startswith("https://") or not p256dh or not auth:
        return jsonify({"error": "La suscripción de notificaciones no es válida."}), 400
    conn = get_db_connection(); cur = conn.cursor(); ph = "%s" if os.environ.get("DATABASE_URL") else "?"
    cur.execute(
        f"INSERT INTO push_subscriptions(endpoint,email,p256dh,auth,created_at) VALUES({ph},{ph},{ph},{ph},{ph}) ON CONFLICT(endpoint) DO UPDATE SET email=excluded.email,p256dh=excluded.p256dh,auth=excluded.auth,created_at=excluded.created_at",
        (endpoint, session["user"], p256dh, auth, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit(); conn.close()
    return jsonify({"ok": True})

@app.post("/push/unsubscribe")
def push_unsubscribe():
    if not student_only():
        return jsonify({"error": "Inicia sesión como estudiante."}), 401
    payload = request.get_json(silent=True) or {}
    endpoint = str(payload.get("endpoint", ""))
    conn = get_db_connection(); cur = conn.cursor(); ph = "%s" if os.environ.get("DATABASE_URL") else "?"
    cur.execute(f"DELETE FROM push_subscriptions WHERE endpoint={ph} AND email={ph}", (endpoint, session["user"]))
    conn.commit(); conn.close()
    return jsonify({"ok": True})

def get_student_stats(email, cursor=None):
    own = cursor is None
    conn = get_db_connection() if own else None
    cursor = conn.cursor() if own else cursor
    is_postgres = bool(os.environ.get("DATABASE_URL"))
    ph = "%s" if is_postgres else "?"
    cursor.execute(f"SELECT xp, coins, gems, logins, avatar, accessory, pet, phrase FROM student_stats WHERE email = {ph}", (email,))
    row = cursor.fetchone()
    if own:
        conn.close()
    return row or (0,0,0,0,"🧑🏻‍🎓","","","")

def get_student_equipment(email, cursor=None):
    own = cursor is None
    conn = get_db_connection() if own else None
    cursor = conn.cursor() if own else cursor
    ph = "%s" if os.environ.get("DATABASE_URL") else "?"
    cursor.execute(f"SELECT slot,item_id FROM student_equipment WHERE email={ph}",(email,))
    equipment = dict(cursor.fetchall())
    if own: conn.close()
    return equipment

def equipment_with_legacy(equipment, legacy_accessory):
    resolved = dict(equipment or {})
    old_item = find_equipped(legacy_accessory, "accessory")
    if old_item:
        resolved.setdefault(old_item.get("slot", "outfit"), old_item["id"])
    return resolved

def render_student_page(title, subtitle, body, email=None):
    stats = get_student_stats(email or session["user"])
    push_control = "<button id='push-notification-control' type='button' class='fixed bottom-4 right-4 z-50 rounded-full border-2 border-emerald-200 bg-emerald-700 px-4 py-3 text-sm font-black text-white shadow-xl'>🔔 Activar recordatorios</button><script src='/static/push.js' defer></script>"
    body = push_control + body
    return render_template_string(PAGE_TEMPLATE, title=title, subtitle=subtitle, body=body,
        xp=stats[0], coins=stats[1], gems=stats[2])

@app.route("/shop")
def shop():
    if not student_only(): return redirect(url_for("index"))
    conn=get_db_connection(); cur=conn.cursor(); ph="%s" if os.environ.get("DATABASE_URL") else "?"
    cur.execute(f"SELECT COUNT(*) FROM progress WHERE email={ph} AND status='COMPLETADO'",(session["user"],)); completed_tasks=cur.fetchone()[0]
    if grant_task_backgrounds(session["user"],cur,ph):
        conn.commit(); flash("¡Desbloqueaste dos fondos gratis por completar dos tareas!")
    cur.execute(f"SELECT item_id FROM shop_purchases WHERE email = {ph}",(session["user"],)); owned={r[0] for r in cur.fetchall()}
    conn.close()
    category=request.args.get("category","todo")
    categories=[("todo","Todo"),("ropa","Ropa"),("fondos","Fondos"),("auras","Auras"),("entradas","Entradas"),("mascotas","Mascotas"),("accesorios","Accesorios")]
    nav="<div class='flex flex-wrap gap-2 mb-5'>"+"".join(f"<a href='/shop?category={key}' class='rounded-full border-2 px-4 py-2 font-black {'bg-red-800 text-yellow-200 border-yellow-400' if category==key else 'bg-white text-red-900 border-red-100 hover:border-red-400'}'>{label}</a>" for key,label in categories)+"</div>"
    cards="<div class='grid sm:grid-cols-2 lg:grid-cols-3 gap-4'>"
    visible_items=[item for item in SHOP_ITEMS if category=="todo" or item.get("category")==category]
    for item in visible_items:
        if item["id"] in owned: owned_badge="<span class='text-emerald-700 font-bold'>Ya es tuyo</span>"
        elif item.get("unlock_tasks") and completed_tasks < item["unlock_tasks"]: owned_badge=f"<span class='font-bold text-red-700'>🔒 Completa {item['unlock_tasks']} tareas ({completed_tasks}/{item['unlock_tasks']}) para desbloquearlo gratis</span>"
        else: owned_badge=f"<form method='post' action='/shop/buy/{item['id']}'><button class='bg-amber-500 hover:bg-amber-400 text-white font-bold rounded-xl px-4 py-2'>{'Reclamar gratis' if not item['coins'] and not item['gems'] else 'Comprar'}</button></form>"
        tier=item.get("tier", "Casual")
        tier_style={"Casual":"bg-slate-100 text-slate-700","Bueno":"bg-emerald-100 text-emerald-800","Exclusivo":"bg-yellow-100 text-amber-900"}.get(tier,"bg-slate-100 text-slate-700")
        slot_label={"shirt":"Camiseta","pants":"Pantalón","shoes":"Calzado","hat":"Gorra","glasses":"Gafas","scarf":"Bufanda","outfit":"Conjunto","pet":"Mascota","phrase":"Frase","aura":"Aura","entry":"Entrada de perfil","profile_effect":"Efecto de perfil"}.get(item.get("slot",item["kind"]),"Artículo")
        cards+=f"<article class='bg-white border-2 border-amber-100 rounded-2xl p-5 shadow-sm'><div class='flex items-center justify-between'><div class='text-5xl'>{item['emoji']}</div><span class='rounded-full px-3 py-1 text-xs font-black {tier_style}'>{tier}</span></div><h2 class='font-black mt-3'>{item['name']}</h2><p class='text-xs font-bold uppercase tracking-wide text-red-700'>{slot_label}</p><p class='text-sm text-slate-600 min-h-10'>{item['description']}</p><p class='font-bold my-3'>🪙 {item['coins']}　💎 {item['gems']}</p>{owned_badge}</article>"
    return render_student_page("Tienda de la academia","Explora por categoría y canjea artículos con monedas o gemas.",nav+cards+"</div><a class='inline-flex mt-5 rounded-xl bg-red-800 px-4 py-3 font-bold text-white' href='/customize'>🎒 Abrir personalizador e inventario</a>")

@app.route("/shop/buy/<item_id>", methods=["POST"])
def shop_buy(item_id):
    if not student_only(): return redirect(url_for("index"))
    item=ITEM_BY_ID.get(item_id)
    if not item: return redirect(url_for("shop"))
    email=session["user"]; conn=get_db_connection(); cur=conn.cursor(); ph="%s" if os.environ.get("DATABASE_URL") else "?"
    if item.get("unlock_tasks"):
        cur.execute(f"SELECT COUNT(*) FROM progress WHERE email={ph} AND status='COMPLETADO'",(email,))
        if cur.fetchone()[0] < item["unlock_tasks"]:
            flash(f"Completa {item['unlock_tasks']} tareas para desbloquear este fondo gratis."); conn.close(); return redirect(url_for("shop", category="fondos"))
    cur.execute(f"SELECT coins,gems FROM student_stats WHERE email={ph}",(email,)); balance=cur.fetchone() or (0,0)
    cur.execute(f"SELECT item_id FROM shop_purchases WHERE email={ph} AND item_id={ph}",(email,item_id))
    if cur.fetchone(): flash("Ya tienes este artículo.")
    elif balance[0] < item["coins"] or balance[1] < item["gems"]: flash("Aún no tienes suficientes monedas o gemas.")
    else:
        cur.execute(f"UPDATE student_stats SET coins=coins-{ph}, gems=gems-{ph} WHERE email={ph}",(item["coins"],item["gems"],email))
        cur.execute(f"INSERT INTO shop_purchases(email,item_id) VALUES({ph},{ph})",(email,item_id)); flash("¡Artículo comprado! Ya puedes equiparlo en tu perfil.")
    conn.commit(); conn.close(); return redirect(url_for("shop"))

@app.route("/profile", methods=["GET","POST"])
def profile():
    if not student_only(): return redirect(url_for("index"))
    email=session["user"]; conn=get_db_connection(); cur=conn.cursor(); ph="%s" if os.environ.get("DATABASE_URL") else "?"
    if request.method=="POST":
        field=request.form.get("field"); item_id=request.form.get("item_id","")
        allowed={"pet":"pet","phrase":"phrase"}
        item=ITEM_BY_ID.get(item_id)
        if field=="avatar":
            avatar=request.form.get("avatar","🧑🏻‍🎓")
            if avatar in ("🧑🏻‍🎓","👩🏻‍🎓","👨🏻‍🎓","🧑🏽‍🎓","👩🏽‍🎓","👨🏽‍🎓"):
                cur.execute(f"UPDATE student_stats SET avatar={ph} WHERE email={ph}",(avatar,email)); flash("Avatar actualizado.")
        elif item and field==item["kind"] and field in ("accessory","pet","phrase","aura","entry","effect","background"):
            cur.execute(f"SELECT item_id FROM shop_purchases WHERE email={ph} AND item_id={ph}",(email,item_id))
            if cur.fetchone():
                slot=item.get("slot","outfit")
                cur.execute(f"INSERT INTO student_equipment(email,slot,item_id) VALUES({ph},{ph},{ph}) ON CONFLICT(email,slot) DO UPDATE SET item_id=excluded.item_id",(email,slot,item_id))
                if field=="accessory":
                    if slot=="outfit": cur.execute(f"UPDATE student_stats SET accessory={ph} WHERE email={ph}",(item_id,email))
                elif field in ("pet","phrase"):
                    cur.execute(f"UPDATE student_stats SET {allowed[field]}={ph} WHERE email={ph}",(item_id,email))
                flash("¡Equipado! El artículo ya está activo en tu avatar o perfil.")
            else: flash("Primero debes comprar ese artículo en la tienda.")
        conn.commit()
    grant_task_backgrounds(email,cur,ph); conn.commit()
    cur.execute(f"SELECT item_id FROM shop_purchases WHERE email={ph}",(email,)); owned=[ITEM_BY_ID[x[0]] for x in cur.fetchall() if x[0] in ITEM_BY_ID]
    stats=get_student_stats(email,cur)
    cur.execute(f"SELECT COUNT(*) FROM progress WHERE email={ph} AND status='COMPLETADO'",(email,)); completed=cur.fetchone()[0]
    equipment=equipment_with_legacy(get_student_equipment(email,cur),stats[5])
    conn.close()
    level, collection_value = collection_level(owned)
    badges = achievement_badges(completed, stats[3], stats[0])
    options="".join(f"<option value='{a}' {'selected' if a==stats[4] else ''}>{a}</option>" for a in ("🧑🏻‍🎓","👩🏻‍🎓","👨🏻‍🎓","🧑🏽‍🎓","👩🏽‍🎓","👨🏽‍🎓"))
    current_accessory=find_equipped(equipment.get("outfit",stats[5]),"accessory"); current_pet=find_equipped(stats[6],"pet"); current_phrase=find_equipped(stats[7],"phrase")
    avatar_html=avatar_figure(stats[4],equipment,stats[6],stats[7],full_body=True)
    badge_html="".join(f"<span class='inline-flex items-center gap-1 rounded-full bg-yellow-100 border border-yellow-300 px-3 py-2 text-sm font-bold' title='{name}'>{icon} {name}</span>" for icon,name in badges) or "<p class='text-sm text-slate-500'>Completa tareas y entra a la app para desbloquear insignias.</p>"
    body=f"<section class='bg-white rounded-3xl p-6 shadow'><div class='grid md:grid-cols-[220px_1fr] gap-6 items-center'><div class='rounded-3xl bg-gradient-to-b from-sky-50 to-amber-50 p-3'>{avatar_html}</div><div><h2 class='text-xl font-black'>{escape(email)}</h2><p class='text-lg font-black text-purple-800'>Nivel de colección: {level}</p><p class='text-sm text-slate-600'>Valor de colección: {collection_value} puntos según tus artículos.</p><p class='mt-3 text-sm'>Ropa: {escape(current_accessory['name'] if current_accessory else 'Sin equipar')} · Mascota: {escape(current_pet['name'] if current_pet else 'Sin mascota')}</p><p class='text-sm'>Frase: {escape(current_phrase['name'].replace('Frase: ','') if current_phrase else 'Sin frase')}</p></div></div><div class='grid grid-cols-2 md:grid-cols-4 gap-3 mt-6 text-center'><div class='bg-sky-50 p-4 rounded-xl'><b>{stats[0]}</b><br>XP</div><div class='bg-emerald-50 p-4 rounded-xl'><b>{completed}</b><br>Tareas</div><div class='bg-amber-50 p-4 rounded-xl'><b>{stats[1]}</b><br>Monedas</div><div class='bg-purple-50 p-4 rounded-xl'><b>{stats[2]}</b><br>Gemas</div></div><h3 class='font-bold mt-6 mb-2'>Insignias de logro</h3><div class='flex flex-wrap gap-2'>{badge_html}</div><h3 class='font-bold mt-6 mb-2'>Cambiar avatar</h3><form method='post' class='flex gap-2'><input type='hidden' name='field' value='avatar'><select class='border rounded-xl p-2' name='avatar'>{options}</select><button class='bg-sky-500 text-white rounded-xl px-4 font-bold'>Guardar</button></form><h3 class='font-bold mt-6 mb-2'>Tu colección · pulsa Equipar para verlo puesto</h3><div class='grid sm:grid-cols-2 gap-3'>"
    for item in owned:
        field=item["kind"]
        equipped = (item['id'] in (stats[6],stats[7])) if field in ('pet','phrase') else (equipment.get(item.get('slot','outfit'))==item['id'])
        body+=f"<form method='post' class='bg-slate-50 p-3 rounded-xl flex justify-between items-center'><input type='hidden' name='field' value='{field}'><input type='hidden' name='item_id' value='{item['id']}'><span>{item['emoji']} {item['name']}</span><button class='text-sky-700 font-bold'>{'Equipado ✓' if equipped else 'Equipar'}</button></form>"
    body+="</div><a href='/customize' class='inline-flex mt-5 rounded-xl bg-red-800 px-4 py-3 font-black text-white'>🎒 Abrir personalizador completo</a></section>"
    return render_student_page("Mi perfil","Tu avatar, estadísticas y artículos equipados.",body,email)

@app.route("/customize", methods=["GET","POST"])
def customize_avatar():
    if not student_only(): return redirect(url_for("index"))
    email=session["user"]; conn=get_db_connection(); cur=conn.cursor(); ph="%s" if os.environ.get("DATABASE_URL") else "?"
    if request.method=="POST":
        item_id=request.form.get("item_id",""); item=ITEM_BY_ID.get(item_id)
        if request.form.get("action")=="unequip":
            slot=request.form.get("slot","")
            if slot in {x.get("slot") for x in SHOP_ITEMS}:
                cur.execute(f"DELETE FROM student_equipment WHERE email={ph} AND slot={ph}",(email,slot))
                if slot=="outfit": cur.execute(f"UPDATE student_stats SET accessory='' WHERE email={ph}",(email,))
                if slot in ("pet","phrase"): cur.execute(f"UPDATE student_stats SET {slot}='' WHERE email={ph}",(email,))
                flash("Artículo retirado del avatar.")
        elif item:
            cur.execute(f"SELECT 1 FROM shop_purchases WHERE email={ph} AND item_id={ph}",(email,item_id))
            if cur.fetchone():
                slot=item.get("slot","outfit")
                cur.execute(f"INSERT INTO student_equipment(email,slot,item_id) VALUES({ph},{ph},{ph}) ON CONFLICT(email,slot) DO UPDATE SET item_id=excluded.item_id",(email,slot,item_id))
                if item["kind"]=="accessory" and slot=="outfit": cur.execute(f"UPDATE student_stats SET accessory={ph} WHERE email={ph}",(item_id,email))
                if item["kind"] in ("pet","phrase"): cur.execute(f"UPDATE student_stats SET {item['kind']}={ph} WHERE email={ph}",(item_id,email))
                flash(f"{item['name']} equipado.")
            else: flash("Ese artículo aún no está en tu inventario.")
        conn.commit()
    grant_task_backgrounds(email,cur,ph); conn.commit()
    cur.execute(f"SELECT item_id FROM shop_purchases WHERE email={ph}",(email,)); owned=[ITEM_BY_ID[x[0]] for x in cur.fetchall() if x[0] in ITEM_BY_ID]
    stats=get_student_stats(email,cur); equipment=equipment_with_legacy(get_student_equipment(email,cur),stats[5])
    # Las prendas antiguas de mascota y frase también se conservan al migrar al inventario nuevo.
    if stats[6]: equipment.setdefault("pet",stats[6])
    if stats[7]: equipment.setdefault("phrase",stats[7])
    conn.close()
    avatar_html=avatar_figure(stats[4],equipment,equipment.get("pet",stats[6]),equipment.get("phrase",stats[7]),full_body=True)
    groups=[("ropa","Ropa"),("fondos","Fondos"),("auras","Auras"),("entradas","Entradas"),("mascotas","Mascotas"),("accesorios","Accesorios")]
    tabs="<div class='flex flex-wrap gap-2 mb-5'>"+"".join(f"<button type='button' data-inventory-tab='{key}' class='inventory-tab rounded-full border-2 border-red-100 bg-white px-4 py-2 font-black text-red-900'>{label}</button>" for key,label in groups)+"</div>"
    cards="<div class='grid gap-3 sm:grid-cols-2 lg:grid-cols-3'>"
    for item in owned:
        slot=item.get("slot","outfit"); equipped=equipment.get(slot)==item["id"]
        cards+=f"<article data-inventory-item='{item['category']}' class='inventory-card rounded-2xl border-2 {'border-yellow-400 bg-yellow-50' if equipped else 'border-red-100 bg-white'} p-4 shadow-sm'><div class='flex items-center justify-between'><span class='text-4xl'>{item['emoji']}</span><span class='rounded-full bg-red-100 px-2 py-1 text-xs font-black text-red-900'>{item['tier']}</span></div><h3 class='mt-2 font-black'>{item['name']}</h3><p class='mb-3 text-xs text-slate-600'>{item['description']}</p><form method='post' class='flex gap-2'>"
        if equipped: cards+=f"<input type='hidden' name='action' value='unequip'><input type='hidden' name='slot' value='{slot}'><button class='w-full rounded-xl border border-red-200 px-3 py-2 font-bold text-red-800'>Quitar</button>"
        else: cards+=f"<input type='hidden' name='item_id' value='{item['id']}'><button class='w-full rounded-xl bg-red-800 px-3 py-2 font-bold text-yellow-100 hover:bg-red-700'>Previsualizar y equipar</button>"
        cards+="</form></article>"
    cards+="</div>" if owned else "<div class='rounded-2xl bg-white p-6 text-slate-600'>Tu inventario está vacío. Visita la tienda para conseguir artículos.</div>"
    script="<script>document.querySelectorAll('[data-inventory-tab]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('[data-inventory-tab]').forEach(x=>x.classList.remove('bg-red-800','text-yellow-100'));b.classList.add('bg-red-800','text-yellow-100');document.querySelectorAll('[data-inventory-item]').forEach(c=>c.hidden=c.dataset.inventoryItem!==b.dataset.inventoryTab)}));const first=document.querySelector('[data-inventory-tab]');if(first)first.click();</script>"
    body=f"<div class='grid items-start gap-6 lg:grid-cols-[300px_1fr]'><section class='rounded-3xl border-2 border-yellow-300 bg-gradient-to-b from-red-50 to-amber-50 p-4'><h2 class='text-center font-black text-red-900'>Vista previa</h2>{avatar_html}<p class='text-center text-xs text-slate-600'>Los cambios se guardan al equipar cada artículo.</p></section><section><h2 class='mb-1 text-xl font-black text-red-900'>🎒 Tu inventario</h2><p class='mb-4 text-sm text-slate-600'>Selecciona una categoría y equipa tus artículos comprados.</p>{tabs}{cards}<a href='/shop' class='mt-5 inline-flex rounded-xl bg-amber-400 px-4 py-3 font-black text-red-950'>Ir a la tienda</a></section></div>{script}"
    return render_student_page("Personalizar avatar","Tu vestidor: organiza y equipa todo lo que has conseguido.",body,email)

@app.route("/ranking")
def ranking():
    if not student_only(): return redirect(url_for("index"))
    conn=get_db_connection(); cur=conn.cursor()
    cur.execute("SELECT email, COALESCE(xp,0), COALESCE(coins,0), COALESCE(gems,0), COALESCE(logins,0), avatar, accessory, pet, phrase FROM student_stats")
    rows=cur.fetchall(); students=[]
    for row in rows:
        cur.execute("SELECT COUNT(*) FROM progress WHERE email = " + ("%s" if os.environ.get("DATABASE_URL") else "?") + " AND status='COMPLETADO'", (row[0],)); completed=cur.fetchone()[0]
        students.append({"email":row[0],"xp":row[1],"coins":row[2],"gems":row[3],"logins":row[4],"avatar":row[5],"accessory":row[6],"pet":row[7],"phrase":row[8],"equipment":equipment_with_legacy(get_student_equipment(row[0],cur),row[6]),"completed":completed,"score":completed+row[4]})
    students.sort(key=lambda s:(-s["score"],-s["xp"],s["email"].lower()))
    # Premio único por puesto y estudiante; consultar ranking no vuelve a pagar.
    is_pg=bool(os.environ.get("DATABASE_URL")); ph="%s" if is_pg else "?"
    for position,s in enumerate(students[:5],1):
        cur.execute(f"SELECT rank FROM rank_rewards WHERE email={ph} AND rank={ph}",(s["email"],position))
        if not cur.fetchone():
            coins,gems=RANK_PRIZES[position]
            cur.execute(f"UPDATE student_stats SET coins=coins+{ph}, gems=gems+{ph} WHERE email={ph}",(coins,gems,s["email"]))
            cur.execute(f"INSERT INTO rank_rewards(email,rank,awarded_at) VALUES({ph},{ph},{ph})",(s["email"],position,datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            s["coins"]+=coins; s["gems"]+=gems
    conn.commit(); conn.close()
    body="<div class='overflow-x-auto bg-white rounded-2xl shadow border-2 border-red-200'><table class='w-full text-left'><thead class='bg-gradient-to-r from-red-800 to-red-600 text-yellow-100'><tr><th class='p-3'>Puesto</th><th class='p-3'>Estudiante</th><th class='p-3'>Tareas</th><th class='p-3'>Inicios</th><th class='p-3'>Puntos</th><th class='p-3'>Premio</th><th class='p-3'></th></tr></thead><tbody>"
    for pos,s in enumerate(students,1):
        prize=RANK_PRIZES.get(pos,(0,0)); top=pos<=5
        figure=avatar_figure(s['avatar'],s['equipment'],s['pet'],s['phrase'],compact=True,render_3d=False)
        body+=f"<tr class='border-t {'bg-yellow-100 font-bold' if top else 'hover:bg-red-50'}'><td class='p-3'>{'👑 ' if top else ''}{pos}</td><td class='p-3'><div class='flex items-center gap-3'>{figure}<div><a class='font-black text-red-800 hover:text-red-600 underline decoration-yellow-500 decoration-2' href='/profile/{pos}'>{escape(str(s['email']))}</a><div class='text-xs text-slate-600'>⭐ {s['xp']} XP</div></div></div></td><td class='p-3'>{s['completed']}</td><td class='p-3'>{s['logins']}</td><td class='p-3 font-black'>{s['score']}</td><td class='p-3'>{'🪙 '+str(prize[0])+' 💎 '+str(prize[1]) if top else '—'}</td><td class='p-3'><a class='rounded-xl bg-red-700 px-3 py-2 font-bold text-white hover:bg-red-600' href='/profile/{pos}'>Ver ficha</a></td></tr>"
    body+="</tbody></table></div><p class='text-xs text-slate-500 mt-3'>Puntos del ranking = tareas completadas + inicios de sesión. Los premios se entregan una sola vez por estudiante y puesto.</p>"
    return render_student_page("Ranking de estudiantes","Ordenado por tareas completadas más inicios de sesión.",body)

@app.route("/profile/<int:position>")
def public_profile(position):
    if not student_only(): return redirect(url_for("index"))
    conn=get_db_connection(); cur=conn.cursor(); cur.execute("SELECT email,xp,coins,gems,logins,avatar,accessory,pet,phrase FROM student_stats"); rows=cur.fetchall(); data=[]
    for row in rows:
        ph="%s" if os.environ.get("DATABASE_URL") else "?"; cur.execute(f"SELECT COUNT(*) FROM progress WHERE email={ph} AND status='COMPLETADO'",(row[0],)); done=cur.fetchone()[0]
        data.append((done+row[4],row))
    data.sort(key=lambda x:(-x[0],-x[1][1],x[1][0].lower()))
    if position<1 or position>len(data): conn.close(); return redirect(url_for("ranking"))
    _,r=data[position-1]; ph="%s" if os.environ.get("DATABASE_URL") else "?"; cur.execute(f"SELECT COUNT(*) FROM progress WHERE email={ph} AND status='COMPLETADO'",(r[0],)); completed=cur.fetchone()[0]
    cur.execute(f"SELECT item_id FROM shop_purchases WHERE email={ph}",(r[0],)); owned=[ITEM_BY_ID[x[0]] for x in cur.fetchall() if x[0] in ITEM_BY_ID]
    equipment=equipment_with_legacy(get_student_equipment(r[0],cur),r[6])
    conn.close()
    level, collection_value=collection_level(owned); badges=achievement_badges(completed,r[4],r[1])
    figure=avatar_figure(r[5],equipment,equipment.get("pet",r[7]),equipment.get("phrase",r[8]),full_body=True)
    entry_item=find_equipped(equipment.get("entry",""),"entry")
    background_item=find_equipped(equipment.get("background",""),"background")
    profile_tier=max((ITEM_BY_ID.get(item_id,{}).get("tier","Casual") for item_id in list(equipment.values())+[r[7],r[8]]),key=lambda tier:{"Casual":1,"Bueno":2,"Exclusivo":3}.get(tier,1),default="Casual")
    entry_class=f"profile-arrival arrival-{entry_item['id']}" if entry_item else "profile-idle"
    background_class=f"profile-bg-{background_item['id']}" if background_item else ""
    entry_caption=f"<span class='entry-caption'>{escape(entry_item['name'])}</span>" if entry_item else ""
    badge_html="".join(f"<span class='inline-flex items-center gap-1 rounded-full bg-yellow-300/15 border border-yellow-200/50 px-3 py-2 text-sm font-bold text-yellow-100'>{icon} {name}</span>" for icon,name in badges)
    rating=min(99,40+(r[1]//25)); display_name=escape(str(r[0]).split("@")[0].replace("."," ").title())
    points=completed+r[4]
    body=f"""<section class='relative overflow-hidden rounded-[2rem] border-4 border-yellow-300 bg-gradient-to-br from-red-950 via-red-800 to-rose-600 text-white shadow-2xl'>
      <div class='absolute -right-12 -top-20 h-72 w-72 rounded-full border-[28px] border-yellow-300/10'></div><div class='absolute -left-16 bottom-0 h-48 w-48 rounded-full bg-red-500/20 blur-2xl'></div>
      <div class='relative flex flex-wrap items-center justify-between gap-3 border-b border-yellow-200/30 bg-black/10 px-6 py-4'><div><p class='text-xs font-black tracking-[.25em] text-yellow-200'>ACADEMIA LA DOLOROSA · TEMPORADA ESCOLAR</p><p class='mt-1 text-sm font-bold text-red-100'>FICHA DEL ESTUDIANTE</p></div><span class='rounded-full border border-yellow-200/50 bg-yellow-300/15 px-4 py-2 text-sm font-black text-yellow-100'>{escape(level)} · {collection_value} VAL</span></div>
      <div class='relative grid items-center gap-2 p-5 md:grid-cols-[.85fr_1.15fr] md:p-8'>
        <div class='relative {entry_class} {background_class} flex min-h-[330px] items-end justify-center overflow-hidden rounded-[1.5rem] border border-yellow-200/25 bg-gradient-to-b from-red-700/40 via-red-900/20 to-black/20 px-2 pt-8' data-entry='{escape(entry_item["id"] if entry_item else "")}' data-background='{escape(background_item["id"] if background_item else "")}' data-tier='{profile_tier.lower()}'>
          <div class='entry-atmosphere' aria-hidden='true'></div><div class='absolute bottom-8 h-8 w-40 rounded-[50%] bg-yellow-300/25 blur-md'></div>{entry_caption}{figure}<span class='absolute bottom-3 left-4 z-10 text-[10px] font-black tracking-[.2em] text-yellow-100/70'>AVATAR · EN MOVIMIENTO</span></div>
        <div class='py-3 md:pl-4'><div class='flex items-start gap-4'><div class='flex h-24 w-24 shrink-0 flex-col items-center justify-center rounded-2xl border-2 border-yellow-200 bg-gradient-to-br from-yellow-300 to-amber-500 text-red-950 shadow-xl'><span class='text-4xl font-black leading-none'>{rating}</span><span class='mt-1 text-[10px] font-black tracking-widest'>OVR</span></div><div class='min-w-0'><p class='text-xs font-black tracking-[.2em] text-yellow-200'>#{position} · PERFIL DE JUGADOR</p><h2 class='mt-1 break-words text-3xl font-black uppercase leading-tight md:text-4xl'>{display_name}</h2><p class='mt-2 text-sm font-bold text-red-100'>Estudiante · Nivel {escape(level)}</p></div></div>
          <div class='mt-7 grid grid-cols-2 gap-3'><div class='rounded-2xl border border-yellow-200/30 bg-black/15 p-4'><p class='text-[10px] font-black tracking-widest text-yellow-200'>APRENDIZAJE</p><p class='mt-1 text-2xl font-black'>{completed}</p><p class='text-xs text-red-100'>tareas terminadas</p></div><div class='rounded-2xl border border-yellow-200/30 bg-black/15 p-4'><p class='text-[10px] font-black tracking-widest text-yellow-200'>CONSTANCIA</p><p class='mt-1 text-2xl font-black'>{r[4]}</p><p class='text-xs text-red-100'>inicios de sesión</p></div><div class='rounded-2xl border border-yellow-200/30 bg-black/15 p-4'><p class='text-[10px] font-black tracking-widest text-yellow-200'>EXPERIENCIA</p><p class='mt-1 text-2xl font-black'>{r[1]}</p><p class='text-xs text-red-100'>XP acumulados</p></div><div class='rounded-2xl border border-yellow-200/30 bg-black/15 p-4'><p class='text-[10px] font-black tracking-widest text-yellow-200'>PUNTOS</p><p class='mt-1 text-2xl font-black'>{points}</p><p class='text-xs text-red-100'>puntos de ranking</p></div></div>
        </div>
      </div><div class='relative border-t border-yellow-200/30 bg-black/10 px-6 py-5'><div class='mb-3 flex items-center gap-2'><span class='text-xl'>🏅</span><h3 class='font-black tracking-wide text-yellow-100'>INSIGNIAS DESBLOQUEADAS</h3></div><div class='flex flex-wrap gap-2'>{badge_html or "<span class='text-sm text-red-100'>Sigue aprendiendo para ganar tu primera insignia.</span>"}</div><p class='mt-4 text-xs text-red-100/80'>Estadísticas académicas del calendario · Colección valorada según los artículos obtenidos.</p></div>
    </section><div class='mt-5 flex flex-wrap gap-3'><a class='rounded-xl bg-red-800 px-5 py-3 font-bold text-white shadow hover:bg-red-700' href='/ranking'>← Volver al ranking</a><a class='rounded-xl border-2 border-yellow-400 bg-yellow-300 px-5 py-3 font-black text-red-950 shadow hover:bg-yellow-200' href='/profile'>Ver mi perfil</a></div>"""
    if position <= 5:
        top_intro="""<div class='top-intro' id='top-intro' role='status' aria-live='polite'><span class='top-bolt top-bolt-left'>⚡</span><span class='top-bolt top-bolt-right'>⚡</span><div class='top-intro-card'><div class='top-intro-medal'>🏆</div><p class='text-xs font-black tracking-[.3em] text-yellow-200'>ACADEMIA LA DOLOROSA</p><h2 class='top-intro-title'>¡BOOM!</h2><p class='text-xl font-black text-yellow-100'>¡ENHORABUENA!</p><p class='mt-1 font-bold text-white'>¡ESTÁS EN EL TOP 5!</p></div></div>"""
        body=top_intro+body
    return render_student_page("Ficha de jugador", "Rendimiento, nivel y logros de la academia.", body)

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
