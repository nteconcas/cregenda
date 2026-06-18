web: python init_app.py && gunicorn -w 1 -b 0.0.0.0:$PORT --timeout 120 --keep-alive 5 --access-logfile - --error-logfile - --log-level info wsgi:app
