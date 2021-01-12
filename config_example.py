# С ОСТОРОЖНОСТЬЮ! Скрытые директории в списке не скрываются,
# следовательно можно зайти в папку с миниатюрами,
# открыть миниатюру и создать на нее миниатюру, и так до бесконечности.

import os

ROOT_PATH = '/<path>/<to>/<root>/<directory>'
THUMBNAILS_FOLDER = '.thumbnails'

THUMBNAIL_MEDIA_ROOT = ROOT_PATH
THUMBNAIL_MEDIA_THUMBNAIL_ROOT = os.path.join(ROOT_PATH, THUMBNAILS_FOLDER)

THUMBNAIL_MEDIA_URL = '/files/'
THUMBNAIL_MEDIA_THUMBNAIL_URL = '/files/.thumbnails/'

THUMBNAIL_DEFAUL_FORMAT = 'JPEG'
