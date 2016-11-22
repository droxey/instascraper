Start celery: python manage.py celery worker --app=instascraper --broker='redis://localhost:6379/0' --loglevel=INFO
Ensure redis port and celery port are both set and matching in django settings