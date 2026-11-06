import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ims_core.settings')

app = Celery('ims_core')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

