import functools
import traceback


def LogError(logger):
    """Decorator to log exceptions.

    This decorator will log any exceptions raised by the decorated function using the provided logger.

    Args:
        logger (logging.Logger): The logger to use for logging exceptions.

    Returns:
        Callable: The decorated function.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Capture function name, arguments, exception type, and message
                message = (
                    f"Exception in function '{func.__name__}' with arguments {args} and keyword arguments {kwargs}. "
                    f"Exception type: {type(e).__name__}, Message: {str(e)}.\n"
                    f"Traceback:\n{traceback.format_exc()}"
                )
                logger.error(message)
                raise  # Re-raise the exception after logging

        return wrapper

    return decorator
