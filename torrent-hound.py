#!/usr/bin/env python3
# @author : Yashovardhan Sharma
# @github : github.com/baddymaster

#   <Torrent Hound - Search torrents from multiple websites via the CLI.>
#    Copyright (C) <2023>  <Yashovardhan Sharma>
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU Affero General Public License as published
#     by the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU Affero General Public License for more details.
#
#     You should have received a copy of the GNU Affero General Public License
#     along with this program.  If not, see <http://www.gnu.org/licenses/>.

from bs4 import BeautifulSoup
from clint.textui import colored
from veryprettytable import VeryPrettyTable
import requests
import re
import sys
import pyperclip
import webbrowser
import json
import argparse

defaultQuery, query = 'jason bourne', ''
results_tpb_condensed = None
results_1337x = None
results, results_rarbg, exit = None, None, None
num_results = 0
tpb_working_domain = 'thepiratebay.zone'
tpb_url, url_1337x = '', ''

def extract_magnet_link_1337x(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.0; WOW64; rv:24.0) Gecko/20100101 Firefox/24.0'}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.content, 'html.parser')
    magnet_link = soup.find('a', href=lambda href: href and href.startswith("magnet:"))
    if magnet_link:
        return magnet_link['href']
    else:
        return None
    
def search1337x(search_string=defaultQuery, domain='1337x.to', quiet_mode=False, limit=10):
    global results_1337x, url_1337x

    query = removeAndReplaceSpaces(search_string)
    page_no = 1
    baseURL = f'https://{domain}'
    url = f'{baseURL}/search/{query}/{page_no}/'
    url_1337x = url
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.0; WOW64; rv:24.0) Gecko/20100101 Firefox/24.0'}
    response = requests.get(url, headers=headers)
    results_1337x = []

    if response.status_code == 403 and response.headers.get('cf-mitigated', '').lower() == 'challenge':
        if quiet_mode == False:
            print(colored.magenta("[1337x] Error : Blocked by Cloudflare captcha"))
        return results_1337x

    soup = BeautifulSoup(response.text, 'html.parser')

    try:
        table = soup.find('table', {'class': 'table-list'})
        rows = table.tbody.find_all('tr')
        for row in rows[:limit]:
            row_data = {}
            name_col = row.find('td', {'class': 'coll-1 name'})
            row_data['name'] = name_col.a.next_sibling.text
            row_data['link'] = baseURL + name_col.a.next_sibling['href']
            row_data['seeders'] = int(row.find('td', {'class': 'coll-2 seeds'}).text.strip())
            row_data['leechers'] = int(row.find('td', {'class': 'coll-3 leeches'}).text.strip())
            try:
                row_data['ratio'] = format( (float(row_data['seeders'])/float(row_data['leechers'])), '.1f' )
            except ZeroDivisionError:
                row_data['ratio'] = 'inf'
            row_data['time'] = row.find('td', {'class': 'coll-date'}).text.strip()
            size_col = row.find('td', {'class': 'coll-4'})
            if size_col:
                row_data['size'] = size_col.contents[0].strip()
            else:
                row_data['size'] = ''
            # uploader_col = row.find('td', {'class': 'coll-5'})
            # if uploader_col:
            #     row_data['uploader'] = uploader_col.contents[0].text.strip()
            # else:
            #     row_data['uploader'] = ''
            row_data['magnet'] = extract_magnet_link_1337x(row_data['link'])
            results_1337x.append(row_data)
    except AttributeError as e:
        if quiet_mode == False:
            print(colored.magenta("[1337x] Error : No results found"))
    return results_1337x

def pretty_print_top_results_1337x(limit=10):
    global results_1337x, num_results
    table_1337x = VeryPrettyTable(left_padding_width=0, right_padding_width=0, padding_width=0)
    no_str = str(colored.red('No'))
    name_str = str(colored.red('Torrent Name'))
    size_str = str(colored.red('Size'))
    seed_str = str(colored.red('S'))
    leech_str = str(colored.red('L'))
    ratio_str = str(colored.red('S/L'))
    table_1337x.field_names = [no_str, name_str, size_str, seed_str, leech_str, ratio_str]

    #print '\n\t\t\t\t\t\t' + '+-----------+'
    #print '\t\t\t\t\t\t| ' + colored.green('PirateBay') + ' |'
    print('\n\t\t\t\t\t\t' + colored.green('1337x'))
    # print results
    if results_1337x != [{}] and results_1337x != [] and results_1337x != None:
        index = num_results + 1 # Index after TBP
        for r in results_1337x[:limit]:
            try :
                table_1337x.add_row([index, r['name'][:57], r['size'], r['seeders'], r['leechers'], r['ratio']])
                index = index + 1
            except KeyError as e:
                # Fix error where {} is included in results and screws up numbering #
                if r != {}:
                    print(r)
                    print(e)
        table_1337x.align[no_str] = 'l'
        table_1337x.align[name_str] = 'l'
        table_1337x.align[size_str] = 'r'
        table_1337x.align[seed_str] = 'r'
        table_1337x.align[leech_str] = 'r'
        table_1337x.align[ratio_str] = 'r'
        print(table_1337x)
        return index - 1
    else:
        table_1337x.add_row(["Null", "Null", "Null", "Null", "Null", "Null"])
        #table_piratebay.align[colored.red('Torrent Name')] = 'l'
        print(table_1337x)
        return num_results

def removeAndReplaceSpaces(string):
    if string[0] == " ":
        string = string[1:]
    return string.replace(" ", "+")

def searchPirateBayCondensed(search_string=defaultQuery, domain='thepiratebay.org', quiet_mode=False, limit=10):
    global tpb_working_domain, tpb_url, results_tpb_condensed
    url = f'https://{tpb_working_domain}/s/?q={removeAndReplaceSpaces(search_string)}&page=0&orderby=99'
    tpb_url = url
    #print url
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.0; WOW64; rv:24.0) Gecko/20100101 Firefox/24.0'}
    table = None

    try:
        r = requests.get(url, headers=headers)
        soup = BeautifulSoup(r.content, "html.parser")
        table = soup.find("table", {"id": "searchResult"})
        trs = table.find_all("tr")
        del trs[:1]

        results_tpb_condensed = []
        #for tr in trs:
        for tr in trs[:limit]:
            tds = tr.find_all("td")

            res = {}
            link_name = tds[1].find("a", {"class": "detLink"})
            res['name'] = link_name.contents[0].strip()
            res['link'] = link_name["href"]
            res['seeders'] = int(tds[2].contents[0])
            res['leechers'] = int(tds[3].contents[0])
            try:
                res['ratio'] = format( (float(res['seeders'])/float(res['leechers'])), '.1f' )
            except ZeroDivisionError:
                res['ratio'] = 'inf'
            res['magnet'] = tds[1].find("img", {"alt": "Magnet link"}).parent['href']
            res['size'] = str(tds[1].find("font").contents[0].split(',')[1].split(' ')[2].replace('\xa0', ' '))

            results_tpb_condensed.append(res)
    except Exception as e:
        if quiet_mode == False:
            if table == None:
                print(colored.magenta("[PirateBay] Error : No results found"))
            else:
                print(colored.red("[PirateBay] Error : Unkown problem while searching"))
                print(colored.yellow('ERR_MSG : ' + str(e)))
                #table = None
    #print(f"Search results TBP: {results_tpb_condensed}")
    return results_tpb_condensed

def pretty_print_top_results_piratebay(limit=10):
    global results
    table_piratebay = VeryPrettyTable(left_padding_width=0, right_padding_width=0, padding_width=0)
    no_str = str(colored.red('No'))
    name_str = str(colored.red('Torrent Name'))
    size_str = str(colored.red('Size'))
    seed_str = str(colored.red('S'))
    leech_str = str(colored.red('L'))
    ratio_str = str(colored.red('S/L'))
    table_piratebay.field_names = [no_str, name_str, size_str, seed_str, leech_str, ratio_str]

    print('\n\t\t\t\t\t\t' + colored.green('PirateBay'))
    if results != [{}] and results != [] and results != None:
        index = 1
        for r in results[:limit]:
            try:
                table_piratebay.add_row([index, r['name'][:57], r['size'], r['seeders'], r['leechers'], r['ratio']])
                index = index + 1
            except KeyError as e:
                # Skip empty {} entries that can slip in on parser errors
                if r != {}:
                    print(r)
                    print(e)
        table_piratebay.align[no_str] = 'l'
        table_piratebay.align[name_str] = 'l'
        table_piratebay.align[size_str] = 'r'
        table_piratebay.align[seed_str] = 'r'
        table_piratebay.align[leech_str] = 'r'
        table_piratebay.align[ratio_str] = 'r'
        print(table_piratebay)
        return index - 1
    else:
        table_piratebay.add_row(["Null", "Null", "Null", "Null", "Null", "Null"])
        print(table_piratebay)
        return 0

def _get_entry(resNum):
    """Return the search result dict for a 1-indexed result number, or None if invalid."""
    if resNum <= 0 or resNum > num_results:
        return None
    return results[resNum - 1]

# Commands that take a numeric argument and their handlers. Each handler
# receives the result entry (dict with 'magnet' and 'link' keys).
def _cmd_m(entry):
    print("\nMagnet Link : \n" + entry['magnet'])

def _cmd_c(entry):
    pyperclip.copy(str(entry['magnet']))
    print('Magnet link copied to clipboard!')

def _cmd_cs(entry):
    pyperclip.copy(str(entry['magnet']))
    webbrowser.open('https://www.seedr.cc', new=2)
    print('Seedr.cc opened and Magnet link copied to clipboard!')

def _cmd_d(entry):
    webbrowser.open(entry['magnet'], new=2)
    print('Magnet link sent to default torrent client!')

def _cmd_o(entry):
    webbrowser.open(entry['link'], new=2)
    print('Torrent page opened in default browser!')

# Longer prefixes must come first so 'cs' matches before 'c'.
_NUMERIC_CMDS = [('cs', _cmd_cs), ('c', _cmd_c), ('m', _cmd_m), ('d', _cmd_d), ('o', _cmd_o)]

def switch(arg):
    global exit, query

    # Numeric commands: m<n>, c<n>, cs<n>, d<n>, o<n>
    for prefix, handler in _NUMERIC_CMDS:
        match = re.match(rf'^{prefix}(\d+)$', arg)
        if match:
            entry = _get_entry(int(match.group(1)))
            if entry is None:
                print('Invalid command!\n')
            else:
                handler(entry)
            return

    # Commands with no argument
    if arg == 'u':
        print(colored.green('[PirateBay] URL') + ' : ' + tpb_url)
    elif arg == 'h':
        print_menu(0)
    elif arg == 'q':
        exit = True
    elif arg == 'p':
        printTopResults()
    elif arg == 's':
        query = input("Enter query : ")
        if query == '':
            query = defaultQuery
        searchAllSites(query, force_search=True)
        printTopResults()
    elif arg == 'r':
        searchAllSites(query)
        printTopResults()
    else:
        print('Invalid command!\n')

def print_menu(arg=0):
    if arg == 0:
        print('''
        ------ Help Menu -------
        Available Commands :
        1. m<result number> - Print magnet link of selected torrent
        2. c<result number> - Copy magnet link of selected torrent to clipboard
        3. d<result number> - Download torrent using default torrent client
        4. o<result number> - Open the torrent page of the selected torrent in the default browser
        5. cs<result number> - Copy magnet link and open seedr.cc
        6. p - Re-print top 10 results for the last search
        7. s - Enter a new query to search for over all available torrent websites
        8. r - Repeat last search (with same query)
        ------------------------''')
    elif arg == 1:
        print('''
        Enter 'q' to exit and 'h' to see all available commands.
        ''')

def searchAllSites(query=defaultQuery, force_search=False, quiet_mode=False):
    global results, results_rarbg, tpb_working_domain, results_tpb_condensed, results_1337x

    if force_search == True:
        results_1337x = None
        results = None
        results_tpb_condensed = None

    # RARBG and SkyTorrents permanently removed. See git history.
    results_rarbg = []

    if quiet_mode == False:
        print(colored.magenta("Searching TBP..."), end='')
    if results_tpb_condensed == None or results_tpb_condensed == []:
        tpb_working_domain = 'thepiratebay.zone'
        results_tpb_condensed = searchPirateBayCondensed(search_string=query, domain=tpb_working_domain, quiet_mode=quiet_mode)
        results = results_tpb_condensed
    if quiet_mode == False:
        print(colored.green("Done."))

    ## Search 1337x
    # Disabled: 1337x sits behind a Cloudflare managed challenge that requires
    # JS execution; no lightweight pure-Python approach bypasses it.
    # print(colored.magenta("Searching 1337x..."), end='')
    # if results_1337x == None or results_1337x == []:
    #     results_1337x = search1337x(query, quiet_mode=quiet_mode)
    # print(colored.green("Done."))
    results_1337x = []

def prettyPrintCombinedTopResults():
    global num_results
    num_results = pretty_print_top_results_piratebay(10)
    
def printTopResults():
    prettyPrintCombinedTopResults()

def convertListJSONToPureJSON(result_list): 
    # Sample JSON Structure
    # { 
    #  'count' : x,    ### Gives total number of results
    #  'results' : {'0' : {...}, {'1' : {...}, ...}   ### Stores actual results
    # }
    result_json = {'count' : '0'}
    index = 0

    if result_list != [] and result_list != None: # Create a key 'results' only if there are some results
        result_json['results'] = {}
        rj_results = result_json['results']
    
        for item in result_list:
            rj_results[str(index)] = result_list[index]
            index += 1
        result_json['count'] = str(index) # Update total number of results

    return result_json

def printResultsQuietly(as_json=False):
    global results_rarbg, results_tpb_condensed, results_1337x

    combined_json_results = {
        'rarbg': convertListJSONToPureJSON(results_rarbg),
        'tpb': convertListJSONToPureJSON(results_tpb_condensed),
        '1337x': convertListJSONToPureJSON(results_1337x),
    }

    if as_json:
        print(json.dumps(combined_json_results))
    else:
        print(combined_json_results)

if __name__ == '__main__':
    # initiate the parser
    parser = argparse.ArgumentParser()  

    # add arguments
    parser.add_argument("query", help="Specify the search query", nargs='+', default=defaultQuery)
    parser.add_argument('-q', '--quiet', help='Print output of search without any additional options', default=False, action='store_true')
    parser.add_argument('--json', help='Print results as JSON (implies --quiet)', default=False, action='store_true', dest='as_json')

    # read arguments from the command line
    args = parser.parse_args()

    if args.query:
        query = ' '.join(args.query) # converts args from list to string
    else:
        print("Please enter a valid query.")
        sys.exit(0)

    if args.quiet or args.as_json: # Continue in non-interactive mode
        searchAllSites(query, quiet_mode=True)
        printResultsQuietly(as_json=args.as_json)
    else: # Continue in interactive mode
        searchAllSites(query) # quiet_mode is off by default
        printTopResults()

        exit = False
        while(exit != True):
            print_menu(1)
            choice = input("Enter command : ")
            switch(choice)