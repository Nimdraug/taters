#!/usr/bin/env python2
from setuptools import setup

setup(
    name = 'deploy',
    version = '0.1-dev',
    
    maintainer = u'Martin Hult\xe9n-Ashauer',
    maintainer_email = 'martin@designondemand.com.au',
    description = 'A fully modular build and deployment framework',
    
    py_modules = [
        '__init__', 'deploy', 'locations'
    ]

)
