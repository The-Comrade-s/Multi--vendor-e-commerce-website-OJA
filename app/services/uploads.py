import os
import uuid
from werkzeug.utils import secure_filename
from flask import current_app


def allowed_file(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]


def save_upload(file_storage, subfolder=""):
    """Saves an uploaded file and returns its filename (relative to the
    static/uploads folder), or None if no valid file was given."""
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_file(file_storage.filename):
        return None

    ext = file_storage.filename.rsplit(".", 1)[-1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"

    folder = os.path.join(current_app.config["UPLOAD_FOLDER"], subfolder)
    os.makedirs(folder, exist_ok=True)
    file_storage.save(os.path.join(folder, filename))

    return f"{subfolder}/{filename}" if subfolder else filename
