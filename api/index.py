import os
import sys
import urllib.parse

# Ensure the root directory is on the Python path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ims_core.settings')

import django
django.setup()

# Auto-migrate and seed on cold start if running on serverless / fresh DB
try:
    from django.core.management import call_command
    from inventory.models import Product
    call_command('migrate', interactive=False)
    seed_file = os.path.join(ROOT_DIR, 'seed_data.json')
    if os.path.exists(seed_file) and not Product.objects.exists():
        call_command('loaddata', seed_file)
except Exception as e:
    print(f"Auto-migration/seed note: {e}")

from django.core.wsgi import get_wsgi_application

_django_app = get_wsgi_application()

def app(environ, start_response):
    """
    WSGI Adapter for Vercel Serverless Functions.
    Restores the original request URL from Vercel rewrite params or headers,
    preventing 404s when rewritten to /api/index.py.
    """
    # 1. Recover true path from Vercel edge proxy headers
    true_path = (
        environ.get('HTTP_X_FORWARDED_URI') or
        environ.get('HTTP_X_REAL_PATH') or
        environ.get('RAW_URI') or
        environ.get('REQUEST_URI') or
        environ.get('HTTP_X_MATCHED_PATH')
    )
    if true_path and not true_path.startswith('/api/index.py'):
        environ['PATH_INFO'] = true_path.split('?')[0]
    # 2. Recover from rewrite query parameter ?__path__=...
    elif 'QUERY_STRING' in environ:
        query = urllib.parse.parse_qs(environ['QUERY_STRING'])
        if '__path__' in query and query['__path__']:
            environ['PATH_INFO'] = '/' + query['__path__'][0].lstrip('/')
        elif 'path' in query and query['path']:
            environ['PATH_INFO'] = '/' + query['path'][0].lstrip('/')

    # 3. Guard against unresolved serverless entrypoint path
    path_info = environ.get('PATH_INFO', '')
    if path_info in ('/api/index.py', 'api/index.py', '/api', '/api/'):
        environ['PATH_INFO'] = '/'

    return _django_app(environ, start_response)
