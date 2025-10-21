from flask import Flask, render_template, request, jsonify, send_from_directory
import sqlite3
import os
from flask_cors import CORS
from werkzeug.utils import secure_filename

# === Настройки ===
UPLOAD_FOLDER = 'uploads'
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
CORS(app)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# === Категории для постов ===
DBS = {
    'listening': 'listening.db',
    'vocabulary': 'vocabulary.db',
    'reading': 'reading.db',
    'writing': 'writing.db',
    'speaking': 'speaking.db',
    'grammar': 'grammar.db'
}

# === Инициализация основной БД (пользователи и рейтинг) ===
def init_main_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            login TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_scores (
            login TEXT UNIQUE,
            score INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

# === Инициализация баз данных постов ===
def init_post_db(db_name):
    with sqlite3.connect(db_name) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                filename TEXT,
                author TEXT
            )
        ''')
        conn.commit()

# === Добавление колонки author, если её нет (обновление старых таблиц) ===
def add_author_column_if_missing(db_name):
    with sqlite3.connect(db_name) as conn:
        c = conn.cursor()
        c.execute("PRAGMA table_info(posts)")
        columns = [info[1] for info in c.fetchall()]
        if 'author' not in columns:
            c.execute("ALTER TABLE posts ADD COLUMN author TEXT")
            conn.commit()

# === Инициализация всех баз ===
init_main_db()
for db_file in DBS.values():
    init_post_db(db_file)
    add_author_column_if_missing(db_file)

# === Роуты ===

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login')
def login():
    return render_template('loginvolonter.html')

@app.route('/student')
def student():
    return render_template('student2page.html')

@app.route('/nextpage2')
def nextpage2():
    return render_template('nextpage2.html')

@app.route('/rating')
def rating():
    return render_template('rating.html')

# Получение рейтинга
@app.route('/get_rating')
def get_rating():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT login, score FROM user_scores ORDER BY score DESC')
    rows = cursor.fetchall()
    conn.close()
    return jsonify(rows)

# Создание поста + начисление баллов
@app.route('/create_post', methods=['POST'])
def create_post():
    try:
        post_text = request.form.get('post_text')
        category = request.form.get('category')
        file = request.files.get('attachment')
        login = request.form.get('login')

        if not post_text or not category or not login:
            return jsonify({'success': False, 'error': 'Все поля обязательны'}), 400

        if category not in DBS:
            return jsonify({'success': False, 'error': 'Неверная категория'}), 400

        filename = None
        if file and file.filename:
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

        db_name = DBS[category]
        with sqlite3.connect(db_name) as conn:
            c = conn.cursor()
            c.execute('INSERT INTO posts (text, filename, author) VALUES (?, ?, ?)', (post_text, filename, login))
            conn.commit()

        # Обновление рейтинга
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO user_scores (login, score) VALUES (?, 0)', (login,))
        c.execute('UPDATE user_scores SET score = score + 10 WHERE login = ?', (login,))
        conn.commit()
        conn.close()

        return jsonify({'success': True})
    except Exception as e:
        print('❌ Ошибка в create_post:', e)
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500

# Авторизация
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json(force=True)
    login_input = data.get('login')
    password_input = data.get('password')

    if not login_input or not password_input:
        return jsonify({'status': 'error', 'message': 'Введите логин и пароль'}), 400

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE login=? AND password=?", (login_input, password_input))
    user = cursor.fetchone()
    conn.close()

    if user:
        return jsonify({'status': 'success'})
    else:
        return jsonify({'status': 'error', 'message': 'Неверный логин или пароль'}), 401

# Регистрация
@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json(force=True)
    login_input = data.get('login')
    password_input = data.get('password')
    password_check = data.get('password_check')

    if not login_input or not password_input or not password_check:
        return jsonify({'status': 'error', 'message': 'Заполните все поля'}), 400

    if password_input != password_check:
        return jsonify({'status': 'error', 'message': 'Пароли не совпадают'}), 400

    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (login, password) VALUES (?, ?)", (login_input, password_input))
        cursor.execute("INSERT INTO user_scores (login, score) VALUES (?, 0)", (login_input,))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success'})
    except sqlite3.IntegrityError:
        return jsonify({'status': 'error', 'message': 'Логин уже занят'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Получение постов с поддержкой filename для вложений
@app.route('/get_posts')
def get_posts():
    category = request.args.get('category')
    if category not in DBS:
        return jsonify([])  # пустой список, если категория неправильная

    db_name = DBS[category]
    with sqlite3.connect(db_name) as conn:
        c = conn.cursor()
        c.execute("SELECT text, author, filename FROM posts ORDER BY id DESC")
        posts = c.fetchall()

    posts_list = []
    for row in posts:
        post = {
            'text': row[0],
            'author': row[1],
            'filename': row[2] if row[2] else None
        }
        posts_list.append(post)

    return jsonify(posts_list)

# Раздача загруженных файлов
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Запуск приложения
if __name__ == '__main__':
    app.run(debug=True, port=5500)
