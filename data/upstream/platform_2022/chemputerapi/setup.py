#!/usr/bin/python

from setuptools import setup, find_packages

VERSION = '2.0.dev0'
NAME = 'ChemputerAPI'

setup(
    name=NAME,
    version=VERSION,
    package_data={'': ['docs/*']},
    packages=find_packages(),
    zip_safe=True,
    author='Sebastian Steiner, Graham Keenan',
    author_email='s.steiner.1@research.gla.ac.uk, Graham.Keenan@glasgow.ac.uk',
    license='See LICENSE.txt',
    description='API to control Chemputer pumps and valves.',
    platforms='any',
)
