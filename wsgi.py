import os
from app import app
from database import init_db

# Automatically initialize database and default bootstrap records on server startup
init_db()

# Expose WSGI application callable
application = app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
