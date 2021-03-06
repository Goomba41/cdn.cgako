"""API for handling with files on server."""
# -*- coding: utf-8 -*-

import os
import pathlib
import shutil
import uuid

from app import app, thumbnail
from distutils.util import strtobool
from operator import itemgetter

from app.classes import FileSystemObject
from app.utils import json_http_response, pagination_of_list, add_watermark

from flask import Response, json, redirect, request, \
    send_from_directory, url_for, send_file

from flask_thumbnails.utils import parse_size
from werkzeug.utils import secure_filename


@app.route('/favicon.ico')
def favicon():
    """Get favicon for dev version."""
    return send_from_directory(
        directory=pathlib.Path().absolute(),
        filename='faviconDev.ico'
    )


@app.route('/', methods=['GET', 'POST', 'PUT', 'DELETE'])
def hello():
    """Redirect for root route."""
    return redirect(url_for('get_file', _external=True))

# ----------------------------------------------------------------------


@app.route('/files', methods=['GET'])
@app.route('/files/<path:asked_file_path>', methods=['GET'])
def get_file(asked_file_path=''):
    """
    Get files and directories in json dictionary.

    Method for getting paginated list of objects in directory
    or returning separate file.
    """
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
                    make_watermark = request.args.get('watermark', False)

                    if not isinstance(make_thumbnail, bool):
                        try:
                            make_thumbnail = strtobool(make_thumbnail)
                        except Exception:
                            return Response(
                                response=json.dumps(
                                    {
                                        'responseType': 'Error',
                                        'status': 400,
                                        'message': 'Your «thumbnail» '
                                        'parameter is invalid (must be '
                                        'boolean value)!'
                                    }
                                ),
                                status=400,
                                mimetype='application/json'
                            )

                    if not isinstance(make_watermark, bool):
                        try:
                            make_watermark = strtobool(make_watermark)
                        except Exception:
                            return Response(
                                response=json.dumps(
                                    {
                                        'responseType': 'Error',
                                        'status': 400,
                                        'message': 'Your «watermark» '
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

                        original_relpath = os.path.relpath(
                            original,
                            app.config['ROOT_PATH']
                        )
                        thumbnail_link = thumbnail.get_thumbnail(
                            original_relpath,
                            size=thumbnail_size,
                            crop=thumbnail_crop
                        )
                        thumbnail_path, thumbnail_filename = os.path.split(
                            thumbnail_link
                        )
                        original_relpath_path, \
                            original_relpath_name = os.path.split(
                                original_relpath
                            )
                        directory = os.path.join(
                            app.config['THUMBNAIL_MEDIA_THUMBNAIL_ROOT'],
                            original_relpath_path
                        )
                        filename = thumbnail_filename
                    else:
                        directory = app.config['ROOT_PATH']
                        filename = asked_file_path

                    if make_watermark:
                        wm_interval = request.args.get('wmInterval', None)
                        wm_opacity = request.args.get('wmOpacity', 50.0)
                        wm_size = request.args.get('wmSize', 100.0)
                        wm_angle = request.args.get('wmAngle', 45.0)

                        try:
                            wm_x = request.args.get('wmX', None)
                            if wm_x is not None:
                                wm_x = int(wm_x)
                        except Exception:
                            return json_http_response(
                                status=400,
                                given_message='Your «wmX» '
                                'parameter is invalid (must be '
                                'integer number value)!'
                            )
                        try:
                            wm_y = request.args.get('wmY', None)
                            if wm_y is not None:
                                wm_y = int(wm_y)
                        except Exception:
                            return json_http_response(
                                status=400,
                                given_message='Your «wmY» '
                                'parameter is invalid (must be '
                                'integer number value)!'
                            )
                        image_path = os.path.join(directory, filename)
                        try:
                            marked_image = add_watermark(
                                    image_path,
                                    wm_opacity=wm_opacity,
                                    wm_interval=wm_interval,
                                    wm_size=wm_size,
                                    wm_angle=wm_angle,
                                    wm_x=wm_x,
                                    wm_y=wm_y
                                )
                        except Exception as error:
                            return error.args[0]
                        return send_file(marked_image, mimetype="image/jpeg")

                    return send_from_directory(
                        directory=directory,
                        filename=filename
                    )
                except IOError as e:
                    return json_http_response(status=500, given_message=e)
        else:
            return json_http_response(status=404)
    except Exception:
        return json_http_response(dbg=request.args.get('dbg', False))


@app.route('/files', methods=['DELETE'])
@app.route('/files/<path:asked_file_path>', methods=['DELETE'])
def delete_file(asked_file_path=''):
    """
    Delete files and directories.

    Method for deleting separate file or directory with recursive option.
    """
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

                    thumbnail_path = os.path.join(
                        app.config['THUMBNAIL_MEDIA_THUMBNAIL_ROOT'],
                        os.path.relpath(file_path, app.config['ROOT_PATH'])
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
    """
    Post files with directory tree creation.

    Method for posting files in directory with tree creation if directory
    not exist. Also, if files not sended, check parameter and create empty
    directory.
    """
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
    """Change name of directory or file method."""
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
                    given_message="%s «%s» renamed to «%s» successfully!" % (
                        object_type,
                        old_file_name,
                        new_object_name
                    ),
                    dbg=request.args.get('dbg', False)
                )
            else:
                return json_http_response(status=404)
        else:
            return json_http_response(
                status=400,
                given_message="You didn`t send a new name for file/directory!"
                " Request ignored!",
                dbg=request.args.get('dbg', False)
            )
    except Exception:
        return json_http_response(dbg=request.args.get('dbg', False))
