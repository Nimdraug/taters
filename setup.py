#!/usr/bin/env python2
from setuptools import setup

setup(
    name = 'taters',
    version = '0.1-dev',
    description = 'A fully modular build and deployment framework',
    
    author = u'Martin Hult\xe9n-Ashauer',
    author_email = 'taters-info@nimdraug.com',

    licence = 'MIT',

    classifiers = [
        'Development Status :: 3 - Alpha',

        'Intended Audience :: Developers',

        'Topic :: Software Development :: Build Tools',

        'License :: OSI Approved :: MIT License',

        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',

        'Operating System :: MacOS',
        'Operating System :: POSIX :: Linux',

        'Topic :: Internet',
        'Topic :: Internet :: File Transfer Protocol (FTP)',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: System :: Archiving',
        'Topic :: System :: Installation/Setup',
        'Topic :: Utilities',
    ]

    keywords = 'webdev build deployment ftp ssh less javascript'

    packages = [ 'taters' ],

    install_requires = [
        'paramiko',
        'sh'
    ]
)
