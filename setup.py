#!/usr/bin/env python

"""The setup script."""

from setuptools import setup, find_packages


def read_readme():
    with open("README.md", encoding="utf-8") as f:
        return f.read()


def read_history():
    with open("HISTORY.rst", encoding="utf-8") as f:
        return f.read()


requirements = [
    'requests>=2.25.0',
    'pandas>=1.3.0',
    'numpy>=1.20.0',
    'persiantools>=2.0.0',
    'urllib3>=1.26.0',
]

test_requirements = ['pytest>=7.0', ]

setup(
    author="Mohsen Alipour",
    author_email='alipour@algotik.ir',
    python_requires='>=3.8',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Intended Audience :: Financial and Insurance Industry',
        'Topic :: Office/Business :: Financial :: Investment',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Programming Language :: Python :: 3.14',
    ],
    description="A comprehensive Python library for fetching Tehran Stock Exchange (TSETMC) and currency/coin market data.",
    install_requires=requirements,
    license="GNU General Public License v3",
    long_description=read_readme() + '\n\n' + read_history(),
    long_description_content_type="text/markdown",
    include_package_data=True,
    keywords='tse, tsetmc, tehran stock exchange, bourse, algotik, stock, market data, iran',
    name='algotik_tse',
    packages=find_packages(include=['algotik_tse', 'algotik_tse.*']),
    url='https://github.com/mohsenalipour/algotik_tse',
    project_urls={
        'Website': 'https://algotik.com',
        'Bug Tracker': 'https://github.com/mohsenalipour/algotik_tse/issues',
        'Documentation': 'https://github.com/mohsenalipour/algotik_tse#readme',
        'Telegram': 'https://t.me/algotik',
    },
    version='1.0.0',
    zip_safe=False,
)
