# web: — команда запуска. Дефолт gunicorn (1 sync-worker!) означает «весь API обслуживает
# один запрос одновременно»: один медленный ?search= блокирует каталог для всех.
# --bind 0.0.0.0:$PORT обязателен для Render (он проксирует на container port).
web: gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-10000} --workers 3 --threads 4 --worker-class gthread --timeout 60 --graceful-timeout 30 --max-requests 1000 --max-requests-jitter 200 --access-logfile - --error-logfile -
