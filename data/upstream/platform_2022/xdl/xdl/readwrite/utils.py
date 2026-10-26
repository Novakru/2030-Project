from ..utils.logging import get_logger

def read_file(file_name: str) -> str:
    """Read file, allowing for different encodings caused by Windows grrr.
    Assumes existence of file etc has already been checked, just here to read.

    Args:
        file_name (str): File to read.

    Returns:
        str: Contents of file.
    """
    try:
        with open(file_name, encoding='utf8') as fileobj:
            contents = fileobj.read()
    except UnicodeDecodeError:
        # Try different encoding to UTF-8
        logger = get_logger()
        logger.debug('Unable to decode file using UTF-8.\
 Falling back to ISO-8859-1')

        with open(file_name, encoding='iso-8859-1') as fileobj:
            contents = fileobj.read()

    return contents
