from setuptools import setup, find_packages

setup(
    name="math-knowledge-base",
    version="0.1.0b1",  # versión beta 1
    packages=find_packages(exclude=["notebooks", "tests"]),
    include_package_data=True,
    install_requires=[
        "streamlit>=1.24",
        "pandas>=2.0",
        "matplotlib>=3.7",
        "networkx>=3.0",
        "pyvis>=0.3",
        "pymongo>=4.0",
        "pypdf>=3.0",
        "latex2mathml>=3.74"
    ],
    entry_points={
        "console_scripts": [
            "mathdb=app.main:main"  # 
        ]
    },
    author="Enrique Díaz Ocampo",
    description="Base de datos personalizable para registrar definiciones, teoremas y ejemplos matemáticos usando LaTeX.",
    url="https://github.com/EnriqueDiazO/math-knowledge-base",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License", 
        "Operating System :: OS Independent",
        "Development Status :: 4 - Beta",
    ],
    python_requires=">=3.10",
)
