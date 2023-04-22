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

from __future__ import print_function
from builtins import input
from builtins import str
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from clint.textui import colored
from veryprettytable import VeryPrettyTable
import requests
import re
import sys
import pyperclip
import webbrowser
import json
import humanize
import traceback
import random
import time
import argparse
import cfscrape as cfs
import traceback

defaultQuery, query = 'jason bourne', ''
results_sky = None
results_tpb_condensed = None
results_tpb_api, num_results_tpb_api = None, 0
results_1337x = None
results, results_rarbg, exit, error_detected_rarbg, error_detected_tpb = None, None, None, None, None
num_results, num_results_rarbg, num_results_sky, num_results_1337x, print_version = 0, 0, 0, 0, 1
auth_token = 'None'
app_id = 'None'
tpb_working_domain = 'tpb.tw'
rarbg_url, skytorrents_url, tpb_url, url_1337x = '', '', '', ''
tpb_retries, max_tpb_retries = 0, 3

def enum(**enums):
    """
    Lets define enums
    """
    return type('Enum', (), enums)

ORDER_BY = enum(NAME = 1,
                SIZE = 3,
                UPLOADER = 5,
                SEEDERS = 7,
                LEECHERS = 9,
                TYPE = 13,
                UPLOADED = 99)

SORT_BY_TBP = enum(NAME = 'title_asc',
                   NAME_DESC = 'title_desc',
                   SEEDS = 'seeds_asc',
                   SEEDS_DESC = 'seeds_desc',
                   LEECHERS = 'leeches_asc',
                   LEECHERS_DESC = 'leeches_desc',
                   MOST_RECENT = 'time_desc',
                   OLDEST = 'time_asc',
                   UPLOADER = 'uploader_asc',
                   UPLOADER_DESC = 'uploader_desc',
                   SIZE = 'size_asc',
                   SIZE_DESC = 'size_desc',
                   FILE_TYPE = 'category_asc',
                   FILE_TYPE_DESC = 'category_desc')

ORDER_BY_SKY = enum(RELEVANCE = 'ss',
                    SEEDS_DESC = 'ed',
                    SEEDS_ASC = 'ea',
                    PEERS_DESC = 'pd',
                    PEERS_ASC = 'pa',
                    SIZE_DESC = 'sd',
                    SIZE_ASC = 'sa',
                    NEWEST = 'ad',
                    OLDEST = 'aa')

def generateNewTorrentAPIToken(error=False, quiet_mode=False):
    global auth_token, error_detected_rarbg, app_id
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.0; WOW64; rv:24.0) Gecko/20100101 Firefox/24.0'}
    headers_safari = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15'}
    refresh_url = 'https://torrentapi.org/pubapi_v2.php?get_token=get_token&app_id=' + str(app_id)
    
    #print(f"App ID: {app_id}")
    #print(f"Token Refresh URL: {refresh_url}")
    try:
        r = requests.get(refresh_url, headers=headers_safari)
        if(str(r).split()[1][1:4] != '200'):
            if quiet_mode == False:
                print(colored.red("HTTP Response Error : %s" % str(r)))
            error_detected_rarbg = True
            return error_detected_rarbg

        auth_token = json.loads(r.text)['token']
        #print(f"Auth Token: {auth_token}")

        if error != False:
            success_string = '[RARBG] Success : Generated new token! '
            if quiet_mode == False:
                print(colored.blue(success_string))
    except requests.exceptions.ConnectionError as e:
        err_string = str(e).split(',')[0]
        if 'Connection aborted' in err_string:
            if quiet_mode == False:
                print(colored.red("Server cannot be reached. Check Internet connectivity!"))
            #sys.exit(1)
    
    #except SysCallError, e:
    #    print colored.red("SysCallError for RARBG search. Fix?")

def searchRarbg(search_string=defaultQuery, quiet_mode=False):
    global auth_token, results_rarbg, error_detected_rarbg, app_id, rarbg_url
    # API Documentaion : https://torrentapi.org/apidocs_v2.txt
    # https://torrentapi.org/pubapi_v2.php?mode=search&search_string=Suits%20S06E10&format=json_extended&ranked=0&token=7dib9orxpa&app_id=0
    # echo 'torrent-hound' | shasum -a 512
    generateNewTorrentAPIToken(quiet_mode=quiet_mode)
    #print(f"Auth Token: {auth_token}")
    if error_detected_rarbg == True:
        #print "Error detected!\n"
        return results_rarbg

    #print(f"Auth token: {auth_token.decode('utf-8')}\n")
    search_string = search_string.replace(" ", "%20")
    base_url = 'https://torrentapi.org/pubapi_v2.php?'
    new_token = 'get_token=get_token&app_id=' + str(app_id)
    search_criteria = 'mode=search&search_string=' + search_string + "&"
    options = 'format=json_extended&ranked=0&token=' + str(auth_token) + '&app_id=' + str(app_id)
    url = base_url + search_criteria + options
    rarbg_url = url
    #print(f"RARBG Search URL: {url}")

    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X x.y; rv:42.0) Gecko/20100101 Firefox/42.0'}
    # User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15
    headers_safari = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15'}

    try:
        response = requests.get(url, headers=headers_safari)
        #print(f"Response: {response}")
        rt = response.text
        #print(f"Response Text: {rt}\n")
        response_json = json.loads(rt)
        #print response_json
    except Exception as e:
        if quiet_mode == False:
            status_code = str(response).split()[1].strip('<[]>')
            if status_code == '429': # Too Many Requests
                print(colored.yellow('<HTTP 429> : Too Many Requests. Please try again after a while!'))
                print(colored.red('[RARBG] Error : ' + str(e)))
            else:
                print(colored.red('[RARBG] Error : ' + str(e)))
            #traceback.print_exc()
            
        return []
    results_rarbg = []

    error_detected_rarbg = checkResponseForErrors(response_json, quiet_mode=quiet_mode)
    if(error_detected_rarbg == False):
        results_rarbg = parse_results_rarbg(response_json, quiet_mode=quiet_mode)
    return results_rarbg

def checkResponseForErrors(response_json, quiet_mode=False):
    global results_rarbg, error_detected_rarbg, query, auth_token
    search_string = query.replace(" ", "%20")

    if 'error_code' in response_json:
        #print 'In function'
        error_string = '[RARBG] Error : ' + response_json['error']
        if quiet_mode == False:
            print(colored.magenta(error_string))
        
        if response_json['error_code'] == 4:
            generateNewTorrentAPIToken(error=True)
            results_rarbg = searchRarbg(search_string)
        # elif response_json['error_code'] == 20:
        #     print "No results found. Try different keywords!\n"
        return True #Some error detected
    else:
        return False #No errors. Print results

def parse_results_rarbg(response_json, quiet_mode=False, limit=10):
    global results_rarbg
    if error_detected_rarbg == False:
        #print len(response_json['torrent_results'])
        for post in response_json['torrent_results'][:limit]:
            res = {}
            res['name'] = post['title']
            res['link'] = post['info_page']

            temp_size = humanize.naturalsize(post['size'], binary=True, format='%.2f')
            s1 = temp_size.split('.')
            if(len(s1[0]) == 4):
                res['size'] = humanize.naturalsize(post['size'], binary=True, format='%.0f')
            elif(len(s1[1]) == 3):
                res['size'] = humanize.naturalsize(post['size'], binary=True, format='%.1f')
            else:
                res['size'] = temp_size
            #res['time'] = Implement later
            res['seeders'] = post['seeders']
            res['leechers'] = post['leechers']
            try:
                res['ratio'] = format( (float(res['seeders'])/float(res['leechers'])), '.1f' )
            except ZeroDivisionError:
                res['ratio'] = 'inf'
            res['magnet'] = post['download']
            results_rarbg.append(res)
    else:
        if quiet_mode == False:
            print("----------- " + colored.green('RARBG') + " -----------")
            print("             [No results found]                ")
        return []
    return results_rarbg

def print_top_results_rarbg(limit=10):
    global results_rarbg
    if results_rarbg != [] and results_rarbg != None:
        print('\n---------------------------------------------- ' + colored.green('RARBG') + ' ----------------------------------------------')
        print('{0} {1} {2} {3} {4} {5}'.format(colored.red('No.').ljust(3), colored.red('Torrent Name').ljust(60), colored.red('File Size').rjust(10), colored.red('Seeders').rjust(7), colored.red('Leechers').rjust(6), colored.red('Ratio').rjust(6)))
        index = 1
        for r in results_rarbg[:limit]:
            print('{0} {1} {2} {3} {4} {5}'.format(str(index).ljust(3), r['name'][:60].ljust(60), r['size'].rjust(10), str(r['seeders']).rjust(6), str(r['leechers']).rjust(6), str(r['ratio']).rjust(8)))
            index = index + 1
        print("---------------------------------------------------------------------------------------------------")
        return index - 1

def pretty_print_top_results_rarbg(limit=10):
    global results_rarbg
    table_rarbg = VeryPrettyTable(left_padding_width=0, right_padding_width=0, padding_width=0)
    no_str = str(colored.red('No'))
    name_str = str(colored.red('Torrent Name'))
    size_str = str(colored.red('Size'))
    seed_str = str(colored.red('S'))
    leech_str = str(colored.red('L'))
    ratio_str = str(colored.red('S/L'))
    table_rarbg.field_names = [no_str, name_str, size_str, seed_str, leech_str, ratio_str]

    print('\n\t\t\t\t\t\t' + colored.green('RARBG'))
    if (results_rarbg != []) and (results_rarbg != None):
        #print 'Empty table'
        #print '{0} {1} {2} {3} {4} {5}'.format(colored.red('No.').ljust(3), colored.red('Torrent Name').ljust(60), colored.red('File Size').rjust(10), colored.red('Seeders').rjust(7), colored.red('Leechers').rjust(6), colored.red('Ratio').rjust(6))
        index = 1
        for r in results_rarbg[:limit]:
            table_rarbg.add_row([index, r['name'][:57], r['size'], r['seeders'], r['leechers'], r['ratio']])
            #print '{0} {1} {2} {3} {4} {5}'.format(str(index).ljust(3), r['name'][:60].ljust(60), r['size'].rjust(10), str(r['seeders']).rjust(6), str(r['leechers']).rjust(6), str(r['ratio']).rjust(8))
            index = index + 1
        table_rarbg.align[no_str] = 'l'
        table_rarbg.align[name_str] = 'l'
        table_rarbg.align[size_str] = 'r'
        table_rarbg.align[seed_str] = 'r'
        table_rarbg.align[leech_str] = 'r'
        table_rarbg.align[ratio_str] = 'r'
        print(table_rarbg)
        return index - 1
    else:
        table_rarbg.add_row(["Null", "Null", "Null", "Null", "Null", "Null"])
        table_rarbg.align[colored.red('Torrent Name')] = 'l'
        print(table_rarbg)
        return 0

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
    soup = BeautifulSoup(response.text, 'html.parser')
    results_1337x = []
    
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
    return results_1337x

def pretty_print_top_results_1337x(limit=10):
    global results_1337x, num_results_tpb_api, num_results
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
        #index = num_results_tpb_api + 1 # Index after TBP API
        index = num_results + 1 # Index after TBP regular
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

def searchSkyTorrents(search_string=defaultQuery, domain='skytorrents.lol', order_by=ORDER_BY_SKY.RELEVANCE, quiet_mode=False, limit=10):
    global results_sky, skytorrents_url
    search_string = removeAndReplaceSpaces(search_string)
    baseURL = 'https://' + domain
    url = baseURL + '/?query=' + search_string
    skytorrents_url = url
    #url = baseURL + '/search/all/' + order_by + '/1/?l=en-us&q=' + search_string
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.0; WOW64; rv:24.0) Gecko/20100101 Firefox/24.0'}
    tbody = None
    #headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        scraper = cfs.create_scraper()
        r = scraper.get(url, headers=headers)
        soup = BeautifulSoup(r.content, "html.parser")
        #print soup
        tbody = soup.find('tbody')
        results_sky = []

        trows = tbody.findAll("tr")
        #print len(trows)
        for trow in trows[:limit]:
            res = {}
            tds = trow.findAll("td")
            #tds[0] -> Name, Magnet, Link
            res['name'] = tds[0].findAll("a")[0].contents[0]
            res['link'] = baseURL + '/' + tds[0].findAll("a")[0].attrs['href']

            if tds[0].findAll("img")[0].attrs['src'] == '/files/thumb_upm.png' and tds[0].findAll("img")[1].attrs['src'] == '/files/thumb_downm.png':
                # Both upvotes and downvotes found
                res['up'] = '{:+}'.format(int(tds[0].contents[2]))
                res['down'] = '{:+}'.format(int(tds[0].contents[4]))
            elif tds[0].findAll("img")[0].attrs['src'] == '/files/thumb_upm.png':
                # Only upvotes, no downvotes found
                res['up'] = '{:+}'.format(int(tds[0].contents[2]))
                res['down'] = '0'
            elif tds[0].findAll("img")[0].attrs['src'] == '/files/thumb_downm.png':
                # Only downvotes, no upvotes found
                res['up'] = '0'
                res['down'] = '{:+}'.format(int(tds[0].contents[2]))
            else:
                # No upvotes or downvotes found
                res['up'] = '0'
                res['down'] = '0'
            
            res['magnet'] = tds[0].findAll("a")[2].attrs['href']
            #tds[1] -> Size
            res['size'] = tds[1].contents[0].encode('utf-8')
            #tds[2] -> No. of files
            # res['num_files'] = tds[0].contents[0].encode('utf-8')
            #tds[3] -> Date added
            # res['date'] = tds[3].contents[0].encode('utf-8')
            #tds[4] -> Seeders
            res['seeders'] = tds[4].contents[0].replace(',', '')
            #tds[5] -> Leechers
            res['leechers'] = tds[5].contents[0].replace(',', '')
            try:
                res['ratio'] = format( (float(res['seeders'])/float(res['leechers'])), '.1f' )
            except ZeroDivisionError:
                res['ratio'] = 'inf'
            results_sky.append(res)

    except Exception as e:
        if quiet_mode == False:
            if tbody == None:
                print(colored.magenta("[SkyTorrents] Error : No results found"))    
            else:
                print(colored.red("[SkyTorrents] Error : Unkown problem while searching"))
                print(colored.yellow('ERR_MSG : ' + str(e)))
                #traceback.print_exc()

    return results_sky

def removeAndReplaceSpaces(string):
    if string[0] == " ":
        string = string[1:]
    return string.replace(" ", "+")

def pretty_print_top_results_skytorrents(limit=10):
    global results_sky, num_results_tpb_api, num_results
    table_skytorrents = VeryPrettyTable(left_padding_width=0, right_padding_width=0, padding_width=0)
    no_str = str(colored.red('No'))
    name_str = str(colored.red('Torrent Name'))
    size_str = str(colored.red('Size'))
    seed_str = str(colored.red('S'))
    leech_str = str(colored.red('L'))
    ratio_str = str(colored.red('S/L'))
    votes_str = str(colored.red('Votes'))
    table_skytorrents.field_names = [no_str, name_str, size_str, seed_str, leech_str, ratio_str, votes_str]

    #print '\n\t\t\t\t\t\t' + '+-----------+'
    #print '\t\t\t\t\t\t| ' + colored.green('PirateBay') + ' |'
    print('\n\t\t\t\t\t\t' + colored.green('Sky Torrents'))
    # print results
    if results_sky != [{}] and results_sky != [] and results_sky != None:
        #index = num_results_tpb_api + 1
        index = num_results + 1
        for r in results_sky[:limit]:
            try :
                table_skytorrents.add_row([index, r['name'][:57], r['size'].decode('utf-8'), r['seeders'], r['leechers'], r['ratio'], (r['up'] + '/' + r['down'])])
                index = index + 1
            except KeyError as e:
                # Fix error where {} is included in results and screws up numbering #
                if r != {}:
                    print(r)
                    print(e)
        table_skytorrents.align[no_str] = 'l'
        table_skytorrents.align[name_str] = 'l'
        table_skytorrents.align[size_str] = 'r'
        table_skytorrents.align[seed_str] = 'r'
        table_skytorrents.align[leech_str] = 'r'
        table_skytorrents.align[ratio_str] = 'r'
        table_skytorrents.align[votes_str] = 'c'
        print(table_skytorrents)
        return index - 1
    else:
        table_skytorrents.add_row(["Null", "Null", "Null", "Null", "Null", "Null", "Null"])
        #table_piratebay.align[colored.red('Torrent Name')] = 'l'
        print(table_skytorrents)
        return num_results

def searchPirateBayCondensed(search_string=defaultQuery, page=0, order_by=ORDER_BY.SEEDERS, domain='thepiratebay.org', quiet_mode=False, limit=10):
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
        trs = table.findAll("tr")
        del trs[:1]

        results_tpb_condensed = []
        #for tr in trs:
        for tr in trs[:limit]:
            tds = tr.findAll("td")

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

def searchPirateBay(search_string = defaultQuery, page = 0, order_by = ORDER_BY.UPLOADER, domain = 'thepiratebay.org', quiet_mode=False):
    """
    Searches for the given string in The Pirate Bay.
    Returns a list of dictionaries with the information of each torrent.
    """
    global tpb_working_domain, tpb_url
    baseURL = 'https://' + domain + '/s/?q='
    url = baseURL + removeAndReplaceSpaces(search_string) + '&page=0&orderby=99'
    tpb_url = url
    #print url
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.0; WOW64; rv:24.0) Gecko/20100101 Firefox/24.0'}
    try:
        r = requests.get(url, headers=headers)
        soup = BeautifulSoup(r.content, "html.parser")
        table = soup.find("table", {"id": "searchResult"})
        # print "TBP Response : \n"
        # print r.content
    except requests.exceptions.ConnectionError as e:
        #print e
        err_string = str(e).split(',')[2]
        #print err_string
        if 'Operation timed out' in err_string:
            if domain == 'thepiratebay.org':
                tpb_working_domain = alternate_domain ='piratebay.red'
                error_str = colored.yellow("[PirateBay] Error : Connection to ") + colored.magenta(domain) + colored.yellow(" timed out.\n")
                error_str += colored.yellow("Trying to connect via ") + colored.magenta(alternate_domain) + colored.yellow("...")
                if quiet_mode == False:
                    print(error_str)
                return searchPirateBay(search_string=search_string, domain='piratebay.red')
            elif domain == 'piratebay.red':
                error_str = colored.yellow("[PirateBay] Error : Connection to ") + colored.magenta(domain) + colored.yellow(" timed out.\n")
                error_str += colored.red("Exiting. Try connecting via a proxy...")
                if quiet_mode == False:
                    print(error_str)
                table = None
                #sys.exit(1)
        elif 'Connection refused' in err_string:
            if domain == 'thepiratebay.org':
                tpb_working_domain = alternate_domain = 'piratebay.red'
                error_str = colored.red("[PirateBay] Error : Connection to ") + (domain) + colored.red(" refused.\n")
                error_str += colored.red("Trying to connect via ") + (alternate_domain) + colored.red("...")
                if quiet_mode == False:
                    print(error_str)
                return searchPirateBay(search_string=search_string, domain='piratebay.red')
            elif domain == 'piratebay.red':
                error_str = colored.red("[PirateBay] Error : Connection to ") + (domain) + colored.red(" refused.\n")
                error_str += colored.red("Exiting. Try connecting via a proxy...")
                if quiet_mode == False:
                    print(error_str)
                table = None
                #sys.exit(1)
        elif 'failed to respond' in err_string:
            if domain == 'thepiratebay.org':
                tpb_working_domain = alternate_domain = 'piratebay.red'
                error_str = colored.red("[PirateBay] Error : Connection to ") + (domain) + colored.red(" is probably blocked.\n")
                error_str += colored.red("Trying to connect via ") + (alternate_domain) + colored.red("...")
                if quiet_mode == False:
                    print(error_str)
                return searchPirateBay(search_string=search_string, domain='piratebay.red')
            elif domain == 'piratebay.red':
                error_str = colored.red("[PirateBay] Error : Connection to ") + (domain) + colored.red(" refused.\n")
                error_str += colored.red("Exiting. Try connecting via a proxy...")
                if quiet_mode == False:
                    print(error_str)
                table = None
                #sys.exit(1)
        else:
            error_str = colored.red("[PirateBay] Unhandled Error : ") + colored.red(str(e)) + colored.red("\nExiting...")
            if quiet_mode == False:
                print(error_str)
            table = None
            #sys.exit(1)
    except TypeError as e:
        #print("Something's wrong...")
        table = None

    # print table
    if table == None:
        if domain == 'piratebay.red':
            error_string = str(colored.yellow('[PirateBay] Error : No results found. ')) + str(colored.magenta(domain)) + str(colored.yellow(' might be unreachable!'))
            if quiet_mode == False:
                print(error_string)
            return _parse_search_result_table(table, quiet_mode)
        else:
            tpb_working_domain = alternate_domain = 'piratebay.red'
            # print "!!!!"
            error_string = str(colored.yellow('[PirateBay] Error  : No results found. ')) + str(colored.magenta(domain)) + str(colored.yellow(' might be unreachable!'))
            error_string += str(colored.yellow('\nTrying ')) + str(colored.magenta(alternate_domain)) + str(colored.yellow('...'))
            if quiet_mode == False:
                print (error_string)
            return searchPirateBay(search_string=search_string, domain='piratebay.red')
    else:
        return _parse_search_result_table(table, quiet_mode=quiet_mode)

def _parse_search_result_table(table, quiet_mode=False, limit=10):
    if table == None:
        results = []
        return results
    trs = table.findAll("tr")
    del trs[:1]
    # print "\n'tr' tags within table : \n"
    # print trs
    results = []
    error_detected_tpb = False
    index = 1
    for tr in trs[:limit]:
        #print index
        #print tr
        index += 1
        if(error_detected_tpb == False):
            results.append(_parse_search_result_table_row(tr))
        else:
            error_string = '[PirateBay] Error  : No results found'
            if quiet_mode == False:
                print(colored.yellow(error_string))
            break
    return results

def _parse_search_result_table_row(tr):
    global error_detected_tpb, tpb_working_domain
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.0; WOW64; rv:24.0) Gecko/20100101 Firefox/24.0'}
    
    res = {}
    tds = tr.findAll("td")
    #print tds
    
    link_name = tds[1].find("a", {"class": "detLink"})
    #print "Link Name : " + str(link_name.contents)
    if link_name.contents == []:
        error_detected_tpb = True
        #print error_detected_tpb
        return {}
    else:
        res['name'] = link_name.contents[0].encode('utf-8').strip()
        res['link'] = link_name["href"].encode('utf-8')
        desc_string = tds[1].find("font").contents[0].encode('utf-8').replace("&nbsp;", " ")
        m = re.search(r"^Uploaded (Today|Y-day|\d\d-\d\d)\xc2\xa0(\d{4}|\d\d:\d\d), " + r"Size (\d+(?:.\d*)?\xc2\xa0(?:[KMG]iB))", desc_string)
        try :
            temp_size = str(m.group(3)).replace('\xc2\xa0', ' ')
            s1 = temp_size.split('.')
            #print s1
            try:
                s2 = s1[1].split(' ')
            except IndexError as e: # Special case where size is an integer (eg. s1 = 2 GiB), i.e, no decimal place
                #print 'Reached here'
                s1 = s1[0].split(' ')
                #print s1
                s2 = ['0']
                s2.append(s1[1])
                temp_size = s1[0] + '.0 ' + s1[1]
            if(len(s1[0]) == 4):
                res['size'] = s1[0] + s2[1]
            elif(len(s1[0]) == 3):
                res['size'] = s1[0] + '.' + s2[0][0] + " " + s2[1]
            else:
                res['size'] = temp_size
        except AttributeError as e:
            #print 'Reached here next'
            error_detected_tpb = True
            #print e
            #print "\nRegex misbehaving. Try running the script again!\n"
            return {}
        now = datetime.today()
        if re.match(r"\d{4}", m.group(2)) == None:
            hour =" " + m.group(2)
            if m.group(1) == "Today":
                res['time'] = datetime.strptime(
                        now.strftime("%m-%d-%Y") + hour,
                        "%m-%d-%Y %H:%M")
            elif m.group(1) == "Y-day":
                res['time'] = datetime.strptime(
                        (now + timedelta(-1)).strftime("%m-%d-%Y") + hour,
                         "%m-%d-%Y %H:%M")
            else:
                res['time'] = datetime.strptime(
                        m.group(1) + "-" + str(now.year) + hour,
                        "%m-%d-%Y %H:%M")
        else:
            res['time'] = datetime.strptime(m.group(1) + "-" + m.group(2),
                    "%m-%d-%Y")
        res['seeders'] = int(tds[2].contents[0])
        res['leechers'] = int(tds[3].contents[0])
        try:
            res['ratio'] = format( (float(res['seeders'])/float(res['leechers'])), '.1f' )
        except ZeroDivisionError:
            res['ratio'] = 'inf'
        res['magnet'] = tds[1].find("img", {"alt": "Magnet link"}).parent['href']

        # Check if magnet link was found on this page, or if need to go one level deeper
        if res['magnet'] == res['link']: # Magnet link not found
            magnet_link_page = 'https://' + tpb_working_domain + res['link']
            #print magnet_link_page
            try:
                magnet_req = requests.get(magnet_link_page, headers=headers)
                soup2 = BeautifulSoup(magnet_req.content, "html.parser")
                content = soup2.find_all(class_='download')
                res['magnet'] = content[0].contents[1].attrs['href'].encode('utf-8')
            except Exception as e:
                print(colored.red("[PirateBay] Error : Unkown problem while searching for magnet link"))
                print(colored.yellow('ERR_MSG : ' + str(e)))
        #print res
        return res

def searchPirateBayWithAPI(search_string = defaultQuery, sort_by = SORT_BY_TBP.SEEDS_DESC, domain = 'tpbc.herokuapp.com', quiet_mode=False):
    global results_tpb_api, tpb_url
    base_url = 'https://' + domain
    url = base_url + '/search/' + removeAndReplaceSpaces(search_string) + '/?sort=' + sort_by
    tpb_url = url

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.0; WOW64; rv:24.0) Gecko/20100101 Firefox/24.0'}
    
    try:
        response = requests.get(url, headers=headers)
        response_json = json.loads(response.text)
        results_tpb_api = parse_results_tpb_api(response_json, quiet_mode=quiet_mode)
    except Exception as e:
        if quiet_mode == False :
            print(colored.red("[PirateBay] : Error while searching"))
            print(colored.yellow('ERR_MSG : ' + str(e)))
        #traceback.print_exc()
    
    # try:
    #     results_tpb_api = parse_results_tpb_api(response_json)
    # except Exception, e:
    #     print colored.red("[PirateBay] : Error while parsing search results.")
    #     print colored.yellow('ERR_MSG : ' + str(e))
    
    return results_tpb_api

def parse_results_tpb_api(response_json, quiet_mode=False):
    #global results_tpb_api
    results_list = []
    if response_json == []:
        if quiet_mode == False:
            error_string = '[PirateBay] Error : No results found'
            print(colored.magenta(error_string))
        return []
    else:
        for post in response_json:
            res = {}
            res['name'] = post['title'].encode('utf-8')
            #res['link'] = ''

            temp_size = humanize.naturalsize(post['size'], binary=True, format='%.2f')
            s1 = temp_size.split('.')
            if(len(s1[0]) == 4):
                res['size'] = humanize.naturalsize(post['size'], binary=True, format='%.0f')
            else:
                res['size'] = temp_size
            #res['time'] = Implement later
            res['seeders'] = post['seeds']
            res['leechers'] = post['leeches']
            try:
                res['ratio'] = format( (float(res['seeders'])/float(res['leechers'])), '.1f' )
            except ZeroDivisionError:
                res['ratio'] = 'inf'
            res['magnet'] = post['magnet'].encode('utf-8')
            results_list.append(res)
    
    return results_list

def getQuery():
    global query
    query = input('Enter search query : ')
    return query

def print_top_results(limit=10):
    global results
    if results != [{}]:
        print('-------------------------------------------- ' + colored.green('PirateBay') + ' --------------------------------------------')
        print('{0} {1} {2} {3} {4} {5}'.format(colored.red('No.').ljust(3), colored.red('Torrent Name').ljust(60), colored.red('File Size').rjust(10), colored.red('Seeders').rjust(7), colored.red('Leechers').rjust(6), colored.red('Ratio').rjust(6)))
        index = num_results_rarbg + 1
        for r in results[:limit]:
            print('{0} {1} {2} {3} {4} {5}'.format(str(index).ljust(3), r['name'][:60].ljust(60), r['size'].rjust(11), str(r['seeders']).rjust(6), str(r['leechers']).rjust(6), str(r['ratio']).rjust(8)))
            index = index + 1
        print("---------------------------------------------------------------------------------------------------")
        return index - 1

def pretty_print_top_results_piratebay(limit=10):
    global results, num_results_rarbg
    table_piratebay = VeryPrettyTable(left_padding_width=0, right_padding_width=0, padding_width=0)
    no_str = str(colored.red('No'))
    name_str = str(colored.red('Torrent Name'))
    size_str = str(colored.red('Size'))
    seed_str = str(colored.red('S'))
    leech_str = str(colored.red('L'))
    ratio_str = str(colored.red('S/L'))
    table_piratebay.field_names = [no_str, name_str, size_str, seed_str, leech_str, ratio_str]

    print('\n\t\t\t\t\t\t' + colored.green('PirateBay'))
    # print results
    if results != [{}] and results != [] and results != None:
        index = num_results_rarbg + 1
        #print index
        #print len(results)
        for r in results[:limit]:
            try :
                #print index
                #print r
                table_piratebay.add_row([index, r['name'][:57], r['size'], r['seeders'], r['leechers'], r['ratio']])
                index = index + 1
            except KeyError as e:
                # Fix error where {} is included in results and screws up numbering #
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
        #table_piratebay.align[colored.red('Torrent Name')] = 'l'
        print(table_piratebay)
        return num_results_rarbg

def pretty_print_top_results_piratebay_api(limit=10):
    global results_tpb_api, num_results_rarbg
    table_piratebay = VeryPrettyTable(left_padding_width=0, right_padding_width=0, padding_width=0)
    no_str = str(colored.red('No'))
    name_str = str(colored.red('Torrent Name'))
    size_str = str(colored.red('Size'))
    seed_str = str(colored.red('S'))
    leech_str = str(colored.red('L'))
    ratio_str = str(colored.red('S/L'))
    table_piratebay.field_names = [no_str, name_str, size_str, seed_str, leech_str, ratio_str]

    print('\n\t\t\t\t\t\t' + colored.green('PirateBay'))
    if results_tpb_api != [] and results_tpb_api != None:
        index = num_results_rarbg + 1
        for r in results_tpb_api[:limit]:
            try :
                table_piratebay.add_row([index, r['name'][:57], r['size'], r['seeders'], r['leechers'], r['ratio']])
                index = index + 1
            except KeyError as e:
                # Fix error where {} is included in results and screws up numbering #
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
        #table_piratebay.align[colored.red('Torrent Name')] = 'l'
        print(table_piratebay)
        return num_results_rarbg

def switch(arg, tpb_api=False):
    global results, exit, defaultQuery, num_results, query, num_results_rarbg, results_rarbg, print_version, tpb_working_domain, results_tpb_api, num_results_tpb_api, results_1337x, num_results_1337x, rarbg_url, skytorrents_url, tpb_url, url_1337x
    if ('c' in arg) and ('s' not in arg) and ('z' not in arg):
        try:
            resNum = int(re.search(r'\d+', arg).group())
            if resNum <= 0 or resNum > num_results_1337x:
                print('Invalid command!\n')
            else:
                if tpb_api == True:
                    if resNum <= num_results_rarbg :
                        mLink = results_rarbg[resNum-1]['magnet']
                    elif resNum > num_results_rarbg and resNum <= num_results_tpb_api:
                        mLink = results_tpb_api[(resNum-1)-num_results_rarbg]['magnet']
                    else:
                        #mLink = results_sky[(resNum-1)-num_results_tpb_api]['magnet']
                        mLink = results_1337x[(resNum-1)-num_results_tpb_api]['magnet']
                else:
                    if resNum <= num_results_rarbg :
                        mLink = results_rarbg[resNum-1]['magnet']
                    elif resNum > num_results_rarbg and resNum <= num_results:
                        mLink = results[(resNum-1)-num_results_rarbg]['magnet']
                    else:
                        #mLink = results_sky[(resNum-1)-num_results]['magnet']
                        mLink = results_1337x[(resNum-1)-num_results]['magnet']
                pyperclip.copy(str(mLink))
                print('Magnet link copied to clipboard!')
        except AttributeError:
            print('Enter a valid torrent number as well!')
    elif ('cs' in arg) and ('z' not in arg):
        try:
            resNum = int(re.search(r'\d+', arg).group())
            if resNum <= 0 or resNum > num_results_1337x:
                print('Invalid command!\n')
            else:
                if tpb_api == True:
                    if resNum <= num_results_rarbg :
                        mLink = results_rarbg[resNum-1]['magnet']
                    elif resNum > num_results_rarbg and resNum <= num_results_tpb_api:
                        mLink = results_tpb_api[(resNum-1)-num_results_rarbg]['magnet']
                    else:
                        #mLink = results_sky[(resNum-1)-num_results_tpb_api]['magnet']
                        mLink = results_1337x[(resNum-1)-num_results_tpb_api]['magnet']
                else:
                    if resNum <= num_results_rarbg :
                        mLink = results_rarbg[resNum-1]['magnet']
                    elif resNum > num_results_rarbg and resNum <= num_results:
                        mLink = results[(resNum-1)-num_results_rarbg]['magnet']
                    else:
                        #mLink = results_sky[(resNum-1)-num_results]['magnet']
                        mLink = results_1337x[(resNum-1)-num_results]['magnet']
                pyperclip.copy(str(mLink))
                webbrowser.open('https://www.seedr.cc', new=2)
                print('Seedr.cc opened and Magnet link copied to clipboard!')
        except AttributeError:
            print('Enter a valid torrent number as well!')
    elif 'cz' in arg:
        try:
            resNum = int(re.search(r'\d+', arg).group())
            if resNum <= 0 or resNum > num_results_1337x:
                print('Invalid command!\n')
            else:
                if tpb_api == True:
                    if resNum <= num_results_rarbg :
                        mLink = results_rarbg[resNum-1]['magnet']
                    elif resNum > num_results_rarbg and resNum <= num_results_tpb_api:
                        mLink = results_tpb_api[(resNum-1)-num_results_rarbg]['magnet']
                    else:
                        #mLink = results_sky[(resNum-1)-num_results_tpb_api]['magnet']
                        mLink = results_1337x[(resNum-1)-num_results_tpb_api]['magnet']
                else:
                    if resNum <= num_results_rarbg :
                        mLink = results_rarbg[resNum-1]['magnet']
                    elif resNum > num_results_rarbg and resNum <= num_results:
                        mLink = results[(resNum-1)-num_results_rarbg]['magnet']
                    else:
                        #mLink = results_sky[(resNum-1)-num_results]['magnet']
                        mLink = results_1337x[(resNum-1)-num_results]['magnet']
                pyperclip.copy(str(mLink))
                webbrowser.open('https://zbigz.unihax.in/', new=2)
                print('zbigz opened and Magnet link copied to clipboard!')
        except AttributeError:
            print('Enter a valid torrent number as well!')
    elif 'm' in arg:
        try:
            resNum = int(re.search(r'\d+', arg).group())
            if resNum <= 0 or resNum > num_results_1337x:
                print('Invalid command\n')
            else:
                if tpb_api == True:
                    if resNum <= num_results_rarbg :
                        mLink = results_rarbg[resNum-1]['magnet']
                    elif resNum > num_results_rarbg and resNum <= num_results_tpb_api:
                        mLink = results_tpb_api[(resNum-1)-num_results_rarbg]['magnet']
                    else:
                        #mLink = results_sky[(resNum-1)-num_results_tpb_api]['magnet']
                        mLink = results_1337x[(resNum-1)-num_results_tpb_api]['magnet']
                else:
                    if resNum <= num_results_rarbg :
                        mLink = results_rarbg[resNum-1]['magnet']
                    elif resNum > num_results_rarbg and resNum <= num_results:
                        mLink = results[(resNum-1)-num_results_rarbg]['magnet']
                    else:
                        #mLink = results_sky[(resNum-1)-num_results]['magnet']
                        mLink = results_1337x[(resNum-1)-num_results]['magnet']
                print("\nMagnet Link : \n" + mLink)
        except AttributeError:
            print('Enter a valid torrent number as well!')
    elif 'd' in arg:
        try:
            resNum = int(re.search(r'\d+', arg).group())
            if resNum <= 0 or resNum > num_results_1337x:
                print('Invalid command!\n')
            else:
                if tpb_api == True:
                    if resNum <= num_results_rarbg :
                        mLink = results_rarbg[resNum-1]['magnet']
                    elif resNum > num_results_rarbg and resNum <= num_results_tpb_api:
                        mLink = results_tpb_api[(resNum-1)-num_results_rarbg]['magnet']
                    else:
                        #mLink = results_sky[(resNum-1)-num_results_tpb_api]['magnet']
                        mLink = results_1337x[(resNum-1)-num_results_tpb_api]['magnet']
                else:
                    if resNum <= num_results_rarbg :
                        mLink = results_rarbg[resNum-1]['magnet']
                    elif resNum > num_results_rarbg and resNum <= num_results:
                        mLink = results[(resNum-1)-num_results_rarbg]['magnet']
                    else:
                        #mLink = results_sky[(resNum-1)-num_results]['magnet']
                        mLink = results_1337x[(resNum-1)-num_results]['magnet']
                webbrowser.open(mLink, new=2)
                print('Magnet link sent to default torrent client!')
        except AttributeError:
            print('Enter a valid torrent number as well!')
    elif 'o' in arg:
        try:
            resNum = int(re.search(r'\d+', arg).group())
            #print("resNum : %d" % resNum)
            if resNum <= 0 or resNum > num_results_1337x:
                print('Invalid command!\n')
            else:
                if tpb_api == True:
                    if resNum <= num_results_rarbg :
                        tLink = results_rarbg[resNum-1]['link']
                        #print("resNum(%d) <= num_results_rarbg(%d)" % (resNum, results_rarbg))
                    elif resNum > num_results_rarbg and resNum <= num_results_tpb_api:
                        tLink = "https://" + tpb_working_domain + results_tpb_api[(resNum-1)-num_results_rarbg]['link']
                        #print("resNum(%d) > num_results_rarbg(%d) and resNum(%d) <= (num_results_rarbg(%d)+num_results(%d))" % (resNum, num_results_rarbg, resNum, num_results_rarbg, num_results))
                    else:
                        #tLink = results_sky[(resNum-1)-num_results_tpb_api]['link']
                        #print("Reached SkyTorrents. Link : %s" % tLink)
                        tLink = results_1337x[(resNum-1)-num_results_tpb_api]['link']
                else:
                    if resNum <= num_results_rarbg :
                        tLink = results_rarbg[resNum-1]['link']
                    elif resNum > num_results_rarbg and resNum <= num_results:
                        #tLink = "https://" + tpb_working_domain + results[(resNum-1)-num_results_rarbg]['link']
                        tLink = results[(resNum-1)-num_results_rarbg]['link']
                    else:
                        #tLink = results_sky[(resNum-1)-num_results]['link']
                        tLink = results_1337x[(resNum-1)-num_results]['link']
                #webbrowser.get('chrome').open(tLink, new=2)
                webbrowser.open(tLink, new=2)
                print('Torrent page opened in default browser!')
        except AttributeError:
            print('Enter a valid torrent number as well!')
    elif arg == 'u':
        print(colored.green('[RARBG] URL') + ' : ' + rarbg_url)
        print(colored.green('[PirateBay] URL') + ' : ' + tpb_url)
        print(colored.green('[SkyTorrents] URL') + ' : ' + url_1337x)
    elif arg == 'h':
        print_menu(0)
    elif arg == 'q':
        exit = True
    elif 'p' in arg:
        try:
            resNum = int(re.search(r'\d+', arg).group())
            if resNum == 0:
                printTopResults(resNum)
            elif resNum == 1:
                printTopResults(resNum)
            else:
                print("Not a valid option!")
        except AttributeError:
            if arg == 'p':
                printTopResults(print_version)
            else:
                print("Not a valid command!")
    elif arg == 's':
        query = input("Enter query : ")
        if query == '':
            query = defaultQuery
        searchAllSites(query, force_search=True)
        printTopResults(print_version)
    elif arg == 'r':
        searchAllSites(query)
        printTopResults(print_version)
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
        6. cz<result number> - Copy magnet link and open zbigz
        7. p[optional:<choice>] - Print top 10 results from each website for the given query
            <choice> : [{default : 1}, {0 : Print formatted result}, {1 : Pretty print results}]
        8. s - Enter a new query to search for over all avilable torrent websites
        9. r - Repeat last search (with same query)
        ------------------------''')
    elif arg == 1:
        print('''
        Enter 'q' to exit and 'h' to see all available commands.
        ''')

def searchAllSites(query=defaultQuery, force_search=False, quiet_mode=False):
    global results, results_rarbg, results_sky, results_tpb_api, tpb_retries, max_tpb_retries, tpb_working_domain, results_tpb_condensed, results_1337x
    #results = searchPirateBay(query, domain='pirateproxy.cam')
    #results = searchPirateBay(query)

    if force_search == True:
        results_rarbg = None
        results_tpb_api = None
        results_sky = None
        results_1337x = None
        results = None
        results_tpb_condensed = None

    print(colored.magenta("Searching RARBG..."), end='')
    if results_rarbg == None or results_rarbg == []:
        results_rarbg = searchRarbg(query, quiet_mode=quiet_mode)
    print(colored.green("Done."))
    #     print 'R searching...'
    # else:
    #     print 'R not searching...'
    # print 'Results R : '
    # print results_rarbg

    # if results_tpb_api == None or results_tpb_api == []:
    #     if tpb_retries < max_tpb_retries:
    #         results_tpb_api = searchPirateBayWithAPI(query, quiet_mode=quiet_mode)
    #         results = results_tpb_api
    #         tpb_retries += 1
    #     else:
    #         results_tpb_api = searchPirateBay(query, quiet_mode=quiet_mode)
    #         results = results_tpb_api

    #     print 'P searching...'
    # else:
    #     print 'P not searching...'
    # print 'Results P : '
    # print results_tpb_api
    
    # if results == None or results == []:
    #     tpb_working_domain = 'thepiratebay.zone'
    #     results = searchPirateBay(query, quiet_mode=quiet_mode, domain=tpb_working_domain)
    # #     #print results

    print(colored.magenta("Searching TBP..."), end='')
    if results_tpb_condensed == None or results_tpb_condensed == []:
        tpb_working_domain = 'thepiratebay.zone'
        results_tpb_condensed = searchPirateBayCondensed(search_string=query, domain=tpb_working_domain, quiet_mode=quiet_mode)
        results = results_tpb_condensed
    print(colored.green("Done."))
    #     print('P searching...')
    # else:
    #     print('P not searching...')
    # print(f'Results P: {results_tpb_condensed}')

    # if results_sky == None or results_sky == []:
    #     results_sky = searchSkyTorrents(query, quiet_mode=quiet_mode)
    # #     print 'S searching...'
    # else:
    #     print 'S not searching...'
    # print 'Results S : '
    # print results_sky

    print(colored.magenta("Searching 1337x..."), end='')
    if results_1337x == None or results_1337x == []:
        results_1337x = search1337x(query, quiet_mode=quiet_mode)
    print(colored.green("Done."))

def printCombinedTopResults():
    global num_results, num_results_rarbg
    num_results_rarbg = print_top_results_rarbg(10)
    num_results = print_top_results(10)

def prettyPrintCombinedTopResults():
    global num_results, num_results_rarbg, num_results_sky, num_results_tpb_api, num_results_1337x
    num_results_rarbg = pretty_print_top_results_rarbg(10)
    num_results = pretty_print_top_results_piratebay(10)
    #num_results_tpb_api = pretty_print_top_results_piratebay_api(10)
    #num_results = num_results_tpb_api

    #num_results_sky = pretty_print_top_results_skytorrents(10)
    num_results_1337x = pretty_print_top_results_1337x(10)
    
def printTopResults(version=1):
    if version == 0:
        printCombinedTopResults()
    elif version == 1:
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

def printResultsQuietly():
    global results_rarbg, results_tpb_api, results_sky, results_1337x

    results_json_rarbg = convertListJSONToPureJSON(results_rarbg)
    results_json_tpb = convertListJSONToPureJSON(results_tpb_api)
    #results_json_sky = convertListJSONToPureJSON(results_sky)
    results_json_1337x = convertListJSONToPureJSON(results_1337x)
    #print results_json_tpb

    combined_json_results = {}
    combined_json_results['rarbg'] = results_json_rarbg
    combined_json_results['tpb'] = results_json_tpb
    #combined_json_results['sky'] = results_json_sky
    combined_json_results['1337x'] = results_json_1337x

    print(combined_json_results)

def generateAppID(version=-1):
    if version == 0: # Product of 3 random numbers
        x, y, z = random.randint(1, 100), random.randint(1, 100), random.randint(1, 100)
        app_id = x * y * z
    else : # Hash current epoch time
        epoch_time = time.time()
        app_id = hash(epoch_time)
    return app_id

if __name__ == '__main__':
    # initiate the parser
    parser = argparse.ArgumentParser()  

    # add arguments
    parser.add_argument("query", help="Specify the search query", nargs='+', default=defaultQuery)
    parser.add_argument('-q', '--quiet', help='Print output of search without any additional options', default=False, action='store_true')

    # read arguments from the command line
    args = parser.parse_args()

    if args.query:  
        #print("The query is :  %s\n" % (' '.join(args.query)))
        print_version = 1
        app_id = generateAppID()
        query = ' '.join(args.query) # converts args from list to string
    else:
        print("Please enter a valid query.")
        sys.exit(0)

    if args.quiet: # Continue in non-interactive mode
        #print("Result will be printed quiety...")
        searchAllSites(query, quiet_mode=True)
        printResultsQuietly()
    else: # Continue in interactive mode
        searchAllSites(query) # quiet_mode is off by default
        printTopResults(print_version)
        
        exit = False
        while(exit != True):
            print_menu(1)
            choice = input("Enter command : ")
            switch(choice, tpb_api=False)