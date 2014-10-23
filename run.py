#!/usr/bin/env python
"""

"""
import datetime
import requests
import logging
import lxml.html
import json


"""
Upon Login We Get
{'entity': {'access': 4,
            'email': 'pingwin@gmail.com',
            'externalUserId': 'F6B3607E19798E6CE040070A0B1C1DEE',
            'id': '10963115387',
            'nikePlusId': 'b555052a-40f6-4370-b51f-3ffa1fe2c87b',
            'notComplex': False,
            'passwordSettings': None,
            'screenName': 'da_pingwin',
            'type': 'nike'},
 'links': [{'mediaType': 'application/json',
            'method': 'GET',
            'name': 'getUser',
            'uri': '/profile/services/users/10963115387'}],
 'statusOverview': {'durationInMS': None,
                    'messages': [],
                    'statusIndicator': None}}

An Activity from the index /lifetime
{'activity': {'activeTime': 0,
               'activityId': '6140000000020665821130032697466960014119',
               'activityType': 'RUN',
               'deviceType': 'SPORTWATCH',
               'dstOffset': '00:00',
               'gps': True,
               'heartrate': False,
               'latitude': 37.77576,
               'longitude': -83.67821,
               'metrics': {'averageHeartRate': 0.0,
                           'calories': 460,
                           'distance': 4.799900054931641,
                           'duration': 8390000,
                           'fuel': 1131,
                           'maximumHeartRate': 0.0,
                           'minimumHeartRate': 0.0,
                           'steps': 0},
               'name': 'RUN ON: 04/12/14 11:47 AM',
               'startTimeUtc': '2014-04-12T11:47:00-05:00',
               'status': 'complete',
               'tags': {},
               'timeZone': '-05:00',
               'timeZoneId': 'GMT-05:00'}},

"""


class NikePlus(object):
    _am_in = False

    def __init__(self, email, passwd):
        self._email = email
        self._passwd = passwd
        self._s = requests.session()
    
    def _with_auth(fun):
        def login(self, *args, **kwargs):
            if not self._am_in:
                # need cookies
                self._s.get('https://secure-nikeplus.nike.com/plus/')
                
                ret = self._s.post(
                    'https://www.nike.com/profile/login',
                    {
                        'login' : self._email,
                        'password' : self._passwd,
                    })

                assert ret.status_code == 200

                self._profile = ret.json()

                self._am_in = True
            return fun(self, *args, **kwargs)
        return login

    @_with_auth
    def index_activities(self):
        ret = self._s.get("https://secure-nikeplus.nike.com/plus/activity/running/%(screenName)s/lifetime" % self._profile['entity'])
        try:
            js = list(filter(lambda x: x.text.find('window.np.activity') != -1,
                             filter(lambda x: x.text is not None,
                                    lxml.html.fromstring(ret.text).findall('.//script')
                                    )
                             ))[0].text
            js = json.loads( js[ js.find('{') : ].strip()[:-1] )
        
            return js['activities']
        except IndexError:
            logging.warn("no activities found")
            return []

    @_with_auth
    def download_all(self):
        for a in self.index_activities():
            ret = self._s.get("https://secure-nikeplus.nike.com/plus/activity/running/%s/detail/%s" % (
                self._profile['entity']['screenName'],
                a['activity']['activityId']
                ))
            js = list(filter(lambda x: x.text.find('window.np.baked_data') != -1,
                        filter(lambda x: x.text is not None,
                               lxml.html.fromstring(ret.text).findall('.//script')
                               )
                        ))[0].text
            js = json.loads( js[ js.find('{') : ].strip()[:-1] )
            try:
                timedelta = js['activity']['history'][0]['intervalMetric']
            except KeyError:
                timedelta = 10

            num_waypoints = len(js['activity']['geo']['waypoints'])
            ts = 0
            with open('%s.csv' % js['activity']['activityId'], 'wb') as out:
                for p in js['activity']['geo']['waypoints']:
                    ptype = 'ManualPoint'
                    if p == js['activity']['geo']['waypoints'][0]:
                        ptype = 'StartPoint'
                    elif p == js['activity']['geo']['waypoints'][num_waypoints-1]:
                        ptype = 'EndPoint'
                        
                    out.write(bytes("%s,%s,%s,%s,0,0,%s;" % (
                        ptype,
                        p['lat'],
                        p['lon'],
                        timedelta,
                        ts), 'UTF-8'))
                    ts += timedelta

    @_with_auth
    def sync_runkeeper(self, rk, after):
        LAST_IMPORT = after
        for a in self.index_activities():
            if not a['activity']['metrics']['duration']:
                logging.info("Bailing on activity because zero activeTime %s" % a['activity']['activityId'])
                continue

            atime = datetime.datetime.strptime(a['activity']['startTimeUtc'][:-6], "%Y-%m-%dT%H:%M:%S")
            if atime <= after:
                continue
            LAST_IMPORT = atime

            logging.error("New Run Being Imported")
            ret = self._s.get("https://secure-nikeplus.nike.com/plus/activity/running/%s/detail/%s" % (
                self._profile['entity']['screenName'],
                a['activity']['activityId']
                ))

            js = list(filter(lambda x: x.text.find('window.np.baked_data') != -1,
                        filter(lambda x: x.text is not None,
                               lxml.html.fromstring(ret.text).findall('.//script')
                               )
                        ))[0].text

            js = json.loads( js[ js.find('{') : ].strip()[:-1] )

            try:
                timedelta = js['activity']['history'][0]['intervalMetric']
            except KeyError:
                timedelta = 10

            num_waypoints = len(js['activity']['geo']['waypoints'])
            ts = 0
            points = ''
            for p in js['activity']['geo']['waypoints']:
                ptype = 'ManualPoint'
                if p == js['activity']['geo']['waypoints'][0]:
                    ptype = 'StartPoint'
                elif p == js['activity']['geo']['waypoints'][num_waypoints-1]:
                    ptype = 'EndPoint'
                    
                points += "%s,%s,%s,%s,0,0,%s;" % (
                        ptype,
                        p['lat'],
                        p['lon'],
                        timedelta,
                        ts)
                ts += timedelta
            rk.upload_nikeplus(js, atime, points)
            del points
        return LAST_IMPORT
            
            
            
            

if __name__ == '__main__':
    import optparse
    import configparser
    import runkeeper

    option_list = (
        optparse.make_option('-v', dest='log_level', help='Verbose Logging', action='count', default=0),
        optparse.make_option('-c', dest='config_file', help='Config File', default='config.ini'),
        optparse.make_option('-l', dest='last_import_tracker', help='File to store the last track date', default='LAST_IMPORT'),
    )
    
    parser = optparse.OptionParser(option_list=option_list, description='A simple script to synchronize Nike+ logs with Runkeeper')
    opts,args=parser.parse_args()
    # for convenience
    opts = opts.__dict__

    config = configparser.ConfigParser()
    config.read(opts['config_file'])

    logging.basicConfig(level=(40-(opts['log_level']*10)))

    try:
        LAST_DATE = datetime.datetime.strptime(open(opts['last_import_tracker'],'r').read().strip(), "%Y-%m-%dT%H:%M:%S")
    except IOError:
        LAST_DATE = datetime.datetime(1970, 1, 1)
    
    nike = NikePlus(
        config['nikeplus']['email'],
        config['nikeplus']['password']
    )

    rk = runkeeper.RunkeeperUploader(
        config['runkeeper']['email'],
        config['runkeeper']['password']
    )
    try:
        last_import = nike.sync_runkeeper(rk, LAST_DATE)

        open(opts['last_import_tracker'],'wb').write(bytes(last_import.isoformat(), 'UTF-8'))
    except AssertionError as inst:
        # these are mostly harmless for this scripts purpose.
        logging.info("Assertion Error: %s" % inst)
