# Torrent Hound
Search torrents from multiple websites via the CLI


### Requirements
- Python 2.7
- bs4
- clint
- pyperclip
- humanize
- VeryPrettyTable


### Installation
Run `pip install -r requirements.txt` in the shell to install all dependencies


### Update existing Intallation
If installed via `git`, then simply run `git pull` in the shell after navigating to the `torrent-hound` directory

Otherwise download the latest binary from the `releases` section of this repository


### Usage
Download the `torrent-hound` binary from the `bin/` directory.

`torrent-hound 'search-query'` or simply `torrent-hound`


### Menu
Available Commands :

  1. `m<result number>` - Print magnet link of selected torrent   
  2. `c<result number>` - Copy magnet link of selected torrent to clipboard
  3. `d<result number>` - Download torrent using default torrent client
  4. `o<result number>` - Open the torrent page of the selected torrent in the default browser
  5. `cs<result number>` - Copy magnet link and open Seedr.cc
  6. `cz<result number>` - Copy magnet link and open zbigz
  7. `p<optional choice>` - Print top 10 results from each website for the given query
     
     `<choice>` : [{default : 1}, {0 : Print formatted result}, {1 : Pretty print results}]        
  8. `s` - Enter a new query to search for over all avilable torrent websites
  9. `r` - Repeat last search (with same query)


### Help
In case of an `SSL Error`, consult [these answers on Stackoverflow](https://stackoverflow.com/questions/31649390/python-requests-ssl-handshake-failure) for potential fixes.
