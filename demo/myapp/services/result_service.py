import json
from django.utils import timezone
from myapp.models import FunctionResult

class ResultService:
    @staticmethod
    def save_function_result(func, args, kwargs, result, success=True, error=None):
        """
        Save function execution results to database
        """
        try:
            # Convert complex objects to strings for storage
            args_str = json.dumps([str(arg) for arg in args])
            kwargs_str = json.dumps({k: str(v) for k, v in kwargs.items()})
            
            FunctionResult.objects.create(
                function_name=func.__name__,
                arguments=args_str,
                result=json.dumps(result) if success and result is not None else None,
                success=success,
                error_message=str(error)[:500] if error else None,  # Limit error length
                executed_at=timezone.now()
            )
        except Exception as e:
            # Log the error but don't break the main function
            print(f"Failed to save function result: {e}")

def post(func):
    """
    Decorator to automatically save function results to database
    """
    from functools import wraps
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
            ResultService.save_function_result(func, args, kwargs, result, success=True)
            return result
        except Exception as e:
            ResultService.save_function_result(func, args, kwargs, None, success=False, error=e)
            raise e
    
    return wrapper