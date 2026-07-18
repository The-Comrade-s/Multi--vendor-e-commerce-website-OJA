from app.extensions import db
from app.models import Notification


def notify(user_id, title, body=None, url=None, icon="bi-bell"):
    n = Notification(user_id=user_id, title=title, body=body, url=url, icon=icon)
    db.session.add(n)
    db.session.commit()
    return n
