from setuptools import setup, find_packages

setup(
    name="ruby-companion-cat",
    version="0.9.2",
    description="Open-source interactive companion cat platform",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=[
        "numpy>=1.26",
        "opencv-python>=4.8",
        "pyserial>=3.5",
        "smbus2>=0.4",
        "pyyaml>=6.0",
        "SQLAlchemy>=2.0",
        "structlog>=24.0",
    ],
    entry_points={
        "console_scripts": [
            "ruby=ruby.runtime:main",
        ]
    },
)
