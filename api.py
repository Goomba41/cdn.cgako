# -*- coding: utf-8 -*-

import hashlib
import math
import os
import pathlib
import shutil
import subprocess
import traceback
import uuid
from datetime import datetime
from distutils.util import strtobool
from operator import itemgetter
from urllib.parse import urljoin

from flask import Flask, Response, json, redirect, request, \
    send_from_directory, url_for

from flask_thumbnails import Thumbnail
from flask_thumbnails.utils import parse_size

import magic

from werkzeug.utils import secure_filename

app = Flask(__name__)

thumbnail = Thumbnail(app)

app.config.from_object('config')

# ----------------------------------------------------------------------


class FileSystemObject:

    def __init__(self, path):
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
        return "File system object «%s»" % (self.name)

    def get_metadata(self):
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
        for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
            if abs(num) < 1024.0:
                return {
                    'number': float("{:.2f}".format(num)),
                    'suffix': "%s%s" % (unit, suffix)
                }
            num /= 1024.0
        return {
            'number': float("{:.2f}".format(num)),
            'suffix': "%s%s" % (num, 'Yi', suffix)
        }

    def file_hash(self):
        hash = hashlib.sha512()
        with open(self.path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash.update(chunk)
        return hash.hexdigest()

# ----------------------------------------------------------------------


# Генерация ответа сервера при ошибке
def json_http_response(dbg=False, given_message=None, status=500):
    """Вывод серверной ошибки с трейсом. Параметр dbg отвечает за вывод
    в формате traceback."""

    if status in (400, 401, 403, 404, 500):
        response_type = 'Error'
        if status == 400:
            message = 'Bad request!'
        if status == 401:
            message = 'Unauthorized!'
        if status == 403:
            message = 'Forbidden'
        if status == 404:
            message = 'Not found!'
        if status == 500:
            message = 'Internal server error!'
    elif status in (200, 201):
        response_type = 'Success'
        if status == 200:
            message = 'OK!'
        if status == 201:
            message = 'Created!'
    elif status in (304,):
        response_type = 'Warning'
        message = 'Not modified!'
    else:
        response_type = 'Info'
        message = 'I don`t know what to say! Probably this is test response?'

    info = {
        'responseType': response_type,
        'message': message,
        'status': status
    }

    info['message'] = given_message if given_message is not None else message

    if isinstance(dbg, bool):
        if dbg is True:
            info['debugInfo'] = traceback.format_exc()
    else:
        try:
            if strtobool(dbg):
                info['debugInfo'] = traceback.format_exc()
        except Exception:
            info['debugInfo'] = "Debugging info is turned off, because " \
                "incorrect type of value of parameter 'dbg' " \
                "(should be boolean)"

    return Response(
        response=json.dumps(info),
        status=status,
        mimetype='application/json'
    )


# Пагинация получаемого с API списка
def pagination_of_list(query_result, url, query_params):
    """ Пагинация результатов запроса. Принимает параметры:
    результат запроса (json), URL API для генерации ссылок, стартовая позиция,
    количество выводимых записей"""

    start = query_params.get('start', 1)
    limit = query_params.get('limit', 10)

    query_params_string = ''
    for i in query_params:
        if i not in ('start', 'limit'):
            query_params_string += '&%s=%s' % (
                i, query_params.get(i).replace(' ', '+')
            )

    records_count = len(query_result)

    if not isinstance(start, int):
        try:
            start = int(start)
        except ValueError:
            start = 1
    elif start < 1:
        start = 1

    if not isinstance(limit, int):
        try:
            limit = int(limit)
        except ValueError:
            limit = 10
    elif limit < 1:
        limit = 10

    if records_count < start and records_count != 0:
        start = records_count
    elif records_count < start and records_count <= 0:
        start = 1

    response_obj = {}
    response_obj['start'] = start
    response_obj['limit'] = limit
    response_obj['itemsCount'] = records_count

    pages_count = math.ceil(records_count / limit)
    response_obj['pages'] = pages_count if pages_count > 0 else 1

    # Создаем URL на предыдущую страницу
    if start == 1:
        response_obj['previousPage'] = ''
    else:
        start_copy = max(1, start - limit)
        limit_copy = start - 1
        params = '?start=%d&limit=%d%s' % (
            start_copy,
            limit_copy,
            query_params_string
        )
        new_url = urljoin(url,
                          params)
        response_obj['previousPage'] = new_url

    # Создаем URL на следующую страницу
    if start + limit > records_count:
        response_obj['nextPage'] = ''
    else:
        start_copy = start + limit
        params = '?start=%d&limit=%d%s' % (
            start_copy,
            limit,
            query_params_string
        )
        new_url = urljoin(url,
                          params)
        response_obj['nextPage'] = new_url

    # Отсеивание результатов запроса
    response_obj['results'] = query_result[(start - 1):(start - 1 + limit)]

    return response_obj

# ----------------------------------------------------------------------


# Фавиконка
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        directory=pathlib.Path().absolute(),
        filename='faviconDev.ico'
    )


# Редирект с корня на список файлов
@app.route('/', methods=['GET', 'POST', 'PUT', 'DELETE'])
def hello():
    return redirect(url_for('get_file', _external=True))

# ----------------------------------------------------------------------


@app.route('/files', methods=['GET'])
@app.route('/files/<path:asked_file_path>', methods=['GET'])
def get_file(asked_file_path=''):
    try:
        if not os.path.exists(app.config['ROOT_PATH']):
            os.makedirs(app.config['ROOT_PATH'])

        file_real_path = os.path.join(app.config['ROOT_PATH'], asked_file_path)

        if os.path.exists(file_real_path):
            is_directory = os.path.isdir(file_real_path)
            if is_directory:

                search_query = request.args.get('q', None)
                if search_query:
                    try:
                        search_params_all = dict(
                            e.split(':') for e in search_query.split(' ')
                        )
                    except Exception:
                        return json_http_response(
                            status=400,
                            given_message="Incorrect value of parameter 'q' "
                            "(should be 'field1:value1+field2:value2')",
                            dbg=request.args.get('dbg', False)
                        )
                    supported_params = (
                        'name',
                        'sizeNumber',
                        'sizeSuffix',
                        'type',
                        'created',
                        'modified',
                        'sizeBytes'
                    )
                    unprocessed_params = ()
                    search_params = {
                        k: search_params_all[k] for k in supported_params
                        if k in search_params_all
                    }
                else:
                    search_params = None

                files = []
                if asked_file_path:
                    partial_asked_file_path = '/'.join(
                        asked_file_path.split('/')[:-1]
                    )
                    parent_directory = url_for(
                        '.get_file',
                        asked_file_path=partial_asked_file_path
                        if partial_asked_file_path else None,
                        _external=True
                    )
                else:
                    parent_directory = 'This is root directory!'

                for filename in os.listdir(file_real_path):
                    file_path = os.path.join(file_real_path, filename)

                    metadata = FileSystemObject(file_path).get_metadata()

                    if search_params:
                        if all(
                            True if val in metadata.get(key, None) else False
                            for key, val in search_params.items()
                        ):
                            files.append(metadata)
                    else:
                        files.append(metadata)

                sorting_query = request.args.get('sf', None)
                sorting_order = request.args.get('so', None)

                sorting_reverse = False
                if sorting_order and sorting_order.lower() == 'd':
                    sorting_reverse = True

                if sorting_query:
                    try:
                        sorting_params_all = sorting_query.split(' ')
                    except Exception:
                        return json_http_response(
                            status=400,
                            given_message="Incorrect value of parameter 'sf' "
                            "(should be 'field1+field2')",
                            dbg=request.args.get('dbg', False)
                        )
                    supported_s_params = (
                        'name',
                        'type',
                        'created',
                        'modified',
                        'sizeBytes',
                        'sizeNumber',
                        'sizeSuffix'
                    )
                    unprocessed_s_params = ('sizeNumber', 'sizeSuffix')
                    sorting_params = [
                        k for k in supported_s_params
                        if (
                            k in sorting_params_all and
                            k not in unprocessed_s_params
                        )
                    ]
                    if not sorting_params:
                        sorting_params.append('name')
                else:
                    sorting_params = ['name']

                sorted_files = sorted(
                    files,
                    key=itemgetter(*sorting_params),
                    reverse=sorting_reverse
                )

                paginated_data = pagination_of_list(
                    sorted_files,
                    url_for(
                        '.get_file',
                        asked_file_path=asked_file_path,
                        _external=True
                    ),
                    query_params=request.args
                )

                response_obj = {
                    'parentDirectory': parent_directory,
                    'filesList': paginated_data.pop('results'),
                    'paginationData': paginated_data
                }

                if search_params:
                    for k in search_params_all:
                        search_params[k] = 'Unsupported :(' \
                            if k not in supported_params else 'Unprocessed :('\
                            if k in unprocessed_params else search_params[k]
                    response_obj['searchParams'] = search_params
                if sorting_query or sorting_order:
                    sorting_params = {'sortedBy': sorting_params}
                    if sorting_query:
                        unsupported_s_params = [
                            k for k in sorting_params_all
                            if k not in supported_s_params
                        ]
                        if unsupported_s_params:
                            sorting_params['unsupportedParams'] =\
                                unsupported_s_params
                        if unprocessed_s_params:
                            sorting_params['unprocessedParams'] = [
                                k for k in sorting_params_all
                                if k in unprocessed_s_params
                            ]
                    sorting_params['sortingDirection'] = 'Desc' \
                        if sorting_reverse else 'Asc'
                    response_obj['sortingParams'] = sorting_params

                return Response(
                    response=json.dumps(response_obj, ensure_ascii=False),
                    status=200,
                    mimetype='application/json'
                )
            else:
                try:
                    original = os.path.join(
                        app.config['ROOT_PATH'],
                        asked_file_path
                    )

                    make_thumbnail = request.args.get('thumbnail', False)

                    if not isinstance(make_thumbnail, bool):
                        try:
                            make_thumbnail = strtobool(make_thumbnail)
                        except Exception:
                            return Response(
                                response=json.dumps(
                                    {
                                        'responseType': 'Error',
                                        'status': 400,
                                        'message': 'Your «makeThumbnail» '
                                        'parameter is invalid (must be '
                                        'boolean value)!'
                                    }
                                ),
                                status=400,
                                mimetype='application/json'
                            )

                    if make_thumbnail:

                        thumbnail_size = request.args.get('size', None)
                        thumbnail_crop = request.args.get('crop', False)

                        if thumbnail_size:
                            try:
                                parse_size(thumbnail_size)
                            except Exception:
                                return Response(
                                    response=json.dumps(
                                        {
                                            'responseType': 'Error',
                                            'status': 400,
                                            'message': 'Your «size» parameter '
                                            'is invalid (must be INT '
                                            'or INTxINT value)!'
                                        }
                                    ),
                                    status=400,
                                    mimetype='application/json'
                                )
                        else:
                            thumbnail_size = '200x200'

                        if not isinstance(thumbnail_crop, bool):
                            try:
                                thumbnail_crop = strtobool(thumbnail_crop)
                                if thumbnail_crop:
                                    thumbnail_crop = 'fit'
                                else:
                                    thumbnail_crop = 'sized'
                            except Exception:
                                return Response(
                                    response=json.dumps(
                                        {
                                            'responseType': 'Error',
                                            'status': 400,
                                            'message': 'Your «crop» parameter '
                                            'is invalid (must be '
                                            'boolean value)!'
                                        }
                                    ),
                                    status=400,
                                    mimetype='application/json'
                                )

                        originalPath, originalName = os.path.split(original)
                        if app.config['THUMBNAILS_FOLDER'][0] != '.':
                            app.config['THUMBNAILS_FOLDER'] = '.'\
                                + app.config['THUMBNAILS_FOLDER']
                        app.config['THUMBNAIL_MEDIA_THUMBNAIL_ROOT'] = \
                            os.path.join(
                                originalPath,
                                app.config['THUMBNAILS_FOLDER']
                        )
                        thumbnail_link = thumbnail.get_thumbnail(
                            original,
                            size=thumbnail_size,
                            crop=thumbnail_crop
                        )
                        thumbnail_path, thumbnailFilename = os.path.split(
                            thumbnail_link
                        )
                        return send_from_directory(
                            directory=thumbnail.thumbnail_directory,
                            filename=thumbnailFilename
                        )
                    else:
                        return send_from_directory(
                            directory=app.config['ROOT_PATH'],
                            filename=asked_file_path
                        )
                except IOError:
                    return send_from_directory(
                        directory=app.config['ROOT_PATH'],
                        filename=asked_file_path
                    )
        else:
            return json_http_response(status=404)
    except Exception:
        return json_http_response(dbg=request.args.get('dbg', False))


@app.route('/files', methods=['DELETE'])
@app.route('/files/<path:asked_file_path>', methods=['DELETE'])
def delete_file(asked_file_path=''):
    try:
        file_real_path = os.path.join(app.config['ROOT_PATH'], asked_file_path)

        if os.path.exists(file_real_path):
            is_directory = os.path.isdir(file_real_path)
            if is_directory:
                if asked_file_path:
                    recursive = request.args.get('recursive', False)
                    given_message = ''
                    if not isinstance(recursive, bool):
                        try:
                            recursive = strtobool(recursive)
                        except Exception:
                            recursive = False
                            given_message += "Value of parameter «recursive» "
                            "is incorrect and set as FALSE by default. "
                    if recursive:
                        given_message += 'Directory delete recursively '
                        '(with all contents)!'
                        shutil.rmtree(file_real_path)
                    else:
                        try:
                            os.rmdir(file_real_path)
                            given_message += 'Directory «%s» delete '
                            'successful!' % (
                                asked_file_path.split('/')[-1:][0]
                            )
                        except Exception:
                            return json_http_response(
                                dbg=request.args.get('dbg', False),
                                given_message="Directory not empty! Check "
                                "directory and delete content manually or "
                                "set «recursive» parameter to true if you "
                                "want delete directory with all its "
                                "content."
                            )
                else:
                    return json_http_response(
                        status=403,
                        given_message='Root directory cannot be deleted!'
                    )
            else:
                try:
                    if os.path.exists(file_real_path):
                        os.remove(file_real_path)

                    file_path, fileName = os.path.split(file_real_path)

                    if app.config['THUMBNAILS_FOLDER'][0] != '.':
                        app.config['THUMBNAILS_FOLDER'] = '.'\
                            + app.config['THUMBNAILS_FOLDER']

                    thumbnail_path = os.path.join(
                        file_path,
                        app.config['THUMBNAILS_FOLDER']
                    )

                    if os.path.exists(thumbnail_path):
                        shutil.rmtree(thumbnail_path)
                    given_message = "File «%s» delete successful!" % (fileName)
                except Exception:
                    return json_http_response(
                        dbg=request.args.get('dbg', False)
                    )

            remove_empty = request.args.get('removeEmpty', False)

            if not isinstance(remove_empty, bool):
                try:
                    remove_empty = strtobool(remove_empty)
                except Exception:
                    return Response(
                        response=json.dumps(
                            {
                                'info': "Your «removeEmpty» "
                                "parameter is invalid (must "
                                "be boolean value)!",
                                'responseType': 'Error',
                                'status': 400,
                                'message': 'You didn`t send '
                                'file! Request ignored!'
                            }
                        ),
                        status=400,
                        mimetype='application/json'
                    )

            if remove_empty:
                file_path, fileName = os.path.split(file_real_path)

                if not os.listdir(file_path):
                    shutil.rmtree(file_path)
                    given_message += " Empty parent directory also removed."

            return json_http_response(status=200, given_message=given_message)
        else:
            return json_http_response(status=404)
    except Exception:
        return json_http_response(dbg=request.args.get('dbg', False))


@app.route('/files', methods=['POST'])
@app.route('/files/<path:asked_file_path>', methods=['POST'])
def post_file(asked_file_path=''):
    try:
        uploads = request.files.getlist('uploads')

        file_real_path = os.path.join(app.config['ROOT_PATH'], asked_file_path)

        if uploads:

            defined_files_names = request.args.get('names', None)

            if not os.path.exists(file_real_path):
                os.makedirs(file_real_path)

            uploaded_files_list = []
            defined_files_names = defined_files_names.split(' ')\
                if defined_files_names else None

            for file in uploads:
                old_file_name = file.filename
                old_file_ext = old_file_name.split(".")[-1]

                if defined_files_names:
                    new_full_file_name = secure_filename(
                        defined_files_names.pop(0) + '.' + old_file_ext
                    )
                else:
                    new_full_file_name = secure_filename(
                        uuid.uuid1().hex + '.' + old_file_ext
                    )

                file_path = os.path.join(file_real_path, new_full_file_name)
                file.save(file_path)

                metadata = FileSystemObject(file_path).get_metadata()
                metadata['oldName'] = old_file_name

                uploaded_files_list.append(metadata)

            parent_directory = url_for(
                '.get_file',
                asked_file_path=asked_file_path if asked_file_path else None,
                _external=True
            )

            response_obj = {
                'uploadedIn': parent_directory,
                'uploadedFiles': uploaded_files_list,
                'responseType': 'Success',
                'status': 200,
                'message': 'Files upload successful!'
            }

            unprocessed_params = ['createDirectory', 'random']
            tmp_unprocessed_params = []
            request_params = request.args
            for p in unprocessed_params:
                if p in request_params:
                    tmp_unprocessed_params.append(p)
            if tmp_unprocessed_params:
                response_obj['unprocessedParams'] = tmp_unprocessed_params

            return Response(
                response=json.dumps(response_obj),
                status=200,
                mimetype='application/json'
            )
        elif not uploads:
            create_directory = request.args.get('createDirectory', False)

            if not isinstance(create_directory, bool):
                try:
                    create_directory = strtobool(create_directory)
                except Exception:
                    return Response(
                        response=json.dumps(
                            {
                                'info': "Your «createDirectory» parameter "
                                "is invalid (must be boolean value)!",
                                'responseType': 'Error',
                                'status': 400,
                                'message': 'You didn`t send file! Request '
                                'ignored!'
                            }
                        ),
                        status=400,
                        mimetype='application/json'
                    )

            if create_directory:
                if not os.path.exists(file_real_path):
                    os.makedirs(file_real_path)
                return Response(
                    response=json.dumps(
                        {
                            'responseType': 'Success',
                            'status': 200,
                            'message': 'Directory created successfully!'
                        }
                    ),
                    status=200,
                    mimetype='application/json'
                )
            else:
                return Response(
                    response=json.dumps(
                        {
                            'info': "Maybe you want create directory? Send "
                            "«createDirectory» parameter with "
                            "True value then!",
                            'responseType': 'Error',
                            'status': 400,
                            'message': 'You didn`t send file! Request ignored!'
                        }
                    ),
                    status=400,
                    mimetype='application/json'
                )

        else:
            return json_http_response(
                status=400,
                given_message="You didn`t send file! Request ignored!"
            )
    except Exception:
        return json_http_response(dbg=request.args.get('dbg', False))


@app.route('/files', methods=['PUT'])
@app.route('/files/<path:asked_file_path>', methods=['PUT'])
def put_file(asked_file_path=''):
    try:
        file_real_path = os.path.join(app.config['ROOT_PATH'], asked_file_path)
        new_object_name = request.args.get('rename', None)

        if new_object_name:
            if os.path.exists(file_real_path):

                real_path_splitted = file_real_path.rsplit('/', maxsplit=1)
                old_file_name = real_path_splitted[1]
                file_save_path = real_path_splitted[0]

                is_directory = os.path.isdir(file_real_path)
                if is_directory:
                    object_type = 'Directory'
                    if not asked_file_path:
                        return json_http_response(
                            status=400,
                            given_message="Root directory cannot be renamed!",
                            dbg=request.args.get('dbg', False)
                        )
                else:
                    object_type = 'File'
                    old_file_ext = old_file_name.split('.')[-1]
                    new_object_name += '.' + old_file_ext

                os.rename(file_real_path, os.path.join(
                    file_save_path,
                    new_object_name
                ))

                return json_http_response(
                    status=200,
                    given_message="%s «%s» renamed to «%s» successfully!"\
                        % (object_type, old_file_name, new_object_name),
                    dbg=request.args.get('dbg', False)
                )
            else:
                return json_http_response(status=404)
        else:
            return json_http_response(
                status=400,
                given_message="You didn`t send a new name for file/directory! Request ignored!",
                dbg=request.args.get('dbg', False)
            )
    except Exception:
        return json_http_response(dbg=request.args.get('dbg', False))

if __name__ == '__main__':
    app.run(host='0.0.0.0')
