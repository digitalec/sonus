import logging
import shutil
import tempfile

import xmltodict
from mutagen.mp3 import MP3
from mutagen.id3 import ID3
import ffmpeg
from pathlib import Path

logger = logging.getLogger(__name__)


def scan_overdrive_metadata(file_list):
    all_markers = []
    for file in file_list:
        file_marker = {'file': file, 'markers': []}
        tag_data = ID3(file)
        xmlstring = str(tag_data['TXXX:OverDrive MediaMarkers'])
        audio_data = xmltodict.parse(xmlstring)
        for k, v in audio_data.items():
            for key, val in v.items():
                if not isinstance(val, list):
                    val = [val]
                for marker in val:
                    marker['Time'] = convert_timestamp_to_secs(marker['Time'])
                    file_marker['markers'].append(dict(marker))
        all_markers.append(file_marker)
    return all_markers


def convert_timestamp_to_secs(ts):
    split_ts = ts.split(":")
    if len(split_ts) == 3:
        hours = int(split_ts[0])
        mins = int(split_ts[1])
        secs = float(split_ts[2])
        return (hours * 3600) + (mins * 60) + secs
    else:
        mins = int(split_ts[0])
        secs = float(split_ts[1])
        return (mins * 60) + secs


def get_chapter_list(markers):
    current_chapter = ""
    chapter_list = []
    for marker in markers:
        for chapter in marker['markers']:
            if current_chapter == "" or current_chapter not in chapter['Name']:
                current_chapter = chapter['Name']
                if current_chapter not in chapter_list:
                    chapter_list.append(current_chapter)
    return chapter_list


def get_chapter_timings(file_metadata):

    current_chapter = None
    current_chapter_index = 1
    breakdown = []

    for f in file_metadata:
        start = None
        end = None
        for i, markers in enumerate(f['markers']):
            if not current_chapter:
                current_chapter = markers['Name']

            if current_chapter not in markers['Name']:
                # Save current file/chapter info and move to next chapter
                if start is not None and end is not None:
                    chapter_info = {'file': f['file'], 'chapter': current_chapter, 'start': start, 'end': end,
                                    'track': current_chapter_index}
                    breakdown.append(chapter_info)
                current_chapter = markers['Name']
                current_chapter_index += 1
                start = None

            if start is None:
                start = markers['Time']

            try:
                end = f['markers'][i+1]['Time']
            except IndexError:
                # Reached the end of the current file, save current file/chapter info and move to next file
                end = MP3(f['file']).info.length
                chapter_info = {'file': f['file'], 'chapter': current_chapter, 'start': start, 'end': end,
                                'track': current_chapter_index}
                breakdown.append(chapter_info)
    return breakdown


def split_chapters(files, tmpdir, ffmpeg_debug):
    for i, file in enumerate(files):
        if file['start'] == file['end']:
            continue
        logger.info(f"Extracting chapter {file['chapter']} from {file['file'].name}")
        try:
            stream = ffmpeg.input(file['file'], ss=file['start'], to=file['end'])
            stream = ffmpeg.output(stream, f"{tmpdir.name}/tmp_{str(i).rjust(3, '0')}.mp3", c='copy', f='mp3',
                                   **{'metadata:g:0': f'title={file["chapter"]}',
                                    'metadata:g:1': f'track={file["track"]}'},
                                   loglevel=f'{ffmpeg_debug}')
            stream = ffmpeg.overwrite_output(stream)
            ffmpeg.run(stream)
        except FileNotFoundError as e:
            if 'ffmpeg' in str(e):
                print(" --- ERROR! Please make sure ffmpeg is installed")


def merge_chapter_parts(file_list, output_dir, generic=False):
    author, title = None, None
    current_chapter = None
    current_track = None
    temp_chapter_file = None
    generic = generic

    for i, file in enumerate(file_list):
        tag_data = ID3(file)
        if not author:
            author = tag_data.get('TPE1')
            title = tag_data.get('TALB')
            logger.info(f"Processing audiobook \"{title}\" by {author}")
        last_track = False

        if current_chapter is None:
            current_chapter = tag_data.get('TIT2').text[0]
            current_track = int(tag_data.get('TRCK').text[0])
            if generic:
                current_chapter = f"Chapter {current_track}"
            logger.debug(f"Set current chapter to {current_chapter} | Track: {current_track}")

        logger.debug("Checking if next file belongs to this chapter")
        try:
            next_tag_data = ID3(file_list[i+1])
            next_track = int(next_tag_data.get('TRCK').text[0])
            next_file = file_list[i+1]
        except IndexError:
            next_track, next_file = None, None
            last_track = True

        if current_track == next_track:
            if temp_chapter_file:
                file = temp_chapter_file
                temp_chapter_file = str(file) + "_" + str(i).rjust(2, '0') + ".mp3"
            else:
                temp_chapter_file = str(file) + "_" + str(i).rjust(2, '0') + ".mp3"

            temp_chapter_file = temp_chapter_file.replace(':', '-')
            logger.debug(f"Merging {file} with {next_file}")
            stream = ffmpeg.input(f"concat:{file}|{next_file}")
            stream = ffmpeg.output(stream, str(temp_chapter_file), c="copy", loglevel='quiet')
            stream = ffmpeg.overwrite_output(stream)
            logger.debug(f"Saving to {temp_chapter_file}")
            ffmpeg.run(stream)
        else:
            if not temp_chapter_file:
                temp_chapter_file = file

            author = str(author).split("/")[0]

            # Create output dir if it doesn't exist
            output_to = f"{output_dir}/{author}/{title}"
            Path(output_to).mkdir(parents=True, exist_ok=True)
            if generic:
                chapter_filename = f"Chapter {current_track}"
            else:
                invalid_chars = [
                    ['!', ''],
                    ['?', ''],
                    [':', ' -'],
                ]
                for i in invalid_chars:
                    current_chapter = current_chapter.replace(i[0], i[1])
                chapter_filename = str(current_track) + " " + current_chapter
            logger.info(f"Saving chapter to {output_to}/{chapter_filename}.mp3")

            # Save chapter to output directory
            shutil.copy(temp_chapter_file, f"{output_dir}/{author}/{title}/{chapter_filename}.mp3")
            if not last_track:
                logger.debug(f"Next track is different, track {next_track}")
            current_track = None
            current_chapter = None
            temp_chapter_file = None


def main(input_dir, output_dir, generic_chapters, debug):
    file_list = sorted([f for f in Path(input_dir).rglob('*.mp3')])
    tmpdir = tempfile.TemporaryDirectory()
    logger.debug(f"Temporary directory created at: {tmpdir.name}")
    all_markers = scan_overdrive_metadata(file_list)
    chapter_names = get_chapter_list(all_markers)
    logger.info(f"Found {len(file_list)} files, containing {len(chapter_names)} chapters...")
    timings = get_chapter_timings(all_markers)
    split_chapters(timings, tmpdir, debug)
    tmpfiles = sorted([f for f in Path(tmpdir.name).rglob('*.mp3')])
    merge_chapter_parts(tmpfiles, output_dir, generic_chapters)
    tmpdir.cleanup()
