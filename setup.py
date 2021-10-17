from pathlib import Path
from setuptools import setup, find_packages

__version__ = "0.0.1a"

# with open('requirements.txt') as f:
#     required = f.read().splitlines()

HERE = Path(__file__).parent
README = (HERE / "README.md").read_text()
DESCRIPTION = "Audiobook client for OverDrive"

setup(
    name="sonus",
    version=__version__,
    author="digitalec",
    description=DESCRIPTION,
    long_description=README,
    long_description_content_type="text/markdown",
    license="GPL3",
    classifiers=[
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Programming Language :: Python :: 3.6",
        "Operating System :: OS Independent",
    ],
    packages=find_packages(),
    include_package_data=True,
    python_requires=">=3.6",
    # install_requires=required,
    url="https://github.com/digitalec/sonus"
)
