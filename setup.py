#!/usr/bin/env python2
from setuptools import setup

setup(
    name = 'deploy',
    version = '0.1-dev',
    
    maintainer = u'Martin Hult\xe9n-Ashauer',
    maintainer_email = 'martin@designondemand.com.au',
    description = 'A fully modular build and deployment framework',
    
    packages = [ 'deploy' ],
    install_requires = [
        'paramiko',
        'sh'
    ]
)
