from setuptools import setup

# Stops exit traceback on tests
try:
    import multiprocessing
except:
   pass

setup(
    name='Flask-MongoRest',
    version='0.1.1',
    url='http://github.com/closeio/flask-mongorest',
    license='BSD',
    author='Close.io',
    author_email='engineering@close.io',
    maintainer='Close.io',
    maintainer_email='engineering@close.io',
    description='Flask restful API framework for MongoDB/MongoEngine',
    long_description=__doc__,
    packages=[
        'flask_mongorest',
    ],
    package_data={
        'flask_mongorest': ['templates/mongorest/*']
    },
    test_suite='nose.collector',
    zip_safe=False,
    platforms='any',
    setup_requires=[
        'Flask-Views',
        'Flask-MongoEngine',
        'mimerender',
        'nose',
        'coverage',
        'python-dateutil',
        'cleancat'
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
