import os, magic, traceback, math, pathlib, shutil
from flask import Flask, send_from_directory, request, json, url_for, Response, redirect
from datetime import datetime
from urllib.parse import urljoin
from distutils.util import strtobool
from operator import itemgetter, attrgetter

app = Flask(__name__)

#Определение размера файла
def getFileSize(num, suffix='B'):
    for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
        if abs(num) < 1024.0:
            return {'number': float("{:.2f}".format(num)), 'suffix': "%s%s" % (unit, suffix)}
        num /= 1024.0
    return {'number': float("{:.2f}".format(num)), 'suffix': "%s%s" % (num, 'Yi', suffix)}

#  Генерация ответа сервера при ошибке
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

#  Пагинация получаемого с API списка
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

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(directory=pathlib.Path().absolute(), filename='faviconDev.ico')

@app.route('/')
def hello():
    return redirect(url_for('get_file', _external=True))

@app.route('/files', methods=['GET'])
@app.route('/files/<path:askedFilePath>', methods=['GET'])
def get_file(askedFilePath=''):
    try:
        fileRealPath = os.path.join('/data/static', askedFilePath)
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
                    if partialAskedFilePath:
                        parentDirectory = url_for('.get_file', askedFilePath=partialAskedFilePath, _external=True)
                    else:
                        parentDirectory = url_for('.get_file', _external=True)
                else:
                    parentDirectory = 'This is root directory!'
                for filename in os.listdir(fileRealPath):
                    filePath = os.path.join(fileRealPath, filename)
                    fileSizeBytes = os.stat(filePath).st_size
                    fileSize = getFileSize(fileSizeBytes)

                    metadata = {
                        "name": filename,
                        "path": filePath,
                        "type": ('directory' if os.path.isdir(filePath) else magic.from_file(filePath, mime=True)),
                        "link": url_for('.get_file', askedFilePath=os.path.join(askedFilePath, filename), _external=True),
                        "sizeBytes": fileSizeBytes,
                        "sizeNumber": fileSize['number'],
                        "sizeSuffix": fileSize['suffix'],
                        "created": str(datetime.fromtimestamp(int(os.stat(filePath).st_ctime))),
                        "modified": str(datetime.fromtimestamp(int(os.stat(filePath).st_mtime))),
                    }
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
                    response=json.dumps(responseObj),
                    status=200,
                    mimetype='application/json'
                )
            else:
                return send_from_directory(directory='/data/static', filename=askedFilePath)
        else:
            return jsonHTTPResponse(status=404)
    except Exception:
        return jsonHTTPResponse(dbg=request.args.get('dbg', False))

@app.route('/files', methods=['DELETE'])
@app.route('/files/<path:askedFilePath>', methods=['DELETE'])
def delete_file(askedFilePath=''):
    try:
        fileRealPath = os.path.join('/data/static', askedFilePath)
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
                            givenMessage += "Value of parameter 'recursive' is incorrect and set as FALSE by default. "
                    if recursive:
                        givenMessage += 'Directory delete recursively (with all contents)!'
                        shutil.rmtree(fileRealPath)
                    else:
                        try:
                            os.rmdir(fileRealPath)
                            givenMessage += 'Directory delete successful!'
                        except Exception:
                            return jsonHTTPResponse(dbg=request.args.get('dbg', False), givenMessage="Directory not empty! Check directory and delete content manually or set 'recursive' parameter to true if you want delete directory with all its content.")
                    return jsonHTTPResponse(status=200, givenMessage=givenMessage)
                else:
                    return jsonHTTPResponse(status=403, givenMessage='Root directory cannot be deleted!')
            else:
                try:
                    os.remove(fileRealPath)
                    fileName = askedFilePath.split('/')[-1:][0]
                    return jsonHTTPResponse(status=200, givenMessage="File '%s' delete successful!" % (fileName))
                except Exception:
                    return jsonHTTPResponse(dbg=request.args.get('dbg', False))
        else:
            return jsonHTTPResponse(status=404)
    except Exception:
        return jsonHTTPResponse(dbg=request.args.get('dbg', False))

@app.route('/files/', methods=['PUT'])
@app.route('/files/<path:askedFilePath>', methods=['PUT'])
def put_file(askedFilePath=''):
    return "PUT ok!"

@app.route('/files/', methods=['POST'])
@app.route('/files/<path:askedFilePath>', methods=['POST'])
def post_file(askedFilePath=''):
    return "POST ok!"

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
