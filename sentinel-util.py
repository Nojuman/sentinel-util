import os
import sys
import zipfile

import gippy
import homura
import requests
from osgeo import gdal

from gippy import algorithms

MIDNIGHT = 'T00:00:00.000Z'
ABS_START = '2014-01-01T00:00:00.000Z'
INGESTION_KEYWORD = 'ingestiondate'
FOOTPRINT_KEYWORD = 'footprint:"intersects('
POLYGON_KEYWORD = 'POLYGON(('
CODE_2_MEANING = 'Code 2: invalid arguements'
POINT_DELIM = ', '
URL_START = 'https://scihub.copernicus.eu/dhus/search?q='
QUERY_DELIM = ' AND '
session = requests.Session()
files = []
PRODUCT_KEYWORD = 'producttype:'

#TODO: create more catches for invalid agruments
def main(args=None):
    print('started')
    if args is None:
        args = sys.argv
    if isinstance(args, str):
        args = args.split(' ')
    maxRows = '100'
    outDir = args[1] #where to put the mosaic
    zipDir = outDir + '/zip/' #where to put downloads
    unzipDir = outDir + '/unzip/' #where to put working files

    #create directory to store downloads, output, and working files
    if not os.path.isdir(outDir):
        os.mkdir(outDir)
    if not os.path.isdir(zipDir):
        os.mkdir(zipDir)
    if not os.path.isdir(unzipDir):
        os.mkdir(unzipDir)
    bbox = args[2] #corners of the bounding box
    username = args[3]
    password = args[4]
    product = 'GRD'
    mission = "1" #min sense time
    end = "NOW" #max sense time
    beginning = ABS_START

    i = 5 #argument index
    while i<len(args):
        arg = args[i]
        if arg == '-m':
            i += 1
            mission = args[i]
        elif arg == '-e':
            i += 1
            end = args[i] + MIDNIGHT
        elif arg == '-b':
            i += 1
            beginning = args[i] + MIDNIGHT
        elif arg == '-p':
            i += 1
            maxRows = args[i]
        elif arg == '-t':
            i += 1
            type = args[i].upper()
        else:
            print('Unrecognized flag ' + arg)
            print(CODE_2_MEANING)
            sys.exit(2)
        i += 1
    #create strings that will be used as options for querying scihub
    ingestOption = INGESTION_KEYWORD + ':[' + beginning + ' TO ' + end + ']'
    p = parse_bbox(bbox)
    #Point 0 appears twice because the polygon must be a closed loop
    geographicType = POLYGON_KEYWORD + p[0] + POINT_DELIM + p[1] + POINT_DELIM\
                      + p[2] + POINT_DELIM + p[3] + POINT_DELIM + p[0] + '))'
    footprintOption = FOOTPRINT_KEYWORD + geographicType + ')"'
    platformOption = 'platformname:Sentinel-' + mission
    if mission == '1':
        productOption = PRODUCT_KEYWORD + product + QUERY_DELIM
    else:
        productOption = ''
    #there's no QUERY_DELIM between product option and platform option because product option is sometime blank
    queryURL = URL_START + ingestOption + QUERY_DELIM + footprintOption + QUERY_DELIM + productOption\
               + platformOption + '&rows=' + maxRows + '&start=0&format=json'
    queryURL = queryURL.replace(' ', '%20')
    session.auth = (username, password)
    print queryURL
    response = session.post(queryURL, auth=session.auth)
    try:
        json_feed = response.json()['feed']
        total_results = int(json_feed['opensearch:totalResults'])
    except (ValueError, KeyError):
        print(response)
        print 'API response not valid. JSON decoding failed. Exiting with code 3.'
        exit(3)

    entries = json_feed.get('entry', [])
    download_all(entries, zipDir, unzipDir)
    #add the images to the list
    for dir in os.listdir(unzipDir):
        if dir[len(dir)-5:] == '.SAFE':
            dir = dir + '/measurement/'
            dir = unzipDir + dir
            for file in os.listdir(dir):
                if file.endswith('tiff'):
                    warp(file, dir)
                    thisFile = dir + file
                    files.append(thisFile)
    geoimgs = []
    for file in files:
        img = gippy.GeoImage(file)
        img.set_nodata(0)
        geoimgs.append(img)
    print files
    algorithms.cookie_cutter(geoimgs, outDir + '/mosaic', xres=10.0, yres=10.0, proj='EPSG:3857')



def download_all(entries, zipDir, unzipDir):
    for i in range(0, len(entries)):
        entry = entries[i]
        url = entry['link'][0]['href']
        print 'downloading product ' + str(i)
        filepath = zipDir + str(i) + '.zip'
        homura.download(url=url, auth=session.auth, path=filepath)
        zip_ref = zipfile.ZipFile(filepath, 'r')
        zip_ref.extractall(unzipDir)
        zip_ref.close()
    print 'finished downloads'


def parse_bbox(string):
    nums = string.split(',')
    if len(nums) != 4:
        print("Bbox must contain exactly 4 comma seperated decimal degrees, recieved " + len(nums))
        print(CODE_2_MEANING)
        sys.exit(2)
    lat1 = nums[0]
    lon1 = nums[1]
    lat2 = nums[2]
    lon2 = nums[3]
    if not float(lat1) > float(lat2):
        print("Latitude1 was less than Latitude2")
        print(CODE_2_MEANING)
        sys.exit(2)
    elif not float(lon2) > float(lon1):
        print("Longitude2 was less than Longitude1")
        print(CODE_2_MEANING)
        sys.exit(2)
    elif abs(float(lat1)-float(lat2)) > 10:
        print("The bbox was taller than 10 degrees")
        print(CODE_2_MEANING)
        sys.exit(2)
    elif abs(float(lon1)-float(lon2)) > 10:
        print("The bbox was wider than 10 degrees")
        print(CODE_2_MEANING)
        sys.exit(2)
    cords = []
    cords.append(lat1 + " " + lon1) #top left
    cords.append(lat1 + " " + lon2) #top right
    cords.append(lat2 + " " + lon2) #bottom right
    cords.append(lat2 + " " + lon1) #bottom left
    return cords


#change from 16bit to 8bit using gdalTranslate, project to EPSG:3857
def warp(filename, dirname):
    tempfile = dirname + 'temp_' + filename
    filename = dirname + filename
    file = gdal.Open(filename)
    gdal.Warp(tempfile, file, dstSRS='EPSG:3857')
    file = gdal.Open(tempfile)
    gdal.Translate(filename, file, outputType=gdal.GDT_Byte)
    os.remove(tempfile)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt):
        exit('Received Ctrl + C... Exiting', 1)

