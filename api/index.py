import os
import sys

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

# WSGI application callable for Vercel Serverless Functions
app = get_wsgi_application()
