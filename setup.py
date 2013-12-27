#!/usr/bin/env python

from setuptools import setup

setup(name='pylitter',
      entry_points = {
          'console_scripts' :
          ['pylitter = pylitter:main',
               ]},
      packages=['pylitter'],
      package_data={'pylitter':['data/template.tex']},
      provides='pylitter',
      install_requires=[
        "opster",
        "sh",
      ],
      classifiers=[
        'Development Status :: Alpha',
        'Topic :: Text Processing :: Markup',
        'Intended Audience :: Science/Research',
        'Topic :: Scientific/Engineering',
        'Topic :: Software Development :: Documentation',
        'License :: OSI Approved :: GNU General Public License (GPL)'],
)
