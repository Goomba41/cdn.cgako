"""Classes for API."""
# -*- coding: utf-8 -*-
import os
import magic
import subprocess
import hashlib
from datetime import datetime
from flask import url_for
from app import app


class FileSystemObject:
    """Class describing files and directories on filesystem as objects."""

    def __init__(self, path):
        """Class description."""
        self.path = path
        self.type = 'directory' if os.path.isdir(self.path) \
            else magic.from_file(self.path, mime=True)
        self.name = self.path.rsplit('/', maxsplit=1)[-1]
        self.link = url_for(
            '.get_file',
            asked_file_path=os.path.relpath(
                self.path,
                app.config['ROOT_PATH']
            ),
            _external=True
        )
        self.sizeBytes = int(
            subprocess.check_output(
                "du -sb %s | cut -f1" % (self.path),
                shell=True
            )
        ) if os.path.isdir(self.path) else os.stat(self.path).st_size
        self.sizeFormatted = self.get_file_size(self.sizeBytes)
        self.created = str(
            datetime.fromtimestamp(
                int(os.stat(self.path).st_ctime)
            )
        )
        self.modified = str(
            datetime.fromtimestamp(
                int(os.stat(self.path).st_mtime)
            )
        )
        if os.path.isfile(self.path):
            self.hash = self.file_hash()

    def __repr__(self):
        """Class representation string."""
        return "File system object «%s»" % (self.name)

    def get_metadata(self):
        """Get class data in json dictionary."""
        returned_dict = {
            "name": self.name,
            "path": self.path,
            "type": self.type,
            "link": self.link,
            "sizeBytes": self.sizeBytes,
            "sizeNumber": self.sizeFormatted['number'],
            "sizeSuffix": self.sizeFormatted['suffix'],
            "created": self.created,
            "modified": self.modified,
        }
        if hasattr(self, 'hash'):
            returned_dict["hash"] = self.hash
        return returned_dict

    def get_file_size(self, num, suffix='B'):
        """Get size in json dictionary with auto detecting measure unit."""
        for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
            if abs(num) < 1024.0:
                return {
                    'number': float("{:.2f}".format(num)),
                    'suffix': "%s%s" % (unit, suffix)
                }
            num /= 1024.0
        return {
            'number': float("{:.2f}".format(num)),
            'suffix': "%s%s%s" % (num, 'Yi', suffix)
        }

    def file_hash(self):
        """Get file hash in sha512."""
        hash = hashlib.sha512()
        with open(self.path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash.update(chunk)
        return hash.hexdigest()
