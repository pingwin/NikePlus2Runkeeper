#!/usr/bin/env python
"""
This script is intended to directly upload exported Runtastic TCX tracks up to
Runkeeper. Use the below script found at the below URL to export the tracks
from Runtastic you want.

http://blog.favo.org/post/56040226362/export-all-activities-from-runtastic-as-tcx

var links = []; $('.type > a').each ( function () {
  links.push($(this).attr('href'))
} )
setInterval(function () {
    if ( !links.length) { return; }
    var link = links.shift();
    link += '.tcx';
    var newFrame = document.createElement('iframe');
    document.body.appendChild(newFrame);
    newFrame.style = 'width: 1px; height: 1px;';
    newFrame.src = link;
}, 500);
"""

import sys
import logging
import lxml.html
import requests
import json
import datetime
from math import floor

class RunkeeperUploader(object):
    _s      = None
    _email  = None
    _passwd = None
    _am_in  = False

    def __init__(self, email, passwd):
        self._s = requests.session()
        self._email  = email
        self._passwd = passwd

    def grab_bits_from_url(self, url, formname):
        ret = self._s.get(url).text

        values = {}
        form = None

        for elm in lxml.html.fromstring(ret).findall('.//form'):
            if elm.values()[2].lower().find(formname) != -1:
                form = elm
                break

        #import pdb; pdb.set_trace()
        assert form is not None
        
        return dict(zip(form.inputs.keys(),
                   map(lambda x: form.inputs[x].value,
                       form.inputs.keys()
                       )
                   ))

    
    def _with_authentication(fun):
        # aren't decorators neat?
        def login(self, *args, **kwargs):
            if not self._am_in:
                url = 'https://runkeeper.com/login'
                formbits = self.grab_bits_from_url(url, 'login')
                
                formbits['email']    = self._email
                formbits['password'] = self._passwd

                ret = self._s.post(url, formbits, allow_redirects=False)
                #import pdb; pdb.set_trace()

                assert ret.status_code == 302

                self._am_in = True
            return fun(self, *args, **kwargs)
        return login
    
    @_with_authentication
    def upload_tcx(self, fn):
        fd = open(fn, 'rb')
        tree = lxml.html.parse(fd)
        
        url = "http://runkeeper.com/new/activity"
        formbits = self.grab_bits_from_url(url, 'new/activity')
        
        if len(tree.findall('.//trackpoint')):
            # {{{ trackpoint encoding
            fd.seek(0)
            res = self._s.post('http://runkeeper.com/trackFileUpload',
                               {'uploadType' : '.tcx'},
                               files = {'trackFile'  : fd}
                               )
            assert res.status_code == 200

            data = json.loads(res.text)
            if len(data['error']):
                logging.error("%s %s" % (fn, data['error']))
                return

            formbits['importFormat'] = 'tcx'
            formbits['hasMap'] = 'true'
            formbits['mapEdited'] = 'true'

            # transcoding the points from the server into csv for runkeeper
            formbits['points'] = ';'.join(
                map(lambda x:
                    "%(type)s,%(latitude)s,%(longitude)s,%(deltaTime)s,0,0,%(timestamp)s" % x,
                    data['trackImportData']['trackPoints']
                    )
                ) + ';'
            
            duration_sec = data['trackImportData']['duration']/1000.0
            stime = datetime.datetime.fromtimestamp(data['trackImportData']['startTime']/1000)
            # }}} trackpoint encoding
        else:
            # {{{ manual data entry
            formbits['hasMap'] = 'false'
            formbits['mapEdited'] = 'false'
            formbits['distance'] = int(tree.find('.//distancemeters').text) * 0.00062137

            formbits['caloriesEdited'] = 'true'
            formbits['calories'] = int(tree.find('.//calories').text)

            if tree.find('.//notes') is not None:
                formbits['notes'] = tree.find('.//notes').text
                

            duration_sec = int(tree.find('.//totaltimeseconds').text)
            stime = datetime.datetime.strptime(tree.find('.//id').text[:-5], '%Y-%m-%dT%H:%M:%S')
            # }}} manual data entry


        if stime.hour > 12:
            formbits['startHour'] = stime.hour - 12
        else:
            formbits['startHour'] = stime.hour
            formbits['am'] = 'true'
        formbits['startMinute'] = stime.minute
        
        
        formbits['durationHours']   = int( duration_sec / 3600 )
        formbits['durationMinutes'] = int( (duration_sec - (formbits['durationHours']*3600)) / 60 )
        formbits['durationSeconds'] = int( duration_sec - ((formbits['durationHours']*3600)+(formbits['durationMinutes']*60)) )
        
        
        formbits['startTimeString'] = stime.strftime("%Y/%m/%d %H:%M:%S")+'.000'
            
        del formbits['trackFile']
        del formbits['hrmFile']

        ret = self._s.post(
            'https://runkeeper.com/new/activity',
            formbits, # data
            files={'trackFile':('',''), 'hrmFile':('','')},
            allow_redirects=False
            )

        open('/tmp/n.html', 'wb').write(ret.text)

        del tree
        fd.close()

        assert ret.status_code == 302

    @_with_authentication
    def upload_nikeplus(self, activity, stime, points):
        url = "http://runkeeper.com/new/activity"
        formbits = self.grab_bits_from_url(url, 'new/activity')
        
        if len(points):
            formbits['importFormat'] = 'tcx'
            formbits['hasMap'] = 'true'
            formbits['mapEdited'] = 'true'

            # transcoding the points from the server into csv for runkeeper
            formbits['points'] = points
        else:
            # Nike records distance in KM, RK in miles.
            formbits['distance'] = activity['activity']['distance'] * 0.621371
            formbits['gymEquipment'] = 'TREADMILL'

        formbits['startTimeString'] = (activity['activity']['startTimeUtc'][:-6]+'.000').replace('-','/').replace('T', ' ')
        if stime.hour > 12:
            formbits['startHour'] = stime.hour - 12
        else:
            formbits['startHour'] = stime.hour
            formbits['am'] = 'true'
        formbits['startMinute'] = stime.minute
        
        duration_sec = activity['activity']['duration']/1000.0
        formbits['durationHours']   = int( duration_sec / 3600 )
        formbits['durationMinutes'] = int( (duration_sec - (formbits['durationHours']*3600)) / 60 )
        formbits['durationSeconds'] = int( duration_sec - ((formbits['durationHours']*3600)+(formbits['durationMinutes']*60)) )


        del formbits['trackFile']
        del formbits['hrmFile']

        ret = self._s.post(
            'https://runkeeper.com/new/activity',
            formbits, # data
            files={'trackFile':('',''), 'hrmFile':('','')},
            allow_redirects=False
            )

        assert ret.status_code == 302

        
        
if __name__ == '__main__':
    import optparse
    import getpass
    import os.path
    import os
    
    option_list = (
        optparse.make_option('-v', dest='log_level', help='Verbose Logging', action='count', default=0),
        )

    parser = optparse.OptionParser(option_list=option_list, description='A simple script for migrating data into Runkeeper')

    opts,args=parser.parse_args()
    # for convenience
    opts = opts.__dict__

    if len(args) is not 2:
        print("[-v[vvv]] <email> <file | directory>")
        sys.exit(-1)

    logging.basicConfig(level=(40-(opts['log_level']*10)))

    (email, source) = args
    
    if not ( os.path.isfile(source) or os.path.isdir(source) ):
        print("last arg must be a valid file or directory")
        sys.exit(-1)


    passwd = getpass.getpass("Password:")

    if not len(passwd):
        sys.exit(-1)
    
    obj = RunkeeperUploader(email, passwd)


    if os.path.isfile(source):
        obj.upload_tcx(source)
    elif os.path.isdir(source):
        (dir,ign, files) = os.walk(source).next()

        for i in filter(lambda x: x[-4:] == '.tcx', files):
            if i.find('Running') != -1:
                obj.upload_tcx(dir+i)
