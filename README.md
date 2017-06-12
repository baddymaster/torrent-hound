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


### Usage
Download the `torrent-hound` binary from the `bin/` directory.

`torrent-hound 'search-query'` or simply `torrent-hound`


### Help
Available Commands :

  1. `m<result number>` - Print magnet link of selected torrent   
  2. `c<result number>` - Copy magnet link of selected torrent to clipboard
  3. `d<result number>` - Download torrent using default torrent client
  4. `o<result number>` - Open the torrent page of the selected torrent in the default browser
  5. `cs<result number>` - Copy magnet link and open Seedr.cc  
  6. `p<optional choice>` - Print top 10 results from each website for the given query
     
     `<choice>` : [{default : 1}, {0 : Print formatted result}, {1 : Pretty print results}]        
  7. `s` - Enter a new query to search for over all avilable torrent websites
  8. `r` - Repeat last search (with same query)
