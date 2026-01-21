# reports/middleware.py
import logging
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


class ReportAccessLogMiddleware(MiddlewareMixin):
    """
    Log report access and downloads for audit purposes
    """
    
    def process_request(self, request):
        # Log report generation requests
        if '/api/reports/generate/' in request.path:
            logger.info(
                f"Report generation request: {request.method} {request.path} "
                f"by user {request.user.phone_number if request.user.is_authenticated else 'anonymous'}"
            )
        
        # Log report downloads
        if '/download/' in request.path and '/api/reports/exports/' in request.path:
            logger.info(
                f"Report download: {request.path} "
                f"by user {request.user.phone_number if request.user.is_authenticated else 'anonymous'}"
            )
        
        return None
    
    def process_response(self, request, response):
        # Log failed report operations
        if '/api/reports/' in request.path and response.status_code >= 400:
            logger.warning(
                f"Report operation failed: {request.method} {request.path} "
                f"Status: {response.status_code} "
                f"User: {request.user.phone_number if request.user.is_authenticated else 'anonymous'}"
            )
        
        return response