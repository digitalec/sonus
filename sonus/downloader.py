import base64
import hashlib
import logging
import os
import re
import sys
import uuid
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import requests

from os.path import (abspath, basename, expanduser, getsize, isdir, isfile, sep)
from tqdm import tqdm

logger = logging.getLogger(__name__)


class Downloader:
    """Downloader class is a heavily modified version of the download logic
    in overdrive-dl written by davideg - https://github.com/davideg/overdrive-dl"""
    USER_AGENT = 'OverDrive Media Console'
    USER_AGENT_LONG = 'OverDrive Media Console (unknown version)' \
                      'CFNetwork/976 Darwin/18.2.0 (x86_64)'
    OMC = '1.2.0'
    OS = '10.14.2'
    HASH_SECRET = 'ELOSNOC*AIDEM*EVIRDREVO'
    CLIENT_ID_PATH = expanduser('~/.overdrive-dl.clientid')

    DOWNLOAD_PATH_FORMAT = '{author}/{title}/{filename}'
    DOWNLOAD_FILENAME_FORMAT = '{title}-part{number:02d}.mp3'
    COVER_FILENAME_FORMAT = '{title}.jpg'
    CHUNK_SIZE = 1024

    def __init__(self, download_path):
        self.root_download_path = download_path
        self.download_path = None
        self.base_url = None
        self.author = None
        self.title = None
        self.cover_url = None
        self.base_url = None
        self.headers = None

    def process_download(self, part):
        logger.info(f"Downloading {self.DOWNLOAD_FILENAME_FORMAT.format(title=self.title, number=int(part.get('number')))}")
        logger.debug(f"Filename: {part.get('filename')} | Filesize: {part.get('filesize')} | "
                     f"Duration: {part.get('duration')}")
        dl_url = self.base_url + '/' + part.get('filename')
        filepath = self.download_path \
                   + sep \
                   + self.DOWNLOAD_FILENAME_FORMAT.format(title=self.title,
            number=int(part.get('number')))
        filesize = int(part.get('filesize'))
        if self._file_exists(filepath, filesize):
            logger.debug(f"{part.get('name')} already exists with expected size "
                        f"{(filesize / (1024 * 1024)):.2f}MB: {filepath}")

        r = requests.get(dl_url, headers=self.headers, stream=True)
        with open(filepath, 'wb') as fd:
            for it, chunk in enumerate(r.iter_content(chunk_size=self.CHUNK_SIZE)):
                fd.write(chunk)
        return

    def download_audiobook(self, odm_filename):
        self._verify_odm_file(odm_filename)
        license, client_id = self._get_license_and_client_id(odm_filename)
        self.author, self.title, self.cover_url, self.base_url, parts = \
            self._extract_author_title_urls_parts(odm_filename)
        num_parts = len(parts)

        self.download_path = self._construct_download_dir_path()
        logger.debug('Will save files to {}'.format(self.download_path))
        if not isdir(self.download_path):
            logger.debug('Creating {}'.format(self.download_path))
            os.makedirs(self.download_path, exist_ok=True)

        logger.debug('Downloading using ODM file: {}'.format(odm_filename))
        if self.cover_url:
            logger.debug('Downloading cover image: {}'.format(self.cover_url))
            cover_path = self.download_path + sep \
                         + self.COVER_FILENAME_FORMAT.format(title=self.title)
            if self._file_exists(cover_path):
                logger.info('Cover image {} already exists'.format(cover_path))
            else:
                self._download_cover_image(self.cover_url, cover_path)
        logger.debug('Using ClientID: {}'.format(client_id))

        self.headers = {
            'License': license,
            'ClientID': client_id,
            'User-Agent': self.USER_AGENT
        }

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(tqdm(executor.map(self.process_download, parts),
                                total=len(parts),
                                desc="",
                                ascii=" #",
                                bar_format="Downloading part {n_fmt} of {total_fmt}... {percentage:3.0f}%"))

    def _download_cover_image(self, cover_url, cover_path):
        headers = {'User-Agent': self.USER_AGENT_LONG}
        r = requests.get(cover_url, headers=headers)
        if r.status_code == 200:
            with open(cover_path, 'wb') as fd:
                logger.debug('Saving as {}'.format(cover_path))
                fd.write(r.content)
        else:
            logger.debug('Could not download cover. Status code: {}'.format(
                r.status_code))

    def _extract_author_title_urls_parts(self, odm_filename):
        odm_root, metadata = self._get_odm_root_and_metadata(odm_filename)
        author = self._get_author_from_metadata(metadata)
        title = metadata.findtext('Title')
        cover_url = metadata.findtext('CoverUrl', '')
        logger.info('Got title "{}" and author'.format(title)
                     + ('s' if ';' in author else '')
                     + ' {} from ODM file {}'.format(
            ', '.join(author.split(';')),
            basename(odm_filename)))

        # Find the Protocol element with the URL for downloading
        p = odm_root.find('.//Protocol[@method="download"]')
        base_url = p.get('baseurl', default='') if p is not None else ''
        if not base_url:
            self._die('Trouble extracting URL from ODM file')

        p = odm_root.find('.//Parts')
        num_parts = int(p.get('count', default=0)) if p is not None else 0
        # Find all the parts to download
        parts = odm_root.findall('.//Part')
        if len(parts) != num_parts:
            self._die('Bad ODM file: Expecting {} parts, but found {}'
                      'part records'.format(num_parts, len(parts)))
        return (author, title, cover_url, base_url, parts)

    def _get_odm_root_and_metadata(self, odm_filename):
        odm_str = ''
        with open(odm_filename, 'r') as fd:
            odm_str = fd.read()

        root = ET.fromstring(odm_str)
        m = re.search(r'<Metadata>.*</Metadata>', odm_str, flags=re.S)
        if not m:
            self._die('Could not find Metadata in {}'.format(odm_filename))
        # escape standalone ampersands
        metadata_str = re.sub(r' & ', ' &amp; ', m.group(0))
        metadata = ET.fromstring(metadata_str)
        return root, metadata

    @staticmethod
    def _get_author_from_metadata(metadata):
        creator_elements = metadata.findall('.//Creator')
        author_elements = [elmt for elmt in creator_elements
                           if 'author' in str.lower(elmt.attrib.get('role'))]
        author = ';'.join([e.text for e in author_elements])
        # Use editors if there are no authors
        if author == '':
            author_elements = [elmt for elmt in creator_elements
                               if 'editor' in str.lower(elmt.attrib.get('role'))]
            author = ';'.join([e.text for e in author_elements])
        return author

    def _construct_download_dir_path(self):
        return abspath(expanduser(self.root_download_path)
                       + sep
                       + self.DOWNLOAD_PATH_FORMAT.format(
            author=self.author,
            title=self.title,
            filename=''))

    @staticmethod
    def _file_exists(file_path, expected_size_bytes=None):
        does_file_exist = isfile(file_path) \
                          and (expected_size_bytes is None
                               or getsize(file_path) == expected_size_bytes)
        logger.debug('File \"{}\" exists'.format(file_path) \
                      + (' with size {} bytes?'.format(expected_size_bytes)
                         if expected_size_bytes
                         else '?') \
                      + ' {}'.format(does_file_exist))
        return does_file_exist

    def _verify_odm_file(self, odm_filename):
        logger.debug('Attempting to verify ODM file "{}"'.format(odm_filename))
        if isfile(odm_filename):
            with open(odm_filename, 'r') as f:
                if not re.search(r'<OverDriveMedia', f.read(100)):
                    self._die('Expected ODM file. Specified file "{}"'
                              ' is not in the correct OverDriveMedia'
                              ' format'.format(basename(odm_filename)))
        elif isdir(odm_filename):
            self._die('Expected ODM file. Given directory: {}'.format(
                basename(odm_filename)))
        else:
            self._die('Expected ODM file. Specified file "{}"'
                      ' does not exist'.format(basename(odm_filename)))

    def _get_license_and_client_id(self, odm_filename):
        license = ''
        license_filepath = odm_filename + '.license'
        if not isfile(license_filepath):
            license = self.acquire_license(odm_filename)
            logger.debug('Writing to license file: {}'.format(license_filepath))
            with open(license_filepath, 'w') as fd:
                fd.write(license)
        else:
            logger.debug('Reading from license file: {}'.format(license_filepath))
            with open(license_filepath, 'r') as fd:
                license = fd.read()
        if not license:
            self._die('Missing license content')
        license_xml = ET.fromstring(license)
        client_id = license_xml.findtext(
            './{http://license.overdrive.com/2008/03/License.xsd}SignedInfo'
            '/{http://license.overdrive.com/2008/03/License.xsd}ClientID')
        if not client_id:
            self._die('Failed to extract ClientID from License')
        return (license, client_id)

    def _generate_hash(self, client_id):
        """Hash algorithm and secret complements of
        https://github.com/jvolkening/gloc/blob/v0.601/gloc#L1523-L1531"""
        rawhash = '|'.join([client_id, self.OMC, self.OS, self.HASH_SECRET])
        return base64.b64encode(hashlib.sha1(rawhash.encode('utf-16-le')).digest())

    def acquire_license(self, odm_filename):
        logger.debug('Acquiring license')
        tree = ET.parse(odm_filename)
        root = tree.getroot()
        acquisition_url = root.findtext('./License/AcquisitionUrl')
        logger.debug('Using AcquisitionUrl: {}'.format(acquisition_url))
        media_id = root.attrib.get('id', '')
        logger.debug('Using MediaID: {}'.format(media_id))

        client_id = ''
        if not isfile(self.CLIENT_ID_PATH):
            # Generate random Client ID
            client_id = str(uuid.uuid4()).upper()
            with open(self.CLIENT_ID_PATH, 'w') as fd:
                fd.write(client_id)
        else:
            with open(self.CLIENT_ID_PATH, 'r') as fd:
                client_id = fd.read()
        logger.debug('Using ClientID: {}'.format(client_id))

        hsh = self._generate_hash(client_id)
        logger.debug('Using Hash: {}'.format(hsh))

        headers = {'User-Agent': self.USER_AGENT}
        payload = {
            'MediaID': media_id,
            'ClientID': client_id,
            'OMC': self.OMC,
            'OS': self.OS,
            'Hash': hsh}
        r = requests.get(acquisition_url, params=payload, headers=headers)
        if r.status_code == 200:
            return r.text
        else:
            self._die('Failed to acquire License for {}'.format(odm_filename))

    @staticmethod
    def _die(msg):
        logger.error(' --- ERROR: ' + msg + '\n')
        sys.exit(1)
