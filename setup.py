from setuptools import setup

setup(
    name='Kuyruk',
    version='0.1',
    packages=['kuyruk'],
    install_requires=['pika>=0.9.9', 'importlib>=1.0.2'],
    entry_points={
        'console_scripts': [
            'kuyruk = kuyruk.__main__:main'
        ],
    }
)
