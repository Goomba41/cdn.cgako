# -*- coding: utf-8 -*-

import os, magic, traceback, math, pathlib, shutil, uuid, subprocess, hashlib
from flask import Flask, send_from_directory, request, json, url_for, Response, redirect
from datetime import datetime
from urllib.parse import urljoin
from distutils.util import strtobool
from operator import itemgetter
from werkzeug.utils import secure_filename

from flask_thumbnails import Thumbnail
from flask_thumbnails.utils import parse_size
from PIL import Image

app = Flask(__name__)

thumbnail = Thumbnail(app)

app.config.from_object('config')

#----------------------------------------------------------------------

class fileSystemObject:

    def __init__(self, path):
        self.path = path
        self.type = 'directory' if os.path.isdir(self.path) else magic.from_file(self.path, mime=True)
        self.name = self.path.rsplit('/', maxsplit=1)[-1]
        self.link = url_for('.get_file', askedFilePath=os.path.relpath(self.path, app.config['ROOT_PATH']), _external=True)
        self.sizeBytes = int(subprocess.check_output("du -sb %s | cut -f1" % (self.path), shell=True)) if os.path.isdir(self.path) else os.stat(self.path).st_size
        self.sizeFormatted = self.getFileSize(self.sizeBytes)
        self.created = str(datetime.fromtimestamp(int(os.stat(self.path).st_ctime)))
        self.modified = str(datetime.fromtimestamp(int(os.stat(self.path).st_mtime)))
        if os.path.isfile(self.path):
            self.hash = self.hashFile()

    def __repr__(self):
        return "File system object «%s»" % (self.name)

    def getMetadata(self):
        returnedDict = {
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
            returnedDict["hash"] = self.hash
        return returnedDict

    def getFileSize(self, num, suffix='B'):
        for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
            if abs(num) < 1024.0:
                return {'number': float("{:.2f}".format(num)), 'suffix': "%s%s" % (unit, suffix)}
            num /= 1024.0
        return {'number': float("{:.2f}".format(num)), 'suffix': "%s%s" % (num, 'Yi', suffix)}

    def hashFile(self):
        hash = hashlib.sha512()
        with open(self.path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash.update(chunk)
        return hash.hexdigest()

#----------------------------------------------------------------------

# Генерация ответа сервера при ошибке
def jsonHTTPResponse(dbg=False, givenMessage=None, status=500):
    """Вывод серверной ошибки с трейсом. Параметр dbg отвечает за вывод
    в формате traceback."""
    
    if status in (400, 401, 403, 404, 500):
        responseType = 'Error'
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
        responseType = 'Success'
        if status == 200:
            message = 'OK!'
        if status == 201:
            message = 'Created!'
    elif status in (304,):
        responseType = 'Warning'
        message = 'Not modified!'
    else:
        responseType = 'Info'
        message = 'I don`t know what to say! Probably this is test response?'

    info = {'responseType': responseType, 'message': message, 'status': status}

    info['message'] = givenMessage if givenMessage is not None else message

    if isinstance(dbg, bool):
        if dbg is True:
            info['debugInfo'] = traceback.format_exc()
    else:
        try:
            if strtobool(dbg):
                info['debugInfo'] = traceback.format_exc()
        except Exception:
            info['debugInfo'] = "Debugging info is turned off, because incorrect type of value of parameter 'dbg' (should be boolean)"

    return Response(
        response=json.dumps(info),
        status=status,
        mimetype='application/json'
    )

# Пагинация получаемого с API списка
def pagination_of_list(query_result, url, queryParams):
    """ Пагинация результатов запроса. Принимает параметры:
    результат запроса (json), URL API для генерации ссылок, стартовая позиция,
    количество выводимых записей"""

    start = queryParams.get('start', 1)
    limit = queryParams.get('limit', 10)

    queryParamsString = ''
    for i in queryParams:
        if i not in ('start', 'limit'):
            queryParamsString += '&%s=%s' % (i, queryParams.get(i).replace(' ', '+'))

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
        params = '?start=%d&limit=%d%s' % (start_copy, limit_copy, queryParamsString)
        new_url = urljoin(url,
                          params)
        response_obj['previousPage'] = new_url

    # Создаем URL на следующую страницу
    if start + limit > records_count:
        response_obj['nextPage'] = ''
    else:
        start_copy = start + limit
        params = '?start=%d&limit=%d%s' % (start_copy, limit, queryParamsString)
        new_url = urljoin(url,
                          params)
        response_obj['nextPage'] = new_url

    # Отсеивание результатов запроса
    response_obj['results'] = query_result[(start - 1):(start - 1 + limit)]

    return response_obj

#----------------------------------------------------------------------

# Фавиконка
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(directory=pathlib.Path().absolute(), filename='faviconDev.ico')

# Редирект с корня на список файлов
@app.route('/', methods=['GET', 'POST', 'PUT', 'DELETE'])
def hello():
    return redirect(url_for('get_file', _external=True))

#----------------------------------------------------------------------

@app.route('/files', methods=['GET'])
@app.route('/files/<path:askedFilePath>', methods=['GET'])
def get_file(askedFilePath=''):
    try:
        if not os.path.exists(app.config['ROOT_PATH']):
            os.makedirs(app.config['ROOT_PATH'])

        fileRealPath = os.path.join(app.config['ROOT_PATH'], askedFilePath)

        if os.path.exists(fileRealPath):
            isDirectory = os.path.isdir(fileRealPath)
            if isDirectory:

                searchQuery = request.args.get('q', None)
                if searchQuery:
                    try:
                        searchParamsAll = dict(e.split(':') for e in searchQuery.split(' '))
                    except Exception:
                        return jsonHTTPResponse(status=400, givenMessage="Incorrect value of parameter 'q' (should be 'field1:value1+field2:value2')", dbg=request.args.get('dbg', False))
                    supportedParams = ('name', 'sizeNumber', 'sizeSuffix', 'type', 'created', 'modified', 'sizeBytes')
                    unprocessedParams = ()
                    searchParams = {k: searchParamsAll[k] for k in supportedParams if k in searchParamsAll}
                else:
                    searchParams = None

                files = []
                if askedFilePath:
                    partialAskedFilePath = '/'.join(askedFilePath.split('/')[:-1])
                    parentDirectory = url_for('.get_file', askedFilePath=partialAskedFilePath if partialAskedFilePath else None, _external=True)
                else:
                    parentDirectory = 'This is root directory!'

                for filename in os.listdir(fileRealPath):
                    filePath = os.path.join(fileRealPath, filename)

                    metadata = fileSystemObject(filePath).getMetadata()

                    if searchParams:
                        if all(True if val in metadata.get(key, None) else False for key, val in searchParams.items()):
                            files.append(metadata)
                    else:
                        files.append(metadata)

                sortingQuery = request.args.get('sf', None)
                sortingOrder = request.args.get('so', None)

                sortingReverse = False
                if sortingOrder and sortingOrder.lower() == 'd':
                    sortingReverse = True

                if sortingQuery:
                    try:
                        sortingParamsAll = sortingQuery.split(' ')
                    except Exception:
                        return jsonHTTPResponse(status=400, givenMessage="Incorrect value of parameter 'sf' (should be 'field1+field2')", dbg=request.args.get('dbg', False))
                    supportedSParams = ('name', 'type', 'created', 'modified', 'sizeBytes', 'sizeNumber', 'sizeSuffix')
                    unprocessedSParams = ('sizeNumber', 'sizeSuffix')
                    sortingParams = [k for k in supportedSParams if (k in sortingParamsAll and k not in unprocessedSParams)]
                    if not sortingParams:
                        sortingParams.append('name')
                else:
                    sortingParams = ['name']

                sortedFiles = sorted(files, key = itemgetter(*sortingParams), reverse = sortingReverse)

                paginatedData = pagination_of_list(
                    sortedFiles,
                    url_for('.get_file', askedFilePath=askedFilePath, _external=True),
                    queryParams = request.args
                )

                responseObj = {'parentDirectory': parentDirectory, 'filesList': paginatedData.pop('results'), 'paginationData': paginatedData}

                if searchParams:
                    for k in searchParamsAll:
                        searchParams[k] = 'Unsupported :(' if k not in supportedParams else 'Unprocessed :(' if k in unprocessedParams else searchParams[k]
                    responseObj['searchParams'] = searchParams
                if sortingQuery or sortingOrder:
                    sortingParams = {'sortedBy': sortingParams}
                    if sortingQuery:
                        unsupportedSParams = [k for k in sortingParamsAll if k not in supportedSParams]
                        if unsupportedSParams:
                            sortingParams['unsupportedParams'] = unsupportedSParams
                        if unprocessedSParams:
                            sortingParams['unprocessedParams'] = [k for k in sortingParamsAll if k in unprocessedSParams]
                    sortingParams['sortingDirection'] = 'Desc' if sortingReverse else 'Asc'
                    responseObj['sortingParams'] = sortingParams

                return Response(
                    response=json.dumps(responseObj, ensure_ascii=False),
                    status=200,
                    mimetype='application/json'
                )
            else:
                try:
                    original = os.path.join(app.config['ROOT_PATH'], askedFilePath)
                    i=Image.open(original)

                    makeThumbnail = request.args.get('thumbnail', False)

                    if not isinstance(makeThumbnail, bool):
                        try:
                            makeThumbnail = strtobool(makeThumbnail)
                        except Exception:
                            return Response(
                                response=json.dumps({'responseType': 'Error', 'status': 400, 'message': 'Your «makeThumbnail» parameter is invalid (must be boolean value)!'}),
                                status=400,
                                mimetype='application/json'
                            )

                    if makeThumbnail:

                        thumbnailSize = request.args.get('size', None)
                        thumbnailCrop = request.args.get('crop', False)

                        if thumbnailSize:
                            try:
                                parse_size(thumbnailSize)
                            except Exception:
                                return Response(
                                    response=json.dumps({'responseType': 'Error', 'status': 400, 'message': 'Your «size» parameter is invalid (must be INT or INTxINT value)!'}),
                                    status=400,
                                    mimetype='application/json'
                                )
                        else:
                            thumbnailSize = '200x200'

                        if not isinstance(thumbnailCrop, bool):
                            try:
                                thumbnailCrop = strtobool(thumbnailCrop)
                                if thumbnailCrop:
                                    thumbnailCrop = 'fit'
                                else:
                                    thumbnailCrop = 'sized'
                            except Exception:
                                return Response(
                                    response=json.dumps({'responseType': 'Error', 'status': 400, 'message': 'Your «crop» parameter is invalid (must be boolean value)!'}),
                                    status=400,
                                    mimetype='application/json'
                                )

                        originalPath, originalName = os.path.split(original)
                        if app.config['THUMBNAILS_FOLDER'][0] != '.':
                            app.config['THUMBNAILS_FOLDER'] = '.' + app.config['THUMBNAILS_FOLDER']
                        app.config['THUMBNAIL_MEDIA_THUMBNAIL_ROOT'] =  os.path.join(originalPath, app.config['THUMBNAILS_FOLDER'])
                        thumbnailLink = thumbnail.get_thumbnail(original, size=thumbnailSize, crop=thumbnailCrop)
                        thumbnailPath, thumbnailFilename = os.path.split(thumbnailLink)
                        return send_from_directory(directory=thumbnail.thumbnail_directory, filename=thumbnailFilename)
                    else:
                        return send_from_directory(directory=app.config['ROOT_PATH'], filename=askedFilePath)
                except IOError:
                    return send_from_directory(directory=app.config['ROOT_PATH'], filename=askedFilePath)
        else:
            return jsonHTTPResponse(status=404)
    except Exception:
        return jsonHTTPResponse(dbg=request.args.get('dbg', False))

@app.route('/files', methods=['DELETE'])
@app.route('/files/<path:askedFilePath>', methods=['DELETE'])
def delete_file(askedFilePath=''):
    try:
        fileRealPath = os.path.join(app.config['ROOT_PATH'], askedFilePath)

        print(fileRealPath)

        if os.path.exists(fileRealPath):
            isDirectory = os.path.isdir(fileRealPath)
            if isDirectory:
                if askedFilePath:
                    recursive = request.args.get('recursive', False)
                    givenMessage = ''
                    if not isinstance(recursive, bool):
                        try:
                            recursive = strtobool(recursive)
                        except Exception:
                            recursive = False
                            givenMessage += "Value of parameter «recursive» is incorrect and set as FALSE by default. "
                    if recursive:
                        givenMessage += 'Directory delete recursively (with all contents)!'
                        shutil.rmtree(fileRealPath)
                    else:
                        try:
                            os.rmdir(fileRealPath)
                            givenMessage += 'Directory «%s» delete successful!' % (askedFilePath.split('/')[-1:][0])
                        except Exception:
                            return jsonHTTPResponse(dbg=request.args.get('dbg', False), givenMessage="Directory not empty! Check directory and delete content manually or set «recursive» parameter to true if you want delete directory with all its content.")
                else:
                    return jsonHTTPResponse(status=403, givenMessage='Root directory cannot be deleted!')
            else:
                try:
                    if os.path.exists(fileRealPath):
                        os.remove(fileRealPath)

                    filePath, fileName = os.path.split(fileRealPath)

                    if app.config['THUMBNAILS_FOLDER'][0] != '.':
                        app.config['THUMBNAILS_FOLDER'] = '.' + app.config['THUMBNAILS_FOLDER']

                    thumbnailPath = os.path.join(filePath, app.config['THUMBNAILS_FOLDER'])

                    if os.path.exists(thumbnailPath):
                        shutil.rmtree(thumbnailPath)
                    givenMessage="File «%s» delete successful!" % (fileName)
                except Exception:
                    return jsonHTTPResponse(dbg=request.args.get('dbg', False))

            removeEmpty = request.args.get('removeEmpty', False)

            if not isinstance(removeEmpty, bool):
                try:
                    removeEmpty = strtobool(removeEmpty)
                except Exception:
                    return Response(
                        response=json.dumps({'info': "Your «removeEmpty» parameter is invalid (must be boolean value)!", 'responseType': 'Error', 'status': 400, 'message': 'You didn`t send file! Request ignored!'}),
                        status=400,
                        mimetype='application/json'
                    )

            if removeEmpty:
                filePath, fileName = os.path.split(fileRealPath)

                if not os.listdir(filePath):
                    shutil.rmtree(filePath)
                    givenMessage += " Empty parent directory also removed."

            return jsonHTTPResponse(status=200, givenMessage=givenMessage)
        else:
            return jsonHTTPResponse(status=404)
    except Exception:
        return jsonHTTPResponse(dbg=request.args.get('dbg', False))

@app.route('/files', methods=['POST'])
@app.route('/files/<path:askedFilePath>', methods=['POST'])
def post_file(askedFilePath=''):
    try:
        uploads = request.files.getlist('uploads')

        fileRealPath = os.path.join(app.config['ROOT_PATH'], askedFilePath)

        if uploads:

            definedFilesNames = request.args.get('names', None)

            if not os.path.exists(fileRealPath):
                os.makedirs(fileRealPath)

            uploadedFilesList = []    
            definedFilesNames = definedFilesNames.split(' ') if definedFilesNames else None

            for file in uploads:
                oldFileName = file.filename
                oldFileExt = oldFileName.split(".")[-1]

                if definedFilesNames:
                    newFullFileName = secure_filename(definedFilesNames.pop(0) + '.' + oldFileExt)
                else:
                    newFullFileName = secure_filename(uuid.uuid1().hex + '.' + oldFileExt)

                filePath = os.path.join(fileRealPath, newFullFileName)
                file.save(filePath)

                metadata = fileSystemObject(filePath).getMetadata()
                metadata['oldName'] = oldFileName

                uploadedFilesList.append(metadata)

            parentDirectory = url_for('.get_file', askedFilePath=askedFilePath if askedFilePath else None, _external=True)

            responseObj = {'uploadedIn': parentDirectory, 'uploadedFiles': uploadedFilesList, 'responseType': 'Success', 'status': 200, 'message': 'Files upload successful!'}

            unprocessedParams = ['createDirectory', 'random']
            tmpUnprocessedParams = []
            requestParams = request.args
            for p in unprocessedParams:
                if p in requestParams:
                    tmpUnprocessedParams.append(p)
            if tmpUnprocessedParams:
                responseObj['unprocessedParams'] = tmpUnprocessedParams

            return Response(
                response=json.dumps(responseObj),
                status=200,
                mimetype='application/json'
            )
        elif not uploads:
            createDirectory = request.args.get('createDirectory', False)

            if not isinstance(createDirectory, bool):
                try:
                    createDirectory = strtobool(createDirectory)
                except Exception:
                    return Response(
                        response=json.dumps({'info': "Your «createDirectory» parameter is invalid (must be boolean value)!", 'responseType': 'Error', 'status': 400, 'message': 'You didn`t send file! Request ignored!'}),
                        status=400,
                        mimetype='application/json'
                    )

            if createDirectory:
                if not os.path.exists(fileRealPath):
                    os.makedirs(fileRealPath)
                return Response(
                    response=json.dumps({'responseType': 'Success', 'status': 200, 'message': 'Directory created successfully!'}),
                    status=200,
                    mimetype='application/json'
                )
            else:
                return Response(
                    response=json.dumps({'info': "Maybe you want create directory? Send «createDirectory» parameter with True value then!", 'responseType': 'Error', 'status': 400, 'message': 'You didn`t send file! Request ignored!'}),
                    status=400,
                    mimetype='application/json'
                )

        else:
            return jsonHTTPResponse(status=400, givenMessage="You didn`t send file! Request ignored!")
    except Exception:
        return jsonHTTPResponse(dbg=request.args.get('dbg', False))

@app.route('/files', methods=['PUT'])
@app.route('/files/<path:askedFilePath>', methods=['PUT'])
def put_file(askedFilePath=''):
    try:
        fileRealPath = os.path.join(app.config['ROOT_PATH'], askedFilePath)
        newObjectName = request.args.get('rename', None)

        if newObjectName:
            if os.path.exists(fileRealPath):

                realPathSplitted = fileRealPath.rsplit('/', maxsplit=1)
                oldFileName = realPathSplitted[1]
                fileSavePath = realPathSplitted[0]

                isDirectory = os.path.isdir(fileRealPath)
                if isDirectory:
                    objectType = 'Directory'
                    if not askedFilePath:
                        return jsonHTTPResponse(status=400, givenMessage="Root directory cannot be renamed!", dbg=request.args.get('dbg', False))
                else:
                    objectType = 'File'
                    oldFileExt = oldFileName.split('.')[-1]
                    newObjectName += '.' + oldFileExt
 
                os.rename(fileRealPath, os.path.join(fileSavePath, newObjectName))

                return jsonHTTPResponse(status=200, givenMessage="%s «%s» renamed to «%s» successfully!" % (objectType, oldFileName, newObjectName), dbg=request.args.get('dbg', False))
            else:
                return jsonHTTPResponse(status=404)
        else:
            return jsonHTTPResponse(status=400, givenMessage="You didn`t send a new name for file/directory! Request ignored!", dbg=request.args.get('dbg', False))
    except Exception:
        return jsonHTTPResponse(dbg=request.args.get('dbg', False))

if __name__ == '__main__':
    app.run(host='0.0.0.0')
