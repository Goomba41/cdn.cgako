"""CDNAPI utils file."""

import math
import traceback
import io

from distutils.util import strtobool
from urllib.parse import urljoin
from PIL import Image, ImageEnhance, ImageDraw, ImageFont
from flask import Response, json, request
from app import app


def json_http_response(dbg=False, given_message=None, status=500):
    """
    Return http response by status and with given message.

    Parameters:
    dbg (Boolean) - Send with traceback if value is 'true'
    given_message (String) - Response text
    status (Integer number) - Response status
    """
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


def pagination_of_list(query_result, url, query_params):
    """
    Pagination of query results.

    Parameters:
    query_result (List of dictionaries) - result of query in json dictionary
    url (String) - URL API for links generation
    query_params (Dictionary) - parameters, sended with query
    """
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


def add_watermark(
        path, wm_opacity=0.5, wm_interval=None, wm_size=1.0, wm_angle=45.0,
        wm_x=None, wm_y=None
):
    """
    Adding watermark to image.

    Parameters:
    path (String) - Path to original image
    wm_opacity (Float number) - Degree of transparency of watermark image
    wm_interval (Integer number) - Interval between cells of watermarks grid
    wm_size (Float number) - Size of watermark image (scaling degree)
    wm_angle (Float number) - Degrees of image rotation
    wm_x (Integer number) - x coordinate of image left upper point
    wm_y (Integer number) - y coordinate of image left upper point
    """
    # Parameters checkings
    try:
        if wm_interval is not None:
            wm_interval = int(wm_interval)
    except Exception:
        raise Exception(json_http_response(
            status=400,
            given_message='Your «wmInterval» '
            'parameter is invalid (must be '
            'integer value)!'
        ))
    if wm_interval is not None and wm_interval < 0:
        raise Exception(json_http_response(
            status=400,
            given_message='Your «wmInterval» '
            'parameter is invalid (must be '
            '> 0)!'
        ))
    try:
        wm_opacity = float(wm_opacity)/100
    except Exception:
        raise Exception(json_http_response(
            status=400,
            given_message='Your «wmOpacity» '
            'parameter is invalid (must be '
            'number value)!'
        ))
    if wm_opacity < 0 or wm_opacity > 1:
        raise Exception(json_http_response(
            status=400,
            given_message='Your «wmOpacity» '
            'parameter is invalid (must be '
            'in 0 to 100 interval)!'
        ))
    try:
        wm_size = float(wm_size)/100
    except Exception:
        raise Exception(json_http_response(
            status=400,
            given_message='Your «wmSize» '
            'parameter is invalid (must be '
            'number value)!'
        ))
    if wm_size <= 0:
        raise Exception(json_http_response(
            status=400,
            given_message='Your «wmSize» '
            'parameter is invalid (must be '
            '> 0)!'
        ))
    try:
        wm_angle = float(wm_angle)
    except Exception:
        raise Exception(json_http_response(
            status=400,
            given_message='Your «wmAngle» '
            'parameter is invalid (must be '
            'number value)!'
        ))
    if wm_angle < 0 or wm_angle > 360:
        raise Exception(json_http_response(
            status=400,
            given_message='Your «wmAngle» '
            'parameter is invalid (must be '
            'in 0 to 360 interval)!'
        ))
    try:
        if wm_x is not None:
            wm_x = int(wm_x)
    except Exception:
        raise Exception(json_http_response(
            status=400,
            given_message='Your «wmX» '
            'parameter is invalid (must be '
            'integer number value)!'
        ))
    try:
        if wm_y is not None:
            wm_y = int(wm_y)
    except Exception:
        raise Exception(json_http_response(
            status=400,
            given_message='Your «wmY» '
            'parameter is invalid (must be '
            'integer number value)!'
        ))

    # Try to open watermark file, if not - open font and draw phrase
    try:
        watermark = Image.open(app.config['WATERMARK_FILE'])
    except Exception:
        watermark = Image.new("RGBA", (510, 45), (0, 0, 0, 0))
        try:
            font = ImageFont.truetype(app.config['WATERMARK_FONT'], 40)
        except Exception:
            raise Exception(json_http_response(
                status=400,
                given_message='Cannot draw watermark! Check watermark file in'
                ' "%s" or font file in "%s"' % (
                    app.config['WATERMARK_FILE'],
                    app.config['WATERMARK_FONT']
                ),
                dbg=request.args.get('dbg', False)
            ))
        draw = ImageDraw.Draw(watermark)
        phrase = "КОГБУ «ЦГАКО» ОБРАЗЕЦ"
        draw.text((0, 0), phrase, font=font, fill=(0, 0, 0, 255))

    # Open image by sended path parameter
    image = Image.open(path, "r")

    # Check watermark image mode and convert to RGBA if needed
    if watermark.mode != 'RGBA':
        watermark = watermark.convert('RGBA')
    else:
        watermark = watermark.copy()
    # Check sended opacity parameter
    assert wm_opacity >= 0 and wm_opacity <= 1
    if wm_opacity < 1:
        # Change opacity of watermark
        alpha = watermark.split()[3]
        alpha = ImageEnhance.Brightness(alpha).enhance(wm_opacity)
        watermark.putalpha(alpha)
    # Calculate new size according to original size and sended scaling
    new_width = int(image.size[0]*wm_size)
    new_hight = int(
        round(
            abs(new_width / watermark.size[0]) * watermark.size[1]
        )
    )
    if new_width <= 0 or new_hight <= 0:
        raise Exception(json_http_response(
            status=400,
            given_message='The resulting watermark is too small!',
            dbg=request.args.get('dbg', False)
        ))

    # Resize image to calculated size and rotate to given angle
    watermark = watermark.resize((new_width, new_hight), Image.ANTIALIAS)
    watermark = watermark.rotate(wm_angle, expand=True)

    # Create new empty layer with size of original image
    layer = Image.new('RGBA', image.size, (0, 0, 0, 0))

    # Stamping by all image surface if interval parameter sended
    if wm_interval is not None:
        row = 1
        for y in range(
            watermark.size[1]*-1,  # Start point with shift by one image left
            image.size[1]+watermark.size[1],  # End point with shift
            # by one image right
            watermark.size[1]+wm_interval  # Step size
        ):
            for x in range(
                watermark.size[0]*-1,
                image.size[0],
                watermark.size[0]+wm_interval
            ):
                if row % 2 == 0:
                    # Shift by half of the image in every even line
                    x += watermark.size[0]*0.5
                layer.paste(watermark, (int(x), int(y)))
            row += 1
    # Else make single watermark stamp
    else:
        # On point according to x and y sended parameters
        if wm_x is not None or wm_y is not None:
            if wm_x is not None:
                if wm_x > image.size[0]-watermark.size[0]:
                    wm_x = image.size[0]-watermark.size[0]
            else:
                wm_x = 0
            if wm_y is not None:
                if wm_y > image.size[1]-watermark.size[1]:
                    wm_y = image.size[1]-watermark.size[1]
            else:
                wm_y = 0
        # Else on center of image if x and y parameters don't sended
        else:
            wm_x = int(image.size[0]*0.5)-int(watermark.size[0]*0.5)
            wm_y = int(image.size[1]*0.5)-int(watermark.size[1]*0.5)
        place = (wm_x, wm_y)
        layer.paste(watermark, place)
    layer.convert('RGB')
    # Make in-memory buffer
    data = io.BytesIO()
    # Join image and watermark
    n_image = Image.composite(layer,  image,  layer)
    # Save image to buffer instead of file in filesystem
    n_image.save(data, "JPEG")
    # Move to begin of buffer
    data.seek(0)
    return data
