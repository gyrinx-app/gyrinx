import mimetypes

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from ..models import UploadedFile
from ..models.events import EventNoun, EventVerb, log_event


@require_POST
@login_required
@csrf_protect
def tinymce_upload(request):
    """Handle file uploads from TinyMCE editor.

    Returns JSON response with file location or error message.
    """
    # Check if file is in request
    if "file" not in request.FILES:
        return JsonResponse({"error": "No file provided"}, status=400)

    uploaded_file = request.FILES["file"]

    # Get file info
    file_size = uploaded_file.size
    file_name = uploaded_file.name
    content_type = uploaded_file.content_type

    # Fallback content type detection
    if not content_type:
        content_type, _ = mimetypes.guess_type(file_name)
        if not content_type:
            content_type = "application/octet-stream"

    # Check user quota
    can_upload, remaining, message = UploadedFile.check_user_quota(
        request.user, file_size
    )

    if not can_upload:
        return JsonResponse({"error": message}, status=400)

    try:
        # Create the uploaded file record
        upload = UploadedFile(
            owner=request.user,
            file=uploaded_file,
            original_filename=file_name,
            file_size=file_size,
            content_type=content_type,
        )
        upload.save()

        # Log the file upload event
        log_event(
            user=request.user,
            noun=EventNoun.UPLOAD,
            verb=EventVerb.CREATE,
            object=upload,
            request=request,
            filename=upload.original_filename,
            file_size=upload.file_size,
            content_type=content_type,
        )

        # Return the file URL
        return JsonResponse(
            {
                "location": upload.file_url,
                "id": str(upload.id),
                "filename": upload.original_filename,
                "size": upload.file_size,
            }
        )

    except ValidationError as e:
        # Log the error for debugging
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"File upload error: {str(e)}", exc_info=True)

        # Return a generic user-friendly error message to avoid information exposure
        return JsonResponse(
            {"error": "File upload failed due to validation errors"}, status=400
        )

    except Exception as e:
        # Handle any other unexpected errors
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Unexpected file upload error: {str(e)}", exc_info=True)

        return JsonResponse(
            {"error": "An unexpected error occurred during file upload"}, status=500
        )
