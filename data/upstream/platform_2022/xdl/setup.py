from distutils.core import setup
from setuptools import find_packages
import os

HERE = os.path.abspath(os.path.dirname(__file__))

def get_json_files(folder):
    """Get all .json files in given folder recursively."""
    jsons = []
    for f in os.listdir(folder):
        f_path = os.path.join(folder, f)
        if os.path.isdir(f_path):
            jsons.extend(get_json_files(f_path))

        elif f.endswith('.json'):
            jsons.append(f_path)

    return jsons

def get_localisation_files():
    """Get all localisation .json files for package_data."""
    files = get_json_files(os.path.join(HERE, 'xdl', 'localisation'))
    return [f.split(f'xdl{os.sep}')[1] for f in files]


setup(
    name='xdl',
    version='0.5.0',
    description='Package for working with XDL (chemical descriptive language).',
    author='Matthew Craven',
    author_email='matthew.craven@glasgow.ac.uk',
    packages=find_packages(),
    package_data={
        'xdl': get_localisation_files()
    },
    include_package_data=True,
    install_requires=[
        'lxml>=4',
        'networkx>=2',
        'appdirs>=1',
        'termcolor>=1',
        'tabulate>=0.8.7',
        # The reason these are == instead of >= is I am much more paranoid about
        # socket.io stuff breaking than other stuff breaking.
        'python-socketio==4.6.0',
        'websocket-client==0.57.0'
    ]
)
