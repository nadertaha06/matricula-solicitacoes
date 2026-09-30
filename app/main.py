from app.api import create_app
from app.routes import router
from app.handlers import handle_event

app = create_app(router, handle_event)
