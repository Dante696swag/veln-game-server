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

@app.route('/game')
def game():
    """Игровая страница для Telegram Web App"""
    return '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VELN Game - Time Point Coin</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
    <script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
    <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {
            margin: 0;
            padding: 0;
            background: #0a0a0a;
            font-family: 'Inter', system-ui, sans-serif;
            overflow: hidden;
        }
        
        .veln-logo {
            filter: drop-shadow(0 0 40px rgba(0,212,255,0.6)) drop-shadow(0 0 80px rgba(0,212,255,0.3));
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 0.9; }
            50% { opacity: 1; }
        }
        
        .animate-pulse {
            animation: pulse 2s infinite;
        }
    </style>
</head>
<body>
    <div id="root"></div>

    <script type="text/babel">
        const { useState, useEffect } = React;

        // Telegram Web App initialization
        const tg = window.Telegram?.WebApp;
        if (tg) {
            tg.ready();
            tg.expand();
        }

        // Local storage hooks simulation
        const useStoredState = (key, initialValue) => {
            const [value, setValue] = useState(() => {
                try {
                    const item = localStorage.getItem(key);
                    return item ? JSON.parse(item) : initialValue;
                } catch (error) {
                    return initialValue;
                }
            });

            const setStoredValue = (newValue) => {
                setValue(newValue);
                localStorage.setItem(key, JSON.stringify(newValue));
            };

            return [value, setStoredValue];
        };

        const useUser = () => {
            const user = tg?.initDataUnsafe?.user;
            return {
                id: user?.id || 'user_demo',
                name: user?.first_name || 'Dante Moretti',
                color: '#EC5E41',
                avatar: user?.photo_url || null
            };
        };

        const VelnGameInterface = () => {
            const [logoPosition, setLogoPosition] = useStoredState('veln-logo-position', { x: 0, y: -140 });
            const [points, setPoints] = useStoredState('veln-points', 0);
            const [serverPoints, setServerPoints] = useState(0);
            const [lastActiveTime, setLastActiveTime] = useStoredState('veln-last-active', Date.now());
            const [isDragging, setIsDragging] = useState(null);
            const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
            const [isAppVisible, setIsAppVisible] = useState(true);
            const [isRegistered, setIsRegistered] = useState(false);
            const [apiStatus, setApiStatus] = useState('connecting');
            const [leaderboard, setLeaderboard] = useState([]);
            const [showLeaderboard, setShowLeaderboard] = useState(false);
            const [lastSync, setLastSync] = useState(0);
            const user = useUser();

            // API Configuration
            const API_BASE = 'https://veln-game-server.onrender.com';

            // API Functions
            const registerUser = async () => {
                try {
                    const response = await fetch(`${API_BASE}/register`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            telegram_id: parseInt(user.id),
                            username: user.name,
                            first_name: user.name,
                            last_name: ''
                        })
                    });
                    const data = await response.json();
                    console.log('User registered:', data);
                    setIsRegistered(true);
                    setApiStatus('connected');
                    return data;
                } catch (error) {
                    console.error('Registration error:', error);
                    setApiStatus('error');
                    return null;
                }
            };

            const syncPointsToServer = async (currentPoints) => {
                if (!isRegistered || currentPoints <= lastSync) return;
                
                try {
                    const pointsToAdd = currentPoints - lastSync;
                    const response = await fetch(`${API_BASE}/add_points`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            telegram_id: parseInt(user.id),
                            points: pointsToAdd,
                            description: 'Game session points'
                        })
                    });
                    const data = await response.json();
                    console.log('Points synced:', data);
                    setServerPoints(data.new_balance || currentPoints);
                    setLastSync(currentPoints);
                } catch (error) {
                    console.error('Sync error:', error);
                }
            };

            const loadLeaderboard = async () => {
                try {
                    const response = await fetch(`${API_BASE}/leaderboard?limit=10`);
                    const data = await response.json();
                    setLeaderboard(data.leaderboard || []);
                    return data;
                } catch (error) {
                    console.error('Leaderboard error:', error);
                    return [];
                }
            };

            const getUserServerPoints = async () => {
                try {
                    const response = await fetch(`${API_BASE}/points/${user.id}`);
                    const data = await response.json();
                    setServerPoints(data.points || 0);
                    return data.points || 0;
                } catch (error) {
                    console.error('Get points error:', error);
                    return 0;
                }
            };

            // Инициализация при входе в приложение
            useEffect(() => {
                setLastActiveTime(Date.now());
                
                // Автоматическая регистрация и загрузка данных
                const initializeGame = async () => {
                    console.log('Initializing VELN Game...');
                    setApiStatus('connecting');
                    
                    // Регистрируем пользователя
                    await registerUser();
                    
                    // Загружаем поинты с сервера
                    const serverPoints = await getUserServerPoints();
                    if (serverPoints > points) {
                        setPoints(serverPoints);
                    }
                    
                    // Загружаем таблицу лидеров
                    await loadLeaderboard();
                };
                
                initializeGame();
            }, []);

            // Отслеживание видимости приложения
            useEffect(() => {
                const handleVisibilityChange = () => {
                    if (document.hidden) {
                        setIsAppVisible(false);
                        setLastActiveTime(Date.now());
                    } else {
                        setIsAppVisible(true);
                        setLastActiveTime(Date.now());
                    }
                };

                const handleBeforeUnload = () => {
                    setLastActiveTime(Date.now());
                };

                document.addEventListener('visibilitychange', handleVisibilityChange);
                window.addEventListener('beforeunload', handleBeforeUnload);

                return () => {
                    document.removeEventListener('visibilitychange', handleVisibilityChange);
                    window.removeEventListener('beforeunload', handleBeforeUnload);
                };
            }, []);

            // Автоматический счетчик поинтов
            useEffect(() => {
                if (!isAppVisible) return;
                
                const interval = setInterval(() => {
                    setPoints(prev => {
                        const newPoints = prev + 1;
                        setLastActiveTime(Date.now());
                        return newPoints;
                    });
                }, 1000);
                
                return () => clearInterval(interval);
            }, [isAppVisible]);

            // Синхронизация поинтов с сервером каждые 10 секунд
            useEffect(() => {
                if (!isRegistered) return;
                
                const syncInterval = setInterval(() => {
                    syncPointsToServer(points);
                }, 10000);
                
                return () => clearInterval(syncInterval);
            }, [points, isRegistered, lastSync]);

            // Обновление таблицы лидеров каждые 30 секунд
            useEffect(() => {
                const leaderInterval = setInterval(() => {
                    loadLeaderboard();
                }, 30000);
                
                return () => clearInterval(leaderInterval);
            }, []);

            const handleMouseDown = (e, element) => {
                setIsDragging(element);
                setDragStart({
                    x: e.clientX - logoPosition.x,
                    y: e.clientY - logoPosition.y
                });
            };

            const handleMouseMove = (e) => {
                if (!isDragging) return;
                
                const newX = e.clientX - dragStart.x;
                const newY = e.clientY - dragStart.y;
                
                if (isDragging === 'logo') {
                    setLogoPosition({ x: newX, y: newY });
                }
            };

            const handleMouseUp = () => {
                setIsDragging(null);
            };

            return (
                <div 
                    className="flex items-center justify-center min-h-screen bg-gray-100 p-4"
                    onMouseMove={handleMouseMove}
                    onMouseUp={handleMouseUp}
                    onMouseLeave={handleMouseUp}
                >
                    <div className="relative">
                        <div 
                            className="relative bg-black rounded-[55px] p-2 shadow-2xl"
                            style={{ width: '393px', height: '852px' }}
                        >
                            <div 
                                className="relative bg-black rounded-[45px] overflow-hidden"
                                style={{ width: '377px', height: '836px' }}
                            >
                                {/* Dynamic Island */}
                                <div 
                                    className="absolute top-2 left-1/2 transform -translate-x-1/2 bg-black rounded-full z-50"
                                    style={{ width: '126px', height: '37px' }}
                                />
                                
                                {/* Status Bar */}
                                <div className="absolute top-0 left-0 right-0 h-12 flex items-center justify-between px-6 pt-3 text-white text-sm font-semibold z-40">
                                    <div>9:41</div>
                                    <div className="flex items-center space-x-1">
                                        <div className="w-4 h-2 border border-white rounded-sm">
                                            <div className="w-3 h-1 bg-white rounded-sm m-0.5"></div>
                                        </div>
                                        <div className="w-6 h-3 border border-white rounded-sm">
                                            <div className="w-4 h-1 bg-white rounded-sm m-0.5"></div>
                                        </div>
                                        <div className="w-1 h-2 bg-white rounded-full"></div>
                                    </div>
                                </div>

                                {/* Telegram Header */}
                                <div className="absolute top-12 left-0 right-0 h-12 bg-gray-900 flex items-center justify-between px-4 z-40 border-b border-gray-700">
                                    <div className="flex items-center space-x-3">
                                        <svg className="w-6 h-6 text-blue-400" fill="currentColor" viewBox="0 0 24 24">
                                            <path d="M9.78 18.65l.28-4.23 7.68-6.92c.34-.31-.07-.46-.52-.19L7.74 13.3 3.64 12c-.88-.25-.89-.86.2-1.3l15.97-6.16c.73-.33 1.43.18 1.15 1.3l-2.72 12.81c-.19.91-.74 1.13-1.5.71L12.6 16.3l-1.99 1.93c-.23.23-.42.42-.83.42z"/>
                                        </svg>
                                        <div>
                                            <div className="text-white text-sm font-medium">VELN Bot</div>
                                            <div className="text-gray-400 text-xs">Online</div>
                                        </div>
                                    </div>
                                </div>

                                {/* Нижняя панель с иконками */}
                                <div className="absolute bottom-6 left-0 right-0 flex justify-center items-center px-8 z-50">
                                    <div className="flex items-center space-x-6">
                                        
                                        {/* Иконка Рюкзак - API Status */}
                                        <div 
                                            className="w-14 h-14 rounded-full flex items-center justify-center bg-gray-800 border-2 shadow-xl hover:bg-gray-700 transition-colors cursor-pointer relative"
                                            style={{ 
                                                borderColor: apiStatus === 'connected' ? '#10B981' : apiStatus === 'error' ? '#EF4444' : '#F59E0B'
                                            }}
                                            title={`API: ${apiStatus}`}
                                        >
                                            <svg className="w-8 h-8 text-gray-300" fill="currentColor" viewBox="0 0 24 24">
                                                <path d="M14 2v3h2v2h3c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H5c-1.1 0-2-.9-2-2V9c0-1.1.9-2 2-2h3V5h2V2h4zM9 7V5h6v2H9zm10 4H5v10h14V11zm-2 2v2h-2v-2h2zm-8 0v2H7v-2h2z"/>
                                            </svg>
                                            <div 
                                                className="absolute -top-1 -right-1 w-4 h-4 rounded-full"
                                                style={{ 
                                                    backgroundColor: apiStatus === 'connected' ? '#10B981' : apiStatus === 'error' ? '#EF4444' : '#F59E0B'
                                                }}
                                            />
                                        </div>

                                        {/* Иконка Джойстик */}
                                        <div className="w-14 h-14 rounded-full flex items-center justify-center bg-gray-800 border-2 border-gray-600 shadow-xl hover:bg-gray-700 transition-colors cursor-pointer">
                                            <svg className="w-8 h-8 text-gray-300" fill="currentColor" viewBox="0 0 24 24">
                                                <path d="M17.5 7c1.93 0 3.5 1.57 3.5 3.5v6c0 1.93-1.57 3.5-3.5 3.5h-11C4.57 20 3 18.43 3 16.5v-6C3 8.57 4.57 7 6.5 7h11zM17.5 9h-11C5.67 9 5 9.67 5 10.5v6c0 .83.67 1.5 1.5 1.5h11c.83 0 1.5-.67 1.5-1.5v-6c0-.83-.67-1.5-1.5-1.5zm-10 2.5c.28 0 .5.22.5.5s-.22.5-.5.5-.5-.22-.5-.5.22-.5.5-.5zm0 2c.28 0 .5.22.5.5s-.22.5-.5.5-.5-.22-.5-.5.22-.5.5-.5zm1-1c.28 0 .5.22.5.5s-.22.5-.5.5-.5-.22-.5-.5.22-.5.5-.5zm7-1c.28 0 .5.22.5.5s-.22.5-.5.5-.5-.22-.5-.5.22-.5.5-.5zm1 1c.28 0 .5.22.5.5s-.22.5-.5.5-.5-.22-.5-.5.22-.5.5-.5zm-1 1c.28 0 .5.22.5.5s-.22.5-.5.5-.5-.22-.5-.5.22-.5.5-.5zm-1-1c.28 0 .5.22.5.5s-.22.5-.5.5-.5-.22-.5-.5.22-.5.5-.5z"/>
                                            </svg>
                                        </div>

                                        {/* Иконка Лидеры - Leaderboard */}
                                        <div 
                                            className="w-14 h-14 rounded-full flex items-center justify-center bg-gray-800 border-2 border-gray-600 shadow-xl hover:bg-gray-700 transition-colors cursor-pointer"
                                            onClick={() => setShowLeaderboard(!showLeaderboard)}
                                        >
                                            <svg className="w-8 h-8 text-yellow-400" fill="currentColor" viewBox="0 0 24 24">
                                                <path d="M12,15.39L8.24,17.66L9.23,13.38L5.91,10.5L10.29,10.13L12,6.09L13.71,10.13L18.09,10.5L14.77,13.38L15.76,17.66M22,9.24L14.81,8.63L12,2L9.19,8.63L2,9.24L7.45,13.97L5.82,21L12,17.27L18.18,21L16.54,13.97L22,9.24Z"/>
                                            </svg>
                                        </div>

                                        {/* Иконка профиля */}
                                        <div 
                                            className="w-14 h-14 rounded-full flex items-center justify-center overflow-hidden shadow-2xl border-2 border-white cursor-pointer hover:scale-110 transition-transform"
                                            style={{ 
                                                backgroundColor: user.color,
                                                boxShadow: '0 0 20px rgba(255,255,255,0.5), 0 0 40px rgba(255,255,255,0.3)'
                                            }}
                                        >
                                            {user.avatar ? (
                                                <img 
                                                    src={user.avatar} 
                                                    alt={user.name} 
                                                    className="w-full h-full object-cover rounded-full"
                                                />
                                            ) : (
                                                <div className="text-white text-xl font-bold">
                                                    {user.name.charAt(0).toUpperCase()}
                                                </div>
                                            )}
                                        </div>
                                        
                                    </div>
                                </div>

                                {/* Game Content */}
                                <div 
                                    className="absolute top-24 left-0 right-0 bottom-0 overflow-hidden"
                                    style={{
                                        background: `linear-gradient(180deg, #0a0a0a 0%, #1a1a1a 30%, #0d0d0d 60%, #000000 100%)`
                                    }}
                                >
                                    <div className="flex flex-col items-center justify-center h-full relative">
                                        {/* VELN Logo */}
                                        <div 
                                            className="absolute cursor-move select-none"
                                            style={{ 
                                                transform: `translate(${logoPosition.x}px, ${logoPosition.y}px)`,
                                                transition: isDragging === 'logo' ? 'none' : 'transform 0.3s ease'
                                            }}
                                            onMouseDown={(e) => handleMouseDown(e, 'logo')}
                                        >
                                            <div className="relative mb-4">
                                                <div 
                                                    className="flex items-center justify-center shadow-2xl animate-pulse"
                                                    style={{ width: '300px', height: '300px' }}
                                                >
                                                    <div 
                                                        className="w-full h-full rounded-full veln-logo"
                                                        style={{
                                                            background: 'linear-gradient(135deg, #00d4ff 0%, #ffffff 50%, #00d4ff 100%)',
                                                            display: 'flex',
                                                            alignItems: 'center',
                                                            justifyContent: 'center',
                                                            fontSize: '72px',
                                                            fontWeight: '900',
                                                            color: '#000',
                                                            textShadow: '0 0 20px rgba(0,212,255,0.8)'
                                                        }}
                                                    >
                                                        VELN
                                                    </div>
                                                </div>
                                            </div>
                                        </div>

                                        {/* Time-Point-VELN COIN */}
                                        <div 
                                            className="absolute"
                                            style={{ 
                                                transform: `translate(${logoPosition.x}px, ${logoPosition.y + 200}px)`,
                                            }}
                                        >
                                            <div className="text-center">
                                                <div 
                                                    className="inline-block px-6 py-3 border-4 rounded-full"
                                                    style={{
                                                        background: 'transparent',
                                                        backdropFilter: 'blur(10px)',
                                                        boxShadow: '0 0 30px rgba(0,212,255,0.5)',
                                                        borderColor: '#00d4ff'
                                                    }}
                                                >
                                                    <div 
                                                        className="text-xl font-black tracking-wider uppercase"
                                                        style={{
                                                            background: 'linear-gradient(135deg, #00d4ff 0%, #ffffff 25%, #e0e0e0 50%, #ffffff 75%, #00d4ff 100%)',
                                                            WebkitBackgroundClip: 'text',
                                                            WebkitTextFillColor: 'transparent',
                                                            backgroundClip: 'text',
                                                            fontWeight: '900',
                                                            WebkitTextStroke: '2px #000000',
                                                            textShadow: '0 0 30px rgba(0,212,255,0.9)',
                                                            letterSpacing: '0.15em'
                                                        }}
                                                    >
                                                        Time-Point-VELN COIN
                                                    </div>
                                                </div>
                                            </div>
                                        </div>

                                        {/* POINT */}
                                        <div 
                                            className="absolute"
                                            style={{ 
                                                transform: `translate(${logoPosition.x}px, ${logoPosition.y + 300}px)`,
                                            }}
                                        >
                                            <div className="text-center">
                                                <div 
                                                    className="text-3xl font-black mb-6"
                                                    style={{
                                                        background: 'linear-gradient(135deg, #00d4ff 0%, #ffffff 30%, #00bfff 60%, #ffffff 80%, #00d4ff 100%)',
                                                        WebkitBackgroundClip: 'text',
                                                        WebkitTextFillColor: 'transparent',
                                                        backgroundClip: 'text',
                                                        fontWeight: '900',
                                                        WebkitTextStroke: '2px black',
                                                        textShadow: '0 0 25px rgba(0,212,255,0.8)',
                                                        letterSpacing: '0.2em'
                                                    }}
                                                >
                                                    POINT
                                                </div>
                                            </div>
                                        </div>

                                        {/* Счетчик поинтов */}
                                        <div 
                                            className="absolute"
                                            style={{ 
                                                transform: `translate(${logoPosition.x}px, ${logoPosition.y + 360}px)`,
                                            }}
                                        >
                                            <div className="text-center">
                                                <div 
                                                    className="text-6xl font-black mb-4"
                                                    style={{
                                                        background: 'linear-gradient(135deg, #00d4ff 0%, #ffffff 25%, #e0e0e0 50%, #ffffff 75%, #00d4ff 100%)',
                                                        WebkitBackgroundClip: 'text',
                                                        WebkitTextFillColor: 'transparent',
                                                        backgroundClip: 'text',
                                                        fontWeight: '900',
                                                        WebkitTextStroke: '4px black',
                                                        textShadow: '0 0 20px rgba(0,212,255,0.5)',
                                                        letterSpacing: '0.1em'
                                                    }}
                                                >
                                                    {points.toLocaleString()}
                                                </div>
                                                
                                                {/* Server Points Display */}
                                                {serverPoints !== points && (
                                                    <div className="text-sm text-blue-300 opacity-75">
                                                        Server: {serverPoints.toLocaleString()}
                                                    </div>
                                                )}
                                            </div>
                                        </div>

                                        {/* Leaderboard Modal */}
                                        {showLeaderboard && (
                                            <div 
                                                className="absolute inset-0 bg-black bg-opacity-80 flex items-center justify-center z-50"
                                                onClick={() => setShowLeaderboard(false)}
                                            >
                                                <div 
                                                    className="bg-gray-900 rounded-xl p-6 max-w-sm w-full mx-4 border-2 border-blue-500"
                                                    onClick={(e) => e.stopPropagation()}
                                                >
                                                    <div className="flex items-center justify-between mb-4">
                                                        <h3 className="text-xl font-bold text-white flex items-center">
                                                            🏆 Лидеры
                                                        </h3>
                                                        <button 
                                                            onClick={() => setShowLeaderboard(false)}
                                                            className="text-gray-400 hover:text-white text-2xl"
                                                        >
                                                            ×
                                                        </button>
                                                    </div>
                                                    
                                                    <div className="space-y-2 max-h-64 overflow-y-auto">
                                                        {leaderboard.length > 0 ? leaderboard.map((player, index) => (
                                                            <div 
                                                                key={player.telegram_id}
                                                                className={`flex items-center justify-between p-3 rounded-lg ${
                                                                    player.telegram_id === parseInt(user.id) 
                                                                        ? 'bg-blue-600 bg-opacity-30 border border-blue-400' 
                                                                        : 'bg-gray-800'
                                                                }`}
                                                            >
                                                                <div className="flex items-center space-x-3">
                                                                    <div className="text-lg font-bold text-yellow-400">
                                                                        #{index + 1}
                                                                    </div>
                                                                    <div>
                                                                        <div className="text-white font-semibold">
                                                                            {player.first_name || player.username || 'Player'}
                                                                        </div>
                                                                        <div className="text-gray-400 text-sm">
                                                                            @{player.username || 'unknown'}
                                                                        </div>
                                                                    </div>
                                                                </div>
                                                                <div className="text-blue-300 font-bold">
                                                                    {player.points.toLocaleString()}
                                                                </div>
                                                            </div>
                                                        )) : (
                                                            <div className="text-center text-gray-400 py-8">
                                                                Загрузка лидеров...
                                                            </div>
                                                        )}
                                                    </div>
                                                    
                                                    <button 
                                                        onClick={() => loadLeaderboard()}
                                                        className="w-full mt-4 bg-blue-600 text-white py-2 rounded-lg hover:bg-blue-700 transition-colors"
                                                    >
                                                        🔄 Обновить
                                                    </button>
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div className="absolute bottom-2 left-1/2 transform -translate-x-1/2 w-32 h-1 bg-white rounded-full opacity-60"></div>
                    </div>
                </div>
            );
        };

        ReactDOM.render(<VelnGameInterface />, document.getElementById('root'));
    </script>
</body>
</html>
'''

# Webhook functions for Telegram Bot integration
import requests
import json

def send_message(chat_id, text, reply_markup=None):
    """Отправить сообщение пользователю"""
    if not BOT_TOKEN or BOT_TOKEN == 'your_bot_token_here':
        logger.warning("BOT_TOKEN not configured")
        return None
        
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    
    if reply_markup:
        data['reply_markup'] = json.dumps(reply_markup)
    
    try:
        response = requests.post(url, data=data)
        return response.json()
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return None

def create_game_keyboard():
    """Создать клавиатуру с кнопкой игры"""
    game_url = request.host_url.rstrip('/') + '/game'
    return {
        'inline_keyboard': [
            [
                {
                    'text': '🎮 ИГРАТЬ В VELN',
                    'web_app': {'url': game_url}
                }
            ],
            [
                {
                    'text': '🏆 Лидеры',
                    'callback_data': 'leaderboard'
                },
                {
                    'text': '📊 Статистика',
                    'callback_data': 'stats'
                }
            ]
        ]
    }

def register_user_from_telegram(user_data):
    """Зарегистрировать пользователя из Telegram"""
    try:
        conn = sqlite3.connect('veln_game.db')
        cursor = conn.cursor()
        
        # Проверяем, существует ли пользователь
        cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (user_data['id'],))
        existing_user = cursor.fetchone()
        
        if existing_user:
            conn.close()
            return True
        
        # Создаем нового пользователя
        cursor.execute('''
            INSERT INTO users (telegram_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
        ''', (
            user_data['id'],
            user_data.get('username', ''),
            user_data.get('first_name', ''),
            user_data.get('last_name', '')
        ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"New user registered from Telegram: {user_data['id']}")
        return True
    except Exception as e:
        logger.error(f"Registration from Telegram error: {e}")
        return False

def handle_start_command(message):
    """Обработка команды /start"""
    user = message['from']
    chat_id = message['chat']['id']
    
    # Регистрируем пользователя
    register_user_from_telegram(user)
    
    welcome_text = f"""
🎮 <b>Добро пожаловать в VELN Game!</b>

Привет, {user.get('first_name', 'Игрок')}! 

<b>VELN</b> - это увлекательная игра, где ты:
• ⏰ Собираешь поинты каждую секунду
• 🏆 Соревнуешься с другими игроками  
• 📈 Поднимаешься в таблице лидеров
• 💰 Накапливаешь Time-Point-VELN COIN

<i>Твой прогресс сохраняется автоматически!</i>

👇 Нажми кнопку ниже, чтобы начать игру:
"""
    
    keyboard = create_game_keyboard()
    send_message(chat_id, welcome_text, keyboard)

def handle_game_command(message):
    """Обработка команды /game"""
    chat_id = message['chat']['id']
    
    game_text = """
🎯 <b>Запуск VELN Game</b>

Нажми кнопку ниже, чтобы открыть игру:
"""
    
    keyboard = create_game_keyboard()
    send_message(chat_id, game_text, keyboard)

def handle_stats_command(message):
    """Обработка команды /stats"""
    user = message['from']
    chat_id = message['chat']['id']
    
    try:
        conn = sqlite3.connect('veln_game.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (user['id'],))
        user_data = cursor.fetchone()
        conn.close()
        
        if user_data:
            stats_text = f"""
📊 <b>Твоя статистика</b>

👤 <b>Игрок:</b> {user_data[3] or 'Неизвестно'}
💰 <b>Поинты:</b> {user_data[5]:,}
📅 <b>Играешь с:</b> {user_data[6][:10]}

🎮 <b>Продолжай играть и собирай больше поинтов!</b>
"""
        else:
            stats_text = """
❌ <b>Статистика недоступна</b>

Сначала запусти игру командой /game
"""
    except Exception as e:
        logger.error(f"Stats error: {e}")
        stats_text = """
❌ <b>Ошибка получения статистики</b>

Попробуй позже или запусти игру заново.
"""
    
    keyboard = create_game_keyboard()
    send_message(chat_id, stats_text, keyboard)

def handle_leaderboard_command(message):
    """Обработка команды /leaderboard"""
    chat_id = message['chat']['id']
    user_id = message['from']['id']
    
    try:
        conn = sqlite3.connect('veln_game.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT telegram_id, username, first_name, points
            FROM users 
            WHERE points > 0 
            ORDER BY points DESC 
            LIMIT 10
        ''')
        
        results = cursor.fetchall()
        conn.close()
        
        if results:
            leaderboard_text = "🏆 <b>Таблица лидеров</b>\n\n"
            
            for i, player in enumerate(results, 1):
                emoji = "👑" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "▫️"
                highlight = "🔸" if player[0] == user_id else ""
                name = player[2] or player[1] or 'Player'
                
                leaderboard_text += f"{emoji} <b>{i}.</b> {highlight}{name} - {player[3]:,} поинтов\n"
            
            leaderboard_text += "\n🎮 <b>Играй и поднимайся выше!</b>"
        else:
            leaderboard_text = """
🏆 <b>Таблица лидеров пуста</b>

Стань первым! Запусти игру и начни собирать поинты.
"""
    except Exception as e:
        logger.error(f"Leaderboard error: {e}")
        leaderboard_text = """
❌ <b>Ошибка загрузки лидеров</b>

Попробуй позже.
"""
    
    keyboard = create_game_keyboard()
    send_message(chat_id, leaderboard_text, keyboard)

def handle_help_command(message):
    """Обработка команды /help"""
    chat_id = message['chat']['id']
    
    help_text = """
❓ <b>Помощь по VELN Game</b>

<b>Команды бота:</b>
/start - 🎮 Начать игру
/game - 🎯 Открыть игру
/stats - 📊 Твоя статистика  
/leaderboard - 🏆 Таблица лидеров
/help - ❓ Эта справка

<b>Как играть:</b>
• Открой игру через Web App
• Поинты начисляются автоматически
• Перетаскивай логотип VELN
• Соревнуйся с другими игроками
• Прогресс сохраняется навсегда

<b>Поддержка:</b> @dante_moretti
"""
    
    keyboard = create_game_keyboard()
    send_message(chat_id, help_text, keyboard)

def handle_callback_query(callback_query):
    """Обработка inline кнопок"""
    data = callback_query['data']
    message = callback_query['message']
    
    if data == 'leaderboard':
        handle_leaderboard_command({'chat': message['chat'], 'from': callback_query['from']})
    elif data == 'stats':
        handle_stats_command({'chat': message['chat'], 'from': callback_query['from']})

@app.route('/webhook', methods=['POST'])
def webhook():
    """Webhook для получения обновлений от Telegram"""
    if not BOT_TOKEN or BOT_TOKEN == 'your_bot_token_here':
        return jsonify({'error': 'BOT_TOKEN not configured'}), 400
        
    try:
        update = request.get_json()
        
        if 'message' in update:
            message = update['message']
            
            if 'text' in message:
                text = message['text']
                
                if text.startswith('/start'):
                    handle_start_command(message)
                elif text.startswith('/game'):
                    handle_game_command(message)
                elif text.startswith('/stats'):
                    handle_stats_command(message)
                elif text.startswith('/leaderboard'):
                    handle_leaderboard_command(message)
                elif text.startswith('/help'):
                    handle_help_command(message)
                else:
                    # Неизвестная команда
                    chat_id = message['chat']['id']
                    send_message(chat_id, "❓ Неизвестная команда. Используй /help для справки.")
        
        elif 'callback_query' in update:
            handle_callback_query(update['callback_query'])
        
        return jsonify({'status': 'ok'})
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/set_webhook', methods=['GET', 'POST'])
def set_webhook_route():
    """Установить webhook для бота"""
    if not BOT_TOKEN or BOT_TOKEN == 'your_bot_token_here':
        return jsonify({'error': 'BOT_TOKEN not configured'}), 400
        
    webhook_url = request.host_url.rstrip('/') + '/webhook'
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
    
    data = {
        'url': webhook_url,
        'allowed_updates': ['message', 'callback_query']
    }
    
    try:
        response = requests.post(url, data=data)
        return jsonify({
            'webhook_url': webhook_url,
            'telegram_response': response.json()
        })
    except Exception as e:
        logger.error(f"Set webhook error: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
