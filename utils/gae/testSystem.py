#coding=utf-8
# system test code. To run:
# PYTHONPATH=$(PATH_TO_GAE):$(PATH_TO_GAE)/lib/django/ python testSystem.py
import unittest
import os

from webtest import TestApp
from google.appengine.api import apiproxy_stub_map
from google.appengine.api import user_service_stub
from google.appengine.api import datastore_file_stub
from google.appengine.api import mail_stub
from google.appengine.api.xmpp import xmpp_service_stub

from debianmeeting import application

APP_ID = u'debianmeeting'
AUTH_DOMAIN = 'gmail.com'
LOGGED_IN_ADMIN = 'test2@example.com'
LOGGED_IN_USER = 'test3@example.com'
TITLE = 'test1'
PREWORK = 'test4'

class SystemTest(unittest.TestCase):
    def setUp(self):
        """set up stub
        """
        # API proxy
        apiproxy_stub_map.apiproxy = apiproxy_stub_map.APIProxyStubMap()

        # have a dummy datastore
        stub = datastore_file_stub.DatastoreFileStub(APP_ID,
                                                     '/dev/null',
                                                     '/dev/null')
        apiproxy_stub_map.apiproxy.RegisterStub('datastore_v3', stub)
        os.environ['APPLICATION_ID'] = APP_ID

        # user authentication
        apiproxy_stub_map.apiproxy.RegisterStub(
            'user', user_service_stub.UserServiceStub())

        os.environ['AUTH_DOMAIN'] = AUTH_DOMAIN
        os.environ['USER_EMAIL'] = LOGGED_IN_ADMIN

        # mail
        apiproxy_stub_map.apiproxy.RegisterStub(
            'mail', mail_stub.MailServiceStub())
        
        # xmpp
        apiproxy_stub_map.apiproxy.RegisterStub(
            'xmpp', xmpp_service_stub.XmppServiceStub())


    def login(self, username):
        """change login account"""
        os.environ['USER_EMAIL'] = username

    def testTopPage(self):
        """test displaying of the top page."""
        app = TestApp(application)
        response = app.get('/')
        self.assertEqual('200 OK', response.status)
        self.assertTrue(u'Debian勉強会予約管理システム' in response)

    def testCreatePage(self):
        app = TestApp(application)
        response = app.get('/newevent')
        self.assertEqual('200 OK', response.status)
        self.assertTrue('幹事用イベント管理ページ' in response)

    def createPageCommitHelper(self, app):
        response = app.post('/eventadmin/register', 
                            {
                'eventid': 'na',
                'title': TITLE,
                })
        self.assertEqual('302 Moved Temporarily', response.status)
        self.assertTrue('/thanks?eventid=' in response.location)
        eventid = response.location.split('=')[1]
        return eventid

    def testCreatePageCommit(self):
        app = TestApp(application)
        self.createPageCommitHelper(app)

    def testListKnownAdminEvents(self):
        """Check admin dashboard if the newly created event can be seen.
        """
        app = TestApp(application)
        response = app.get('/')
        self.assertEqual('200 OK', response.status)
        self.assertFalse(TITLE in response)

        # generate event data
        self.createPageCommitHelper(app)

        # check the event is viewable.
        response = app.get('/')
        self.assertEqual('200 OK', response.status)
        self.assertTrue(TITLE in response)

    def userEventEntry(self, app, eventid):
        """Register to event."""
        response = app.post('/eventregister', 
                            {
                'eventid': eventid,
                'user_prework': PREWORK,
                'user_attend': 'attend',
                })
        self.assertEqual('302 Moved Temporarily', response.status)
        self.assertTrue('/thanks?eventid=%s' % eventid
                        in response.location)

    def testUserRegisterEvent(self):
        """Test user registration workflow.
        """
        # generate event data first
        app = TestApp(application)

        eventid = self.createPageCommitHelper(app)

        # check user does not see the event yet
        self.login(LOGGED_IN_USER)
        response = app.get('/')
        self.assertEqual('200 OK', response.status)
        self.assertFalse(TITLE in response)

        # check user sees the event after registering
        self.userEventEntry(app, eventid)
        response = app.post('/')
        self.assertEqual('200 OK', response.status)
        self.assertTrue(TITLE in response)

    def testAdminReviewEvent(self):
        app = TestApp(application)
        # register the event
        eventid = self.createPageCommitHelper(app)
        # user joins the event
        self.login(LOGGED_IN_USER)
        self.userEventEntry(app, eventid)

        self.login(LOGGED_IN_ADMIN)
        response = app.post('/eventadmin/summary', 
                            {
                'eventid': eventid,
                })

        print response
        self.assertEqual('200 OK', response.status)
        self.assertTrue(LOGGED_IN_USER in response)
        self.assertTrue(PREWORK in response)


if __name__ == '__main__':
    unittest.main()
    
