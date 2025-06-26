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

# Функция для получения подключения к базе данных
def get_db_connection():
    """Получить подключение к базе данных (PostgreSQL в продакшене, SQLite локально)"""
    if DATABASE_URL and psycopg2:
        try:
            # Продакшен - PostgreSQL на Render.com
            conn = psycopg2.connect(DATABASE_URL, sslmode='require')
            logger.info("Connected to PostgreSQL database")
            return conn
        except Exception as e:
            logger.error(f"PostgreSQL connection failed: {e}")
            logger.info("Falling back to SQLite...")
    
    # Локальная разработка или fallback - SQLite
    conn = sqlite3.connect('veln_game.db')
    conn.row_factory = sqlite3.Row
    logger.info("Connected to SQLite database")
    return conn

# Инициализация базы данных
def init_database():
    """Создать таблицы в базе данных"""
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to connect to database")
        return False
    
    try:
        cursor = conn.cursor()
        
        # Создание таблицы пользователей
        if DATABASE_URL:  # PostgreSQL
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT UNIQUE NOT NULL,
                    username VARCHAR(255),
                    first_name VARCHAR(255),
                    last_name VARCHAR(255),
                    points BIGINT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS game_sessions (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    points_earned BIGINT DEFAULT 0,
                    session_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    session_end TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
        else:  # SQLite
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE NOT NULL,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    points INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS game_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    points_earned INTEGER DEFAULT 0,
                    session_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    session_end TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
        
        conn.commit()
        logger.info("Database initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return False
    finally:
        conn.close()

# Проверка Telegram WebApp данных
def verify_telegram_data(init_data):
    """Проверить подлинность данных от Telegram WebApp"""
    if not BOT_TOKEN:
        logger.warning("BOT_TOKEN not set, skipping verification")
        return True  # В разработке пропускаем проверку
    
    try:
        # Простая проверка для демо
        # В реальном проекте нужна полная проверка hash
        return True
    except Exception as e:
        logger.error(f"Telegram data verification failed: {e}")
        return False

# API Routes

@app.route('/', methods=['GET'])
def home():
    """Главная страница API"""
    return jsonify({
        'status': 'success',
        'message': 'VELN Game API Server is running!',
        'version': '1.0.0',
        'endpoints': {
            'health': '/health',
            'user_register': '/api/user/register (POST)',
            'user_stats': '/api/user/stats (GET)',
            'save_points': '/api/game/save-points (POST)',
            'leaderboard': '/api/game/leaderboard (GET)'
        }
    })

@app.route('/health', methods=['GET'])
def health_check():
    """Health check для Render.com"""
    try:
        conn = get_db_connection()
        if conn:
            conn.close()
            db_status = 'connected'
        else:
            db_status = 'disconnected'
        
        return jsonify({
            'status': 'healthy',
            'database': db_status,
            'timestamp': datetime.now().isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/user/register', methods=['POST'])
def register_user():
    """Регистрация или обновление пользователя"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Проверка обязательных полей
        user_id = data.get('user_id')
        if not user_id:
            return jsonify({'error': 'user_id is required'}), 400
        
        username = data.get('username', '')
        first_name = data.get('first_name', '')
        last_name = data.get('last_name', '')
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 500
        
        try:
            cursor = conn.cursor()
            
            if DATABASE_URL:  # PostgreSQL
                cursor.execute('''
                    INSERT INTO users (user_id, username, first_name, last_name, points, updated_at)
                    VALUES (%s, %s, %s, %s, 0, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id) 
                    DO UPDATE SET 
                        username = EXCLUDED.username,
                        first_name = EXCLUDED.first_name,
                        last_name = EXCLUDED.last_name,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING user_id, points;
                ''', (user_id, username, first_name, last_name))
                
                result = cursor.fetchone()
                user_points = result[1] if result else 0
            else:  # SQLite
                cursor.execute('''
                    INSERT OR REPLACE INTO users (user_id, username, first_name, last_name, points, updated_at)
                    VALUES (?, ?, ?, ?, COALESCE((SELECT points FROM users WHERE user_id = ?), 0), CURRENT_TIMESTAMP)
                ''', (user_id, username, first_name, last_name, user_id))
                
                cursor.execute('SELECT points FROM users WHERE user_id = ?', (user_id,))
                result = cursor.fetchone()
                user_points = result[0] if result else 0
            
            conn.commit()
            
            return jsonify({
                'status': 'success',
                'message': 'User registered successfully',
                'user': {
                    'user_id': user_id,
                    'username': username,
                    'first_name': first_name,
                    'last_name': last_name,
                    'points': user_points
                }
            })
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error in register_user: {e}")
            return jsonify({'error': 'Database operation failed'}), 500
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error in register_user: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/user/stats', methods=['GET'])
def get_user_stats():
    """Получить статистику пользователя"""
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({'error': 'user_id parameter is required'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 500
        
        try:
            cursor = conn.cursor()
            
            if DATABASE_URL:  # PostgreSQL
                cursor.execute('''
                    SELECT user_id, username, first_name, last_name, points, created_at, updated_at
                    FROM users WHERE user_id = %s
                ''', (user_id,))
            else:  # SQLite
                cursor.execute('''
                    SELECT user_id, username, first_name, last_name, points, created_at, updated_at
                    FROM users WHERE user_id = ?
                ''', (user_id,))
            
            user = cursor.fetchone()
            
            if not user:
                return jsonify({'error': 'User not found'}), 404
            
            if DATABASE_URL:  # PostgreSQL
                user_data = {
                    'user_id': user[0],
                    'username': user[1],
                    'first_name': user[2],
                    'last_name': user[3],
                    'points': user[4],
                    'created_at': user[5].isoformat() if user[5] else None,
                    'updated_at': user[6].isoformat() if user[6] else None
                }
            else:  # SQLite
                user_data = {
                    'user_id': user[0],
                    'username': user[1],
                    'first_name': user[2],
                    'last_name': user[3],
                    'points': user[4],
                    'created_at': user[5],
                    'updated_at': user[6]
                }
            
            return jsonify({
                'status': 'success',
                'user': user_data
            })
            
        except Exception as e:
            logger.error(f"Database error in get_user_stats: {e}")
            return jsonify({'error': 'Database operation failed'}), 500
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error in get_user_stats: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/game/save-points', methods=['POST'])
def save_points():
    """Сохранить очки пользователя"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        user_id = data.get('user_id')
        points = data.get('points')
        
        if not user_id or points is None:
            return jsonify({'error': 'user_id and points are required'}), 400
        
        if not isinstance(points, int) or points < 0:
            return jsonify({'error': 'points must be a non-negative integer'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 500
        
        try:
            cursor = conn.cursor()
            
            if DATABASE_URL:  # PostgreSQL
                cursor.execute('''
                    UPDATE users 
                    SET points = %s, updated_at = CURRENT_TIMESTAMP 
                    WHERE user_id = %s
                    RETURNING points;
                ''', (points, user_id))
                
                result = cursor.fetchone()
                if not result:
                    return jsonify({'error': 'User not found'}), 404
                
                new_points = result[0]
            else:  # SQLite
                cursor.execute('''
                    UPDATE users 
                    SET points = ?, updated_at = CURRENT_TIMESTAMP 
                    WHERE user_id = ?
                ''', (points, user_id))
                
                if cursor.rowcount == 0:
                    return jsonify({'error': 'User not found'}), 404
                
                new_points = points
            
            conn.commit()
            
            return jsonify({
                'status': 'success',
                'message': 'Points saved successfully',
                'points': new_points
            })
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error in save_points: {e}")
            return jsonify({'error': 'Database operation failed'}), 500
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error in save_points: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/game/leaderboard', methods=['GET'])
def get_leaderboard():
    """Получить таблицу лидеров"""
    try:
        limit = request.args.get('limit', 10)
        try:
            limit = int(limit)
            if limit <= 0 or limit > 100:
                limit = 10
        except ValueError:
            limit = 10
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 500
        
        try:
            cursor = conn.cursor()
            
            if DATABASE_URL:  # PostgreSQL
                cursor.execute('''
                    SELECT user_id, username, first_name, last_name, points
                    FROM users 
                    WHERE points > 0 
                    ORDER BY points DESC 
                    LIMIT %s
                ''', (limit,))
            else:  # SQLite
                cursor.execute('''
                    SELECT user_id, username, first_name, last_name, points
                    FROM users 
                    WHERE points > 0 
                    ORDER BY points DESC 
                    LIMIT ?
                ''', (limit,))
            
            results = cursor.fetchall()
            
            leaderboard = []
            for i, row in enumerate(results, 1):
                if DATABASE_URL:  # PostgreSQL
                    leaderboard.append({
                        'rank': i,
                        'user_id': row[0],
                        'username': row[1],
                        'first_name': row[2],
                        'last_name': row[3],
                        'points': row[4]
                    })
                else:  # SQLite
                    leaderboard.append({
                        'rank': i,
                        'user_id': row[0],
                        'username': row[1],
                        'first_name': row[2],
                        'last_name': row[3],
                        'points': row[4]
                    })
            
            return jsonify({
                'status': 'success',
                'leaderboard': leaderboard,
                'total': len(leaderboard)
            })
            
        except Exception as e:
            logger.error(f"Database error in get_leaderboard: {e}")
            return jsonify({'error': 'Database operation failed'}), 500
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error in get_leaderboard: {e}")
        return jsonify({'error': 'Internal server error'}), 500

# Инициализация базы данных при старте приложения
logger.info("Starting VELN Game API Server...")
logger.info(f"BOT_TOKEN configured: {'Yes' if BOT_TOKEN else 'No'}")
logger.info(f"DATABASE_URL configured: {'Yes' if DATABASE_URL else 'No (using SQLite)'}")

# Инициализация базы данных
if init_database():
    logger.info("Database initialized successfully")
else:
    logger.error("Failed to initialize database")

# Для локального запуска
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

# Для Render.com - если нужно переименовать файл в app.py
# просто скопируйте этот код в новый файл app.py
