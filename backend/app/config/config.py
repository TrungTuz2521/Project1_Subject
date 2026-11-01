import os
import ssl
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy.engine import URL

def settings():
    load_dotenv(Path(__file__).resolve().parents[2] / '.env', override=False)
    secret = os.getenv('JWT_SECRET_KEY', '')
    uri = os.getenv('DATABASE_URL')
    options = {'pool_pre_ping': True, 'pool_recycle': 300}
    if not uri:
        required = ['TIDB_HOST', 'TIDB_USERNAME', 'TIDB_PASSWORD', 'TIDB_DATABASE']
        if all(os.getenv(k) for k in required):
            uri = URL.create('mysql+pymysql', username=os.environ['TIDB_USERNAME'],
                             password=os.environ['TIDB_PASSWORD'], host=os.environ['TIDB_HOST'],
                             port=int(os.getenv('TIDB_PORT', '4000')), database=os.environ['TIDB_DATABASE'],
                             query={'charset': 'utf8mb4'})
    if uri and str(uri).startswith('mysql'):
        options['isolation_level'] = 'READ COMMITTED'
        options['connect_args'] = {'ssl': ssl.create_default_context(cafile=os.getenv('TIDB_CA_PATH') or None),
                                   'init_command': "SET time_zone = '+00:00'", 'connect_timeout': 10}
    return {'SQLALCHEMY_DATABASE_URI': uri, 'SQLALCHEMY_ENGINE_OPTIONS': options,
            'SQLALCHEMY_TRACK_MODIFICATIONS': False, 'JWT_SECRET_KEY': secret,
            'JWT_ISSUER': 'football-field-api', 'JWT_AUDIENCE': 'football-field-web',
            'CORS_ORIGINS': os.getenv('CORS_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(','),
            'MAX_CONTENT_LENGTH': 64 * 1024}
