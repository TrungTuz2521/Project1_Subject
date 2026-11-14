from flask import Flask, jsonify
from flask_cors import CORS
from sqlalchemy.exc import IntegrityError, OperationalError
from werkzeug.exceptions import HTTPException
from app.config.config import settings
from app.extensions import db
from app.contracts.errors import DomainError
from app.utils.serialization import encode

def create_app(config=None):
    app = Flask(__name__)
    app.config.update(settings())
    app.config.update(config or {})
    if not app.config.get('SQLALCHEMY_DATABASE_URI'):
        raise RuntimeError('Configure backend/.env: TIDB_* or DATABASE_URL.')
    if len(app.config.get('JWT_SECRET_KEY', '').encode()) < 32:
        raise RuntimeError('JWT_SECRET_KEY must have at least 32 bytes. Set it in backend/.env.')
    if app.config['TESTING']:
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {}
        # Tests explicitly opt in; local SMTP settings must not change legacy fixtures.
        app.config['EMAIL_ENABLED'] = (config or {}).get('EMAIL_ENABLED', False)
        app.config['DEMO_PAYMENT_ENABLED'] = (config or {}).get('DEMO_PAYMENT_ENABLED', False)
        # A developer's real SePay key in backend/.env must not switch legacy tests to QR auto-confirmation.
        app.config['SEPAY_WEBHOOK_KEY'] = (config or {}).get('SEPAY_WEBHOOK_KEY', '')
    hops = int(app.config.get('TRUSTED_PROXY_HOPS') or 0)
    if hops:
        # Behind a load balancer the socket address is the proxy: read the client IP and https from its headers,
        # so rate limits apply per customer. Only as many hops as there really are, or a client could forge them.
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops, x_host=hops)
    db.init_app(app)
    from app import models  # noqa: F401  (registers every table on the metadata)
    from app.routes.api import api
    app.register_blueprint(api, url_prefix='/api/v1')
    from app.booking_module import install as install_booking
    install_booking(app)
    from app.middleware.rate_limit import install_auth_limit
    install_auth_limit(app)
    from app.infrastructure.retry import retry_conflicts
    # These endpoints perform only database work; never wrap external payment orchestration.
    for endpoint in ('register', 'me', 'team_collection', 'team_item', 'create_request',
                     'request_item', 'read_notification', 'read_all_notifications'):
        key = 'api.' + endpoint
        app.view_functions[key] = retry_conflicts(app.view_functions[key])
    CORS(app, resources={r'/api/v1/*': {'origins': app.config['CORS_ORIGINS']}},
         allow_headers=['Authorization', 'Content-Type'], expose_headers=['Content-Disposition'],
         methods=['GET', 'POST', 'PATCH', 'DELETE', 'OPTIONS'])

    @app.errorhandler(DomainError)
    def domain_error(error):
        return jsonify(encode({'error': {'code': error.code, 'message': error.message, 'fields': error.fields}})), error.status

    @app.errorhandler(IntegrityError)
    def integrity_error(error):
        app.logger.warning('Database constraint rejected command')
        return domain_error(DomainError('STATE_CONFLICT', 'Dữ liệu trùng hoặc liên kết không hợp lệ.', 409))

    @app.errorhandler(OperationalError)
    def database_error(error):
        app.logger.error('Database operation unavailable (%s)', type(error).__name__)
        return domain_error(DomainError('DATABASE_UNAVAILABLE', 'Database tạm thời không khả dụng.', 503))

    @app.errorhandler(HTTPException)
    def http_error(error):
        return domain_error(DomainError('HTTP_ERROR', error.description, error.code))

    @app.errorhandler(Exception)
    def unexpected(error):
        app.logger.error('Unexpected request failure: %s', type(error).__name__)
        return domain_error(DomainError('INTERNAL_ERROR', 'Đã xảy ra lỗi hệ thống.', 500))

    from app.jobs.commands import register_commands
    register_commands(app)
    return app
