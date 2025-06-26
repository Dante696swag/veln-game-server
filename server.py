import os
import sqlite3
import psycopg2
from urllib.parse import urlparse
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import jwt
import json

# Конфигурация приложения
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'veln-super-secret-key-2024-render')

# Включаем CORS для всех доменов
CORS(app)

# Конфигурация базы данных
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    # PostgreSQL для продакшена (Render.com)
    url = urlparse(DATABASE_URL)
    DB_CONFIG = {
        'host': url.hostname,
        'port': url.port,
        'database': url.path[1:],
        'user': url.username,
        'password': url.password
    }
    USE_POSTGRESQL = True
    print("🗄️ Используется PostgreSQL база данных")
else:
    # SQLite для локальной разработки
    DATABASE = 'veln_game.db'
    USE_POSTGRESQL = False
    print("🗄️ Используется SQLite база данных")

# Telegram Bot Token (замените на ваш реальный токен)
BOT_TOKEN = os.environ.get('BOT_TOKEN', '7372299924:AAEkfBmorTJ7QKFRz1snSCEklVwbllr-rXg')

def get_db_connection():
    """Получить подключение к базе данных"""
    if USE_POSTGRESQL:
        return psycopg2.connect(**DB_CONFIG)
    else:
        return sqlite3.connect(DATABASE)

def init_database():
    """Инициализация базы данных"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if USE_POSTGRESQL:
        # PostgreSQL синтаксис
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE,
                username VARCHAR(255),
                first_name VARCHAR(255),
                last_name VARCHAR(255),
                photo_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS game_data (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                points INTEGER DEFAULT 0,
                total_time_played INTEGER DEFAULT 0,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                session_start TIMESTAMP,
                is_active BOOLEAN DEFAULT FALSE,
                logo_position TEXT DEFAULT '{"x": 0, "y": -140}'
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS achievements (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                achievement_type VARCHAR(255),
                unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                transaction_type VARCHAR(255),
                amount INTEGER,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    else:
        # SQLite синтаксис
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                photo_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS game_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                points INTEGER DEFAULT 0,
                total_time_played INTEGER DEFAULT 0,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                session_start TIMESTAMP,
                is_active BOOLEAN DEFAULT 0,
                logo_position TEXT DEFAULT '{"x": 0, "y": -140}',
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS achievements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                achievement_type TEXT,
                unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                transaction_type TEXT,
                amount INTEGER,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
    
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

# Инициализация базы данных при запуске
init_database()

class VelnGameServer:
    def __init__(self):
        self.active_sessions = {}
        
    def create_user(self, telegram_data):
        """Создание или обновление пользователя"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            if USE_POSTGRESQL:
                cursor.execute('''
                    INSERT INTO users (telegram_id, username, first_name, last_name, photo_url, last_seen)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (telegram_id) DO UPDATE SET
                        username = EXCLUDED.username,
                        first_name = EXCLUDED.first_name,
                        last_name = EXCLUDED.last_name,
                        photo_url = EXCLUDED.photo_url,
                        last_seen = EXCLUDED.last_seen
                    RETURNING id
                ''', (
                    telegram_data.get('id'),
                    telegram_data.get('username'),
                    telegram_data.get('first_name'),
                    telegram_data.get('last_name'),
                    telegram_data.get('photo_url'),
                    datetime.now()
                ))
            else:
                cursor.execute('''
                    INSERT OR REPLACE INTO users (telegram_id, username, first_name, last_name, photo_url, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    telegram_data.get('id'),
                    telegram_data.get('username'),
                    telegram_data.get('first_name'),
                    telegram_data.get('last_name'),
                    telegram_data.get('photo_url'),
                    datetime.now()
                ))
            
            if USE_POSTGRESQL:
                user_id = cursor.fetchone()[0]
            else:
                user_id = cursor.lastrowid
            
            # Создаем игровые данные если их нет
            if USE_POSTGRESQL:
                cursor.execute('''
                    INSERT INTO game_data (user_id)
                    VALUES (%s)
                    ON CONFLICT (user_id) DO NOTHING
                ''', (user_id,))
            else:
                cursor.execute('''
                    INSERT OR IGNORE INTO game_data (user_id)
                    VALUES (?)
                ''', (user_id,))
            
            conn.commit()
            return user_id
            
        except Exception as e:
            print(f"❌ Ошибка создания пользователя: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()
    
    def get_user_data(self, user_id):
        """Получение данных пользователя"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            if USE_POSTGRESQL:
                cursor.execute('''
                    SELECT u.*, g.points, g.total_time_played, g.last_active, g.logo_position
                    FROM users u
                    LEFT JOIN game_data g ON u.id = g.user_id
                    WHERE u.id = %s
                ''', (user_id,))
            else:
                cursor.execute('''
                    SELECT u.*, g.points, g.total_time_played, g.last_active, g.logo_position
                    FROM users u
                    LEFT JOIN game_data g ON u.id = g.user_id
                    WHERE u.id = ?
                ''', (user_id,))
            
            row = cursor.fetchone()
            if row:
                return {
                    'id': row[0],
                    'telegram_id': row[1],
                    'username': row[2],
                    'first_name': row[3],
                    'last_name': row[4],
                    'photo_url': row[5],
                    'points': row[7] or 0,
                    'total_time_played': row[8] or 0,
                    'last_active': row[9],
                    'logo_position': json.loads(row[10] or '{"x": 0, "y": -140}')
                }
            return None
            
        except Exception as e:
            print(f"❌ Ошибка получения данных пользователя: {e}")
            return None
        finally:
            conn.close()
    
    def update_points(self, user_id, points):
        """Обновление поинтов пользователя"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            if USE_POSTGRESQL:
                cursor.execute('''
                    UPDATE game_data 
                    SET points = %s, last_active = %s
                    WHERE user_id = %s
                ''', (points, datetime.now(), user_id))
            else:
                cursor.execute('''
                    UPDATE game_data 
                    SET points = ?, last_active = ?
                    WHERE user_id = ?
                ''', (points, datetime.now(), user_id))
            
            conn.commit()
            return True
            
        except Exception as e:
            print(f"❌ Ошибка обновления поинтов: {e}")
            return False
        finally:
            conn.close()
    
    def get_leaderboard(self, limit=10):
        """Получение таблицы лидеров"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            if USE_POSTGRESQL:
                cursor.execute('''
                    SELECT u.first_name, u.username, g.points
                    FROM users u
                    JOIN game_data g ON u.id = g.user_id
                    ORDER BY g.points DESC
                    LIMIT %s
                ''', (limit,))
            else:
                cursor.execute('''
                    SELECT u.first_name, u.username, g.points
                    FROM users u
                    JOIN game_data g ON u.id = g.user_id
                    ORDER BY g.points DESC
                    LIMIT ?
                ''', (limit,))
            
            rows = cursor.fetchall()
            leaderboard = []
            for i, row in enumerate(rows, 1):
                leaderboard.append({
                    'rank': i,
                    'name': row[0] or row[1] or 'Аноним',
                    'points': row[2]
                })
            
            return leaderboard
            
        except Exception as e:
            print(f"❌ Ошибка получения таблицы лидеров: {e}")
            return []
        finally:
            conn.close()

# Создаем экземпляр игрового сервера
game_server = VelnGameServer()

# JWT функции
def generate_token(user_data):
    """Генерация JWT токена"""
    payload = {
        'user_id': user_data['id'],
        'telegram_id': user_data['telegram_id'],
        'exp': datetime.utcnow() + timedelta(days=30)
    }
    return jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')

def verify_token(token):
    """Проверка JWT токена"""
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

# API маршруты

@app.route('/')
def home():
    """Главная страница сервера"""
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>VELN Game Server</title>
        <style>
            body { 
                font-family: Arial, sans-serif; 
                background: linear-gradient(135deg, #0a0a0a, #1a1a1a);
                color: white; 
                text-align: center; 
                padding: 50px;
            }
            .logo { 
                font-size: 72px; 
                font-weight: bold; 
                background: linear-gradient(135deg, #00d4ff, #ffffff);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: 30px;
            }
            .status { 
                font-size: 24px; 
                margin: 20px 0; 
                color: #00d4ff;
            }
            .endpoint {
                background: rgba(255,255,255,0.1);
                padding: 15px;
                margin: 10px 0;
                border-radius: 10px;
                border-left: 4px solid #00d4ff;
            }
        </style>
    </head>
    <body>
        <div class="logo">VELN</div>
        <div class="status">🚀 VELN Game Server запущен!</div>
        <div class="status">⚡ Time-Point-VELN COIN System</div>
        
        <h2>📊 API Endpoints:</h2>
        <div class="endpoint">
            <strong>GET /api/stats</strong> - Статистика сервера
        </div>
        <div class="endpoint">
            <strong>POST /api/auth</strong> - Аутентификация пользователя
        </div>
        <div class="endpoint">
            <strong>GET /api/user/data</strong> - Данные пользователя
        </div>
        <div class="endpoint">
            <strong>POST /api/user/points</strong> - Обновление поинтов
        </div>
        <div class="endpoint">
            <strong>GET /api/leaderboard</strong> - Таблица лидеров
        </div>
        <div class="endpoint">
            <strong>GET /health</strong> - Проверка здоровья сервера
        </div>
        
        <p style="margin-top: 50px; color: #666;">
            Версия: 1.0.0 | Время: {{ current_time }}
        </p>
    </body>
    </html>
    ''', current_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

@app.route('/health')
def health_check():
    """Health check для Render.com и мониторинга"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0',
        'database': 'PostgreSQL' if USE_POSTGRESQL else 'SQLite',
        'uptime': 'OK'
    })

@app.route('/api/stats')
def get_stats():
    """Получение статистики сервера"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Общее количество пользователей
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        
        # Общее количество поинтов
        cursor.execute('SELECT SUM(points) FROM game_data')
        total_points = cursor.fetchone()[0] or 0
        
        # Активные пользователи (последние 24 часа)
        yesterday = datetime.now() - timedelta(days=1)
        if USE_POSTGRESQL:
            cursor.execute('SELECT COUNT(*) FROM users WHERE last_seen > %s', (yesterday,))
        else:
            cursor.execute('SELECT COUNT(*) FROM users WHERE last_seen > ?', (yesterday,))
        active_users = cursor.fetchone()[0]
        
        return jsonify({
            'success': True,
            'stats': {
                'total_users': total_users,
                'total_points': total_points,
                'active_users_24h': active_users,
                'server_time': datetime.now().isoformat(),
                'database_type': 'PostgreSQL' if USE_POSTGRESQL else 'SQLite'
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    finally:
        conn.close()

@app.route('/api/auth', methods=['POST'])
def authenticate():
    """Аутентификация пользователя через Telegram данные"""
    try:
        data = request.get_json()
        telegram_data = data.get('telegram_data')
        
        if not telegram_data:
            return jsonify({
                'success': False,
                'error': 'Отсутствуют данные Telegram'
            }), 400
        
        # Создаем или обновляем пользователя
        user_id = game_server.create_user(telegram_data)
        if not user_id:
            return jsonify({
                'success': False,
                'error': 'Ошибка создания пользователя'
            }), 500
        
        # Получаем полные данные пользователя
        user_data = game_server.get_user_data(user_id)
        if not user_data:
            return jsonify({
                'success': False,
                'error': 'Ошибка получения данных пользователя'
            }), 500
        
        # Генерируем JWT токен
        token = generate_token(user_data)
        
        return jsonify({
            'success': True,
            'token': token,
            'user': user_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/user/data')
def get_user_data():
    """Получение данных пользователя (требует аутентификации)"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({
                'success': False,
                'error': 'Отсутствует токен авторизации'
            }), 401
        
        token = auth_header.replace('Bearer ', '')
        payload = verify_token(token)
        if not payload:
            return jsonify({
                'success': False,
                'error': 'Недействительный токен'
            }), 401
        
        user_data = game_server.get_user_data(payload['user_id'])
        if not user_data:
            return jsonify({
                'success': False,
                'error': 'Пользователь не найден'
            }), 404
        
        return jsonify({
            'success': True,
            'user': user_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/user/points', methods=['POST'])
def update_user_points():
    """Обновление поинтов пользователя"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({
                'success': False,
                'error': 'Отсутствует токен авторизации'
            }), 401
        
        token = auth_header.replace('Bearer ', '')
        payload = verify_token(token)
        if not payload:
            return jsonify({
                'success': False,
                'error': 'Недействительный токен'
            }), 401
        
        data = request.get_json()
        points = data.get('points')
        
        if points is None:
            return jsonify({
                'success': False,
                'error': 'Отсутствует параметр points'
            }), 400
        
        success = game_server.update_points(payload['user_id'], points)
        if not success:
            return jsonify({
                'success': False,
                'error': 'Ошибка обновления поинтов'
            }), 500
        
        return jsonify({
            'success': True,
            'points': points
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/leaderboard')
def get_leaderboard():
    """Получение таблицы лидеров"""
    try:
        limit = request.args.get('limit', 10, type=int)
        leaderboard = game_server.get_leaderboard(limit)
        
        return jsonify({
            'success': True,
            'leaderboard': leaderboard
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Обработка ошибок
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': 'Эндпоинт не найден'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'error': 'Внутренняя ошибка сервера'
    }), 500

if __name__ == '__main__':
    # Определяем порт для Render.com
    port = int(os.environ.get('PORT', 5000))
    print("🚀 Запуск VELN Game Server...")
    print(f"📊 Dashboard: http://0.0.0.0:{port}")
    print(f"🔌 API: http://0.0.0.0:{port}/api/")
    print(f"🗄️ База данных: {'PostgreSQL' if USE_POSTGRESQL else 'SQLite'}")
    
    # Запускаем сервер
    app.run(host='0.0.0.0', port=port, debug=False)
