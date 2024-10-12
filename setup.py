from setuptools import setup

setup(
    name="schema",
    version="0.1.0",
    py_modules=["schema"],
    install_requires=[
        "Click",
    ],
    entry_points={
        "console_scripts": [
            "schema = src.schema:check",
        ],
    },
)
