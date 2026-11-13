from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status


def custom_exception_handler(exc, context):
    """
    Custom exception handler for all API endpoints.

    Why we need this:
    DRF's default exception handler returns different formats
    for different errors. Sometimes the error is a string,
    sometimes a list, sometimes a dict. This makes it hard
    for the Flutter app to parse errors consistently.

    Our handler always returns the same format:
    {
        "error": true,
        "message": "A human readable error message",
        "code": "authentication_failed",
        "status": 401
    }

    The Flutter app can always check response["message"]
    for the error text regardless of what went wrong.
    """
    # Let DRF handle the exception first
    response = exception_handler(exc, context)

    if response is not None:
        # Get the error detail from DRF's response
        error_detail = response.data

        # Convert various DRF error formats to one clean message
        if isinstance(error_detail, dict):
            # If it is a dict like {"detail": "..."} extract the message
            message = error_detail.get('detail', str(error_detail))
        elif isinstance(error_detail, list):
            # If it is a list of errors join them
            message = ' '.join(str(e) for e in error_detail)
        else:
            message = str(error_detail)

        # Determine a simple error code from the status
        code_map = {
            400: 'bad_request',
            401: 'authentication_required',
            403: 'permission_denied',
            404: 'not_found',
            405: 'method_not_allowed',
            429: 'too_many_requests',
            500: 'server_error',
        }

        response.data = {
            'error':   True,
            'message': str(message),
            'code':    code_map.get(response.status_code, 'error'),
            'status':  response.status_code,
        }

    return response