"""
Package setup for mem-ai.

Install with:
  pip install -e .          # editable / development
  pip install .             # standard

After installation the `mem-ai` command is available system-wide.
"""

from setuptools import find_packages, setup

with open("requirements.txt") as f:
    install_requires = [
        line.strip()
        for line in f
        if line.strip() and not line.startswith("#")
    ]

setup(
    name="mem-ai",
    version="1.0.0",
    description="Universal AI CLI wrapper with persistent memory — wraps claude, openai, gemini, and ollama.",
    long_description=open("README.md").read() if __import__("os").path.exists("README.md") else "",
    long_description_content_type="text/markdown",
    author="AI Memory Layer",
    python_requires=">=3.11",
    packages=find_packages(exclude=["tests*"]),
    install_requires=install_requires,
    entry_points={
        "console_scripts": [
            # Primary CLI command
            "mem-ai=mem_ai.cli:main",
            # Convenience alias
            "memai=mem_ai.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Utilities",
    ],
    project_urls={
        "Source": "https://github.com/yourorg/ai-memory-layer",
        "Bug Tracker": "https://github.com/yourorg/ai-memory-layer/issues",
    },
)
