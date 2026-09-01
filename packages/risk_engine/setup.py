"""Setup script for risk_engine package."""
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="risk_engine",
    version="0.1.0",
    author="Stratsmith contributors",
    description="Trading engine risk control, order management, and position monitoring",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(exclude=["tests", "tests.*"]),
    python_requires=">=3.10",
    install_requires=[
        "pydantic>=2.0.0",
        # Add other dependencies as needed
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "mypy>=1.0.0",
            "ruff>=0.1.0",
        ],
        "redis": [
            "redis>=5.0.0",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Office/Business :: Financial :: Investment",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
