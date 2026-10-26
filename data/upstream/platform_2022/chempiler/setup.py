from setuptools import setup, find_packages

setup(
    name="chempiler",
    version="2.0.9",
    description="Chempiler",
    url="https://gitlab.com/croningroup/chemputer/chempiler",
    author="Chempiler contributors",
    license="MIT",
    packages=find_packages(),
    install_requires=[
        "pyserial>=3.3",
        # 4.4 causes errors in CI, should find a way round this so we can
        # use latest version.
        "opencv-contrib-python==4.5.1.48",
        "imutils==0.5.3",
        # This is only required because scikit-image has a broken install on
        # Python 3.9
        "numpy==1.19.3",
        "scikit-image==0.18.0",
        "networkx>=2.2",
        "python-socketio==4.6.0",
        # Version 4 of python-engineio causes socketio to break.
        "python-engineio==3.13.0",
    ],
    zip_safe=False
)
