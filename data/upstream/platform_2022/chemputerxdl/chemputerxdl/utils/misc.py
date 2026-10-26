import datetime

def pretty_duration(time_in_seconds: float) -> str:
    """Format time in seconds so it's easy to read."""
    td = datetime.timedelta(seconds=time_in_seconds)
    return str(td)
