import logging
import sys
import tempfile
from xml.etree import ElementTree as ET
from pathlib import Path
import click
import requests
from requests import HTTPError

from sonus import __PKGNAME__, __VERSION__
from sonus.downloader import Downloader
from sonus import chapterizer
from tqdm import tqdm

logger = logging.getLogger(__name__)


class TqdmStream(object):

    @classmethod
    def write(cls, msg):
        tqdm.write(msg, end='')


def _setup_logger(log_level='DEBUG'):

    log_formats = {
        'DEBUG': '[%(levelname)s] %(name)s: %(message)s',
        'INFO': '%(message)s',
    }

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    sonus_logger = logging.getLogger("sonus")
    sonus_logger.setLevel(logging.DEBUG)

    stream = logging.StreamHandler(stream=TqdmStream)
    stream.setLevel(log_level)
    stream.setFormatter(logging.Formatter(log_formats[log_level], datefmt="%Y-%m-%d %H:%M:%S"))
    sonus_logger.addHandler(stream)


def version_info():
    return f"""{__PKGNAME__} {__VERSION__}
Support: https://github.com/digitalec/sonus"""


@click.command(name='main')
@click.argument('ODM', metavar='PATH', nargs=-1)
@click.option('-i', '--info', is_flag=True, help="Show info of ODM file", hidden=True)
@click.option('-d', '--download', is_flag=True, help="Download book only, do not chapterize")
@click.option('-g', '--generic', is_flag=True, help="Use generic chapter names (Chapter 1, Chapter 2, etc.)")
@click.option('-r', '--return', 'return_book', is_flag=True, help="Return an audiobook")
@click.option('-o', '--output', 'output_path', type=str, help="Output directory")
@click.option('-v', '--verbose', is_flag=True, help="Show verbose output")
@click.option('-f', '--ffmpeg-debug', is_flag=True, help="Show debug messages for ffmpeg")
@click.version_option(__VERSION__, '--version', '-V', 'version', message=version_info())
def main(odm, info, download, generic, return_book, output_path, verbose, ffmpeg_debug):
    """sonus is an OverDrive download manager and chapterizer for audiobooks
    
    You can download and chapterize a book by simply passing the ODM file
    into sonus like so:

        sonus MyAudiobook.odm --output /media/books

    This will download the book to /media/books/Author/Title, then split
    the downloaded parts into individual MP3 chapters and finally tag each
    file with proper ID3 tag information.

    If you've already downloaded an existing book you can just chapterize
    the existing parts by passing the directory itself:

        sonus /Downloads/MyAudiobook --output /media/books
    """

    verbose = "DEBUG" if verbose else "INFO"

    _setup_logger(verbose)

    if not output_path:
        output_path = str(Path.cwd())

    if output_path[-1] == "/":
        output_path = output_path[:-1]

    logger.info(f"Output will be saved to: {output_path}")

    if ffmpeg_debug:
        ffmpeg_debug = 'debug'
    else:
        ffmpeg_debug = 'quiet'
    
    for arg in [x for x in odm]:
        logger.debug(f"Input file: {str(arg)}")
        
        if Path(arg).is_dir():
            chapterizer.main(arg, output_path, generic, ffmpeg_debug)
            continue

        elif Path(arg).is_file() and Path(arg).suffix == ".odm":
            if info:
                get_info()
            elif return_book:
                return_odm(arg)
                sys.exit()
        else:
            continue

        if download:
            logger.debug(f"Downloading audiobook to {output_path}")
            get_book(arg, output_path)
            continue
        else:
            tmpdir = tempfile.TemporaryDirectory()
            logger.debug(f"Downloading parts to temporary directory: {tmpdir.name}")
            get_book(arg, tmpdir.name)
            chapterizer.main(tmpdir.name, output_path, generic, ffmpeg_debug)
            tmpdir.cleanup()


def get_book(odm, o):
    """Download audiobook from ODM file"""
    downloader = Downloader(o)
    downloader.download_audiobook(odm)
    return downloader.download_path


def return_odm(odm_file):
    """Return audiobook to OverDrive, modified version of code used
    in odmpy, written by ping - https://github.com/ping/odmpy"""
    odm_contents = ET.parse(odm_file)
    logger.info(f"Returning {odm_file} ...")
    early_return_url = odm_contents.find("EarlyReturnURL").text
    try:
        early_return_res = requests.get(
            early_return_url, headers={"User-Agent": "OverDrive Media Console"}, timeout=10
        )
        early_return_res.raise_for_status()
        logger.info(f"Loan returned successfully: {odm_file}")
    except HTTPError as he:
        if he.response.status_code == 403:
            logger.warning("Loan is probably already returned.")
            sys.exit()
        logger.error(f"Unexpected HTTPError while trying to return loan {odm_file}")
        logger.error(f"HTTPError: {str(he)}")
        logger.debug(he.response.content)
        sys.exit(1)
    except ConnectionError as ce:
        logger.error(f"ConnectionError: {str(ce)}")


def get_info():
    """Display audiobook info"""
    pass