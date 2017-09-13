#!/usr/bin/env python
# @author : Yashovardhan Sharma
# @github : github.com/baddymaster

#   <Torrent Hound - Search torrents from multiple websites via the CLI.>
#    Copyright (C) <2017>  <Yashovardhan Sharma>
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

defaultQuery, query = 'jason bourne', ''
results_sky = None
results, results_rarbg, exit, error_detected_rarbg, error_detected_tpb = None, None, None, None, None
num_results, num_results_rarbg, num_results_sky, print_version = 0, 0, 0, 1
auth_token = 'None'
tpb_working_domain = 'thepiratebay.org'

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

ORDER_BY_SKY = enum(RELEVANCE = 'ss',
                    SEEDS_DESC = 'ed',
                    SEEDS_ASC = 'ea',
                    PEERS_DESC = 'pd',
                    PEERS_ASC = 'pa',
                    SIZE_DESC = 'sd',
                    SIZE_ASC = 'sa',
                    NEWEST = 'ad',
                    OLDEST = 'aa')

def generateNewTorrentAPIToken(error=False):
    global auth_token
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.0; WOW64; rv:24.0) Gecko/20100101 Firefox/24.0'}
    refresh_url = 'https://torrentapi.org/pubapi_v2.php?get_token=get_token'
    try:
        auth_token = json.loads(requests.get(refresh_url, headers=headers).text)['token'].encode('utf-8')
        if error != False:
            success_string = '[RARBG] Success : Generated new token! '
            print colored.blue(success_string)
    except requests.exceptions.ConnectionError, e:
        err_string = str(e).split(',')[0]
        if 'Connection aborted' in err_string:
            print colored.red("Server cannot be reached. Check Internet connectivity!")
            sys.exit(1)
    except SysCallError, e:
        print colored.red("SysCallError for RARBG search. Fix?")

def searchRarbg(search_string=defaultQuery):
    global auth_token, results_rarbg, error_detected_rarbg
    # API Documentaion : https://torrentapi.org/apidocs_v2.txt
    # https://torrentapi.org/pubapi_v2.php?mode=search&search_string=Suits%20S06E10&format=json_extended&ranked=0&token=cy6xjhtmev
    generateNewTorrentAPIToken()
    search_string = search_string.replace(" ", "%20")
    base_url = 'https://torrentapi.org/pubapi_v2.php?'
    new_token = 'get_token=get_token'
    search_criteria = 'mode=search&search_string=' + search_string + "&"
    options = 'format=json_extended&ranked=0&token=' + auth_token
    url = base_url + search_criteria + options
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.0; WOW64; rv:24.0) Gecko/20100101 Firefox/24.0'}
    response = requests.get(url, headers=headers)
    response_json = json.loads(response.text)
    #print response_json
    results_rarbg = []

    error_detected_rarbg = checkResponseForErrors(response_json)
    if(error_detected_rarbg == False):
        results_rarbg = parse_results_rarbg(response_json)
    return results_rarbg

def checkResponseForErrors(response_json):
    global results_rarbg, error_detected_rarbg, query, auth_token
    search_string = query.replace(" ", "%20")

    if 'error_code' in response_json:
        error_string = '[RARBG] Error ' + str(response_json['error_code']) + " : " + response_json['error']
        print colored.yellow(error_string)
        if response_json['error_code'] == 4:
            generateNewTorrentAPIToken(error=True)
            results_rarbg = searchRarbg(search_string)
        # elif response_json['error_code'] == 20:
        #     print "No results found. Try different keywords!\n"
        return True #Some error detected
    else:
        return False #No errors. Print results

def parse_results_rarbg(response_json):
    global results_rarbg
    if error_detected_rarbg == False:
        for post in response_json['torrent_results']:
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
                res['ratio'] = float('inf')
            res['magnet'] = post['download']
            results_rarbg.append(res)
    else:
        print "----------- " + colored.green('RARBG') + " -----------"
        print "             [No results found]                "
        return []
    return results_rarbg

def print_top_results_rarbg(limit=10):
    global results_rarbg
    if results_rarbg != [] and results_rarbg != None:
        print '\n---------------------------------------------- ' + colored.green('RARBG') + ' ----------------------------------------------'
        print '{0} {1} {2} {3} {4} {5}'.format(colored.red('No.').ljust(3), colored.red('Torrent Name').ljust(60), colored.red('File Size').rjust(10), colored.red('Seeders').rjust(7), colored.red('Leechers').rjust(6), colored.red('Ratio').rjust(6))
        index = 1
        for r in results_rarbg[:limit]:
            print '{0} {1} {2} {3} {4} {5}'.format(str(index).ljust(3), r['name'][:60].ljust(60), r['size'].rjust(10), str(r['seeders']).rjust(6), str(r['leechers']).rjust(6), str(r['ratio']).rjust(8))
            index = index + 1
        print "---------------------------------------------------------------------------------------------------"
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

    print '\n\t\t\t\t\t\t' + colored.green('RARBG')
    if results_rarbg != []:
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
        print table_rarbg
        return index - 1
    else:
        table_rarbg.add_row(["Null", "Null", "Null", "Null", "Null", "Null"])
        table_rarbg.align[colored.red('Torrent Name')] = 'l'
        print table_rarbg
        return 0

def searchSkyTorrents(search_string=defaultQuery, domain='skytorrents.in', order_by=ORDER_BY_SKY.RELEVANCE):
    global results_sky
    search_string = removeAndReplaceSpaces(search_string)
    baseURL = 'https://www.' + domain
    url = baseURL + '/search/all/' + order_by + '/1/?l=en-us&q=' + search_string
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.0; WOW64; rv:24.0) Gecko/20100101 Firefox/24.0'}
    try:
        r = requests.get(url, headers=headers)
        soup = BeautifulSoup(r.content, "html.parser")
        table = soup.find("table")
        results_sky = []

        trows = table.findAll("tr")
        del trows[:1]
        for trow in trows:
            res = {}
            tds = trow.findAll("td")
            #tds[0] -> Name, Magnet, Link
            res['name'] = tds[0].findAll("a")[0].contents[0].encode('utf-8')
            res['link'] = baseURL + tds[0].findAll("a")[0].attrs['href'].encode('utf-8')
            res['magnet'] = tds[0].findAll("a")[1].attrs['href'].encode('utf-8')
            #tds[1] -> Size
            res['size'] = tds[1].contents[0].encode('utf-8')
            #tds[2] -> No. of files
            # res['num_files'] = tds[0].contents[0].encode('utf-8')
            #tds[3] -> Date added
            # res['date'] = tds[3].contents[0].encode('utf-8')
            #tds[4] -> Seeders
            res['seeders'] = tds[4].contents[0].encode('utf-8')
            #tds[5] -> Leechers
            res['leechers'] = tds[5].contents[0].encode('utf-8')
            try:
                res['ratio'] = format( (float(res['seeders'])/float(res['leechers'])), '.1f' )
            except ZeroDivisionError:
                res['ratio'] = float('inf')
            results_sky.append(res)

    except Exception, e:
        print("Oops...Error while searching Skytorrents.")
        print('ERR_MSG : ' + str(e))
    return results_sky

def removeAndReplaceSpaces(str):
    return str.replace(" ", "+")

def pretty_print_top_results_skytorrents(limit=10):
    global results_sky
    table_skytorrents = VeryPrettyTable(left_padding_width=0, right_padding_width=0, padding_width=0)
    no_str = str(colored.red('No'))
    name_str = str(colored.red('Torrent Name'))
    size_str = str(colored.red('Size'))
    seed_str = str(colored.red('S'))
    leech_str = str(colored.red('L'))
    ratio_str = str(colored.red('S/L'))
    table_skytorrents.field_names = [no_str, name_str, size_str, seed_str, leech_str, ratio_str]

    #print '\n\t\t\t\t\t\t' + '+-----------+'
    #print '\t\t\t\t\t\t| ' + colored.green('PirateBay') + ' |'
    print '\n\t\t\t\t\t\t' + colored.green('Sky Torrents')
    # print results
    if results_sky != [{}] and results_sky != [] and results_sky != None:
        index = num_results + 1
        for r in results_sky[:limit]:
            try :
                table_skytorrents.add_row([index, r['name'][:57], r['size'], r['seeders'], r['leechers'], r['ratio']])
                index = index + 1
            except KeyError, e:
                # Fix error where {} is included in results and screws up numbering #
                if r != {}:
                    print r
                    print e
        table_skytorrents.align[no_str] = 'l'
        table_skytorrents.align[name_str] = 'l'
        table_skytorrents.align[size_str] = 'r'
        table_skytorrents.align[seed_str] = 'r'
        table_skytorrents.align[leech_str] = 'r'
        table_skytorrents.align[ratio_str] = 'r'
        print table_skytorrents
        return index - 1
    else:
        table_skytorrents.add_row(["Null", "Null", "Null", "Null", "Null", "Null"])
        #table_piratebay.align[colored.red('Torrent Name')] = 'l'
        print table_skytorrents
        return num_results

def searchPirateBay(search_string=defaultQuery, page = 0, order_by = ORDER_BY.UPLOADER, domain='thepiratebay.org'):
    """
    Searches for the given string in The Pirate Bay.
    Returns a list of dictionaries with the information of each torrent.
    """
    global tpb_working_domain
    baseURL = 'https://' + domain + '/s/?q='
    url = baseURL + search_string + '&page=0&orderby=99'
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.0; WOW64; rv:24.0) Gecko/20100101 Firefox/24.0'}
    try:
        r = requests.get(url, headers=headers)
        soup = BeautifulSoup(r.content, "html.parser")
        table = soup.find("table", {"id": "searchResult"})
        # print "TBP Response : \n"
        # print r.content
    except requests.exceptions.ConnectionError, e:
        #print e
        err_string = str(e).split(',')[2]
        #print err_string
        if 'Operation timed out' in err_string:
            if domain == 'thepiratebay.org':
                tpb_working_domain = alternate_domain ='piratebay.red'
                error_str = colored.yellow("[PirateBay] Error : Connection to ") + colored.magenta(domain) + colored.yellow(" timed out.\n")
                error_str += colored.yellow("Trying to connect via ") + colored.magenta(alternate_domain) + colored.yellow("...")
                print error_str
                return searchPirateBay(search_string=search_string, domain='piratebay.red')
            elif domain == 'piratebay.red':
                error_str = colored.yellow("[PirateBay] Error : Connection to ") + colored.magenta(domain) + colored.yellow(" timed out.\n")
                error_str += colored.red("Exiting. Try connecting via a proxy...")
                print error_str
                sys.exit(1)
        elif 'Connection refused' in err_string:
            if domain == 'thepiratebay.org':
                tpb_working_domain = alternate_domain = 'piratebay.red'
                error_str = colored.red("[PirateBay] Error : Connection to ") + (domain) + colored.red(" refused.\n")
                error_str += colored.red("Trying to connect via ") + (alternate_domain) + colored.red("...")
                print error_str
                return searchPirateBay(search_string=search_string, domain='piratebay.red')
            elif domain == 'piratebay.red':
                error_str = colored.red("[PirateBay] Error : Connection to ") + (domain) + colored.red(" refused.\n")
                error_str += colored.red("Exiting. Try connecting via a proxy...")
                print error_str
                sys.exit(1)
        elif 'failed to respond' in err_string:
            if domain == 'thepiratebay.org':
                tpb_working_domain = alternate_domain = 'piratebay.red'
                error_str = colored.red("[PirateBay] Error : Connection to ") + (domain) + colored.red(" is probably blocked.\n")
                error_str += colored.red("Trying to connect via ") + (alternate_domain) + colored.red("...")
                print error_str
                return searchPirateBay(search_string=search_string, domain='piratebay.red')
            elif domain == 'piratebay.red':
                error_str = colored.red("[PirateBay] Error : Connection to ") + (domain) + colored.red(" refused.\n")
                error_str += colored.red("Exiting. Try connecting via a proxy...")
                print error_str
                sys.exit(1)
        else:
            error_str = colored.red("[PirateBay] Unhandled Error : ") + colored.red(str(e)) + colored.red("\nExiting...")
            print error_str
            sys.exit(1)
    except TypeError, e:
        #print("Something's wrong...")
        table = None

    # print table
    if table == None:
        if domain == 'piratebay.red':
            error_string = str(colored.yellow('[PirateBay] Error : No results found. ')) + str(colored.magenta(domain)) + str(colored.yellow(' might be unreachable!'))
            print error_string
            return _parse_search_result_table(table)
        else:
            tpb_working_domain = alternate_domain = 'piratebay.red'
            # print "!!!!"
            error_string = str(colored.yellow('[PirateBay] Error  : No results found. ')) + str(colored.magenta(domain)) + str(colored.yellow(' might be unreachable!'))
            error_string += str(colored.yellow('\nTrying ')) + str(colored.magenta(alternate_domain)) + str(colored.yellow('...'))
            print (error_string)
            return searchPirateBay(search_string=search_string, domain='piratebay.red')
    else:
        return _parse_search_result_table(table)

def _parse_search_result_table(table):
    if table == None:
        results = []
        return results
    trs = table.findAll("tr")
    del trs[:1]
    # print "\n'tr' tags within table : \n"
    # print trs
    results = []
    error_detected_tpb = False
    for tr in trs:
        if(error_detected_tpb == False):
            results.append(_parse_search_result_table_row(tr))
        else:
            error_string = '[PirateBay] Error  : No results found'
            print colored.yellow(error_string)
            break
    return results

def _parse_search_result_table_row(tr):
    global error_detected_tpb
    res = {}
    tds = tr.findAll("td")
    # print tds
    link_name = tds[1].find("a", {"class": "detLink"})
    # print "Link Name : " + str(link_name.contents)
    if link_name.contents == []:
        error_detected_tpb = True
        return {}
    else:
        res['name'] = link_name.contents[0].encode('utf-8').strip()
        res['link'] = link_name["href"].encode('utf-8')
        desc_string = tds[1].find("font").contents[0].encode('utf-8').replace("&nbsp;", " ")
        m = re.search(r"^Uploaded (Today|Y-day|\d\d-\d\d)\xc2\xa0(\d{4}|\d\d:\d\d), " + r"Size (\d+(?:.\d*)?\xc2\xa0(?:[KMG]iB))", desc_string)
        try :
            temp_size = str(m.group(3)).replace('\xc2\xa0', ' ')
            s1 = temp_size.split('.')
            try:
                s2 = s1[1].split(' ')
            except IndexError, e: # Special case where size is an integer (eg. s1 = 2 GiB), i.e, no decimal place
                s1 = s1.split(' ')
                s2 = ['0']
                s2.append(s1[1])
                temp_size = s1[0] + '.0 ' + s1[1]
            if(len(s1[0]) == 4):
                res['size'] = s1[0] + s2[1]
            elif(len(s1[0]) == 3):
                res['size'] = s1[0] + '.' + s2[0][0] + " " + s2[1]
            else:
                res['size'] = temp_size
        except AttributeError, e:
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
            res['ratio'] = float('inf')
        res['magnet'] = tds[1].find("img", {"alt": "Magnet link"}).parent['href']
        return res

def getQuery():
    global query
    query = raw_input('Enter search query : ')
    return query

def print_top_results(limit=10):
    global results
    if results != [{}]:
        print '-------------------------------------------- ' + colored.green('PirateBay') + ' --------------------------------------------'
        print '{0} {1} {2} {3} {4} {5}'.format(colored.red('No.').ljust(3), colored.red('Torrent Name').ljust(60), colored.red('File Size').rjust(10), colored.red('Seeders').rjust(7), colored.red('Leechers').rjust(6), colored.red('Ratio').rjust(6))
        index = num_results_rarbg + 1
        for r in results[:limit]:
            print '{0} {1} {2} {3} {4} {5}'.format(str(index).ljust(3), r['name'][:60].ljust(60), r['size'].rjust(11), str(r['seeders']).rjust(6), str(r['leechers']).rjust(6), str(r['ratio']).rjust(8))
            index = index + 1
        print "---------------------------------------------------------------------------------------------------"
        return index - 1

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

    #print '\n\t\t\t\t\t\t' + '+-----------+'
    #print '\t\t\t\t\t\t| ' + colored.green('PirateBay') + ' |'
    print '\n\t\t\t\t\t\t' + colored.green('PirateBay')
    # print results
    if results != [{}] and results != [] and results != None:
        index = num_results_rarbg + 1
        for r in results[:limit]:
            try :
                table_piratebay.add_row([index, r['name'][:57], r['size'], r['seeders'], r['leechers'], r['ratio']])
                index = index + 1
            except KeyError, e:
                # Fix error where {} is included in results and screws up numbering #
                if r != {}:
                    print r
                    print e
        table_piratebay.align[no_str] = 'l'
        table_piratebay.align[name_str] = 'l'
        table_piratebay.align[size_str] = 'r'
        table_piratebay.align[seed_str] = 'r'
        table_piratebay.align[leech_str] = 'r'
        table_piratebay.align[ratio_str] = 'r'
        print table_piratebay
        return index - 1
    else:
        table_piratebay.add_row(["Null", "Null", "Null", "Null", "Null", "Null"])
        #table_piratebay.align[colored.red('Torrent Name')] = 'l'
        print table_piratebay
        return num_results_rarbg

def switch(arg):
    global results, exit, defaultQuery, num_results, query, num_results_rarbg, results_rarbg, print_version, tpb_working_domain
    if 'c' in arg and 's' not in arg:
        try:
            resNum = int(re.search(r'\d+', arg).group())
            if resNum <= 0 or resNum > num_results_sky:
                print 'Invalid command!\n'
            else:
                if resNum <= num_results_rarbg :
                    mLink = results_rarbg[resNum-1]['magnet']
                elif resNum > num_results_rarbg and resNum <= num_results:
                    mLink = results[(resNum-1)-num_results_rarbg]['magnet']
                else:
                    mLink = results_sky[(resNum-1)-num_results]['magnet']
                pyperclip.copy(mLink)
                print 'Magnet link copied to clipboard!'
        except AttributeError:
            print 'Enter a valid torrent number as well!'
    elif 'cs' in arg:
        try:
            resNum = int(re.search(r'\d+', arg).group())
            if resNum <= 0 or resNum > num_results_sky:
                print 'Invalid command!\n'
            else:
                if resNum <= num_results_rarbg :
                    mLink = results_rarbg[resNum-1]['magnet']
                elif resNum > num_results_rarbg and resNum <= num_results:
                    mLink = results[(resNum-1)-num_results_rarbg]['magnet']
                else:
                    mLink = results_sky[(resNum-1)-num_results]['magnet']
                pyperclip.copy(mLink)
                webbrowser.open('https://www.seedr.cc', new=2)
                print 'Seedr.cc opened and Magnet link copied to clipboard!'
        except AttributeError:
            print 'Enter a valid torrent number as well!'
    elif 'cz' in arg:
        try:
            resNum = int(re.search(r'\d+', arg).group())
            if resNum <= 0 or resNum > num_results_sky:
                print 'Invalid command!\n'
            else:
                if resNum <= num_results_rarbg :
                    mLink = results_rarbg[resNum-1]['magnet']
                elif resNum > num_results_rarbg and resNum <= num_results:
                    mLink = results[(resNum-1)-num_results_rarbg]['magnet']
                else:
                    mLink = results_sky[(resNum-1)-num_results]['magnet']
                pyperclip.copy(mLink)
                webbrowser.open('https://zbigz.unihax.in/', new=2)
                print 'zbigz opened and Magnet link copied to clipboard!'
        except AttributeError:
            print 'Enter a valid torrent number as well!'
    elif 'm' in arg:
        try:
            resNum = int(re.search(r'\d+', arg).group())
            if resNum <= 0 or resNum > num_results_sky:
                print 'Invalid command\n'
            else:
                if resNum <= num_results_rarbg :
                    mLink = results_rarbg[resNum-1]['magnet']
                elif resNum > num_results_rarbg and resNum <= num_results:
                    mLink = results[(resNum-1)-num_results_rarbg]['magnet']
                else:
                    mLink = results_sky[(resNum-1)-num_results]['magnet']
                print "\nMagnet Link : \n" + mLink
        except AttributeError:
            print 'Enter a valid torrent number as well!'
    elif 'd' in arg:
        try:
            resNum = int(re.search(r'\d+', arg).group())
            if resNum <= 0 or resNum > num_results_sky:
                print 'Invalid command!\n'
            else:
                if resNum <= num_results_rarbg :
                    mLink = results_rarbg[resNum-1]['magnet']
                elif resNum > num_results_rarbg and resNum <= num_results:
                    mLink = results[(resNum-1)-num_results_rarbg]['magnet']
                else:
                    mLink = results_sky[(resNum-1)-num_results]['magnet']
                webbrowser.open(mLink, new=2)
                print 'Magnet link sent to default torrent client!'
        except AttributeError:
            print 'Enter a valid torrent number as well!'
    elif 'o' in arg:
        try:
            resNum = int(re.search(r'\d+', arg).group())
            print("resNum : %d" % resNum)
            if resNum <= 0 or resNum > num_results_sky:
                print 'Invalid command!\n'
            else:
                if resNum <= num_results_rarbg :
                    tLink = results_rarbg[resNum-1]['link']
                    #print("resNum(%d) <= num_results_rarbg(%d)" % (resNum, results_rarbg))
                elif resNum > num_results_rarbg and resNum <= num_results:
                    tLink = "https://" + tpb_working_domain + results[(resNum-1)-num_results_rarbg]['link']
                    #print("resNum(%d) > num_results_rarbg(%d) and resNum(%d) <= (num_results_rarbg(%d)+num_results(%d))" % (resNum, num_results_rarbg, resNum, num_results_rarbg, num_results))
                else:
                    tLink = results_sky[(resNum-1)-num_results]['link']
                    #print("Reached SkyTorrents. Link : %s" % tLink)
                #webbrowser.get('chrome').open(tLink, new=2)
                webbrowser.open(tLink, new=2)
                print 'Torrent page opened in default browser!'
        except AttributeError:
            print 'Enter a valid torrent number as well!'
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
                print "Not a valid option!"
        except AttributeError:
            if arg == 'p':
                printTopResults(print_version)
            else:
                print "Not a valid command!"
    elif arg == 's':
        query = raw_input("Enter query : ")
        if query == '':
            query = defaultQuery
        searchAllSites(query)
        printTopResults(print_version)
    elif arg == 'r':
        searchAllSites(query)
        printTopResults(print_version)
    else:
        print 'Invalid command!\n'

def print_menu(arg=0):
    if arg == 0:
        print '''
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
        ------------------------'''
    elif arg == 1:
        print '''
        Enter 'q' to exit and 'h' to see all available commands.
        '''

def searchAllSites(query=defaultQuery):
    global results, results_rarbg, results_sky
    results_rarbg = searchRarbg(query)
    results = searchPirateBay(query, domain='pirateproxy.cam')
    results_sky = searchSkyTorrents(query)

def printCombinedTopResults():
    global num_results, num_results_rarbg
    num_results_rarbg = print_top_results_rarbg(10)
    num_results = print_top_results(10)

def prettyPrintCombinedTopResults():
    global num_results, num_results_rarbg, num_results_sky
    num_results_rarbg = pretty_print_top_results_rarbg(10)
    num_results = pretty_print_top_results_piratebay(10)
    num_results_sky = pretty_print_top_results_skytorrents(10)

def printTopResults(version=1):
    if version == 0:
        printCombinedTopResults()
    elif version == 1:
        prettyPrintCombinedTopResults()

if __name__ == '__main__':
    if len(sys.argv) == 1:
        query = getQuery()
        if query == '':
            query = defaultQuery
    else:
        query = ''
        for i in range(1,len(sys.argv)):
            query = query + " " + sys.argv[i]
        if query == '':
            query = defaultQuery

    print_version = 1
    searchAllSites(query)
    printTopResults(print_version)

    exit = False
    while(exit != True):
        print_menu(1)
        choice = raw_input("Enter command : ")
        switch(choice)
