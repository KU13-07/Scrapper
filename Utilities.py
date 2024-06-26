import time


def format_output(var):
    match var:
        case set():
            var = list(var)
        case dict():
            var = {k: format_output(v) for k, v in var.items()}
    return var


def time_func(message: str):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time: float = time.time()
            result = await func(*args, **kwargs)
            end_time: float = time.time()

            output: str = f"{(message + ":").ljust(20)}{{}}s"
            print(output.format(round(end_time - start_time, 3)))
            return result

        return wrapper
    return decorator
