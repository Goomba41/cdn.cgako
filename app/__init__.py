"""CDNAPI version 1.0.0 initialization package."""

from flask import Flask
from flask_thumbnails import Thumbnail

app = Flask(__name__)
app.config.from_object('config')

thumbnail = Thumbnail(app)

from app import api  # noqa
