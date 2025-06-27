import os
import sqlite3
# Временно отключаем PostgreSQL из-за проблем совместимости с Python 3.13
# import psycopg2
psycopg2 = None
from flask import Flask, request, jsonify
from flask_cors import CORS
import jwt
from datetime import datetime, timedelta
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Конфигурация
SECRET_KEY = os.environ.get('SECRET_KEY', 'veln-super-secret-key-2024')
BOT_TOKEN = os.environ.get('BOT_TOKEN')
DATABASE_URL = os.environ.get('DATABASE_URL')

app.config['SECRET_KEY'] = SECRET_KEY

# Инициализация базы данных
def init_db():
    try:
        conn = sqlite3.connect('veln_game.db')
        cursor = conn.cursor()
        
        # Создание таблицы пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                points INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Создание таблицы транзакций
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                points INTEGER,
                transaction_type TEXT,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        return False

# Инициализация при запуске
init_db()

@app.route('/')
def home():
    """Главная страница с информацией об API"""
    return jsonify({
        "message": "VELN Game API Server",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "GET /": "API информация",
            "GET /health": "Проверка здоровья сервера",
            "POST /register": "Регистрация пользователя",
            "GET /user/<telegram_id>": "Получить информацию о пользователе",
            "GET /points/<telegram_id>": "Получить баланс поинтов",
            "POST /add_points": "Добавить поинты пользователю",
            "GET /leaderboard": "Таблица лидеров"
        },
        "bot_configured": bool(BOT_TOKEN and BOT_TOKEN != 'your_bot_token_here'),
        "database": "SQLite"
    })

@app.route('/health')
def health():
    """Health check для Render.com"""
    try:
        # Проверяем подключение к базе данных
        conn = sqlite3.connect('veln_game.db')
        cursor = conn.cursor()
        cursor.execute('SELECT 1')
        conn.close()
        
        logger.info("Connected to SQLite database")
        return jsonify({
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500

@app.route('/register', methods=['POST'])
def register_user():
    """Регистрация нового пользователя"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        telegram_id = data.get('telegram_id')
        username = data.get('username', '')
        first_name = data.get('first_name', '')
        last_name = data.get('last_name', '')
        
        if not telegram_id:
            return jsonify({"error": "telegram_id is required"}), 400
        
        conn = sqlite3.connect('veln_game.db')
        cursor = conn.cursor()
        
        # Проверяем, существует ли пользователь
        cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,))
        existing_user = cursor.fetchone()
        
        if existing_user:
            conn.close()
            return jsonify({
                "message": "User already exists",
                "user": {
                    "telegram_id": existing_user[1],
                    "username": existing_user[2],
                    "points": existing_user[5]
                }
            })
        
        # Создаем нового пользователя
        cursor.execute('''
            INSERT INTO users (telegram_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
        ''', (telegram_id, username, first_name, last_name))
        
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        
        logger.info(f"New user registered: {telegram_id}")
        
        return jsonify({
            "message": "User registered successfully",
            "user": {
                "id": user_id,
                "telegram_id": telegram_id,
                "username": username,
                "first_name": first_name,
                "points": 0
            }
        }), 201
        
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return jsonify({"error": "Registration failed"}), 500

@app.route('/user/<int:telegram_id>')
def get_user(telegram_id):
    """Получить информацию о пользователе"""
    try:
        conn = sqlite3.connect('veln_game.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,))
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        return jsonify({
            "user": {
                "id": user[0],
                "telegram_id": user[1],
                "username": user[2],
                "first_name": user[3],
                "last_name": user[4],
                "points": user[5],
                "created_at": user[6]
            }
        })
        
    except Exception as e:
        logger.error(f"Get user error: {e}")
        return jsonify({"error": "Failed to get user"}), 500

@app.route('/points/<int:telegram_id>')
def get_points(telegram_id):
    """Получить баланс поинтов пользователя"""
    try:
        conn = sqlite3.connect('veln_game.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT points FROM users WHERE telegram_id = ?', (telegram_id,))
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            return jsonify({"error": "User not found"}), 404
        
        return jsonify({
            "telegram_id": telegram_id,
            "points": result[0]
        })
        
    except Exception as e:
        logger.error(f"Get points error: {e}")
        return jsonify({"error": "Failed to get points"}), 500

@app.route('/add_points', methods=['POST'])
def add_points():
    """Добавить поинты пользователю"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        telegram_id = data.get('telegram_id')
        points = data.get('points', 0)
        description = data.get('description', 'Points added')
        
        if not telegram_id:
            return jsonify({"error": "telegram_id is required"}), 400
            
        if not isinstance(points, int) or points <= 0:
            return jsonify({"error": "Points must be a positive integer"}), 400
        
        conn = sqlite3.connect('veln_game.db')
        cursor = conn.cursor()
        
        # Обновляем баланс пользователя
        cursor.execute('''
            UPDATE users 
            SET points = points + ?, updated_at = CURRENT_TIMESTAMP 
            WHERE telegram_id = ?
        ''', (points, telegram_id))
        
        if cursor.rowcount == 0:
            conn.close()
            return jsonify({"error": "User not found"}), 404
        
        # Записываем транзакцию
        cursor.execute('''
            INSERT INTO transactions (user_id, points, transaction_type, description)
            SELECT id, ?, 'add', ? FROM users WHERE telegram_id = ?
        ''', (points, description, telegram_id))
        
        # Получаем новый баланс
        cursor.execute('SELECT points FROM users WHERE telegram_id = ?', (telegram_id,))
        new_balance = cursor.fetchone()[0]
        
        conn.commit()
        conn.close()
        
        logger.info(f"Added {points} points to user {telegram_id}")
        
        return jsonify({
            "message": "Points added successfully",
            "telegram_id": telegram_id,
            "points_added": points,
            "new_balance": new_balance
        })
        
    except Exception as e:
        logger.error(f"Add points error: {e}")
        return jsonify({"error": "Failed to add points"}), 500

@app.route('/leaderboard')
def leaderboard():
    """Получить таблицу лидеров"""
    try:
        limit = request.args.get('limit', 10, type=int)
        limit = min(limit, 100)  # Максимум 100 записей
        
        conn = sqlite3.connect('veln_game.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT telegram_id, username, first_name, points
            FROM users 
            WHERE points > 0 
            ORDER BY points DESC 
            LIMIT ?
        ''', (limit,))
        
        results = cursor.fetchall()
        conn.close()
        
        leaderboard_data = []
        for i, row in enumerate(results, 1):
            leaderboard_data.append({
                "rank": i,
                "telegram_id": row[0],
                "username": row[1],
                "first_name": row[2],
                "points": row[3]
            })
        
        return jsonify({
            "leaderboard": leaderboard_data,
            "total_players": len(leaderboard_data)
        })
        
    except Exception as e:
        logger.error(f"Leaderboard error: {e}")
        return jsonify({"error": "Failed to get leaderboard"}), 500

# Обработка ошибок
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
