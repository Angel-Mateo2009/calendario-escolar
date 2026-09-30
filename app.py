import os
import psycopg2
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, session, flash

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
    if is_postgres:
        cursor.execute("DROP TABLE IF EXISTS progress CASCADE;")
        conn.commit()
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
    
    conn.commit()
    cursor.close()
    conn.close()
    
    # Insertar elementos iniciales si la tabla está vacía
    cursor.execute("SELECT COUNT(*) FROM tasks")
    count = cursor.fetchone()[0]
    if count == 0:
        hoy_str = datetime.now().strftime("%Y-%m-")
        initial_tasks = [
            ("Biología", "Completar trabajo en clase y firmar documentos", hoy_str + "05", "Tarea"),
            ("FOL", "Examen Parcial de Corrección", hoy_str + "06", "Examen"),
            ("Ofimática", "Corrección de Lección", hoy_str + "07", "Tarea"),
            ("Historia", "Pasar materia y dibujar el mapa", hoy_str + "10", "Tarea"),
            ("Matemática", "Evaluación de la plataforma", hoy_str + "04", "Examen"),
            ("Lengua", "Realizar un marco con 5 compromisos", hoy_str + "12", "Tarea"),
            ("Química", "Lección escrita del libro", hoy_str + "15", "Examen"),
            ("Física", "Deberes y materia", hoy_str + "18", "Tarea"),
            ("Ed. Física", "Del libro página 51-63", hoy_str + "20", "Tarea"),
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
    <title>Mi Escuelita // Calendario de Rompecabezas Dinámico</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Quicksand:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Quicksand', sans-serif; background-color: #fdfbf7; color: #4a403b; overflow-x: hidden; }
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
                <h1 class="text-base font-bold text-sky-900 tracking-wide">Calendario Escolar de Rompecabezas</h1>
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
                <div class="w-20 h-20 bg-sky-100 rounded-full flex items-center justify-center border-4 border-sky-300 shadow-md flex-shrink-0">
                    <span class="text-4xl avatar-talking">👦🏽🗣️</span>
                </div>
                <div class="speech-bubble flex-grow">
                    <h2 class="text-base font-bold text-sky-900 mb-1">¡Selecciona un día y revisa tus pendientes y exámenes! 🧩✨</h2>
                    <p class="text-xs text-sky-800">Haz clic en el botón verde de cualquier tarea o examen completado para enviarlo al historial.</p>
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
        Calendario Escolar de Rompecabezas // Unidad Educativa Fiscomisional La Dolorosa 🍎🧩
    </footer>
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

        return render_template_string(HTML_TEMPLATE, tasks=tasks, all_tasks=tasks, selected_day=None, calendar_subjects=calendar_subjects)

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

    return render_template_string(HTML_TEMPLATE, tasks=filtered_tasks, all_tasks=all_tasks, selected_day=day_name, calendar_subjects=calendar_subjects)

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
        flash("¡Completado y movido al historial! 🏆")
    else:
        current_status = row[0]
        new_status = "PENDIENTE" if current_status == "COMPLETADO" else "COMPLETADO"
        cursor.execute(f"UPDATE progress SET status = {ph} WHERE email = {ph} AND task_id = {ph}", (new_status, user, task_id))
        if new_status == "COMPLETADO":
            flash("¡Marcado como completado! 🎉")
        else:
            flash("Devuelto a pendientes ↩️")

    conn.commit()
    cursor.close()
    conn.close()

    if day_filter:
        return redirect(url_for("filter_by_day", day_name=day_filter))
    return redirect(url_for("index"))

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)