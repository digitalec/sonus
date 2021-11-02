## sonus
sonus is a cross-platform OverDrive audiobook client and chapterizer written in Python and the only tool that properly splits and tags chapters.

This tool was written with the need for a portable way to automate chapterizing and tagging of OverDrive MP3 files for use in standard media players. You must have an active OverDrive account and check-out the books you wish to download.

OverDrive stores XML data in each MP3 file containing chapter timings. The biggest hurdle for this project was to detect and skip duplicate chapter markers (`Chapter 1, Chapter 1 (04:02), Chapter 1 (06:19), etc.`) that sometimes spans across multiple files.


### Features
- Download and chapterizer audiobooks
- Chapterize existing OverDrive files
- Return loan early


### Requirements
- Python 3.6+
- ffmpeg


### Installation

Install the latest release from PyPI:
```
$ pip install sonus
$ sonus --version
sonus 0.1.0
```

...or install by cloning this repository
```
$ git clone https://github.com/digitalec/sonus.git
$ cd sonus
$ python -m sonus --version
sonus 0.1.0
```

### Usage
Audiobook files are saved inside the specified `--output` directory under a Artist/Title/Chapters structure.


To download and chapterize an audiobook:
```
$ sonus BookName.odm --output /media/audiobooks
```

&nbsp;

If you already have existing audiobooks downloaded using the OverDrive Media Console, you can still chapterize them to make them easier to play on other devices. Specify the path to the folder containing all of the OverDrive "-partX.mp3" files:
```
C:\> sonus "C:\Users\Name\Documents\My Media\MP3 Audiobooks\BookName" --output "E:\Audiobooks"
```

&nbsp;

Once you're done with an audiobook and wish to return the loan:
```
$ sonus --return BookName.odm
```

### Credits

- sonus was inspired by the _OverDrive Chapterizer_ feature of inAudible
- _Download_ logic is a modified version of that from [overdrive-dl](https://github.com/davideg/overdrive-dl)
- _Return Early_ logic is from [odmpy](https://github.com/ping/odmpy)
