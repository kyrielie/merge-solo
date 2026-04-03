# merge-solo

A [Calibre](https://calibre-ebook.com/) plugin that allows bulk merging complete Ao3 series into one epub. Depends on [EpubMerge](https://github.com/JimmXinu/EpubMerge).

Based on the [fanficfare](https://github.com/jimmxinu/fanficfare) implementation of automatically merging fanfiction.

## Warning

Calibre is inherently destructive and this plugin is beta software. Do not use with your main library, it may delete books and metadata irreparably. 

## Install

Download the zip of the repository and load it in Calibre. See this tutorial: https://www.mobileread.com/forums/showthread.php?t=347331

## Usage

Click on Series Merge. Scan library then select works to merge. Click Merge Selected to merge works.

<img width="1012" height="760" alt="SeriesMerge1" src="https://github.com/user-attachments/assets/d13c1e76-287a-4557-a45e-a29da956ab99" />
<img width="1012" height="760" alt="SeriesMerge2" src="https://github.com/user-attachments/assets/bf92cc04-5a32-4b18-81e7-744b059f5750" />


## Issues

- Calibre cannot deal with multiseries works. Must implement a feature to support or manually sift through broken series to catch multiseries works. 
- Does not detect already merged works. Will create duplicates if run multiple times.
- Cannot fetch missing works unlike fanficfare.
- Cannot identify tailing missing works.
- Unable to mark series with only one work.
- Unable to export search log.
- No multiselect for works, must click checkboxes or all. Using virtual libraries/searches might help.
- No icon.
- Does not respect EpubMerge options, hardcoded for one set of options (combine tags, combine descriptions)
- Date added inherits from the first book in the series.
