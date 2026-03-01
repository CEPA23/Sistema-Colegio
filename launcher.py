import threading
import webview
import os
import sys
from waitress import serve
from django.core.wsgi import get_wsgi_application
from django.contrib.staticfiles.handlers import StaticFilesHandler

if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

os.environ['BASE_DIR'] = BASE_DIR

def start_server():
    application = get_wsgi_application()
    application = StaticFilesHandler(application)
    serve(application, host='127.0.0.1', port=8000)

t = threading.Thread(target=start_server)
t.daemon = True
t.start()

webview.create_window("Sistema", "http://127.0.0.1:8000")
webview.start()