"""
Flask-MongoRest
---------

Restful API framework for MongoDB/MongoEngine

"""
from setuptools import setup

# Stops exit traceback on tests
try:
    import multiprocessing
except:
   pass

setup(
    name='Flask-MongoRest',
    version='0.1.1',
    url='http://github.com/elasticsales/flask-mongorest',
    license='BSD',
    author='Anthony Nemitz',
    author_email='anemitz@gmail.com',
    maintainer='Anthony Nemitz',
    maintainer_email='anemitz@gmail.com',
    description='Flask restful API framework for MongoDB/MongoEngine',
    long_description=__doc__,
    packages=[
        'flask_mongorest',
    ],
    test_suite='nose.collector',
    zip_safe=False,
    platforms='any',
    setup_requires=[
        'Flask-Views',
        'Flask-MongoEngine',
        'mimerender',
        'nose', 
        'coverage',
        'python-dateutil'
    ],
    dependency_links = [
        'http://github.com/elasticsales/flask-mongoengine/tarball/master#egg=flask-mongoengine',
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ]
)
