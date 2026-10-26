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
    files = get_json_files(os.path.join(HERE, 'chemputerxdl', 'localisation'))
    return [f.split(f'chemputerxdl{os.sep}')[1] for f in files]


setup(
    name='chemputerxdl',
    version='1.0.0',
    description='Bindings for Chemputer to XDL.',
    author='Cronin Group',
    author_email='matthew.craven@glasgow.ac.uk',
    packages=find_packages(),
    package_data={
        'chemputerxdl': get_localisation_files() + [
            f'graphgen{os.sep}template.json',
        ]
    },
    include_package_data=True,
    install_requires=[
        'networkx>=2',
        'appdirs>=1',
        'termcolor>=1',
        'tabulate>=0.8'
    ]
)
