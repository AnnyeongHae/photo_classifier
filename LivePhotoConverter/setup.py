"""Setup configuration for LivePhotoConverter package."""

from setuptools import setup, find_packages

setup(
    name="LivePhotoConverter",
    version="1.0.0",
    description="Independent service for converting Live Photos (MP4) to static images (JPEG/PNG)",
    author="Photo Classification System",
    url="https://github.com/yourusername/LivePhotoConverter",
    packages=find_packages(),
    install_requires=[
        "opencv-python>=4.8.0",
        "numpy>=1.24.0",
        "PySide6>=6.6.0",
        "Pillow>=10.0.0",
    ],
    extras_require={
        "dev": ["pytest>=7.0", "black", "flake8"],
    },
    python_requires=">=3.9",
    entry_points={
        "console_scripts": [
            "live-photo-converter=cli.batch_processor:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
