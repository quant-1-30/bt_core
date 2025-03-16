# gunicorn.conf.py
workers = 4
worker_class = "uvicorn.workers.UvicornWorker"
bind = "0.0.0.0:11000"
timeout = 60
accesslog = "access.log"
errorlog = "error.log"
